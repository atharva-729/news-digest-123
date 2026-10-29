"""Backfill past days so patterns have history: python -m digest.backfill --from 2026-10-06 --until 2026-10-26

Sources (no LLM): Google News searches restricted to one day at a time (headlines only, all sections), and
older pages of publisher feeds that support paging (Inc42, Entrackr, YourStory, TechCrunch, Ars Technica),
which carry summaries or full text. Then, per day in order: select (picks) and threads (patterns). Backfilled
days get no edition page: they only build pattern memory, which keeps the cost low.
"""
import argparse
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date as Date, datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import httpx

from digest import articles, select, threads
from digest.common import DATA, IST, load_config, write_json
from digest.ingest import USER_AGENT, dedupe, normalise

log = logging.getLogger(__name__)

PAGEABLE = {"TechCrunch", "Ars Technica", "Inc42", "Entrackr", "YourStory"}  # ?paged=N returns older entries
MAX_PAGES = 30
PER_SECTION = 50  # candidates per section per backfilled day


def ist_day(iso):
    return datetime.fromisoformat(iso).astimezone(IST).date().isoformat()


def get(url):
    for attempt in range(3):
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            return feedparser.parse(r.content).entries
        except Exception as e:
            log.info("fetch failed (%s), retrying: %s", str(e)[:60], url)
            time.sleep(2 + attempt * 3)
    return []


def google_news_day(cfg, section, feed, day):
    """One Google News search limited to one day (after:D before:D+1 returns D and D+1; we keep D)."""
    gn = cfg["google_news"]
    q = feed["gn"].replace("when:1d", "").strip()
    nxt = (Date.fromisoformat(day) + timedelta(days=1)).isoformat()
    url = (f"https://news.google.com/rss/search?q={quote_plus(f'{q} after:{day} before:{nxt}')}"
           f"&hl={gn['hl']}&gl={gn['gl']}&ceid={gn['ceid']}")
    out = [n for e in get(url) if (n := normalise(section, feed, e)) and ist_day(n["published_at"]) == day]
    return out


def paged_feed(section, feed, start):
    """Older pages of a publisher feed until we pass `start`."""
    out, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        sep = "&" if "?" in feed["url"] else "?"
        entries = get(f"{feed['url']}{sep}paged={page}")
        items = [n for e in entries if (n := normalise(section, feed, e)) and n["id"] not in seen]
        if not items:
            break
        seen.update(n["id"] for n in items)
        out += items
        if min(ist_day(n["published_at"]) for n in items) < start:
            break
    return out


def fetch(cfg, start, end):
    """All archive items for [start, end], grouped by IST day."""
    days = [(Date.fromisoformat(start) + timedelta(days=n)).isoformat()
            for n in range((Date.fromisoformat(end) - Date.fromisoformat(start)).days + 1)]
    jobs = [(s, f, d) for s, feeds in cfg["feeds"].items() for f in feeds if "gn" in f for d in days]
    with ThreadPoolExecutor(max_workers=4) as pool:  # gentle on Google News
        gn = [n for batch in pool.map(lambda j: google_news_day(cfg, *j), jobs) for n in batch]
    pages = [n for s, feeds in cfg["feeds"].items() for f in feeds if f["name"] in PAGEABLE
             for n in paged_feed(s, f, start)]
    by_day = {d: [] for d in days}
    for n in gn + pages:
        d = ist_day(n["published_at"])
        if d in by_day:
            by_day[d].append(n)
    return by_day


def save_day(cfg, day, raw):
    """Write data/items/DAY.json like ingest does (dedupe, per-feed cap, readable flag, feed text cache)."""
    icfg = cfg["ingest"]
    # At most 3 items per publisher per section, then the newest PER_SECTION per section, so selection sees
    # about as many candidates as on a normal day (and costs the same).
    items = dedupe(raw, icfg["dedupe_title_similarity"])
    per_source, per_section, kept = Counter(), Counter(), []
    for n in sorted(items, key=lambda n: (not n.get("_text"), n["published_at"]), reverse=False):
        per_source[(n["section"], n["source"])] += 1
        cap = 3 if n["via_google_news"] else cfg["ingest"]["max_items_per_feed"]  # publisher feeds carry text
        if per_source[(n["section"], n["source"])] <= cap and per_section[n["section"]] < PER_SECTION:
            per_section[n["section"]] += 1
            kept.append(n)
    items = kept
    texts = {it["id"]: it.pop("_text", "") for it in items}
    for it in items:
        it["feed_words"] = articles.words(texts[it["id"]])
        it["readable"] = it["feed_words"] >= 80
    articles.save_feed_text(day, {i: t for i, t in texts.items() if articles.words(t) >= 40})
    counts = Counter(it["section"] for it in items)
    write_json(DATA / "items" / f"{day}.json", {
        "date": day, "mode": "backfill", "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {s: counts.get(s, 0) for s in cfg["section_mix"]}, "raw_count": len(raw), "feeds": [],
        "items": items})
    return counts


def main():
    p = argparse.ArgumentParser(description="Backfill past days: fetch, select, threads (no edition pages)")
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--until", required=True)
    p.add_argument("--fetch-only", action="store_true", help="only fetch and save items; no LLM calls")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = load_config()
    by_day = fetch(cfg, args.start, args.until)
    for day, raw in by_day.items():
        counts = save_day(cfg, day, raw)
        print(f"{day}: {sum(counts.values())} items ({', '.join(f'{k} {v}' for k, v in counts.items())})")
    if args.fetch_only:
        return
    for day in by_day:
        sel = select.run(cfg, day)
        out = threads.run(cfg, day)
        t = out["today"]
        active = [x for x in out["threads"] if x["status"] != "dormant"]
        print(f"[{day}] picked {sum(len(v) for v in sel['sections'].values())}; patterns {len(active)}, "
              f"candidates {len(out['candidates'])}; attach {t['attach_rate']}; new {len(t['new_threads'])}, "
              f"promoted {len(t['promoted'])}, merges {len(t['merges'])}; verify dropped "
              f"{t['verify']['dropped']}/{t['verify']['checked']}")


if __name__ == "__main__":
    main()
