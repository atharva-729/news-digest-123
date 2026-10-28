"""Phase 4: turn the day's picks and thread movements into the newsletter.

The writer returns structured text keyed by ids; code checks every id and the Jinja2 template inserts the
titles and links, so the model never produces a link. The day's prediction is appended to data/calls.json.
"""
import json
import logging
import re
from datetime import date as Date, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape

from digest import llm
from digest.common import DATA, ROOT, load_prompt, read_json, write_json

log = logging.getLogger(__name__)

SITE = ROOT / "docs"  # GitHub Pages serves this folder from the main branch
SECTION_LABELS = {"tech": "Tech", "politics_india": "India", "politics_world": "World",
                  "markets": "Markets", "sports": "Sports", "fun": "Fun"}
MOVE_ICONS = {"new": "🆕", "heating": "🔥", "cooling": "🧊"}

SCHEMA = {
    "type": "object",
    "properties": {
        "big_picture": {"type": "string"},
        "scoreboard": {"type": "array", "items": {"type": "object", "properties": {
            "thread_id": {"type": "string"}, "line": {"type": "string"}}}},
        "takes": {"type": "array", "items": {"type": "object", "properties": {
            "item_id": {"type": "string"}, "take": {"type": "string"}}}},
        "pulse_india": {"type": "string"},
        "pulse_world": {"type": "string"},
        "dots": {"type": "string"},
        "call": {"type": "object", "properties": {
            "thread_id": {"type": "string"}, "prediction": {"type": "string"}, "check_in_days": {"type": "integer"}}},
        "fun": {"type": "array", "items": {"type": "object", "properties": {
            "item_id": {"type": "string"}, "text": {"type": "string"}}}},
        "quiz": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"}, "answer": {"type": "string"}}}},
    },
}


def env():
    return Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "j2"]))


def load_day(date):
    sel = read_json(DATA / "selected" / f"{date}.json")
    day = read_json(DATA / "items" / f"{date}.json")
    snap = read_json(DATA / "threads" / f"{date}.json")
    if not (sel and day and snap):
        raise SystemExit(f"missing data for {date}; run ingest, select and threads first")
    return sel, {it["id"]: it for it in day["items"]}, snap


def thread_moves(snap):
    """New, heating and cooling threads today, in that order."""
    today, threads = snap["today"], {t["id"]: t for t in snap["threads"]}
    attached = {a["thread_id"] for a in today["attached"]}
    new = today["new_threads"] + today["promoted"]
    moves = [(tid, "new") for tid in new]
    moves += [(tid, "heating") for tid, t in threads.items()
              if t["status"] == "heating" and tid not in new and tid in attached]
    moves += [(tid, "cooling") for tid, (_, now) in today["status_changes"].items() if now == "cooling"]
    return [(threads[tid], kind) for tid, kind in moves]


def build_input(date, sel, items, snap, moves):
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    threads = {t["id"]: t for t in snap["threads"]}
    row = lambda i, p: {"id": i, "source": items[i]["source"], "title": items[i]["title"],
                        "summary": items[i]["summary"][:300], "why_picked": p["reason"],
                        "evidence_of": threads[attached[i]]["title"] if i in attached else None,
                        **({"funding": p["funding"]} if "funding" in p else {})}
    link = snap["today"]["cross_link"]
    return {
        "sections": [{"section": SECTION_LABELS[s], "items": [row(p["id"], p) for p in picks]}
                     for s, picks in sel["sections"].items() if s != "fun" and picks],
        "fun_items": [row(p["id"], p) for p in sel["sections"].get("fun", [])],
        "thread_moves": [{"id": t["id"], "move": kind, "title": t["title"], "claim": t["claim"], "forces": t["forces"],
                          "evidence_today": [e["title"] for e in t["evidence"] if e["date"] == date]}
                         for t, kind in moves],
        "open_threads": [{"id": t["id"], "title": t["title"], "claim": t["claim"]}
                         for t in snap["threads"] if t["status"] != "dormant"],
        "cross_link": link and {"thread_a": threads[link["thread_a"]]["title"],
                                "thread_b": threads[link["thread_b"]]["title"],
                                "force": link["force"], "sentence": link["sentence"]},
        "funding": [p["funding"] for p in sel["sections"].get("tech", []) if "funding" in p],
    }


