"""Phase 3: attach the day's L1 items to L2 threads, each driven by fixed L3 forces.

State is snapshotted per day in data/threads/DATE.json (built on the latest earlier snapshot), so rerunning
a day replaces that day instead of adding its evidence twice. data/threads.json is a copy of the latest one.

The model proposes; code enforces every rule:
- every story gets an event key; a pattern needs evidence from >= min_events_for_new_thread *different* events
- only `direct` evidence is kept, and a cheap verify pass can still drop it (keep/drop only)
- at most max_new_evidence_per_day new clues per thread per day
- forces are fixed, ids must exist, threads are never deleted (merged_into / split_into / parked_on)
- status comes from distinct events per week compared with the thread's own history (see compute_status)
"""
import copy
import json
import logging
import re
from datetime import date as Date, timedelta

from digest import llm
from digest.articles import CACHE
from digest.common import DATA, load_prompt, read_json, write_json
from digest.quality import overlap_pairs

log = logging.getLogger(__name__)

SNAPSHOTS = DATA / "threads"

THREAD_FIELDS = {
    "key": {"type": "string"}, "title": {"type": "string"}, "nickname": {"type": "string"},
    "plain": {"type": "string"}, "claim": {"type": "string"}, "forces": {"type": "array", "items": {"type": "string"}},
}
SCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {"type": "array", "items": {"type": "object", "properties": {
            "item_id": {"type": "string"}, "event": {"type": "string"},
            "action": {"type": "string", "enum": ["attach", "new", "none"]},
            "thread_id": {"type": "string"}, "mechanism": {"type": "string"},
            "strength": {"type": "string", "enum": ["direct", "indirect"]}}}},
        "new_threads": {"type": "array", "items": {"type": "object", "properties": THREAD_FIELDS}},
        "overlaps": {"type": "array", "items": {"type": "object", "properties": {
            "thread_a": {"type": "string"}, "thread_b": {"type": "string"},
            "decision": {"type": "string", "enum": ["merge", "distinct"]},
            "keep": {"type": "string"}, "absorb": {"type": "string"}, "difference": {"type": "string"}}}},
        "candidate_merges": {"type": "array", "items": {"type": "object", "properties": {
            "keep": {"type": "string"}, "absorb": {"type": "string"}, "reason": {"type": "string"}}}},
        "splits": {"type": "array", "items": {"type": "object", "properties": {
            "thread_id": {"type": "string"},
            "into": {"type": "array", "items": {"type": "object", "properties": {
                **THREAD_FIELDS, "events": {"type": "array", "items": {"type": "string"}}}}}}}},
        "cross_link": {"type": "object", "properties": {
            "thread_a": {"type": "string"}, "thread_b": {"type": "string"},
            "force": {"type": "string"}, "sentence": {"type": "string"}}},
    },
}
VERIFY_SCHEMA = {"type": "object", "properties": {"checks": {"type": "array", "items": {"type": "object", "properties": {
    "n": {"type": "integer"}, "keep": {"type": "boolean"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]}, "reason": {"type": "string"}}}}}}
CONFIDENCE = {"high": 3, "medium": 2, "low": 1}

# Claims that only say something exists or keeps going are not directional.
VAGUE = re.compile(r"\b(is|are) (growing|rising|increasing|changing|evolving|important|booming)$"
                   r"|\b(continues?|persists?|remains?|matters?)$", re.I)


def slug(s):
    s = re.sub(r"^[tc]_", "", s.lower())  # the model sometimes prefixes its keys like our ids
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "thread"


def event_slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60]


# Steady states, not shifts: "VCs are funding Indian AI startups". (A whitelist of direction words proved
# too brittle: it rejected good claims like "Hyperscalers are locking in nuclear power for AI data centres".)
STATIC = re.compile(r"\b(is|are)\s+(funding|investing in|backing|raising|announcing|launching|publishing)\b"
                    r"(?!\s+(more|less|fewer|bigger|smaller|faster)\b)", re.I)


def claim_ok(claim):
    """Specific enough: 7-25 words, not a 'X is growing' / 'X continues' / 'X is funding Y' steady state, and one
    shift rather than a list of them. Bracketed tags like "(rising)" are ignored."""
    claim = re.sub(r"\([^)]*\)", "", claim).strip(" .")
    bundled = claim.count(",") >= 2 or bool(re.search(r",[^,]+\band\b", claim))  # "A, B and C": several shifts
    generic = re.search(r"\b(broader|broad|various|overall|general)\b", claim, re.I)
    return (7 <= len(claim.split()) <= 25 and not VAGUE.search(claim) and not STATIC.search(claim)
            and not bundled and not generic)


