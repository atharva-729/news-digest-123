"""Phase 4: turn the day's picks, threads and connections into the web edition (docs/DATE.html).

The writer returns structured text keyed by ids; code checks every id and the Jinja2 templates insert the
real headlines and links, so the model never produces a link. The day's prediction goes to data/calls.json.
"""
import json
import logging
import random
import shutil
from collections import Counter
from datetime import date as Date, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from digest import llm
from digest.common import DATA, ROOT, load_prompt, read_json, write_json

log = logging.getLogger(__name__)

SITE = ROOT / "docs"  # GitHub Pages serves this folder from the main branch
STATIC = ROOT / "templates" / "static"
SECTIONS = {
    "tech": ("Tech", "⚡"), "politics_india": ("India", "🇮🇳"), "politics_world": ("World", "🌍"),
    "markets": ("Markets", "📈"), "sports": ("Sports", "🏆"), "fun": ("Fun", "🎈"),
}
FORCE_ICONS = {"technology": "⚙️", "capital": "💰", "geopolitics": "🌐", "regulation": "⚖️", "demographics": "👥"}
KIND_LABELS = {"sequel": "Sequel", "reversal": "Plot twist", "cause": "Cause → effect", "same_pattern": "Same pattern"}

hl_text = {"type": "object", "properties": {"text": {"type": "string"}, "highlight": {"type": "string"}}}
SCHEMA = {
    "type": "object",
    "properties": {
        "tldr": {"type": "array", "items": hl_text},
        "hero": hl_text,
        "cards": {"type": "array", "items": {"type": "object", "properties": {
            "item_id": {"type": "string"}, "emoji": {"type": "string"}, "punchy": {"type": "string"},
            "so_what": {"type": "string"}, "highlight": {"type": "string"}}}},
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
    e.globals.update(SECTIONS=SECTIONS, FORCE_ICONS=FORCE_ICONS, KIND_LABELS=KIND_LABELS)
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


def build_input(cfg, date, sel, items, snap, conn, moves):
    threads = {t["id"]: t for t in snap["threads"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    throw = {x["item_id"]: x for x in conn["throwbacks"]}
    rows = []
    for s, picks in sel["sections"].items():
        for p in picks:
            it = items[p["id"]]
            rows.append({"id": p["id"], "section": SECTIONS[s][0], "source": it["source"], "title": it["title"],
                         "summary": it["summary"][:300], "why_picked": p["reason"],
                         "evidence_of": name(threads[attached[p["id"]]]) if p["id"] in attached else None,
                         "links_to_last_week": ({"past_title": throw[p["id"]]["past"]["title"],
                                                 "link": throw[p["id"]]["line"]} if p["id"] in throw else None),
                         **({"funding": p["funding"]} if "funding" in p else {})})
    today_threads = {t for t in attached.values()}
    forces_today = {}
    for tid in today_threads:
        for f in threads[tid]["forces"]:
            forces_today.setdefault(f, []).append({"thread": name(threads[tid]), "claim": threads[tid]["claim"]})
    link = snap["today"]["cross_link"]
    return {
        "items": rows,
        "thread_moves": [{"id": t["id"], "move": kind, "nickname": name(t), "claim": t["claim"],
                          "forces": t["forces"],
                          "evidence_today": [e["title"] for e in t["evidence"] if e["date"] == date]}
                         for t, kind in moves],
        "forces_today": forces_today,
        "open_threads": [{"id": t["id"], "nickname": name(t), "claim": t["claim"]}
                         for t in snap["threads"] if t["status"] != "dormant"],
        "cross_link": link and {"thread_a": name(threads[link["thread_a"]]), "thread_b": name(threads[link["thread_b"]]),
                                "force": link["force"], "sentence": link["sentence"]},
        "throwbacks": [{"today": items[x["item_id"]]["title"], "last_week": x["past"]["title"], "kind": x["kind"],
                        "line": x["line"]} for x in conn["throwbacks"]],
        "funding": [p["funding"] for p in sel["sections"].get("tech", []) if "funding" in p],
    }


def checked(obj):
    """A {text, highlight} pair, with the highlight dropped unless it really occurs in the text."""
    text, hl = obj["text"].strip(), obj["highlight"].strip()
    return {"text": text, "highlight": hl if hl and hl in text else ""}


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
    out = []
    for k in range(days - 1, -1, -1):
        d = (end - timedelta(days=k)).isoformat()
        out.append({"date": d, "n": counts.get(d, 0)})
    return out


def thread_view(t, date, kind=None, line=""):
    ev = sorted(t["evidence"], key=lambda e: e["date"], reverse=True)
    return {
        "id": t["id"], "name": name(t), "title": t["title"], "plain": t.get("plain", ""), "claim": t["claim"],
        "forces": t["forces"], "status": "new" if kind == "new" else t["status"], "line": line,
        "today": sum(e["date"] == date for e in t["evidence"]), "total": len(t["evidence"]),
        "since": short_date(min(e["date"] for e in t["evidence"])),
        "timeline": timeline(t, date),
        "evidence": [{**e, "is_today": e["date"] == date, "is_backstory": bool(e.get("added_on"))} for e in ev[:6]],
    }


def read_minutes(ctx):
    """Minutes to read the Feed tab (TL;DR, the big one, every card). The other tabs are optional depth."""
    texts = [x["text"] for x in ctx["tldr"]] + [ctx["hero"]["text"]]
    texts += [c["punchy"] + " " + (c["so_what"]["text"] if c["so_what"] else "") for s in ctx["sections"] for c in s["items"]]
    return max(1, round(len(" ".join(texts).split()) / 200))


def run(cfg, date):
    sel, items, snap, conn = load_day(date)
    threads = {t["id"]: t for t in snap["threads"]}
    moves = thread_moves(snap)
    data = build_input(cfg, date, sel, items, snap, conn, moves)
    prompt = (load_prompt("write").replace("{{style}}", load_prompt("style")).replace("{{date}}", date)
              .replace("{{card_rules}}", load_prompt("card_rules"))
              .replace("{{input}}", json.dumps(data, ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, SCHEMA, tag="write", model=cfg.get("writing", {}).get("model"), **cfg.get("writing", {}).get("params", {}))

    picked = [p for picks in sel["sections"].values() for p in picks]
    cards = {}
    for c in out["cards"]:
        if c["item_id"] in items and c["item_id"] not in cards and c["punchy"].strip():
            cards[c["item_id"]] = {"emoji": c["emoji"].strip()[:4], "punchy": c["punchy"].strip(),
                                   "so_what": checked({"text": c["so_what"], "highlight": c["highlight"]})}
        else:
            log.warning("writer returned unusable card for %r", c["item_id"])
    missing = [p["id"] for p in picked if p["id"] not in cards]
    if missing:  # the writer sometimes skips a few cards in a long answer; ask again for just those
        log.warning("writer skipped %d cards; asking again for those", len(missing))
        retry = {**data, "items": [r for r in data["items"] if r["id"] in missing]}
        prompt = (load_prompt("write_cards").replace("{{style}}", load_prompt("style"))
                  .replace("{{card_rules}}", load_prompt("card_rules"))
                  .replace("{{input}}", json.dumps(retry["items"], ensure_ascii=False, indent=1)))
        extra = llm.generate_json(prompt, {"type": "object", "properties": {"cards": SCHEMA["properties"]["cards"]}},
                                  tag="write:retry", model=cfg.get("writing", {}).get("model"), **cfg.get("writing", {}).get("params", {}))
        for c in extra["cards"]:
            if c["item_id"] in missing and c["item_id"] not in cards and c["punchy"].strip():
                cards[c["item_id"]] = {"emoji": c["emoji"].strip()[:4], "punchy": c["punchy"].strip(),
                                       "so_what": checked({"text": c["so_what"], "highlight": c["highlight"]})}
        still = [i for i in missing if i not in cards]
        if still:
            log.warning("no card for %d items; showing their original headlines", len(still))

    move_kind = {t["id"]: kind for t, kind in moves}
    lines = {x["thread_id"]: x["line"].strip() for x in out["scoreboard"] if x["thread_id"] in move_kind}
    force_lines = {x["force"].strip().lower(): x["line"].strip() for x in out["forces"]}
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    throw = {x["item_id"]: x for x in conn["throwbacks"]}
    call = record_call(date, out["call"], threads)
    quiz = [q for q in out["quiz"] if len(q["options"]) == 3 and 0 <= q["answer_index"] <= 2][:3]
    if len(quiz) < 3:
        log.warning("writer returned %d usable quiz questions", len(quiz))
    # The model tends to put the answer first. Give each question a different answer slot (A/B/C), the same
    # way on reruns of a date.
    rng = random.Random(date)
    for q, slot in zip(quiz, rng.sample(range(3), 3)):
        right = q["options"][q["answer_index"]]
        wrong = [o for i, o in enumerate(q["options"]) if i != q["answer_index"]]
        rng.shuffle(wrong)
        q["options"], q["answer_index"] = wrong[:slot] + [right] + wrong[slot:], slot

    def card(section, p):
        it, c = items[p["id"]], cards.get(p["id"])
        t = threads.get(attached.get(p["id"]))
        return {**it, "section": section, "emoji": c["emoji"] if c else SECTIONS[section][1],
                "punchy": c["punchy"] if c else it["title"], "so_what": c["so_what"] if c else None,
                "funding": p.get("funding"), "throwback": throw.get(p["id"]),
                "thread": t and {"id": t["id"], "name": name(t), "status": move_kind.get(t["id"], t["status"])}}

    sections = [{"key": s, "label": SECTIONS[s][0], "emoji": SECTIONS[s][1], "items": [card(s, p) for p in picks]}
                for s, picks in sel["sections"].items() if picks]
    all_cards = {c["id"]: c for s in sections for c in s["items"]}

    # "What this means": L1 (today's items), L2 (threads), L3 (forces), plus the connections between them.
    active = [t for t in snap["threads"] if t["status"] != "dormant"]
    active.sort(key=lambda t: t["last_seen"], reverse=True)
    active.sort(key=lambda t: -sum(e["date"] == date for e in t["evidence"]))  # most evidence today first
    l2 = [thread_view(t, date, move_kind.get(t["id"]), lines.get(t["id"], "")) for t in active]
    forces = []
    for f in cfg["threads"]["forces"]:
        ts = [t for t in l2 if f in t["forces"]]
        forces.append({"key": f, "label": f.title(), "icon": FORCE_ICONS.get(f, "•"), "line": force_lines.get(f, ""),
                       "threads": len(ts), "today": sum(t["today"] for t in ts),
                       "names": [t["name"] for t in ts if t["today"]][:3]})
    l1_linked = [{"card": all_cards[i], "thread": threads[tid]} for i, tid in attached.items() if i in all_cards]
    l1_oneoffs = [c for c in all_cards.values() if c["id"] not in attached]
    map_threads = [t for t in l2 if t["today"]]
    link = snap["today"]["cross_link"]

    calls = sorted(read_json(DATA / "calls.json", []), key=lambda c: c["made"], reverse=True)
    ctx = {
        "date": date,
        "day": Date.fromisoformat(date).strftime("%a"),
        "pretty_date": Date.fromisoformat(date).strftime("%d %b %Y").lstrip("0"),
        "tldr": [checked(x) for x in out["tldr"][:3]],
        "hero": checked(out["hero"]),
        "moves": [{"thread": thread_view(t, date, kind), "kind": kind, "line": lines.get(t["id"], "")} for t, kind in moves],
        "sections": sections,
        "pulse": {"india": out["pulse_india"].strip(), "world": out["pulse_world"].strip()},
        "l1_linked": l1_linked, "l1_oneoffs": l1_oneoffs, "l2": l2, "forces": forces,
        "map_items": [x for x in l1_linked if any(t["id"] == x["thread"]["id"] for t in map_threads)],
        "map_threads": map_threads,
        "dots": link and {"a": thread_view(threads[link["thread_a"]], date), "b": thread_view(threads[link["thread_b"]], date),
                          "force": link["force"], "text": out["dots"].strip() or link["sentence"]},
        "throwbacks": [{**x, "now": all_cards.get(x["item_id"])} for x in conn["throwbacks"] if x["item_id"] in all_cards],
        "call": call, "past_calls": [c for c in calls if c["made"] != date][:6],
        "quiz": quiz,
        "credit": cfg["credit"],
        "sources": sorted({c["source"] for c in all_cards.values()}),
        "stats": {"stories": len(all_cards), "threads": len(l2), "today_threads": len(map_threads),
                  "throwbacks": len(conn["throwbacks"]), "backstory": len(conn["backstory"])},
    }
    path = SITE / f"{date}.html"
    ctx["minutes"] = read_minutes(ctx)
    render("daily.html.j2", path, **ctx)

    lead = ctx["tldr"][0]["text"] if ctx["tldr"] else (name(moves[0][0]) if moves else "today's threads")
    subj = f"L1·L2·L3 {short_date(date)}: {lead}"
    write_json(DATA / "written" / f"{date}.json",
               {"date": date, "subject": subj, "lead": lead, "tldr": ctx["tldr"], "hero": ctx["hero"], "writer": out,
                "call": call})
    return {"path": path, "minutes": ctx["minutes"], "takes": len(cards), "items": len(picked), "moves": len(moves),
            "call": call, "subject": subj}
