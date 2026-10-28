"""Phase 2: pick the day's L1 items per section, sized by the section mix. The model returns ids only."""
import json
import logging
import math
import re
from datetime import date as Date, timedelta

from rapidfuzz import fuzz

from digest import llm
from digest.common import DATA, PROMPTS, load_prompt, read_json, write_json

log = logging.getLogger(__name__)

PICKS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["id", "reason"],
    },
}
FUNDING_SCHEMA = {
    "type": "object",
    "properties": {
        "is_funding": {"type": "boolean"},
        "company": {"type": "string"},
        "amount": {"type": "string"},
        "sector": {"type": "string"},
        "country": {"type": "string"},
    },
    "required": ["is_funding", "company", "amount", "sector", "country"],
}


def budgets(mix, size):
    """Largest-remainder rounding, so the budgets always add up to `size`."""
    exact = {s: share * size for s, share in mix.items()}
    out = {s: math.floor(v) for s, v in exact.items()}
    leftover = size - sum(out.values())
    for s in sorted(exact, key=lambda s: exact[s] - out[s], reverse=True)[:leftover]:
        out[s] += 1
    return out


def schema_for(section):
    picks = json.loads(json.dumps(PICKS_SCHEMA))
    props = {"picks": picks}
    if section == "tech":
        picks["items"]["properties"]["funding"] = FUNDING_SCHEMA
        picks["items"]["required"].append("funding")
    if section == "markets":
        props["tech_finance_ids"] = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": props, "required": list(props)}


def build_prompt(cfg, section, n, candidates):
    rules_file = PROMPTS / f"select_{section}.md"
    lines = "\n".join(
        json.dumps({"id": c["id"], "source": c["source"], "title": c["title"], "summary": c["summary"][:250]},
                   ensure_ascii=False)
        for c in candidates
    )
    return (load_prompt("select")
            .replace("{{section}}", section)
            .replace("{{section_description}}", cfg["section_descriptions"][section])
            .replace("{{n}}", str(n))
            .replace("{{section_rules}}", rules_file.read_text(encoding="utf-8") if rules_file.exists() else "")
            .replace("{{candidates}}", lines))


RESERVES = 2  # extra ranked picks, so dropping a same-story duplicate doesn't leave the section short
COMMON_NAMES = {"India", "Indian", "The", "New", "How", "Why", "What", "After", "Amid", "Over", "Says", "With", "From",
                "For", "And", "Its", "Into", "Will", "First", "World", "Global", "Market", "Markets", "Stock", "Stocks",
                "Startup", "Startups", "Funding", "Raises", "Series", "Crore", "Billion", "Million", "Govt", "Government"}


def key_terms(title):
    """Amounts and percentages, and capitalised names: the parts two reports of one story share."""
    nums = set(re.findall(r"\d[\d.,]*\s?(?:%|cr\b|crore|lakh|bn|billion|mn|million|m\b|k\b)", title.lower()))
    names = set(re.findall(r"\b[A-Z][A-Za-z]{2,}\b", title)) - COMMON_NAMES
    return nums, names


def same_story(a, b):
    if fuzz.token_set_ratio(a.lower(), b.lower()) >= 70:
        return True
    (na, wa), (nb, wb) = key_terms(a), key_terms(b)
    return bool(na & nb) and bool(wa & wb)