def days_between(a, b):
    return (Date.fromisoformat(b) - Date.fromisoformat(a)).days


def event_of(e):
    """Evidence's event key; older evidence without one counts each distinct title as its own event."""
    return e.get("event") or f"title:{e['title'].lower()}"


def own_evidence(t):
    """Evidence from our own editions. Backstory added from last week's headlines (data/context) is shown to
    readers but doesn't count towards status or the events rule: that would be faking history."""
    return [e for e in t["evidence"] if not e.get("added_on")]


def distinct_events(t, start=None, end=None):
    return {event_of(e) for e in own_evidence(t) if (not start or e["date"] >= start) and (not end or e["date"] <= end)}


def compute_status(t, date, tcfg):
    """new (< 7 days old) -> building (< min_history_days) -> heating / cooling / active by events this week
    against the thread's own average week. Counts distinct events, not articles."""
    if t.get("merged_into") or t.get("split_into"):
        return "dormant"
    if days_between(t["last_seen"], date) >= tcfg["dormant_after_days"]:
        return "dormant"
    if t.get("parked_on") and t["last_seen"] <= t["parked_on"]:
        return "dormant"
    age = days_between(t["created"], date)
    if age < 7:
        return "new"
    if age < tcfg.get("min_history_days", 14):
        return "building"
    week_start = (Date.fromisoformat(date) - timedelta(days=6)).isoformat()
    before = (Date.fromisoformat(week_start) - timedelta(days=1)).isoformat()
    this_week = len(distinct_events(t, start=week_start, end=date))
    earlier = len(distinct_events(t, end=before))
    avg = earlier / max(1, (age - 7) / 7)
    if avg == 0:
        return "heating" if this_week >= 2 else "active"
    if this_week >= 2 and this_week >= tcfg.get("heating_ratio", 1.5) * avg:
        return "heating"
    if this_week <= tcfg.get("cooling_ratio", 0.5) * avg:
        return "cooling"
    return "active"


def previous_state(date):
    """The latest snapshot strictly before `date`, or an empty state."""
    earlier = sorted(p for p in SNAPSHOTS.glob("*.json") if p.stem < date) if SNAPSHOTS.exists() else []
    if not earlier:
        return {"threads": [], "candidates": []}
    snap = read_json(earlier[-1])
    return {"threads": snap["threads"], "candidates": snap["candidates"]}


def selected_items(date):
    sel = read_json(DATA / "selected" / f"{date}.json")
    day = read_json(DATA / "items" / f"{date}.json")
    if not sel or not day:
        raise SystemExit(f"no selected items for {date}; run the select phase first")
    by_id = {it["id"]: it for it in day["items"]}
    out = {}
    for section, picks in sel["sections"].items():
        for p in picks:
            out[p["id"]] = {**by_id[p["id"]], "section": section, "reason": p["reason"]}
    return out


def recent_events(date, days=7):
    """Event keys seen in the last `days` editions, with one example title each, so the model reuses them."""
    out = {}
    for n in range(days, 0, -1):
        d = (Date.fromisoformat(date) - timedelta(days=n)).isoformat()
        snap, day = read_json(SNAPSHOTS / f"{d}.json"), read_json(DATA / "items" / f"{d}.json")
        if not snap or not day:
            continue
        titles = {it["id"]: it["title"] for it in day["items"]}
        for item_id, ev in snap["today"].get("events", {}).items():
            out.setdefault(ev, titles.get(item_id, ""))
    return out


def split_candidates(threads, date, tcfg):
    start = (Date.fromisoformat(date) - timedelta(days=13)).isoformat()
    return [t for t in threads if t["status"] != "dormant"
            and len(distinct_events(t, start=start)) >= tcfg.get("split_min_events", 10)]


