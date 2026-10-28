"""Phase 3: attach the day's L1 items to L2 threads, each driven by fixed L3 forces.

State is snapshotted per day in data/threads/DATE.json (built on the latest earlier snapshot), so rerunning
a day replaces that day instead of adding its evidence twice. data/threads.json is a copy of the latest one.
The model proposes; code enforces every rule (ids exist, forces are fixed, >=2 items per thread, status).
"""
import copy
import json
import logging
import re
from datetime import date as Date

from digest import llm
from digest.common import DATA, load_prompt, read_json, write_json

log = logging.getLogger(__name__)

SNAPSHOTS = DATA / "threads"

SCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["attach", "new", "none"]},
                    "thread_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["item_id", "action", "thread_id", "note"],
            },
        },
        "new_threads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "nickname": {"type": "string"},
                    "plain": {"type": "string"},
                    "claim": {"type": "string"},
                    "forces": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "title", "claim", "forces"],
            },
        },
        "merges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"keep": {"type": "string"}, "absorb": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["keep", "absorb", "reason"],
            },
        },
        "cross_link": {
            "type": "object",
            "properties": {
                "thread_a": {"type": "string"},
                "thread_b": {"type": "string"},
                "force": {"type": "string"},
                "sentence": {"type": "string"},
            },
            "required": ["thread_a", "thread_b", "force", "sentence"],
        },
    },
    "required": ["assignments", "new_threads", "merges", "cross_link"],
}

# Claims that only say something exists or keeps going are not directional.
VAGUE = re.compile(r"\b(is|are) (growing|rising|increasing|changing|evolving|important|booming)$"
                   r"|\b(continues?|persists?|remains?|matters?)$", re.I)


def slug(s):
    s = re.sub(r"^[tc]_", "", s.lower())  # the model sometimes prefixes its keys like our ids
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "thread"


def claim_ok(claim):
    claim = claim.strip(" .")
    return len(claim.split()) >= 7 and not VAGUE.search(claim)


def days_between(a, b):
    return (Date.fromisoformat(b) - Date.fromisoformat(a)).days


def compute_status(thread, date, dormant_after):
    if thread.get("merged_into"):
        return "dormant"
    if days_between(thread["last_seen"], date) >= dormant_after:
        return "dormant"
    if thread.get("parked_on") and thread["last_seen"] <= thread["parked_on"]:
        return "dormant"
    ages = [days_between(e["date"], date) for e in thread["evidence"]]
    this_week = sum(0 <= a < 7 for a in ages)
    last_week = sum(7 <= a < 14 for a in ages)
    if this_week > last_week:
        return "heating"
    if this_week < last_week:
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


def build_prompt(cfg, date, items, threads, candidates):
    tcfg = cfg["threads"]
    active = [t for t in threads if t["status"] != "dormant"]
    over = len(active) >= tcfg["max_active_threads"]
    lines = lambda rows: "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) or "(none)"
    thread_rows = [{"id": t["id"], "title": t["title"], "claim": t["claim"], "forces": t["forces"],
                    "sections": t["sections"], "status": t["status"], "evidence_count": len(t["evidence"]),
                    "recent_evidence": [e["note"] for e in t["evidence"][-3:]]} for t in active]
    cand_rows = [{"id": c["id"], "title": c["title"], "claim": c["claim"], "forces": c["forces"],
                  "evidence": [e["note"] for e in c["evidence"]]} for c in candidates]
    item_rows = [{"id": i, "section": it["section"], "source": it["source"], "title": it["title"],
                  "summary": it["summary"][:250], "why": it["reason"]} for i, it in items.items()]
    return (load_prompt("threads")
            .replace("{{forces}}", ", ".join(tcfg["forces"]))
            .replace("{{date}}", date)
            .replace("{{active_count}}", str(len(active)))
            .replace("{{min_evidence}}", str(tcfg["min_evidence_for_new_thread"]))
            .replace("{{max_active}}", str(tcfg["max_active_threads"]))
            .replace("{{merge_instruction}}",
                     "We are at or over the cap: you **must** propose at least one merge before adding new threads."
                     if over else "Propose merges only if two threads clearly say the same thing.")
            .replace("{{threads}}", lines(thread_rows))
            .replace("{{candidates}}", lines(cand_rows))
            .replace("{{items}}", lines(item_rows)))


def evidence(date, item, note):
    return {"date": date, "item_id": item["id"], "section": item["section"], "title": item["title"],
            "url": item["url"], "source": item["source"], "note": note}