def select_section(cfg, section, n, candidates):
    """One LLM call; returns (validated picks, raw model output)."""
    if not candidates or n == 0:
        return [], {}
    result = llm.generate_json(build_prompt(cfg, section, n + RESERVES, candidates), schema_for(section),
                               tag=f"select:{section}")
    valid = {c["id"] for c in candidates}
    titles = {c["id"]: c["title"] for c in candidates}
    picks, seen = [], set()
    for p in result.get("picks", []):
        if p["id"] not in valid or p["id"] in seen:
            log.warning("%s: dropping id the model returned that is not a candidate (or repeated): %s", section, p["id"])
            continue
        dup = next((q for q in picks if same_story(titles[q["id"]], titles[p["id"]])), None)
        if dup:
            log.info("%s: dropping same-story pick %r (dup of %r)", section, titles[p["id"]], titles[dup["id"]])
            continue
        seen.add(p["id"])
        pick = {"id": p["id"], "reason": p["reason"].strip()}
        funding = p.get("funding") or {}
        if funding.get("is_funding"):
            pick["funding"] = {k: funding.get(k, "").strip() for k in ("company", "amount", "sector", "country")}
            # Rupee amounts are only ever reported for Indian rounds; backstop for a model that leaves country blank.
            if not pick["funding"]["country"] and re.search(r"(₹|\bRs\.?\s|\bINR\b|\bcrore\b|\bCr\b)", pick["funding"]["amount"], re.I):
                pick["funding"]["country"] = "India"
        picks.append(pick)
    if len(picks) > n:
        picks = picks[:n]
    if len(picks) < n:
        log.warning("%s: model picked %d of %d", section, len(picks), n)
    return picks, result


def funding_split(funding):
    """Count India vs rest of world; a blank country (not stated in the item) is counted as unknown."""
    countries = [f["country"].strip().lower() for f in funding]
    india = sum(c in {"india", "in", "bharat"} for c in countries)
    unknown = countries.count("")
    return {"total": len(funding), "india": india, "world": len(funding) - india - unknown, "unknown": unknown}


def recently_picked(cfg, date, days=3):
    """Titles selected in the previous `days` editions, so a story re-reported the next day isn't picked again."""
    titles = []
    for n in range(1, days + 1):
        d = (Date.fromisoformat(date) - timedelta(days=n)).isoformat()
        sel, day = read_json(DATA / "selected" / f"{d}.json"), read_json(DATA / "items" / f"{d}.json")
        if sel and day:
            by_id = {it["id"]: it for it in day["items"]}
            titles += [by_id[p["id"]]["title"].lower() for picks in sel["sections"].values() for p in picks]
    return titles


def run(cfg, date):
    day = read_json(DATA / "items" / f"{date}.json")
    if not day:
        raise SystemExit(f"no ingested items for {date}; run the ingest phase first")
    items = {it["id"]: it for it in day["items"]}
    seen = recently_picked(cfg, date)
    threshold = cfg["ingest"]["dedupe_title_similarity"]
    fresh = [it for it in day["items"]
             if not any(fuzz.token_set_ratio(it["title"].lower(), t) >= threshold for t in seen)]
    if len(fresh) < len(day["items"]):
        log.info("skipping %d items already picked in recent editions", len(day["items"]) - len(fresh))
    by_section = {s: [it for it in fresh if it["section"] == s] for s in cfg["section_mix"]}
    sizes = budgets(cfg["section_mix"], cfg["edition_size"])

    # Markets runs first so misfiled tech finance can be moved into the tech candidates before tech runs.
    order = ["markets"] + [s for s in cfg["section_mix"] if s not in ("markets", "tech")] + ["tech"]
    sections, moved = {}, []
    for section in order:
        picks, raw = select_section(cfg, section, sizes[section], by_section[section])
        if section == "markets":
            moved = [i for i in dict.fromkeys(raw.get("tech_finance_ids", [])) if i in items and items[i]["section"] == "markets"]
            picks = [p for p in picks if p["id"] not in moved]
            by_section["tech"] += [items[i] for i in moved]
        sections[section] = picks

    funding = [p["funding"] for p in sections.get("tech", []) if "funding" in p]
    out = {
        "date": date,
        "budgets": sizes,
        # Keep the newsletter's section order, not the order the calls ran in.
        "sections": {s: sections[s] for s in cfg["section_mix"]},
        "moved_to_tech": moved,
        "funding": funding_split(funding),
    }
    if out["funding"]["india"] == 0 or out["funding"]["world"] == 0:
        log.warning("funding coverage is one-sided today: %s", out["funding"])
    write_json(DATA / "selected" / f"{date}.json", out)
    return out