def build_prompt(cfg, date, items, threads, candidates):
    tcfg = cfg["threads"]
    active = [t for t in threads if t["status"] != "dormant"]
    over = len(active) >= tcfg["max_active_threads"]
    lines = lambda rows: "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) or "(none)"
    thread_rows = [{"id": t["id"], "name": t.get("nickname") or t["title"], "claim": t["claim"], "forces": t["forces"],
                    "sections": t["sections"], "events": sorted({event_of(e) for e in own_evidence(t)})[-8:],
                    "recent_clues": [e.get("mechanism") or e["note"] for e in own_evidence(t)[-3:]]} for t in active]
    cand_rows = [{"id": c["id"], "claim": c["claim"], "forces": c["forces"],
                  "events": sorted({event_of(e) for e in c["evidence"]}),
                  "clues": [e.get("mechanism") or e["note"] for e in c["evidence"]]} for c in candidates]
    pairs = overlap_pairs(active, tcfg.get("overlap_similarity", 48))
    overlap_rows = [{"thread_a": a["id"], "claim_a": a["claim"], "thread_b": b["id"], "claim_b": b["claim"]}
                    for _, a, b in pairs]
    split_rows = [{"thread_id": t["id"], "claim": t["claim"],
                   "events": {event_of(e): e["title"] for e in own_evidence(t)}} for t in split_candidates(threads, date, tcfg)]
    event_rows = [{"event": k, "example": v} for k, v in recent_events(date).items()]
    item_rows = [{"id": i, "section": it["section"], "source": it["source"], "title": it["title"],
                  "summary": it["summary"][:250], "why": it["reason"]} for i, it in items.items()]
    prompt = (load_prompt("threads")
              .replace("{{forces}}", ", ".join(tcfg["forces"]))
              .replace("{{date}}", date)
              .replace("{{min_events}}", str(tcfg["min_events_for_new_thread"]))
              .replace("{{active_count}}", str(len(active)))
              .replace("{{max_active}}", str(tcfg["max_active_threads"]))
              .replace("{{merge_instruction}}",
                       "We are at or over the cap: merge at least one pair." if over else "Merge only true overlaps.")
              .replace("{{threads}}", lines(thread_rows))
              .replace("{{candidates}}", lines(cand_rows))
              .replace("{{overlaps}}", lines(overlap_rows))
              .replace("{{splits}}", lines(split_rows))
              .replace("{{events}}", lines(event_rows))
              .replace("{{items}}", lines(item_rows)))
    return prompt, [(a["id"], b["id"]) for _, a, b in pairs], {r["thread_id"] for r in split_rows}


def evidence(date, item, mechanism, event):
    return {"date": date, "item_id": item["id"], "section": item["section"], "title": item["title"],
            "url": item["url"], "source": item["source"], "note": mechanism, "mechanism": mechanism, "event": event}


def verify(cfg, date, proposals, items):
    """One cheap keep/drop pass over every proposed attachment. Returns {n: (keep, confidence)}."""
    if not proposals:
        return {}
    texts = read_json(CACHE / "articles" / f"{date}.json", {})
    checks = [{"n": n, "headline": items[p["item_id"]]["title"],
               "text": " ".join((texts.get(p["item_id"]) or items[p["item_id"]]["summary"]).split()[:120]),
               "claim": p["claim"], "mechanism": p["mechanism"]} for n, p in enumerate(proposals)]
    out = llm.generate_json(load_prompt("threads_verify").replace("{{checks}}", "\n".join(json.dumps(c, ensure_ascii=False) for c in checks)),
                            VERIFY_SCHEMA, tag="threads:verify", **cfg["threads"].get("verify_params", {}))
    verdicts = {c["n"]: (c["keep"], c["confidence"]) for c in out["checks"] if 0 <= c["n"] < len(proposals)}
    for n, p in enumerate(proposals):
        if not verdicts.get(n, (False, ""))[0]:
            log.info("verify dropped %s -> %s: %s", p["item_id"], p["target"], p["mechanism"])
    return verdicts


def new_thread(tid, d, date, ev, created=None):
    return {"id": tid, "title": d["title"].strip(), "nickname": d["nickname"].strip() or d["title"].strip(),
            "plain": d["plain"].strip(), "claim": d["claim"].strip(), "forces": d["forces"],
            "created": created or date, "evidence": ev, "last_seen": max(e["date"] for e in ev)}


