"""Entry point: `python run.py daily` / `python run.py weekly`."""
import argparse
import logging
import sys
from collections import Counter

from digest import articles, connect, deliver, ingest, select, threads, weekly as weekly_edition, write
from digest.common import load_config, today_ist

PHASES = ["ingest", "select", "read", "threads", "connect", "write", "deliver"]
WEEKLY_PHASES = ["write", "deliver"]  # the weekly is built from saved thread state; no new headlines


def main():
    p = argparse.ArgumentParser(description="L1-L2-L3 news digest")
    p.add_argument("mode", choices=["daily", "weekly"])
    p.add_argument("--date", default=today_ist(), help="edition date YYYY-MM-DD (default: today in IST)")
    p.add_argument("--until", choices=PHASES, help="stop after this phase")
    p.add_argument("--from", dest="start", choices=PHASES,
                   help="start at this phase, reusing saved data from earlier ones")
    p.add_argument("--no-send", action="store_true", help="dry run: build everything but don't email")
    p.add_argument("--push", action="store_true",
                   help="after the run, commit data/ and docs/ and git push (updates the GitHub Pages site)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    weekly = args.mode == "weekly"
    phases = WEEKLY_PHASES if weekly else PHASES
    start, until = args.start or phases[0], args.until or phases[-1]
    if start not in phases or until not in phases:
        p.error(f"{args.mode} phases are: {', '.join(phases)}")
    todo = phases[phases.index(start): phases.index(until) + 1]

    if weekly and "write" in todo:
        out = weekly_edition.run(cfg, args.date)
        print(f"[weekly] {out['moved']} threads moved, {out['born']} born, {out['died']} went quiet, "
              f"{out['calls_reviewed']} calls reviewed")
        print(f"  {out['path']}")

    if "ingest" in todo:
        out = ingest.run(cfg, args.date, weekly)
        failed = [f["feed"] for f in out["feeds"] if f["error"]]
        print(f"[ingest] {len(out['items'])} items after dedupe ({out['raw_count']} before)")
        for section, n in out["counts"].items():
            print(f"  {section:<15} {n}")
        if failed:
            print(f"  feeds failed: {', '.join(failed)}")

    if "select" in todo:
        out = select.run(cfg, args.date)
        print(f"[select] {sum(len(v) for v in out['sections'].values())} items selected")
        for section, picks in out["sections"].items():
            print(f"  {section:<15} {len(picks)}/{out['budgets'][section]}")
        if out["moved_to_tech"]:
            print(f"  moved markets -> tech: {len(out['moved_to_tech'])}")
        f = out["funding"]
        print(f"  funding items: {f['total']} (India {f['india']}, world {f['world']}, country unknown {f['unknown']})")

    if "read" in todo:
        meta = articles.run(cfg, args.date)
        via = Counter(m["via"] for m in meta.values())
        limited = [m["reason"] or "short" for m in meta.values() if m["limited"]]
        print(f"[read] {len(meta)} stories: {via.get('page', 0)} from the article page, {via.get('feed', 0)} from the feed, "
              f"{len(limited)} limited")
        for reason, n in Counter(limited).items():
            print(f"  limited ({reason}): {n}")

    if "threads" in todo:
        out = threads.run(cfg, args.date)
        t = out["today"]
        active = [x for x in out["threads"] if x["status"] != "dormant"]
        print(f"[threads] {len(active)} active threads, {len(out['candidates'])} candidates")
        print(f"  attached {len(t['attached'])}, new {len(t['new_threads'])}, promoted {len(t['promoted'])}, "
              f"new candidates {len(t['new_candidates'])}, merges {len(t['merges'])}")
        print(f"  teaching cards written: {t.get('taught', 0)}")
        print(f"  cross-link: {'yes' if t['cross_link'] else 'none'}")

    if "connect" in todo:
        out = connect.run(cfg, args.date)
        print(f"[connect] {len(out['throwbacks'])} throwbacks to last week, {len(out['backstory'])} backstory clues added")

    if "write" in todo and not weekly:
        out = write.run(cfg, args.date)
        print(f"[write] {out['takes']}/{out['items']} cards ({out['limited']} limited), {out['moves']} pattern moves, "
              f"{out['remember']} remember questions, ~{out['minutes']} min read")
        print(f"  call: {out['call']['prediction'] if out['call'] else 'none'}")
        print(f"  {out['path']}")

    if "deliver" in todo:
        out = deliver.run(cfg, args.date, weekly, args.no_send)
        print(f"[deliver] email {out['email']}; archive has {out['editions']} editions")

    if args.push:
        print(f"[push] {deliver.push(args.date, weekly)}")


if __name__ == "__main__":
    main()
