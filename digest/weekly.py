"""Phase 6: the Sunday edition. Thread-only: how each thread moved this week, births and deaths, and a
review of any calls that are due, judged against the week's selected items. No new ingestion."""
import json
import logging
from datetime import date as Date, timedelta

from digest import llm
from digest.common import DATA, load_prompt, read_json, write_json
from digest.write import SITE, env

log = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "intro": {"type": "string"},
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
                out[p["id"]] = {"id": p["id"], "date": d, "title": it["title"], "summary": it["summary"][:200]}
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
            rows.append({"thread": t, "evidence_this_week": len(ev), "total": len(t["evidence"]),
                         "from": was.get(t["id"], "new"), "to": t["status"], "born": born, "died": died,
                         "notes": [e["note"] for e in ev]})
    rows.sort(key=lambda r: (-r["evidence_this_week"], r["thread"]["title"]))

    calls = read_json(DATA / "calls.json", [])
    due = [(n, c) for n, c in enumerate(calls) if c["review_by"] <= date and not c["verdict"]]
    items = week_items(days)
    data = {
        "moved": [{"id": r["thread"]["id"], "title": r["thread"]["title"], "claim": r["thread"]["claim"],
                   "forces": r["thread"]["forces"], "status_last_week": r["from"], "status_now": r["to"],
                   "born_this_week": r["born"], "went_dormant": r["died"],
                   "evidence_this_week": r["notes"]} for r in rows],
        "calls_due": [{"index": n, "made": c["made"], "thread": c["thread_title"], "prediction": c["prediction"]}
                      for n, c in due],
        "week_items": list(items.values()) if due else [],
    }
    prompt = (load_prompt("weekly").replace("{{style}}", load_prompt("style")).replace("{{start}}", days[0])
              .replace("{{end}}", date).replace("{{input}}", json.dumps(data, ensure_ascii=False, indent=1)))
    out = llm.generate_json(prompt, SCHEMA, **cfg.get("writing", {}).get("params", {}))

    lines = {x["thread_id"]: x["line"].strip() for x in out["threads"]}
    reviewed = []
    due_idx = {n for n, _ in due}
    for v in out["calls"]:
        if v["index"] not in due_idx:
            continue
        c = calls[v["index"]]
        # Only news that arrived after the call can settle it; the items that inspired it don't count.
        evidence = [items[i] for i in v["item_ids"] if i in items and items[i]["date"] > c["made"]]
        verdict = v["verdict"] if evidence else "too_early"
        if verdict != "too_early":
            c["verdict"], c["verdict_note"], c["verdict_date"] = verdict, v["note"].strip(), date
        reviewed.append({**c, "shown_verdict": verdict, "note": v["note"].strip(), "evidence": evidence})
    write_json(DATA / "calls.json", calls)

    ctx = {
        "start": days[0], "end": date, "headline": out["headline"].strip(), "intro": out["intro"].strip(),
        "moved": [{**r, "line": lines.get(r["thread"]["id"], "")} for r in rows if not r["died"]],
        "born": [r["thread"] for r in rows if r["born"]],
        "died": [r["thread"] for r in rows if r["died"]],
        "calls": reviewed, "watch": out["watch"].strip(), "credit": cfg["credit"],
        "open_calls": sum(not c["verdict"] for c in calls),
    }
    html = env().get_template("weekly.html.j2").render(**ctx)
    SITE.mkdir(exist_ok=True)
    (SITE / f"weekly-{date}.html").write_text(html, encoding="utf-8")
    subject = f"L1·L2·L3 weekly {date}: {ctx['headline']}"
    write_json(DATA / "weekly" / f"{date}.json", {"date": date, "subject": subject, "writer": out})
    return {"path": SITE / f"weekly-{date}.html", "moved": len(ctx["moved"]), "born": len(ctx["born"]),
            "died": len(ctx["died"]), "calls_reviewed": len(reviewed), "subject": subject}