def apply(cfg, date, items, state, result, pairs, split_ids):
    """Apply the model's proposal to `state` under the code-enforced rules. Returns the day's change log."""
    tcfg = cfg["threads"]
    forces = set(tcfg["forces"])
    min_events = tcfg["min_events_for_new_thread"]
    threads = {t["id"]: t for t in state["threads"]}
    cands = {c["id"]: c for c in state["candidates"]}
    prev_status = {t["id"]: t["status"] for t in threads.values()}
    today = {"attached": [], "new_threads": [], "new_candidates": [], "promoted": [], "merges": [], "distinct": [],
             "splits": [], "cross_link": None, "events": {}}

    def valid_def(d):
        fs = [f.strip().lower() for f in d["forces"] if f.strip().lower() in forces]
        if not fs or not claim_ok(d["claim"]):
            log.warning("rejecting thread definition %r: forces %s, claim %r", d.get("key"), d["forces"], d["claim"])
            return None
        return {**d, "forces": fs}

    defs = {d["key"]: v for d in result["new_threads"] if (v := valid_def(d))}

    # 1. Every story gets an event key; collect direct attachment proposals.
    proposals, seen, indirect = [], set(), 0
    for a in result["assignments"]:
        i = a["item_id"]
        if i not in items or i in seen:
            continue
        seen.add(i)
        today["events"][i] = event_slug(a["event"]) or f"item-{i}"
        if a["action"] == "none" or not a["mechanism"].strip():
            continue
        if a["strength"] != "direct":
            indirect += 1
            log.info("dropping indirect link %s -> %s", i, a["thread_id"])
            continue
        tid = a["thread_id"].strip()
        if tid not in defs and tid not in threads and tid not in cands and tid[2:] in defs and tid[:2] in ("t_", "c_"):
            tid = tid[2:]  # the model sometimes writes a new thread's key with our "t_" id prefix
        kind = "new" if tid in defs else "thread" if tid in threads and not threads[tid].get("merged_into") \
            else "candidate" if tid in cands else None
        if not kind:
            log.warning("dropping %s of %s to undefined thread %r", a["action"], i, tid)
            continue
        claim = (defs.get(tid) or threads.get(tid) or cands.get(tid))["claim"]
        proposals.append({"item_id": i, "target": tid, "kind": kind, "claim": claim, "mechanism": a["mechanism"].strip()})

    # 2. Verify (keep/drop), then cap each thread's new clues per day, keeping the most confident.
    verdicts = verify(cfg, date, proposals, items)
    kept = [dict(p, conf=CONFIDENCE.get(verdicts[n][1], 1)) for n, p in enumerate(proposals) if verdicts.get(n, (False,))[0]]
    by_target = {}
    for p in sorted(kept, key=lambda p: -p["conf"]):
        by_target.setdefault(p["target"], []).append(p)
    cap = tcfg.get("max_new_evidence_per_day", 4)
    capped = [p for ps in by_target.values() for p in ps[:cap]]
    today["verify"] = {"checked": len(proposals), "dropped": len(proposals) - len(kept),
                       "indirect": indirect, "capped": len(kept) - len(capped)}
    if proposals:
        llm.log_note("threads:verify", edition=date, **today["verify"],
                     drop_rate=round(today["verify"]["dropped"] / len(proposals), 2))

    new_items = {}
    for p in capped:
        ev = evidence(date, items[p["item_id"]], p["mechanism"], today["events"][p["item_id"]])
        if p["kind"] == "thread":
            threads[p["target"]]["evidence"].append(ev)
            threads[p["target"]]["last_seen"] = date
            today["attached"].append({"item_id": p["item_id"], "thread_id": p["target"], "note": p["mechanism"]})
        elif p["kind"] == "candidate":
            cands[p["target"]]["evidence"].append(ev)
        else:
            new_items.setdefault(p["target"], []).append(ev)

    # 3. New threads need >= min_events distinct events; otherwise they wait as candidates.
    key_to_id = {}
    for key, ev in new_items.items():
        d = defs[key]
        if len({e["event"] for e in ev}) >= min_events:
            tid = unique_id("t_" + slug(key), threads)
            threads[tid] = new_thread(tid, d, date, ev)
            today["new_threads"].append(tid)
            today["attached"] += [{"item_id": e["item_id"], "thread_id": tid, "note": e["note"]} for e in ev]
            key_to_id[key] = tid
        else:
            cid = unique_id("c_" + slug(key), cands)
            cands[cid] = {"id": cid, **{k: v for k, v in new_thread(cid, d, date, ev).items() if k not in ("id", "last_seen")}}
            today["new_candidates"].append(cid)

    # Candidates that describe the same shift in different words: combine them, so two separate events can
    # make a pattern. Only existing candidates, with a stated reason.
    for m in result["candidate_merges"]:
        keep, absorb = cands.get(m["keep"]), cands.get(m["absorb"])
        if not keep or not absorb or keep is absorb or not m["reason"].strip():
            continue
        keep["evidence"] = sorted(keep["evidence"] + absorb["evidence"], key=lambda e: e["date"])
        keep["forces"] = list(dict.fromkeys(keep["forces"] + absorb["forces"]))
        keep["created"] = min(keep["created"], absorb["created"])
        del cands[absorb["id"]]
        today["merges"].append({"keep": keep["id"], "absorb": absorb["id"], "reason": m["reason"].strip(), "candidates": True})

    for cid, c in list(cands.items()):
        if len({event_of(e) for e in c["evidence"]}) >= min_events:
            tid = unique_id("t_" + cid.removeprefix("c_"), threads)
            threads[tid] = {"id": tid, **{k: v for k, v in c.items() if k != "id"},
                            "last_seen": max(e["date"] for e in c["evidence"])}
            today["promoted"].append(tid)
            today["attached"] += [{"item_id": e["item_id"], "thread_id": tid, "note": e["note"]}
                                  for e in c["evidence"] if e["date"] == date]
            del cands[cid]
        elif days_between(c["created"], date) >= tcfg["dormant_after_days"]:
            del cands[cid]  # candidates are not threads yet; letting them lapse is not deleting a thread

    # 4. Look-alike pairs: merge, or record the difference. Only pairs we offered can be merged.
    offered = {frozenset(p) for p in pairs}
    for o in result["overlaps"]:
        pair = frozenset((o["thread_a"], o["thread_b"]))
        if pair not in offered:
            continue
        if o["decision"] == "distinct":
            today["distinct"].append({"pair": sorted(pair), "difference": o["difference"].strip()})
            continue
        keep, absorb = threads.get(o["keep"]), threads.get(o["absorb"])
        if not keep or not absorb or keep is absorb or {keep["id"], absorb["id"]} != set(pair):
            log.warning("dropping invalid merge %s <- %s", o["keep"], o["absorb"])
            continue
        keep["evidence"] = sorted(keep["evidence"] + absorb["evidence"], key=lambda e: e["date"])
        keep["forces"] = list(dict.fromkeys(keep["forces"] + absorb["forces"]))
        keep["last_seen"] = max(keep["last_seen"], absorb["last_seen"])
        keep["created"] = min(keep["created"], absorb["created"])
        keep.pop("teach", None)  # merged meaning: write a fresh teaching card
        absorb["merged_into"] = keep["id"]
        today["merges"].append({"keep": keep["id"], "absorb": absorb["id"], "reason": o["difference"].strip()})

    # 5. Splits: two narrower threads take the evidence of their events; the old one points to them.
    for s in result["splits"]:
        old = threads.get(s["thread_id"])
        if not old or s["thread_id"] not in split_ids or len(s["into"]) != 2 or old.get("merged_into"):
            continue
        parts = []
        for d in s["into"]:
            v, evs = valid_def(d), {event_slug(e) for e in d["events"]} | set(d["events"])
            ev = [e for e in old["evidence"] if event_of(e) in evs]
            if v and len({event_of(e) for e in ev}) >= min_events:
                parts.append((v, ev))
        if len(parts) != 2:
            log.warning("dropping split of %s: parts not valid", old["id"])
            continue
        ids = []
        for d, ev in parts:
            tid = unique_id("t_" + slug(d["key"]), threads)
            threads[tid] = new_thread(tid, d, date, sorted(ev, key=lambda e: e["date"]), created=min(e["date"] for e in ev))
            ids.append(tid)
        old["split_into"] = ids
        today["splits"].append({"from": old["id"], "into": ids})

    for t in threads.values():
        t["sections"] = list(dict.fromkeys(e["section"] for e in t["evidence"]))
        t["distinct_events"] = len(distinct_events(t))
        t["status"] = compute_status(t, date, tcfg)

    # Over the cap after merges: park the stalest threads. They wake up when new evidence arrives.
    active = sorted((t for t in threads.values() if t["status"] != "dormant"),
                    key=lambda t: (t["last_seen"], len(t["evidence"])))
    for t in active[: max(0, len(active) - tcfg["max_active_threads"])]:
        t["parked_on"], t["status"] = date, "dormant"
        log.warning("over max_active_threads: parked %s", t["id"])

    today["cross_link"] = check_link(result.get("cross_link") or {}, threads, key_to_id, forces)
    today["status_changes"] = {tid: [prev_status.get(tid), t["status"]] for tid, t in threads.items()
                               if prev_status.get(tid) != t["status"]}
    today["attach_rate"] = round(len({a["item_id"] for a in today["attached"]}) / max(1, len(items)), 2)
    state["threads"], state["candidates"] = list(threads.values()), list(cands.values())
    return today


