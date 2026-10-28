"""Phase 1: fetch RSS feeds, normalise, filter by time, dedupe. Deterministic, no LLM."""
import calendar
import hashlib
import html
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from rapidfuzz import fuzz

from digest.common import DATA, write_json

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; l1l2l3-digest/0.1; personal RSS reader)"
TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "cmpid", "ref", "ito", "src")


def canonical_url(url):
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(TRACKING_PARAMS)]
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(query), ""))


def item_id(url):
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:10]


def clean_text(s, limit=400):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"


def feed_url(feed, cfg, weekly):
    if "url" in feed:
        return feed["url"]
    q = feed["gn"].replace("when:1d", "when:7d") if weekly else feed["gn"]
    gn = cfg["google_news"]
    return f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={gn['hl']}&gl={gn['gl']}&ceid={gn['ceid']}"


def fetch_feed(section, feed, cfg, weekly):
    """Return (section, feed name, entries, error). Never raises: one dead feed must not stop the run."""
    url = feed_url(feed, cfg, weekly)
    try:
        r = httpx.get(url, timeout=cfg["ingest"]["timeout_seconds"], follow_redirects=True,
                      headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"unparseable feed: {parsed.bozo_exception}")
        return section, feed, parsed.entries, None
    except Exception as e:
        return section, feed, [], str(e)[:200]


def normalise(section, feed, entry):
    link = entry.get("link")
    when = entry.get("published_parsed") or entry.get("updated_parsed")
    if not link or not entry.get("title") or not when:
        return None
    title = clean_text(entry["title"], 300)
    source = feed["name"]
    is_gn = "gn" in feed
    if is_gn:
        # Google News titles look like "Headline - Publisher"; the publisher is also in <source>.
        source = (entry.get("source") or {}).get("title") or title.rsplit(" - ", 1)[-1]
        if title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
    summary = clean_text(entry.get("summary", ""))
    if summary.startswith(title) or fuzz.partial_ratio(summary.lower(), title.lower()) > 90:
        summary = ""  # Google News "summaries" just repeat the headline
    return {
        "id": item_id(link),
        "section": section,
        "title": title,
        "summary": summary,
        "url": link,
        "source": source,
        "published_at": datetime.fromtimestamp(calendar.timegm(when), timezone.utc).isoformat(),
        "via_google_news": is_gn,
        "also_covered_by": [],
    }


def dedupe(items, threshold):
    # Prefer publisher feeds over Google News redirects, then the earliest report.
    items = sorted(items, key=lambda it: (it["via_google_news"], it["published_at"]))
    kept, by_url = [], {}
    for it in items:
        key = canonical_url(it["url"])
        if key in by_url:
            continue
        match = next((k for k in kept if fuzz.token_set_ratio(k["title"].lower(), it["title"].lower()) >= threshold), None)
        if match:
            if it["source"] != match["source"] and it["source"] not in match["also_covered_by"]:
                match["also_covered_by"].append(it["source"])
            continue
        by_url[key] = it
        kept.append(it)
    return kept


def run(cfg, date, weekly=False):
    icfg = cfg["ingest"]
    window = timedelta(days=icfg["weekly_window_days"]) if weekly else timedelta(hours=icfg["daily_window_hours"])
    cutoff = datetime.now(timezone.utc) - window

    jobs = [(section, feed) for section, feeds in cfg["feeds"].items() for feed in feeds]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda j: fetch_feed(*j, cfg, weekly), jobs))

    raw, feed_stats = [], []
    for section, feed, entries, err in results:
        if err:
            log.warning("feed failed: %s (%s): %s", feed["name"], section, err)
        fresh = [n for e in entries if (n := normalise(section, feed, e)) and n["published_at"] >= cutoff.isoformat()]
        fresh.sort(key=lambda n: n["published_at"], reverse=True)
        fresh = fresh[: icfg["max_items_per_feed"]]
        feed_stats.append({"section": section, "feed": feed["name"], "entries": len(entries),
                           "fresh": len(fresh), "error": err})
        raw.extend(fresh)

    items = dedupe(raw, icfg["dedupe_title_similarity"])
    counts = Counter(it["section"] for it in items)
    out = {
        "date": date,
        "mode": "weekly" if weekly else "daily",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {s: counts.get(s, 0) for s in cfg["section_mix"]},
        "raw_count": len(raw),
        "feeds": feed_stats,
        "items": items,
    }
    write_json(DATA / "items" / f"{date}.json", out)
    return out
