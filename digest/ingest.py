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

from digest import articles
from digest.common import DATA, IST, read_json, write_json

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
    # The fullest text the feed offers (some carry the whole article in <content>). Kept out of the
    # committed data: ingest moves it to the git-ignored cache for the read phase.
    full = max([clean_text(entry.get("summary", ""), 30000)]
               + [clean_text(c.get("value", ""), 30000) for c in entry.get("content", [])], key=len)
    if summary.startswith(title) or fuzz.partial_ratio(summary.lower(), title.lower()) > 90:
        summary = full = ""  # Google News "summaries" just repeat the headline
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
        "_text": full,
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


def collect(cfg, weekly, start, end, per_feed, per_day=False):
    """Fetch every feed and keep items published in [start, end), newest `per_feed` per feed (per feed and
    day if `per_day`, so a week-long window isn't all from the latest day). Never raises."""
    jobs = [(section, feed) for section, feeds in cfg["feeds"].items() for feed in feeds]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda j: fetch_feed(*j, cfg, weekly), jobs))

    raw, feed_stats = [], []
    for section, feed, entries, err in results:
        if err:
            log.warning("feed failed: %s (%s): %s", feed["name"], section, err)
        fresh = [n for e in entries
                 if (n := normalise(section, feed, e)) and start.isoformat() <= n["published_at"] < end.isoformat()]
        fresh.sort(key=lambda n: n["published_at"], reverse=True)
        if per_day:
            seen, kept = Counter(), []
            for n in fresh:
                seen[n["published_at"][:10]] += 1
                if seen[n["published_at"][:10]] <= per_feed:
                    kept.append(n)
            fresh = kept
        else:
            fresh = fresh[:per_feed]
        feed_stats.append({"section": section, "feed": feed["name"], "entries": len(entries),
                           "fresh": len(fresh), "error": err})
        raw.extend(fresh)
    return raw, feed_stats


def run(cfg, date, weekly=False):
    icfg = cfg["ingest"]
    window = timedelta(days=icfg["weekly_window_days"]) if weekly else timedelta(hours=icfg["daily_window_hours"])
    now = datetime.now(timezone.utc)
    raw, feed_stats = collect(cfg, weekly, now - window, now + timedelta(hours=1), icfg["max_items_per_feed"])

    items = dedupe(raw, icfg["dedupe_title_similarity"])
    texts = {it["id"]: it.pop("_text", "") for it in items}
    # Check each publisher's rules once (in parallel), then mark which items we can explain properly.
    by_host = {urlsplit(it["url"]).netloc: it["url"] for it in items if not it["via_google_news"]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(articles.allowed, by_host.values()))
    for it in items:
        it["feed_words"] = articles.words(texts[it["id"]])
        it["readable"] = articles.readable(it, it["feed_words"])
    articles.save_feed_text(date, {i: t for i, t in texts.items() if articles.words(t) >= 40})
    counts = Counter(it["section"] for it in items)
    out = {
        "date": date,
        "mode": "weekly" if weekly else "daily",
        "generated_at": now.isoformat(),
        "counts": {s: counts.get(s, 0) for s in cfg["section_mix"]},
        "raw_count": len(raw),
        "feeds": feed_stats,
        "items": items,
    }
    write_json(DATA / "items" / f"{date}.json", out)
    if not weekly:
        run_lookback(cfg, date, {it["id"] for it in items})
    return out


def run_lookback(cfg, date, today_ids):
    """Last week's headlines, so today's news can be connected to what came before.

    Two sources: a 7-day fetch (Google News searches honour when:7d; publisher feeds give what they still
    carry) and our own saved items from earlier days, which are exact. Saved to data/context/DATE.json.
    """
    icfg = cfg["ingest"]
    days = icfg.get("lookback_days", 7)
    end = datetime.fromisoformat(date).replace(tzinfo=IST) - timedelta(hours=6)  # editions run ~06:00 IST
    start = end - timedelta(days=days)
    raw, _ = collect(cfg, True, start, end, icfg.get("lookback_items_per_feed_day", 4), per_day=True)
    for it in raw:
        it.pop("_text", None)  # last week's items are titles only
    for n in range(1, days + 1):
        d = (datetime.fromisoformat(date) - timedelta(days=n)).date().isoformat()
        raw += (read_json(DATA / "items" / f"{d}.json") or {}).get("items", [])
    items = [it for it in dedupe(raw, icfg["dedupe_title_similarity"])
             if it["id"] not in today_ids and it["published_at"] < end.isoformat()]
    # Take from each day in turn (newest first within a day) so one busy day can't crowd out the week.
    by_day = {}
    for it in sorted(items, key=lambda it: it["published_at"], reverse=True):
        by_day.setdefault(datetime.fromisoformat(it["published_at"]).astimezone(IST).date(), []).append(it)
    cap, items = icfg.get("lookback_max_items", 300), []
    while len(items) < cap and any(by_day.values()):
        for day in sorted(by_day, reverse=True):
            if by_day[day] and len(items) < cap:
                items.append(by_day[day].pop(0))
    items.sort(key=lambda it: it["published_at"], reverse=True)
    write_json(DATA / "context" / f"{date}.json", {"date": date, "from": start.isoformat(), "items": items})
    log.info("lookback: %d items from the previous %d days", len(items), days)
    return items