def unique_id(tid, taken):
    n, out = 2, tid
    while out in taken:
        out, n = f"{tid}_{n}", n + 1
    return out


def check_link(link, threads, key_to_id, forces):
    def resolve(ref):  # an existing id, a new-thread key, or a key the model already prefixed with "t_"
        ref = ref.strip()
        return ref if ref in threads else key_to_id.get(ref) or key_to_id.get(ref.removeprefix("t_"), ref)

    ids = [resolve(link.get(k, "")) for k in ("thread_a", "thread_b")]
    a, b = (threads.get(i) for i in ids)
    force = link.get("force", "").strip().lower()
    if not (a and b and a is not b and link.get("sentence", "").strip()):
        if any(link.values()):
            log.warning("dropping cross-link: unknown or identical threads %s", ids)
        return None
    if a["status"] == "dormant" or b["status"] == "dormant":
        return None
    if force not in forces or force not in a["forces"] or force not in b["forces"]:
        log.warning("dropping cross-link: force %r is not shared by both threads", force)
        return None
    if set(a["sections"]) == set(b["sections"]):
        log.warning("dropping cross-link: both threads cover the same sections")
        return None
    return {"thread_a": a["id"], "thread_b": b["id"], "force": force, "sentence": link["sentence"].strip()}


TEACH_SCHEMA = {
    "type": "object",
    "properties": {"threads": {"type": "array", "items": {"type": "object", "properties": {
        "thread_id": {"type": "string"}, "one_line": {"type": "string"}, "like": {"type": "string"},
        "why": {"type": "string"}, "remember": {"type": "string"}}}}},
}


