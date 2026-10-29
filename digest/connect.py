"""Connect today to last week: backstory evidence for threads, and today<->last-week "throwback" links.

Runs after threads. Backstory items are added to the day's thread snapshot as evidence dated when they were
published, so a thread shows how long the pattern has been building. The model only returns ids; every id is
checked against today's picks or data/context/DATE.json.
"""
import json
import logging
from datetime import datetime

from digest import llm
from digest.common import DATA, IST, load_prompt, read_json, write_json
from digest.threads import SNAPSHOTS, compute_status, selected_items

log = logging.getLogger(__name__)

KINDS = ["sequel", "reversal", "cause", "same_pattern"]
SCHEMA = {
    "type": "object",
    "properties": {
        "backstory": {"type": "array", "items": {"type": "object", "properties": {
            "thread_id": {"type": "string"}, "past_id": {"type": "string"}, "note": {"type": "string"}}}},
        "throwbacks": {"type": "array", "items": {"type": "object", "properties": {
            "item_id": {"type": "string"}, "past_id": {"type": "string"},
            "kind": {"type": "string", "enum": KINDS}, "line": {"type": "string"}}}},
    },
}


def ist_date(iso):
    return datetime.fromisoformat(iso).astimezone(IST).date().isoformat()


def run(cfg, date):
    snap = read_json(SNAPSHOTS / f"{date}.json")
    if not snap:
        raise SystemExit(f"no thread snapshot for {date}; run the threads phase first")
    past = {it["id"]: it for it in (read_json(DATA / "context" / f"{date}.json") or {}).get("items", [])}
    if not past:
        log.warning("no lookback items for %s; skipping connections", date)
        out = {"date": date, "backstory": [], "throwbacks": []}
        write_json(DATA / "connect" / f"{date}.json", out)
        return out
    today = selected_items(date)
    threads = {t["id"]: t for t in snap["threads"] if t["status"] != "dormant"}

    rows = lambda xs: "\n".join(json.dumps(x, ensure_ascii=False) for x in xs) or "(none)"
    prompt = (load_prompt("connect").replace("{{date}}", date)
              .replace("{{threads}}", rows({"id": t["id"], "name": t.get("nickname") or t["title"], "claim": t["claim"],
                                            "forces": t["forces"], "recent": [e["title"] for e in t["evidence"][-3:]]}
                                           for t in threads.values()))
              .replace("{{today}}", rows({"id": i, "section": it["section"], "title": it["title"],
                                          "summary": it["summary"][:160]} for i, it in today.items()))
              .replace("{{past}}", rows({"id": i, "date": ist_date(it["published_at"]), "section": it["section"],
                                         "title": it["title"]} for i, it in past.items())))
    result = llm.generate_json(prompt, SCHEMA, tag="connect", **cfg.get("connect", {}).get("params", {}))

    # Rerunning a day replaces that day's backstory instead of stacking it.
    for t in snap["threads"]:
        t["evidence"] = [e for e in t["evidence"] if e.get("added_on") != date]
    added, per_thread = [], {}
    for b in result["backstory"]:
        t, it = threads.get(b["thread_id"]), past.get(b["past_id"])
        if not t or not it or not b["note"].strip() or per_thread.get(t["id"], 0) >= 3:
            log.warning("dropping backstory %s -> %s", b["past_id"], b["thread_id"])
            continue
        if any(e["item_id"] == it["id"] for e in t["evidence"]):
            continue
        t["evidence"].append({"date": ist_date(it["published_at"]), "item_id": it["id"], "section": it["section"],
                              "title": it["title"], "url": it["url"], "source": it["source"],
                              "note": b["note"].strip(), "added_on": date})
        t["evidence"].sort(key=lambda e: e["date"])
        per_thread[t["id"]] = per_thread.get(t["id"], 0) + 1
        added.append({"thread_id": t["id"], "item_id": it["id"]})
    for t in snap["threads"]:
        t["sections"] = list(dict.fromkeys(e["section"] for e in t["evidence"]))
        t["status"] = compute_status(t, date, cfg["threads"]["dormant_after_days"])
    snap["today"]["backstory"] = added

    # "Same pattern" links only count if both stories really are clues for one thread: today's story is
    # attached to it and last week's is in its evidence. Otherwise "both about AI" passes as a connection.
    attached = {a["item_id"]: a["thread_id"] for a in snap["today"]["attached"]}
    clue_ids = {t["id"]: {e["item_id"] for e in t["evidence"]} for t in snap["threads"]}
    throwbacks, used = [], set()
    for x in result["throwbacks"]:
        if x["item_id"] not in today or x["past_id"] not in past or x["item_id"] in used or not x["line"].strip():
            log.warning("dropping throwback %s <- %s", x["item_id"], x["past_id"])
            continue
        if x["kind"] == "same_pattern" and x["past_id"] not in clue_ids.get(attached.get(x["item_id"]), set()):
            log.info("dropping weak same-pattern link: %s", x["line"])
            continue
        used.add(x["item_id"])
        p = past[x["past_id"]]
        throwbacks.append({"item_id": x["item_id"], "kind": x["kind"], "line": x["line"].strip(),
                           "past": {"id": p["id"], "date": ist_date(p["published_at"]), "title": p["title"],
                                    "url": p["url"], "source": p["source"], "section": p["section"]}})

    write_json(SNAPSHOTS / f"{date}.json", snap)
    if sorted(SNAPSHOTS.glob("*.json"))[-1].stem == date:
        write_json(DATA / "threads.json", {"date": date, "threads": snap["threads"], "candidates": snap["candidates"]})
    out = {"date": date, "backstory": added, "throwbacks": throwbacks}
    write_json(DATA / "connect" / f"{date}.json", out)
    return out
