"""Phase 6: the Sunday edition. Thread-only: how each thread moved this week, births and deaths, and a
review of any calls that are due, judged against the week's selected items. No new ingestion."""
import json
import logging
from datetime import date as Date, timedelta

from digest import llm
from digest.common import DATA, load_prompt, read_json, write_json
from digest.write import SITE, checked, hl_text, name, one_line, render, short_date, thread_view

log = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "tldr": {"type": "array", "items": hl_text},
        "intro": hl_text,
        "threads": {"type": "array", "items": {"type": "object", "properties": {
            "thread_id": {"type": "string"}, "line": {"type": "string"}}}},
        "calls": {"type": "array", "items": {"type": "object", "properties": {
            "index": {"type": "integer"},
            "verdict": {"type": "string", "enum": ["right", "wrong", "too_early"]},
            "note": {"type": "string"},
            "item_ids": {"type": "array", "items": {"type": "string"}}}}},
        "watch": {"type": "string"},
    },
}


def snapshot_on_or_before(date):
    snaps = sorted(p for p in (DATA / "threads").glob("*.json") if p.stem <= date)
    return read_json(snaps[-1]) if snaps else None


def week_items(days):
    """The week's selected items (title + summary only; the model judges calls against these)."""
    out = {}
    for d in days:
        sel, day = read_json(DATA / "selected" / f"{d}.json"), read_json(DATA / "items" / f"{d}.json")
        if not sel or not day:
            continue
        by_id = {it["id"]: it for it in day["items"]}
        for picks in sel["sections"].values():
            for p in picks:
                it = by_id[p["id"]]
                out[p["id"]] = {"id": p["id"], "date": d, "title": it["title"], "summary": it["summary"][:200],
                                "url": it["url"], "source": it["source"]}
    return out


def run(cfg, date):
    end = Date.fromisoformat(date)
    days = [(end - timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
    now = snapshot_on_or_before(date)
    if not now:
        raise SystemExit("no thread snapshots yet; run a few dailies first")
    before = snapshot_on_or_before((end - timedelta(days=7)).isoformat()) or {"threads": []}
    was = {t["id"]: t["status"] for t in before["threads"]}

    rows = []
    for t in now["threads"]:
        ev = [e for e in t["evidence"] if days[0] <= e["date"] <= date]
        born = days[0] <= t["created"] <= date
        died = t["status"] == "dormant" and was.get(t["id"], "dormant") != "dormant"
        if ev or born or died or was.get(t["id"]) != t["status"]:
            rows.append({"thread": t, "week": len(ev), "from": was.get(t["id"], "new"), "to": t["status"],
                         "born": born, "died": died, "notes": [e["note"] for e in ev]})
    rows.sort(key=lambda r: (-r["week"], name(r["thread"])))

    calls = read_json(DATA / "calls.json", [])
    # Every open prediction made before today is checked: it can be "right" early if its threshold is met,
    # but only "wrong" once its window has closed. Otherwise it stays "too early".
    due = [(n, c) for n, c in enumerate(calls) if not c["verdict"] and c["made"] < date]
    items = week_items(days)
    data = {
        "moved": [{"id": r["thread"]["id"], "nickname": name(r["thread"]), "idea": one_line(r["thread"]),
                   "forces": r["thread"]["forces"], "status_last_week": r["from"], "status_now": r["to"],
                   "born_this_week": r["born"], "went_dormant": r["died"], "evidence_this_week": r["notes"]}
                  for r in rows],
        "calls_due": [{"index": n, "made": c["made"], "thread": c["thread_title"], "prediction": c["prediction"],
                       "measure": c.get("measure", ""), "threshold": c.get("threshold", ""), "window_ends": c["review_by"],
                       "window_closed": c["review_by"] <= date} for n, c in due],
        "week_items": [{k: v for k, v in it.items() if k not in ("url", "source")} for it in items.values()] if due else [],
    }
    prompt = (load_prompt("weekly").replace("{{style}}", load_prompt("style")).replace("{{start}}", days[0])
              .replace("{{end}}", date).replace("{{input}}", json.dumps(data, ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, SCHEMA, tag="weekly", model=cfg.get("writing", {}).get("model"), **cfg.get("writing", {}).get("params", {}))

    lines = {x["thread_id"]: x["line"].strip() for x in out["threads"]}
    reviewed = []
    due_idx = {n for n, _ in due}
    for v in out["calls"]:
        if v["index"] not in due_idx:
            continue
        c = calls[v["index"]]
        # Only news that arrived after the call can settle it; the items that inspired it don't count.
        evidence = [items[i] for i in v["item_ids"] if i in items and items[i]["date"] > c["made"]]
        verdict = v["verdict"]
        if verdict == "right" and not evidence:
            verdict = "too_early"  # no evidence, no verdict
        if verdict == "wrong" and c["review_by"] > date:
            verdict = "too_early"  # can't be wrong before its window closes
        if verdict != "too_early":
            c["verdict"], c["verdict_note"], c["verdict_date"] = verdict, v["note"].strip(), date
        reviewed.append({**c, "shown_verdict": verdict, "note": v["note"].strip(), "evidence": evidence})
    write_json(DATA / "calls.json", calls)

    moved = []
    for r in rows:
        if r["died"]:
            continue
        view = thread_view(r["thread"], date, lines.get(r["thread"]["id"], ""))
        moved.append({**view, "week": r["week"], "from": r["from"], "to": r["to"]})
    # Merges and splits this week are shown, never silent.
    all_threads = {t["id"]: t for t in now["threads"]}
    nm = lambda tid: name(all_threads[tid]) if tid in all_threads else tid
    restructured = []
    for d in days:
        snap = read_json(DATA / "threads" / f"{d}.json")
        if not snap:
            continue
        for m in snap["today"].get("merges", []):
            restructured.append(f"{short_date(d)}: “{nm(m['absorb'])}” merged into “{nm(m['keep'])}”")
        for s in snap["today"].get("splits", []):
            restructured.append(f"{short_date(d)}: “{nm(s['from'])}” split into " + " and ".join(f"“{nm(i)}”" for i in s["into"]))
    ctx = {
        "restructured": restructured,
        "start": short_date(days[0]), "end": short_date(date), "headline": out["headline"].strip(),
        "tldr": [checked(x) for x in out["tldr"][:3]], "intro": checked(out["intro"]),
        "moved": moved,
        "born": [r["thread"] for r in rows if r["born"]],
        "died": [r["thread"] for r in rows if r["died"]],
        "calls": reviewed, "watch": out["watch"].strip(), "credit": cfg["credit"],
        "open_calls": sum(not c["verdict"] for c in calls),
    }
    path = SITE / f"weekly-{date}.html"
    render("weekly.html.j2", path, **ctx)
    subject = f"L1·L2·L3 weekly {short_date(date)}: {ctx['headline']}"
    write_json(DATA / "weekly" / f"{date}.json",
               {"date": date, "subject": subject, "lead": ctx["headline"], "tldr": ctx["tldr"], "writer": out})
    return {"path": path, "moved": len(moved), "born": len(ctx["born"]), "died": len(ctx["died"]),
            "calls_reviewed": len(reviewed), "subject": subject}