def teach(cfg, threads):
    """Write the stable teaching card (one line, comparison, why, rule of thumb) for threads that lack one:
    new, merged (card cleared) or split threads. Otherwise written once and reused every day, because
    repetition of the same words is what makes it stick."""
    todo = [t for t in threads if t["status"] != "dormant" and not t.get("teach")]
    if not todo:
        return 0
    rows = "\n".join(json.dumps({"id": t["id"], "name": t.get("nickname") or t["title"], "claim": t["claim"],
                                 "forces": t["forces"], "evidence": [e["note"] for e in t["evidence"][-5:]]},
                                ensure_ascii=False) for t in todo)
    out = llm.generate_json(load_prompt("teach").replace("{{threads}}", rows), TEACH_SCHEMA, tag="teach",
                            model=cfg.get("writing", {}).get("model"), **cfg.get("writing", {}).get("params", {}))
    by_id = {t["id"]: t for t in todo}
    for x in out["threads"]:
        t = by_id.get(x["thread_id"])
        fields = {k: x[k].strip() for k in ("one_line", "like", "why", "remember")}
        if t and all(fields.values()):
            t["teach"] = fields
    missing = [t["id"] for t in todo if not t.get("teach")]
    if missing:
        log.warning("no teaching card for %s", missing)
    return len(todo) - len(missing)


def run(cfg, date):
    items = selected_items(date)
    state = previous_state(date)
    for t in state["threads"]:  # refresh status for today before showing them to the model
        t["status"] = compute_status(t, date, cfg["threads"])
    prompt, pairs, split_ids = build_prompt(cfg, date, items, state["threads"], state["candidates"])
    result = llm.generate_json(prompt, SCHEMA, tag="threads", model=cfg["threads"].get("model"),
                               **cfg["threads"].get("params", {}))
    snap = copy.deepcopy(state)
    today = apply(cfg, date, items, snap, result, pairs, split_ids)
    today["taught"] = teach(cfg, snap["threads"])
    out = {"date": date, "threads": snap["threads"], "candidates": snap["candidates"], "today": today}
    write_json(SNAPSHOTS / f"{date}.json", out)
    latest = sorted(SNAPSHOTS.glob("*.json"))[-1]
    if latest.stem == date:
        write_json(DATA / "threads.json", {"date": date, "threads": snap["threads"], "candidates": snap["candidates"]})
    return out