def apply(cfg, date, items, state, result):
    """Apply the model's proposal to `state` under the code-enforced rules. Returns the day's change log."""
    tcfg = cfg["threads"]
    forces = set(tcfg["forces"])
    min_ev = tcfg["min_evidence_for_new_thread"]
    threads = {t["id"]: t for t in state["threads"]}
    cands = {c["id"]: c for c in state["candidates"]}
    prev_status = {t["id"]: t["status"] for t in threads.values()}
    today = {"attached": [], "new_threads": [], "new_candidates": [], "promoted": [], "merges": [], "cross_link": None}

    defs = {}
    for d in result.get("new_threads", []):
        d_forces = [f.strip().lower() for f in d["forces"] if f.strip().lower() in forces]
        if not d_forces or not claim_ok(d["claim"]):
            log.warning("rejecting new thread %r: forces %s, claim %r", d["key"], d["forces"], d["claim"])
            continue
        defs[d["key"]] = {**d, "forces": d_forces, "items": []}

    seen = set()
    for a in result.get("assignments", []):
        i, tid, note = a["item_id"], a["thread_id"].strip(), a["note"].strip()
        if a["action"] == "none" or i not in items or i in seen or not note:
            continue
        seen.add(i)
        if tid in defs:  # the model sometimes labels a new-thread key as "attach"
            defs[tid]["items"].append((i, note))
        elif tid in threads and not threads[tid].get("merged_into"):
            threads[tid]["evidence"].append(evidence(date, items[i], note))
            threads[tid]["last_seen"] = date
            today["attached"].append({"item_id": i, "thread_id": tid, "note": note})
        elif tid in cands:
            cands[tid]["evidence"].append(evidence(date, items[i], note))
        else:
            log.warning("dropping %s of %s to undefined thread %r", a["action"], i, tid)

    key_to_id = {}
    for key, d in defs.items():
        if not d["items"]:
            continue
        ev = [evidence(date, items[i], note) for i, note in d["items"]]
        base = {"title": d["title"].strip(), "nickname": d["nickname"].strip() or d["title"].strip(),
                "plain": d["plain"].strip(), "claim": d["claim"].strip(), "forces": d["forces"], "created": date,
                "evidence": ev}
        if len(ev) >= min_ev:
            tid = unique_id("t_" + slug(key), threads)
            threads[tid] = {"id": tid, **base, "last_seen": date}
            today["new_threads"].append(tid)
            today["attached"] += [{"item_id": e["item_id"], "thread_id": tid, "note": e["note"]} for e in ev]
            key_to_id[key] = tid
        else:
            cid = unique_id("c_" + slug(key), cands)
            cands[cid] = {"id": cid, **base}
            today["new_candidates"].append(cid)

    for cid, c in list(cands.items()):
        if len({e["item_id"] for e in c["evidence"]}) >= min_ev:
            tid = unique_id("t_" + cid.removeprefix("c_"), threads)
            threads[tid] = {"id": tid, **{k: v for k, v in c.items() if k != "id"},
                            "last_seen": max(e["date"] for e in c["evidence"])}
            today["promoted"].append(tid)
            today["attached"] += [{"item_id": e["item_id"], "thread_id": tid, "note": e["note"]}
                                  for e in c["evidence"] if e["date"] == date]
            del cands[cid]
        elif days_between(c["created"], date) >= tcfg["dormant_after_days"]:
            del cands[cid]  # candidates are not threads yet; letting them lapse is not deleting a thread

    for m in result.get("merges", []):
        keep, absorb = threads.get(m["keep"]), threads.get(m["absorb"])
        if not keep or not absorb or keep is absorb or keep.get("merged_into") or absorb.get("merged_into"):
            log.warning("dropping invalid merge %s <- %s", m["keep"], m["absorb"])
            continue
        keep["evidence"] = sorted(keep["evidence"] + absorb["evidence"], key=lambda e: e["date"])
        keep["forces"] = list(dict.fromkeys(keep["forces"] + absorb["forces"]))
        keep["last_seen"] = max(keep["last_seen"], absorb["last_seen"])
        absorb["merged_into"] = keep["id"]
        today["merges"].append({"keep": keep["id"], "absorb": absorb["id"], "reason": m["reason"]})

    for t in threads.values():
        t["sections"] = list(dict.fromkeys(e["section"] for e in t["evidence"]))
        t["status"] = compute_status(t, date, tcfg["dormant_after_days"])

    # Over the cap after merges: park the stalest threads. They wake up when new evidence arrives.
    active = sorted((t for t in threads.values() if t["status"] != "dormant"),
                    key=lambda t: (t["last_seen"], len(t["evidence"])))
    for t in active[: max(0, len(active) - tcfg["max_active_threads"])]:
        t["parked_on"], t["status"] = date, "dormant"
        log.warning("over max_active_threads: parked %s", t["id"])

    today["cross_link"] = check_link(result.get("cross_link") or {}, threads, key_to_id, forces)
    today["status_changes"] = {tid: [prev_status.get(tid), t["status"]] for tid, t in threads.items()
                               if prev_status.get(tid) != t["status"]}
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
    """Write the stable teaching card (one line, comparison, why, rule of thumb) for threads that lack one.
    Written once per thread and reused every day: repetition of the same words is what makes it stick."""
    todo = [t for t in threads if t["status"] != "dormant" and not t.get("merged_into") and not t.get("teach")]
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
        t["status"] = compute_status(t, date, cfg["threads"]["dormant_after_days"])
    prompt = build_prompt(cfg, date, items, state["threads"], state["candidates"])
    result = llm.generate_json(prompt, SCHEMA, tag="threads", **cfg["threads"].get("params", {}))
    snap = copy.deepcopy(state)
    today = apply(cfg, date, items, snap, result)
    today["taught"] = teach(cfg, snap["threads"])
    out = {"date": date, "threads": snap["threads"], "candidates": snap["candidates"], "today": today}
    write_json(SNAPSHOTS / f"{date}.json", out)
    latest = sorted(SNAPSHOTS.glob("*.json"))[-1]
    if latest.stem == date:
        write_json(DATA / "threads.json", {"date": date, "threads": snap["threads"], "candidates": snap["candidates"]})
    return out
