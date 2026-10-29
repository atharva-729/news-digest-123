"""Phase 4: turn the day's picks, threads and connections into the web edition (docs/DATE.html).

Three writer calls: story cards for tech, story cards for everything else (both read the article text from
the read phase), then the top of the page and the quiz. "Remember?" questions are built in code from the
threads' teaching cards, on a spaced schedule. Code checks every id; the templates insert the real headlines
and links, so the model never produces a link. The day's prediction goes to data/calls.json.
"""
import json
import logging
import random
import shutil
from collections import Counter
from datetime import date as Date, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from digest import articles, llm
from digest.common import DATA, ROOT, load_prompt, read_json, write_json

log = logging.getLogger(__name__)

SITE = ROOT / "docs"  # GitHub Pages serves this folder from the main branch
STATIC = ROOT / "templates" / "static"
SECTIONS = {
    "tech": ("Tech", "⚡"), "politics_india": ("India", "🇮🇳"), "politics_world": ("World", "🌍"),
    "markets": ("Markets", "📈"), "sports": ("Sports", "🏆"), "fun": ("Fun", "🎈"),
}
FORCE_ICONS = {"technology": "⚙️", "capital": "💰", "geopolitics": "🌐", "regulation": "⚖️", "demographics": "👥"}
FORCE_LABELS = {"technology": "Technology", "capital": "Money", "geopolitics": "Geopolitics",
                "regulation": "Rules", "demographics": "People"}
KIND_LABELS = {"sequel": "Sequel", "reversal": "Plot twist", "cause": "Cause → effect", "same_pattern": "Same pattern"}
REVIEW_DAYS = [1, 3, 7, 14, 30]  # spaced "Remember?" questions: a pattern comes back after these gaps

hl_text = {"type": "object", "properties": {"text": {"type": "string"}, "highlight": {"type": "string"}}}
CARDS_SCHEMA = {"type": "object", "properties": {"cards": {"type": "array", "items": {"type": "object", "properties": {
    "item_id": {"type": "string"}, "emoji": {"type": "string"}, "headline": {"type": "string"},
    "explain": {"type": "string"}, "why": {"type": "string"}, "highlight": {"type": "string"}}}}}}
SCHEMA = {
    "type": "object",
    "properties": {
        "tldr": {"type": "array", "items": hl_text},
        "hero": hl_text,
        "scoreboard": {"type": "array", "items": {"type": "object", "properties": {
            "thread_id": {"type": "string"}, "line": {"type": "string"}}}},
        "forces": {"type": "array", "items": {"type": "object", "properties": {
            "force": {"type": "string"}, "line": {"type": "string"}}}},
        "pulse_india": {"type": "string"},
        "pulse_world": {"type": "string"},
        "dots": {"type": "string"},
        "call": {"type": "object", "properties": {
            "thread_id": {"type": "string"}, "prediction": {"type": "string"}, "check_in_days": {"type": "integer"}}},
        "quiz": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
            "answer_index": {"type": "integer"}, "why": {"type": "string"}}}},
    },
}


def highlight(text, phrase):
    """Escape `text` and wrap the first exact occurrence of `phrase` in <mark>. The model picks the phrase."""
    text, phrase = str(text or ""), str(phrase or "").strip()
    if not phrase or phrase not in text:
        return escape(text)
    a, b = text.split(phrase, 1)
    return Markup(f"{escape(a)}<mark>{escape(phrase)}</mark>{escape(b)}")


def short_date(iso):
    return Date.fromisoformat(iso).strftime("%d %b").lstrip("0")


def env():
    e = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "j2"]))
    e.filters["hl"] = lambda obj: highlight(obj.get("text"), obj.get("highlight")) if obj else ""
    e.filters["short_date"] = short_date
    e.globals.update(SECTIONS=SECTIONS, FORCE_ICONS=FORCE_ICONS, FORCE_LABELS=FORCE_LABELS, KIND_LABELS=KIND_LABELS)
    return e


def copy_static():
    shutil.copytree(STATIC, SITE / "assets", dirs_exist_ok=True)
    (SITE / ".nojekyll").touch()


def render(template, path, **ctx):
    SITE.mkdir(exist_ok=True)
    copy_static()
    path.write_text(env().get_template(template).render(**ctx), encoding="utf-8")


def load_day(date):
    sel = read_json(DATA / "selected" / f"{date}.json")
    day = read_json(DATA / "items" / f"{date}.json")
    snap = read_json(DATA / "threads" / f"{date}.json")
    if not (sel and day and snap):
        raise SystemExit(f"missing data for {date}; run ingest, select and threads first")
    conn = read_json(DATA / "connect" / f"{date}.json") or {"throwbacks": [], "backstory": []}
    return sel, {it["id"]: it for it in day["items"]}, snap, conn


