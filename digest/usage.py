"""Summarise data/llm_usage.jsonl: every model call, by step. Run: python -m digest.usage [--since YYYY-MM-DD]"""
import argparse
import json
import statistics
import sys

from digest.common import DATA


def main():
    p = argparse.ArgumentParser(description="LLM usage per pipeline step")
    p.add_argument("--since", default="", help="only calls on or after this date (YYYY-MM-DD)")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    path = DATA / "llm_usage.jsonl"
    rows = [json.loads(line) for line in open(path, encoding="utf-8")] if path.exists() else []
    rows = [r for r in rows if r["ts"][:10] >= args.since]
    if not rows:
        print("no calls logged")
        return
    groups = {}
    for r in rows:
        groups.setdefault((r["tag"].split(":")[0], r["model"]), []).append(r)
    med = lambda rs, k: statistics.median(r[k] or 0 for r in rs)
    print(f"{len(rows)} calls since {rows[0]['ts'][:10]}\n")
    print(f"{'step':<10} {'model':<14} {'calls':>5} {'in/call':>8} {'out/call':>8} {'reasoning':>9} {'sec':>5} {'$/call':>8} {'$ total':>8}")
    for (tag, model), rs in sorted(groups.items()):
        priced = all(r["usd"] is not None for r in rs)
        total = f"{sum(r['usd'] for r in rs):.4f}" if priced else "n/a"
        per = f"{med(rs, 'usd'):.4f}" if priced else "n/a"
        print(f"{tag:<10} {model:<14} {len(rs):>5} {med(rs, 'prompt_tokens'):>8.0f} {med(rs, 'completion_tokens'):>8.0f} "
              f"{med(rs, 'reasoning_tokens'):>9.0f} {med(rs, 'seconds'):>5.0f} {per:>8} {total:>8}")
    tin, tout = sum(r["prompt_tokens"] for r in rows), sum(r["completion_tokens"] for r in rows)
    print(f"\nall calls: {tin:,} tokens in, {tout:,} out. Unpriced models show n/a (add them to model.prices in config).")


if __name__ == "__main__":
    main()
