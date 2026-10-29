"""Pattern-quality report. No LLM. Run: python -m digest.quality [--date D | --from A --until B] [--out FILE]

Per edition: attach rate (share of selected stories attached to a thread), clues and distinct events per
active thread, status mix, look-alike thread pairs, and predictions per thread.
"""
import argparse
import sys
from collections import Counter
from itertools import combinations

from rapidfuzz import fuzz

from digest.common import DATA, load_config, read_json


def event_of(e):
    """The evidence's event key; before events existed, each distinct title stands in for one."""
    return e.get("event") or f"title:{e['title'].lower()}"


def overlap_pairs(threads, threshold):
    """Active thread pairs with look-alike claims (rapidfuzz token_set_ratio) that share a force."""
    out = []
    for a, b in combinations(threads, 2):
        score = fuzz.token_set_ratio(a["claim"].lower(), b["claim"].lower())
        if score >= threshold and set(a["forces"]) & set(b["forces"]):
            out.append((round(score), a, b))
    return sorted(out, key=lambda x: -x[0])


def report(date, cfg):
    snap = read_json(DATA / "threads" / f"{date}.json")
    sel = read_json(DATA / "selected" / f"{date}.json")
    if not snap or not sel:
        return None, f"{date}: no snapshot or selection\n"
    picked = [p["id"] for ps in sel["sections"].values() for p in ps]
    attached = {a["item_id"] for a in snap["today"]["attached"]}
    active = [t for t in snap["threads"] if t["status"] != "dormant"]
    status = Counter(t["status"] for t in active)
    pairs = overlap_pairs(active, cfg["threads"].get("overlap_similarity", 70))
    lines = [f"== {date}",
             f"attach rate     {len(attached & set(picked))}/{len(picked)} = {len(attached & set(picked)) / max(1, len(picked)):.2f}",
             f"active threads  {len(active)}  (status: {', '.join(f'{k} {v}' for k, v in sorted(status.items()))})",
             f"{'thread':<34} {'status':<9} {'clues':>5} {'events':>6} {'today':>5}"]
    for t in sorted(active, key=lambda t: -len(t["evidence"])):
        own = [e for e in t["evidence"] if not e.get("added_on")]  # backstory from last week isn't the thread's own
        lines.append(f"{(t.get('nickname') or t['title'])[:34]:<34} {t['status']:<9} {len(t['evidence']):>5} "
                     f"{len({event_of(e) for e in own}):>6} {sum(e['date'] == date for e in t['evidence']):>5}")
    lines.append(f"look-alike pairs (claim similarity, shared force): {len(pairs)}")
    for score, a, b in pairs:
        lines.append(f"  {score:>3}  {a.get('nickname') or a['title']}  <>  {b.get('nickname') or b['title']}")
    verify = snap["today"].get("verify")
    if verify:
        lines.append(f"verify pass     {verify['dropped']}/{verify['checked']} proposed attachments dropped")
    stats = {"date": date, "attach_rate": len(attached & set(picked)) / max(1, len(picked)), "threads": len(active),
             "events_per_thread": sum(len({event_of(e) for e in t["evidence"] if not e.get("added_on")}) for t in active) / max(1, len(active)),
             "status": dict(status), "pairs": len(pairs)}
    return stats, "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description="L2 pattern quality report (no LLM)")
    p.add_argument("--date")
    p.add_argument("--from", dest="start")
    p.add_argument("--until")
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    dates = sorted(f.stem for f in (DATA / "threads").glob("*.json"))
    if args.date:
        dates = [args.date]
    else:
        dates = [d for d in dates if (not args.start or d >= args.start) and (not args.until or d <= args.until)]
    text, summary = [], []
    for d in dates:
        stats, block = report(d, cfg)
        text.append(block)
        if stats:
            summary.append(stats)
    calls = Counter(c["thread_title"] for c in read_json(DATA / "calls.json", []))
    text.append("predictions per thread: " + (", ".join(f"{k} {v}" for k, v in calls.most_common()) or "none") + "\n")
    out = "\n".join(text)
    print(out)
    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