def thread_moves(snap):
    """New, heating and cooling threads today, in that order."""
    today, threads = snap["today"], {t["id"]: t for t in snap["threads"]}
    attached = {a["thread_id"] for a in today["attached"]}
    new = today["new_threads"] + today["promoted"]
    moves = [(tid, "new") for tid in new]
    moves += [(tid, "heating") for tid, t in threads.items()
              if t["status"] == "heating" and tid not in new and tid in attached]
    moves += [(tid, "cooling") for tid, (_, now) in today["status_changes"].items() if now == "cooling"]
    return [(threads[tid], kind) for tid, kind in moves if tid in threads]


def name(t):
    return t.get("nickname") or t["title"]


def one_line(t):
    return (t.get("teach") or {}).get("one_line") or t.get("plain") or t["claim"]


def checked(obj):
    """A {text, highlight} pair, with the highlight dropped unless it really occurs in the text."""
    text, hl = obj["text"].strip(), obj["highlight"].strip()
    return {"text": text, "highlight": hl if hl and hl in text else ""}


# ---------------------------------------------------------------- story cards

def card_rows(sel, items, snap, conn, texts, meta):
    threads = {t["id"]: t for t in snap["threads"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    throw = {x["item_id"]: x for x in conn["throwbacks"]}
    rows = {}
    for s, picks in sel["sections"].items():
        for p in picks:
            it, m = items[p["id"]], meta.get(p["id"], {})
            t = threads.get(attached.get(p["id"]))
            rows[p["id"]] = {
                "id": p["id"], "section": SECTIONS[s][0], "source": it["source"], "original_title": it["title"],
                "article": texts.get(p["id"]) or it["summary"], "limited": m.get("limited", not it["summary"]),
                "pattern": t and {"name": name(t), "idea": one_line(t)},
                "last_week": throw[p["id"]]["line"] if p["id"] in throw else None,
                **({"funding": p["funding"]} if "funding" in p else {})}
    return rows


def write_cards(cfg, rows, tag):
    wcfg = cfg.get("writing", {})
    prompt = (load_prompt("cards").replace("{{style}}", load_prompt("style"))
              .replace("{{card_rules}}", load_prompt("card_rules"))
              .replace("{{input}}", json.dumps(list(rows.values()), ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, CARDS_SCHEMA, tag=tag, model=wcfg.get("model"), **wcfg.get("params", {}))
    cards = {}
    for c in out["cards"]:
        if c["item_id"] in rows and c["item_id"] not in cards and c["headline"].strip() and c["explain"].strip():
            cards[c["item_id"]] = {"emoji": c["emoji"].strip()[:4], "headline": c["headline"].strip(),
                                   "explain": c["explain"].strip(),
                                   "why": checked({"text": c["why"], "highlight": c["highlight"]})}
    return cards


def all_cards(cfg, rows, tech_ids):
    """Tech in one call, everything else in another (smaller answers skip fewer cards), then one retry."""
    groups = [{i: r for i, r in rows.items() if i in tech_ids}, {i: r for i, r in rows.items() if i not in tech_ids}]
    cards = {}
    for n, g in enumerate(groups):
        if g:
            cards.update(write_cards(cfg, g, f"write:cards{n + 1}"))
    missing = {i: r for i, r in rows.items() if i not in cards}
    if missing:
        log.warning("writer skipped %d cards; asking again for those", len(missing))
        cards.update(write_cards(cfg, missing, "write:retry"))
    still = [i for i in rows if i not in cards]
    if still:
        log.warning("no card for %d items; showing their original headlines", len(still))
    return cards


FACTCHECK_SCHEMA = {"type": "object", "properties": {"cards": {"type": "array", "items": {"type": "object", "properties": {
    "item_id": {"type": "string"}, "headline": {"type": "string"}, "explain": {"type": "string"},
    "why": {"type": "string"}, "highlight": {"type": "string"}, "changed": {"type": "boolean"},
    "note": {"type": "string"}}}}}}


def factcheck(cfg, cards, rows, ids):
    """Second pass for politics and world cards: drop anything the article doesn't say (motives, predictions,
    'what it signals'), and attribute claims. Prompt rules alone let interpretation slip through."""
    todo = [i for i in ids if i in cards]
    if not todo:
        return []
    payload = [{"item_id": i, "article": rows[i]["article"], "headline": cards[i]["headline"],
                "explain": cards[i]["explain"], "why": cards[i]["why"]["text"]} for i in todo]
    wcfg = cfg.get("writing", {})
    out = llm.generate_json(load_prompt("factcheck").replace("{{input}}", json.dumps(payload, ensure_ascii=False, indent=1)),
                            FACTCHECK_SCHEMA, tag="write:factcheck", model=wcfg.get("model"), **wcfg.get("params", {}))
    changes = []
    for c in out["cards"]:
        if c["item_id"] in todo and c["changed"] and c["headline"].strip() and c["explain"].strip() and c["why"].strip():
            cards[c["item_id"]].update(headline=c["headline"].strip(), explain=c["explain"].strip(),
                                       why=checked({"text": c["why"], "highlight": c["highlight"]}))
            changes.append({"item_id": c["item_id"], "note": c["note"].strip()})
    for ch in changes:
        log.info("fact-check changed %s: %s", ch["item_id"], ch["note"])
    return changes


# ---------------------------------------------------------------- remember (spaced retrieval)

def remember(date, threads):
    """Up to two "Remember?" questions about patterns seen on earlier days, spaced 1, 3, 7, 14, 30 days apart.

    Built in code from the threads' teaching cards: the right answer is the pattern's own card and the wrong
    ones are other patterns' cards, so nothing here can be made up. Reruns of a date reuse its picks.
    """
    taught = {t["id"]: t for t in threads if t.get("teach") and not t.get("merged_into")}
    mem = read_json(DATA / "memory.json", {"threads": {}, "days": {}})
    if date in mem["days"]:
        picks = [i for i in mem["days"][date] if i in taught]
    else:
        for tid, t in taught.items():
            first = (Date.fromisoformat(t["created"]) + timedelta(days=REVIEW_DAYS[0])).isoformat()
            mem["threads"].setdefault(tid, {"next": first, "step": 0})
        due = sorted((m["next"], tid) for tid, m in mem["threads"].items()
                     if tid in taught and m["next"] <= date and taught[tid]["created"] < date)
        picks = [tid for _, tid in due[:2]]
        for tid in picks:
            m = mem["threads"][tid]
            m["step"] += 1
            m["next"] = (Date.fromisoformat(date) + timedelta(days=REVIEW_DAYS[min(m["step"], len(REVIEW_DAYS) - 1)])).isoformat()
        mem["days"][date] = picks
        write_json(DATA / "memory.json", mem)

    rng, questions = random.Random(f"remember-{date}"), []
    for k, tid in enumerate(picks):
        others = [x for x in taught if x != tid]
        if len(others) < 2:
            break
        t, wrong = taught[tid], [taught[x] for x in rng.sample(others, 2)]
        if k % 2 == 0:
            q, right, opts = f"Which pattern is this? “{t['teach']['one_line']}”", name(t), [name(w) for w in wrong]
        else:
            q, right, opts = f"What does “{name(t)}” mean?", t["teach"]["one_line"], [w["teach"]["one_line"] for w in wrong]
        slot = rng.randrange(3)
        opts.insert(slot, right)
        questions.append({"question": q, "options": opts, "answer_index": slot,
                          "why": f"{name(t)}: {t['teach']['one_line']} Remember it as: {t['teach']['remember']}",
                          "since": short_date(t["created"])})
    return questions


# ---------------------------------------------------------------- page

def edition_input(date, sel, cards, rows, snap, conn, moves):
    threads = {t["id"]: t for t in snap["threads"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    forces_today = {}
    for tid in set(attached.values()):
        for f in threads[tid]["forces"]:
            forces_today.setdefault(f, []).append({"pattern": name(threads[tid]), "idea": one_line(threads[tid])})
    link = snap["today"]["cross_link"]
    return {
        "stories": [{"id": i, "section": r["section"], "headline": cards[i]["headline"] if i in cards else r["original_title"],
                     "why": cards[i]["why"]["text"] if i in cards else "", "pattern": r["pattern"] and r["pattern"]["name"]}
                    for i, r in rows.items()],
        "thread_moves": [{"id": t["id"], "move": kind, "name": name(t), "idea": one_line(t), "forces": t["forces"],
                          "stories_today": [cards[e["item_id"]]["headline"] if e["item_id"] in cards else e["title"]
                                            for e in t["evidence"] if e["date"] == date]} for t, kind in moves],
        "forces_today": forces_today,
        "open_threads": [{"id": t["id"], "name": name(t), "idea": one_line(t)}
                         for t in snap["threads"] if t["status"] != "dormant"],
        "cross_link": link and {"a": name(threads[link["thread_a"]]), "b": name(threads[link["thread_b"]]),
                                "force": link["force"], "sentence": link["sentence"]},
        "funding": [p["funding"] for p in sel["sections"].get("tech", []) if "funding" in p],
    }


def record_call(date, call, threads):
    """Append today's prediction to data/calls.json (replacing any earlier one from the same date)."""
    t = threads.get(call["thread_id"])
    if not t or not call["prediction"].strip():
        log.warning("no valid call today (thread %r)", call["thread_id"])
        return None
    days = min(max(call["check_in_days"], 30), 120)
    entry = {"made": date, "thread_id": t["id"], "thread_title": name(t), "prediction": call["prediction"].strip(),
             "review_by": (Date.fromisoformat(date) + timedelta(days=days)).isoformat(), "verdict": None, "verdict_note": ""}
    calls = [c for c in read_json(DATA / "calls.json", []) if c["made"] != date]
    write_json(DATA / "calls.json", calls + [entry])
    return entry


def timeline(t, date, days=14):
    counts = Counter(e["date"] for e in t["evidence"])
    end = Date.fromisoformat(date)
    return [{"date": d, "n": counts.get(d, 0)} for d in
            ((end - timedelta(days=k)).isoformat() for k in range(days - 1, -1, -1))]


def thread_view(t, date, kind=None, line="", cards=None):
    cards = cards or {}
    ev = sorted(t["evidence"], key=lambda e: e["date"], reverse=True)
    today = [{**e, "headline": cards[e["item_id"]]["headline"] if e["item_id"] in cards else e["title"]}
             for e in ev if e["date"] == date]
    return {
        "id": t["id"], "name": name(t), "title": t["title"], "claim": t["claim"], "teach": t.get("teach") or {},
        "one_line": one_line(t), "forces": t["forces"], "status": "new" if kind == "new" else t["status"], "line": line,
        "today": len(today), "total": len(t["evidence"]), "since": short_date(min(e["date"] for e in t["evidence"])),
        "timeline": timeline(t, date), "today_items": today,
        "earlier": [e for e in ev if e["date"] != date][:3],
    }


def read_minutes(ctx):
    """Minutes to read the Feed tab (the 3 lines, the big picture, every card)."""
    texts = [x["text"] for x in ctx["tldr"]] + [ctx["hero"]["text"]]
    texts += [f"{c['headline']} {c['explain']} {c['why']['text'] if c['why'] else ''}" for s in ctx["sections"] for c in s["items"]]
    return max(1, round(len(" ".join(texts).split()) / 220))


def shuffle_answers(quiz, seed):
    """The model tends to put the answer first. Spread answers over A/B/C, the same way on reruns."""
    rng = random.Random(seed)
    for q, slot in zip(quiz, rng.sample(range(3), 3)):
        right = q["options"][q["answer_index"]]
        wrong = [o for i, o in enumerate(q["options"]) if i != q["answer_index"]]
        rng.shuffle(wrong)
        q["options"], q["answer_index"] = wrong[:slot] + [right] + wrong[slot:], slot
    return quiz


def run(cfg, date):
    sel, items, snap, conn = load_day(date)
    texts, meta = articles.load(date)
    threads = {t["id"]: t for t in snap["threads"]}
    moves = thread_moves(snap)

    rows = card_rows(sel, items, snap, conn, texts, meta)
    cards = all_cards(cfg, rows, {p["id"] for p in sel["sections"].get("tech", [])})
    political = [p["id"] for s in ("politics_india", "politics_world") for p in sel["sections"].get(s, [])]
    checked_changes = factcheck(cfg, cards, rows, political)

    wcfg = cfg.get("writing", {})
    data = edition_input(date, sel, cards, rows, snap, conn, moves)
    prompt = (load_prompt("write").replace("{{style}}", load_prompt("style")).replace("{{date}}", date)
              .replace("{{input}}", json.dumps(data, ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, SCHEMA, tag="write:page", model=wcfg.get("model"), **wcfg.get("params", {}))

    move_kind = {t["id"]: kind for t, kind in moves}
    lines = {x["thread_id"]: x["line"].strip() for x in out["scoreboard"] if x["thread_id"] in move_kind}
    force_lines = {x["force"].strip().lower(): x["line"].strip() for x in out["forces"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    throw = {x["item_id"]: x for x in conn["throwbacks"]}
    call = record_call(date, out["call"], threads)
    quiz = shuffle_answers([q for q in out["quiz"] if len(q["options"]) == 3 and 0 <= q["answer_index"] <= 2][:3], date)

    def card(section, p):
        it, c, m = items[p["id"]], cards.get(p["id"]), meta.get(p["id"], {})
        t = threads.get(attached.get(p["id"]))
        return {**it, "section": section, "emoji": c["emoji"] if c else SECTIONS[section][1],
                "headline": c["headline"] if c else it["title"], "explain": c["explain"] if c else it["summary"],
                "why": c["why"] if c else None, "limited": rows[p["id"]]["limited"], "limited_reason": m.get("reason", ""),
                "funding": p.get("funding"), "throwback": throw.get(p["id"]),
                "thread": t and {"id": t["id"], "name": name(t), "one_line": one_line(t),
                                 "status": move_kind.get(t["id"], t["status"])}}

    sections = [{"key": s, "label": SECTIONS[s][0], "emoji": SECTIONS[s][1], "items": [card(s, p) for p in picks]}
                for s, picks in sel["sections"].items() if picks]
    shown = {c["id"]: c for s in sections for c in s["items"]}

    # "What it means": L1 (today's stories), L2 (patterns), L3 (forces), and the connections between them.
    active = [t for t in snap["threads"] if t["status"] != "dormant"]
    active.sort(key=lambda t: t["last_seen"], reverse=True)
    active.sort(key=lambda t: -sum(e["date"] == date for e in t["evidence"]))  # most evidence today first
    l2 = [thread_view(t, date, move_kind.get(t["id"]), lines.get(t["id"], ""), cards) for t in active]
    forces = []
    for f in cfg["threads"]["forces"]:
        ts = [t for t in l2 if f in t["forces"]]
        forces.append({"key": f, "label": FORCE_LABELS.get(f, f.title()), "icon": FORCE_ICONS.get(f, "•"),
                       "meaning": cfg.get("forces_explained", {}).get(f, ""), "line": force_lines.get(f, ""),
                       "threads": len(ts), "today": sum(t["today"] for t in ts)})
    l1_linked = [{"card": shown[i], "thread": threads[tid]} for i, tid in attached.items() if i in shown]
    l1_oneoffs = [c for c in shown.values() if c["id"] not in attached]
    map_threads = [t for t in l2 if t["today"]]
    link = snap["today"]["cross_link"]

    calls = sorted(read_json(DATA / "calls.json", []), key=lambda c: c["made"], reverse=True)
    ctx = {
        "date": date,
        "day": Date.fromisoformat(date).strftime("%A"),
        "pretty_date": Date.fromisoformat(date).strftime("%d %B %Y").lstrip("0"),
        "tldr": [checked(x) for x in out["tldr"][:3]],
        "hero": checked(out["hero"]),
        "moves": [{"thread": thread_view(t, date, kind, cards=cards), "kind": kind, "line": lines.get(t["id"], "")}
                  for t, kind in moves],
        "sections": sections,
        "pulse": {"india": out["pulse_india"].strip(), "world": out["pulse_world"].strip()},
        "l1_linked": l1_linked, "l1_oneoffs": l1_oneoffs, "l2": l2, "forces": forces,
        "map_items": [x for x in l1_linked if any(t["id"] == x["thread"]["id"] for t in map_threads)],
        "map_threads": map_threads,
        "dots": link and {"a": thread_view(threads[link["thread_a"]], date), "b": thread_view(threads[link["thread_b"]], date),
                          "force": link["force"], "text": out["dots"].strip() or link["sentence"]},
        "throwbacks": [{**x, "now": shown.get(x["item_id"])} for x in conn["throwbacks"] if x["item_id"] in shown],
        "remember": remember(date, snap["threads"]),
        "call": call, "past_calls": [c for c in calls if c["made"] != date][:6],
        "quiz": quiz,
        "credit": cfg["credit"],
        "sources": sorted({c["source"] for c in shown.values()}),
        "stats": {"stories": len(shown), "limited": sum(c["limited"] for c in shown.values()),
                  "today_threads": len(map_threads)},
    }
    ctx["minutes"] = read_minutes(ctx)
    path = SITE / f"{date}.html"
    render("daily.html.j2", path, **ctx)

    lead = ctx["tldr"][0]["text"] if ctx["tldr"] else (name(moves[0][0]) if moves else "today's news")
    subj = f"L1·L2·L3 {short_date(date)}: {lead}"
    write_json(DATA / "written" / f"{date}.json",
               {"date": date, "subject": subj, "lead": lead, "tldr": ctx["tldr"], "hero": ctx["hero"],
                "cards": cards, "factcheck": checked_changes, "page": out, "call": call})
    return {"path": path, "minutes": ctx["minutes"], "takes": len(cards), "items": len(rows), "moves": len(moves),
            "call": call, "subject": subj, "limited": ctx["stats"]["limited"], "remember": len(ctx["remember"]),
            "factchecked": len(political), "factcheck_changes": len(checked_changes)}
