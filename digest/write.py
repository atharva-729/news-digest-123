"""Phase 4: turn the day's picks, threads and connections into the web edition (docs/DATE.html).

Three writer calls: story cards for tech, story cards for everything else (both read the article text from
the read phase), then the top of the page and the quiz. "Remember?" questions are built in code from the
threads' teaching cards, on a spaced schedule. Code checks every id; the templates insert the real headlines
and links, so the model never produces a link. The day's prediction goes to data/calls.json.
"""
import json
import logging
import random
import re
import shutil
from collections import Counter
from datetime import date as Date, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from digest import articles, llm
from digest.common import DATA, ROOT, load_prompt, read_json, write_json
from digest.threads import SNAPSHOTS, event_of

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
            "thread_id": {"type": "string"}, "prediction": {"type": "string"}, "measure": {"type": "string"},
            "threshold": {"type": "string"}, "window_days": {"type": "integer"},
            "could_fail_because": {"type": "string"}, "confidence": {"type": "integer"}}},
        "quiz": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["evidence", "force", "weaken", "why"]},
            "thread_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}},
            "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
            "answer_index": {"type": "integer"}, "why": {"type": "string"}}}},
    },
}
CALL_SCHEMA = {"type": "object", "properties": {"call": SCHEMA["properties"]["call"]}}
NAMED_EVENT = re.compile(r"\d|(?<=\s)[A-Z][A-Za-z]+")  # a number, or a capitalised name after the first word
MEDIA_MEASURE = re.compile(r"\b(stor(y|ies)|coverage|articles?|headlines?|mentions?|reports? (naming|citing|about))\b", re.I)


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


def thread_moves(snap, limit=3):
    """The patterns that got the most direct evidence today (at most `limit`), with their real status."""
    threads = {t["id"]: t for t in snap["threads"]}
    counts = Counter(a["thread_id"] for a in snap["today"]["attached"] if a["thread_id"] in threads)
    return [(threads[tid], threads[tid]["status"]) for tid, _ in counts.most_common(limit)]


