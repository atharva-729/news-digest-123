"""Read the day's picks properly, within each publisher's rules, so they can be explained (not just named).

- Feed text: some feeds carry hundreds of words per item (Inc42, YourStory, Entrackr). Ingest keeps it here.
- Article pages: fetched only if the site's robots.txt allows our agent, everyone ("*"), *and* the agents
  of AI assistants that fetch pages for one user (ChatGPT-User, Claude-User, Perplexity-User). That is what
  this does, so a site that blocks those has said no to us too.
- Google News links point at a Google page, not the article; we never try to decode them.

Article text is cached in cache/ (git-ignored) and only ever goes to the model. Nothing from it is published;
the site shows our own explanation plus a link to the original.
"""
import logging
import re
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import httpx

from digest.common import DATA, ROOT, read_json, write_json

log = logging.getLogger(__name__)

CACHE = ROOT / "cache"
AGENT = "l1l2l3-digest"
USER_AGENT = f"Mozilla/5.0 (compatible; {AGENT}/0.3; personal news reader)"
AI_FETCHERS = ("ChatGPT-User", "Claude-User", "Perplexity-User")
_robots = {}


def words(text):
    return len((text or "").split())


def clip(text, limit):
    w = (text or "").split()
    return " ".join(w[:limit]) + (" …" if len(w) > limit else "")


def allowed(url):
    """True if robots.txt lets us, everyone, and user-triggered AI fetchers read this URL. Cached per host."""
    host = urlsplit(url).netloc.lower()
    if not host or host.endswith("news.google.com"):
        return False
    if host not in _robots:
        parser = urllib.robotparser.RobotFileParser()
        try:
            r = httpx.get(f"https://{host}/robots.txt", timeout=10, follow_redirects=True, headers={"User-Agent": USER_AGENT})
            if r.status_code in (401, 403):
                parser.disallow_all = True       # same reading as Python's robotparser: locked robots = keep out
            else:
                parser.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception as e:
            log.info("robots.txt for %s unreachable (%s); treating as not allowed", host, str(e)[:80])
            parser.disallow_all = True
        _robots[host] = parser
    p = _robots[host]
    return all(p.can_fetch(a, url) for a in (AGENT, "*", *AI_FETCHERS))


def fetch_page_text(url, timeout):
    """Main text of an article page, or "" if it can't be read. Uses trafilatura, which drops menus and ads."""
    import trafilatura
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        if r.status_code != 200 or "netskope" in r.text[:5000].lower():
            return ""
        return trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or ""
    except Exception as e:
        log.info("could not read %s: %s", url, str(e)[:80])
        return ""


def save_feed_text(date, texts):
    """Called by ingest: the fullest text each feed gave per item (git-ignored cache)."""
    write_json(CACHE / "feedtext" / f"{date}.json", texts)


def readable(item, feed_words):
    """Can we probably explain this item well? Used by select to prefer explainable stories."""
    return feed_words >= 80 or (not item["via_google_news"] and allowed(item["url"]))


def run(cfg, date):
    """Read every pick: feed text first, then the article page if the site allows it. Returns a summary."""
    rcfg = cfg.get("read", {})
    sel = read_json(DATA / "selected" / f"{date}.json")
    day = read_json(DATA / "items" / f"{date}.json")
    if not sel or not day:
        raise SystemExit(f"no selected items for {date}; run the select phase first")
    items = {it["id"]: it for it in day["items"]}
    feedtext = read_json(CACHE / "feedtext" / f"{date}.json", {})
    picks = [p["id"] for ps in sel["sections"].values() for p in ps]

    def read_one(i):
        it = items[i]
        best, via = feedtext.get(i) or it["summary"], "feed"
        reason = "google news link" if it["via_google_news"] else ""
        if words(best) < rcfg.get("enough_words", 250) and not it["via_google_news"]:
            if allowed(it["url"]):
                page = fetch_page_text(it["url"], rcfg.get("timeout_seconds", 15))
                if words(page) > words(best):
                    best, via = page, "page"
                elif not page:
                    reason = "page unreadable"
            else:
                reason = "publisher blocks AI readers"
        return i, clip(best, rcfg.get("max_words", 700)), via, reason

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(read_one, picks))
    texts, meta = {}, {}
    limit = rcfg.get("limited_below_words", 60)
    for i, text, via, reason in results:
        texts[i] = text
        meta[i] = {"words": words(text), "via": via if words(text) else "none", "limited": words(text) < limit,
                   "reason": reason if words(text) < limit else ""}
    write_json(CACHE / "articles" / f"{date}.json", texts)
    write_json(DATA / "read" / f"{date}.json", meta)  # metadata only; the text stays in cache/
    return meta


def load(date):
    """(texts, meta) for a date's picks; texts may be empty if the cache was cleared."""
    return read_json(CACHE / "articles" / f"{date}.json", {}), read_json(DATA / "read" / f"{date}.json", {})