def by_id(rows, key, valid, field):
    out = {}
    for r in rows:
        if r[key] in valid and r[field].strip():
            out.setdefault(r[key], r[field].strip())
        elif r[key] not in valid:
            log.warning("writer returned unknown %s %r; dropped", key, r[key])
    return out


def record_call(date, call, threads):
    """Append today's prediction to data/calls.json (replacing any earlier one from the same date)."""
    t = threads.get(call["thread_id"])
    if not t or not call["prediction"].strip():
        log.warning("no valid call today (thread %r)", call["thread_id"])
        return None
    days = min(max(call["check_in_days"], 30), 120)
    entry = {"made": date, "thread_id": t["id"], "thread_title": t["title"], "prediction": call["prediction"].strip(),
             "review_by": (Date.fromisoformat(date) + timedelta(days=days)).isoformat(), "verdict": None, "verdict_note": ""}
    calls = [c for c in read_json(DATA / "calls.json", []) if c["made"] != date]
    write_json(DATA / "calls.json", calls + [entry])
    return entry


def read_minutes(html):
    words = len(re.sub(r"<[^>]+>", " ", html).split())
    return max(1, round(words / 220))


def run(cfg, date):
    sel, items, snap = load_day(date)
    threads = {t["id"]: t for t in snap["threads"]}
    moves = thread_moves(snap)
    data = build_input(date, sel, items, snap, moves)
    prompt = (load_prompt("write").replace("{{style}}", load_prompt("style")).replace("{{date}}", date)
              .replace("{{input}}", json.dumps(data, ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, SCHEMA, **cfg.get("writing", {}).get("params", {}))

    picked = {p["id"] for picks in sel["sections"].values() for p in picks}
    takes = by_id(out["takes"], "item_id", picked, "take")
    fun_text = by_id(out["fun"], "item_id", {p["id"] for p in sel["sections"].get("fun", [])}, "text")
    lines = by_id(out["scoreboard"], "thread_id", {t["id"] for t, _ in moves}, "line")
    call = record_call(date, out["call"], threads)
    attached = {a["item_id"]: threads[a["thread_id"]] for a in snap["today"]["attached"]}
    if len(out["quiz"]) != 3:
        log.warning("writer returned %d quiz questions", len(out["quiz"]))

    entry = lambda p: {**items[p["id"]], "take": takes.get(p["id"]), "thread": attached.get(p["id"]),
                       "funding": p.get("funding"), "fun": fun_text.get(p["id"])}
    link = snap["today"]["cross_link"]
    ctx = {
        "date": date,
        "pretty_date": Date.fromisoformat(date).strftime("%A, %d %B %Y"),
        "big_picture": out["big_picture"].strip(),
        "scoreboard": [{"icon": MOVE_ICONS[kind], "thread": t, "line": lines.get(t["id"], "")} for t, kind in moves],
        "sections": [{"label": SECTION_LABELS[s], "items": [entry(p) for p in picks]}
                     for s, picks in sel["sections"].items() if s != "fun" and picks],
        "pulse": {"india": out["pulse_india"].strip(), "world": out["pulse_world"].strip()},
        "dots": link and {"a": threads[link["thread_a"]], "b": threads[link["thread_b"]], "force": link["force"],
                          "text": out["dots"].strip() or link["sentence"]},
        "call": call,
        "fun": [entry(p) for p in sel["sections"].get("fun", [])],
        "quiz": out["quiz"][:3],
        "credit": cfg["credit"],
    }
    ctx["sources"] = sorted({it["source"] for s in ctx["sections"] for it in s["items"]} | {it["source"] for it in ctx["fun"]})
    html = env().get_template("newsletter.html.j2").render(**ctx, minutes=0)
    html = env().get_template("newsletter.html.j2").render(**ctx, minutes=read_minutes(html))
    SITE.mkdir(exist_ok=True)
    (SITE / f"{date}.html").write_text(html, encoding="utf-8")
    subj = subject(date, ctx)
    write_json(DATA / "written" / f"{date}.json", {"date": date, "subject": subj, "writer": out, "call": call})
    return {"path": SITE / f"{date}.html", "minutes": read_minutes(html), "takes": len(takes),
            "items": len(picked), "moves": len(moves), "call": call, "subject": subj}


def subject(date, ctx):
    lead = ctx["scoreboard"][0]["thread"]["title"] if ctx["scoreboard"] else "today's threads"
    return f"L1·L2·L3 {date}: {lead}"