def developing(cfg, date, snap, items, cards):
    """Developing stories: one event with several articles (today and the last few days) that isn't evidence
    for any pattern. Shown as a group of updates, not as a pattern. Built in code from the event keys."""
    dcfg = cfg.get("developing", {})
    groups = {}
    for i, ev in snap["today"].get("events", {}).items():
        if i in items:
            groups.setdefault(ev, []).append({"date": date, "item_id": i, "today": True, "url": items[i]["url"],
                                              "title": cards[i]["headline"] if i in cards else items[i]["title"]})
    for n in range(1, dcfg.get("lookback_days", 7) + 1):
        d = (Date.fromisoformat(date) - timedelta(days=n)).isoformat()
        past, day = read_json(SNAPSHOTS / f"{d}.json"), read_json(DATA / "items" / f"{d}.json")
        if not past or not day:
            continue
        titles = {it["id"]: it for it in day["items"]}
        for i, ev in past["today"].get("events", {}).items():
            if ev in groups and i in titles:
                groups[ev].append({"date": d, "item_id": i, "today": False, "url": titles[i]["url"], "title": titles[i]["title"]})
    in_patterns = {event_of(e) for t in snap["threads"] if t["status"] != "dormant" for e in t["evidence"]}
    out = []
    for ev, arts in groups.items():
        if len(arts) >= dcfg.get("min_articles", 3) and ev not in in_patterns:
            out.append({"event": ev, "label": ev.replace("-", " ").capitalize(), "articles": arts})
    return sorted(out, key=lambda d: -len(d["articles"]))


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

    Built in code from stored evidence and teaching cards, so nothing can be made up. Two kinds, alternating:
    "which of these past stories was evidence for <pattern>?" (wrong options are other patterns' stories) and
    "<past story> was evidence of which pattern?" (options are pattern one-liners). Nicknames are only labels,
    never what's tested. Reruns of a date reuse its picks.
    """
    taught = {t["id"]: t for t in threads if t.get("teach") and not t.get("merged_into") and not t.get("split_into")}
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

    past = lambda t: [e for e in t["evidence"] if e["date"] < date]
    rng, questions = random.Random(f"remember-{date}"), []
    for k, tid in enumerate(picks):
        t = taught[tid]
        others = [taught[x] for x in taught if x != tid]
        if len(others) < 2 or not past(t):
            continue
        clue = rng.choice(past(t))
        if k % 2 == 0:
            pool = [e["title"] for o in others for e in past(o) if e["title"] != clue["title"]]
            if len(pool) < 2:
                continue
            q = f"Which of these stories was evidence for “{t['teach']['one_line']}” ({name(t)})?"
            right, opts = clue["title"], rng.sample(pool, 2)
        else:
            q = f"“{clue['title']}” ({short_date(clue['date'])}) was evidence of which pattern?"
            right, opts = t["teach"]["one_line"], [o["teach"]["one_line"] for o in rng.sample(others, 2)]
        slot = rng.randrange(3)
        opts.insert(slot, right)
        questions.append({"question": q, "options": opts, "answer_index": slot,
                          "why": f"{name(t)}: {t['teach']['one_line']} Clue: {clue.get('mechanism') or clue['note']} "
                                 f"Remember it as: {t['teach']['remember']}",
                          "since": short_date(t["created"])})
    return questions


# ---------------------------------------------------------------- page

def edition_input(cfg, date, sel, cards, rows, snap, conn, moves):
    threads = {t["id"]: t for t in snap["threads"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    forces_today = {}
    for tid in set(attached.values()):
        for f in threads[tid]["forces"]:
            forces_today.setdefault(f, []).append({"pattern": name(threads[tid]), "idea": one_line(threads[tid])})
    link = snap["today"]["cross_link"]
    return {
        "stories": [{"id": i, "section": r["section"], "headline": cards[i]["headline"] if i in cards else r["original_title"],
                     "why": cards[i]["why"]["text"] if i in cards else "", "pattern_id": attached.get(i),
                     "pattern": r["pattern"] and r["pattern"]["name"]}
                    for i, r in rows.items()],
        "call_candidates": [{"id": t["id"], "name": name(t), "idea": one_line(t), "claim": t["claim"], "status": t["status"],
                             "recent_clues": [e.get("mechanism") or e["note"] for e in t["evidence"][-4:]]}
                            for t in call_candidates(cfg, date, threads)],
        "forces": cfg["threads"]["forces"],
        "thread_moves": [{"id": t["id"], "move": kind, "name": name(t), "idea": one_line(t), "forces": t["forces"],
                          "stories_today": [cards[e["item_id"]]["headline"] if e["item_id"] in cards else e["title"]
                                            for e in t["evidence"] if e["date"] == date]} for t, kind in moves],
        "forces_today": forces_today,
        "cross_link": link and {"a": name(threads[link["thread_a"]]), "b": name(threads[link["thread_b"]]),
                                "force": link["force"], "sentence": link["sentence"]},
        "funding": [p["funding"] for p in sel["sections"].get("tech", []) if "funding" in p],
    }


def call_candidates(cfg, date, threads):
    """Threads a prediction may be about: active, no call in the cooldown window. Young threads without a
    call yet come first, so predictions spread across patterns."""
    cooldown = cfg.get("calls", {}).get("cooldown_days", 7)
    calls = [c for c in read_json(DATA / "calls.json", []) if c["made"] != date]
    recent = {c["thread_id"] for c in calls if 0 < days_between_iso(c["made"], date) <= cooldown}
    called = {c["thread_id"] for c in calls}
    ok = [t for t in threads.values() if t["status"] != "dormant" and t["id"] not in recent]
    return sorted(ok, key=lambda t: (t["id"] in called, t["status"] not in ("new", "building")))


def days_between_iso(a, b):
    return (Date.fromisoformat(b) - Date.fromisoformat(a)).days


def call_problems(cfg, call, allowed):
    """Why a prediction can't be published, or [] if it's fine. It must be checkable and able to fail."""
    ccfg = cfg.get("calls", {})
    problems = []
    if call["thread_id"] not in allowed:
        problems.append("thread_id must be one of call_candidates (active, not predicted on in the last week)")
    if not all(call[k].strip() for k in ("prediction", "measure", "threshold", "could_fail_because")):
        problems.append("prediction, measure, threshold and could_fail_because are all required")
    if not NAMED_EVENT.search(" " + call["threshold"].strip()):
        problems.append("threshold needs a number or a named event, not 'more' or 'another'")
    if MEDIA_MEASURE.search(call["measure"]):
        problems.append("measure must be a real-world outcome (a deal, price, vote, rule, filing), not how much news "
                        "there is about it: counting stories or coverage can't fail")
    if not ccfg.get("min_confidence", 20) <= call["confidence"] <= ccfg.get("max_confidence", 80):
        problems.append(f"confidence must be {ccfg.get('min_confidence', 20)}-{ccfg.get('max_confidence', 80)}")
    return problems


def make_call(cfg, date, call, threads, data):
    """Validate the writer's prediction; on rejection ask once more with the reasons; else skip the day."""
    allowed = {t["id"] for t in call_candidates(cfg, date, threads)}
    problems = call_problems(cfg, call, allowed)
    if problems:
        log.warning("call rejected (%s); asking once more", "; ".join(problems))
        wcfg = cfg.get("writing", {})
        prompt = (load_prompt("call").replace("{{style}}", load_prompt("style"))
                  .replace("{{problems}}", "\n".join(f"- {p}" for p in problems))
                  .replace("{{previous}}", json.dumps(call, ensure_ascii=False))
                  .replace("{{input}}", json.dumps({"call_candidates": data["call_candidates"]}, ensure_ascii=False, indent=1)))
        call = llm.generate_json(prompt, CALL_SCHEMA, tag="write:call", model=wcfg.get("model"), **wcfg.get("params", {}))["call"]
        problems = call_problems(cfg, call, allowed)
        if problems:
            log.warning("call rejected again (%s); no prediction today", "; ".join(problems))
            return None
    return record_call(date, call, threads)


def record_call(date, call, threads):
    """Append today's prediction to data/calls.json (replacing any earlier one from the same date)."""
    t = threads[call["thread_id"]]
    days = min(max(call["window_days"], 30), 120)
    entry = {"made": date, "thread_id": t["id"], "thread_title": name(t), "prediction": call["prediction"].strip(),
             "measure": call["measure"].strip(), "threshold": call["threshold"].strip(),
             "could_fail_because": call["could_fail_because"].strip(), "confidence": call["confidence"],
             "review_by": (Date.fromisoformat(date) + timedelta(days=days)).isoformat(), "verdict": None, "verdict_note": ""}
    calls = [c for c in read_json(DATA / "calls.json", []) if c["made"] != date]
    write_json(DATA / "calls.json", calls + [entry])
    return entry


def quiz_ok(q, cards, attached, threads, forces):
    """Code checks for the quiz types we can verify: evidence questions must use today's real headlines with
    the right one attached to the pattern; force questions must offer forces and the answer must be a force
    behind both stories' patterns."""
    if len(q["options"]) > 3 and 0 <= q["answer_index"] < len(q["options"]):  # sometimes 4 options: keep the answer
        right = q["options"][q["answer_index"]]
        q["options"] = [right] + [o for o in q["options"] if o != right][:2]
        q["answer_index"] = 0  # shuffle_answers spreads it out again
    opts = [o.strip() for o in q["options"]]
    if len(opts) != 3 or len(set(opts)) != 3 or not 0 <= q["answer_index"] <= 2:
        return False
    if q["type"] == "evidence":
        by_headline = {c["headline"]: i for i, c in cards.items()}
        ids = [by_headline.get(o) for o in opts]
        if None in ids or q["thread_id"] not in threads:
            return False
        return all((attached.get(i) == q["thread_id"]) == (n == q["answer_index"]) for n, i in enumerate(ids))
    if q["type"] == "force":
        if any(o.lower() not in forces for o in opts) or len(q["item_ids"]) < 2:
            return False
        behind = [set(threads[attached[i]]["forces"]) if attached.get(i) in threads else set() for i in q["item_ids"]]
        return opts[q["answer_index"]].lower() in set.intersection(*behind)
    return True


def timeline(t, date, days=14):
    counts = Counter(e["date"] for e in t["evidence"])
    end = Date.fromisoformat(date)
    return [{"date": d, "n": counts.get(d, 0)} for d in
            ((end - timedelta(days=k)).isoformat() for k in range(days - 1, -1, -1))]


def thread_view(t, date, line="", cards=None):
    cards = cards or {}
    ev = sorted(t["evidence"], key=lambda e: e["date"], reverse=True)
    today = [{**e, "headline": cards[e["item_id"]]["headline"] if e["item_id"] in cards else e["title"]}
             for e in ev if e["date"] == date]
    return {
        "id": t["id"], "name": name(t), "title": t["title"], "claim": t["claim"], "teach": t.get("teach") or {},
        "one_line": one_line(t), "forces": t["forces"], "status": t["status"], "line": line,
        "events": t.get("distinct_events") or len({event_of(e) for e in t["evidence"] if not e.get("added_on")}),
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
    data = edition_input(cfg, date, sel, cards, rows, snap, conn, moves)
    prompt = (load_prompt("write").replace("{{style}}", load_prompt("style")).replace("{{date}}", date)
              .replace("{{input}}", json.dumps(data, ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, SCHEMA, tag="write:page", model=wcfg.get("model"), **wcfg.get("params", {}))

    move_kind = {t["id"]: kind for t, kind in moves}
    lines = {x["thread_id"]: x["line"].strip() for x in out["scoreboard"] if x["thread_id"] in move_kind}
    force_lines = {x["force"].strip().lower(): x["line"].strip() for x in out["forces"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    throw = {x["item_id"]: x for x in conn["throwbacks"]}
    call = make_call(cfg, date, out["call"], threads, data)
    good = [q for q in out["quiz"] if quiz_ok(q, cards, attached, threads, set(cfg["threads"]["forces"]))]
    if len(good) < len(out["quiz"]):
        log.warning("dropped %d quiz questions that failed the checks", len(out["quiz"]) - len(good))
    quiz = shuffle_answers(good[:3], date)

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
    l2 = [thread_view(t, date, lines.get(t["id"], ""), cards) for t in active]
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
        "moves": [{"thread": thread_view(t, date, cards=cards), "kind": kind, "line": lines.get(t["id"], "")}
                  for t, kind in moves],
        "developing": developing(cfg, date, snap, items, cards),
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
