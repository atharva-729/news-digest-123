# Project context (read this first)

Handoff file for anyone (human or AI) picking up this project. README.md is the spec; this file is the
current state. **Keep it under ~80 lines: rewrite sections in place, don't append. The log keeps only
the last 5 entries.**

## Where we are
- **Built:** Phases 0–6, explained editions (college-student level), teaching cards, "Remember?", and the
  fixes.md pattern-quality pass (events, direct-only evidence + verify, merges/splits, real statuses,
  developing stories, falsifiable predictions, checked quiz). Runs locally; `--push` publishes to Pages.
- **Not pushed:** the fixes.md rebuild of 27–29 Oct is committed locally only. User reviews it first.
- **Open after fixes.md:** thread attach rate is 0.00–0.08 (target 0.4–0.6). Precision is good; recall is
  low because 3 days of history leave most ideas as single-event candidates (24 on 29 Oct). Re-measure
  after ~7 real days with `python -m digest.quality`; if still < 0.3, revisit (see open questions).
- **Next:** run `python run.py daily` each morning; user decides when to `--push`.

## How to run
- `python run.py daily` = ingest (+7-day lookback) → select → read → threads (+verify, teach) → connect →
  write → deliver. `python run.py weekly` = write → deliver. `--from/--until PHASE`, `--dates A:B` (date
  range, e.g. `--dates 2026-10-27:2026-10-29 --from threads` to rebuild), `--no-send`, `-v`, `--push`.
- Output: `data/items/`, `data/context/`, `data/selected/`, `data/read/`, `data/threads/DATE.json`
  (`today.events`, `today.verify`, `today.attach_rate`), `data/connect/`, `data/written/`, `data/calls.json`,
  `data/memory.json`, `data/llm_usage.jsonl`, `data/quality/` (baseline.txt, after.txt), `docs/`.
  Pre-fixes state: `data/archive/pre-fixes/`. Article text: `cache/` (git-ignored).
- `python -m digest.quality [--from A --until B]`: attach rate, events per thread, status mix, look-alikes.
  `python -m digest.usage`: LLM calls and the verify drop rate (~14 calls, ~$0.09/day; see LLM_USAGE.md).

## Decisions made (and why)
- LLM: gateway via local `.env` only (repo is public). gpt-5-mini for select/connect/verify and threads
  (threads at **medium**: low skipped matching stories to candidates); gpt-5.4-mini for teach + writing.
  gpt-5.4-mini for threads was tried: too few proposals, no patterns formed.
- Patterns (fixes.md): every story gets an `event` key (one story = one key across updates); a thread needs
  ≥2 distinct events; only `direct` links, then a keep/drop verify pass; ≤4 new clues per thread per day;
  `claim_ok` rejects steady states ("X is funding Y"), lists ("A, B and C"), generic words, bracket tags.
  Look-alike pairs (claim similarity ≥48, calibrated) need merge/distinct; ≥10 events in 14 days → split
  offered; candidate merges allowed. Status from distinct events vs own history (new/building/heating/
  cooling/active); backstory from last week never counts. Merges/splits shown in the weekly.
- Developing stories: an event with ≥3 articles in 7 days that isn't a pattern's evidence (e.g. "Israel
  election 2026, 6 updates"), built in code from event keys.
- Predictions: measure must be a real-world outcome (code rejects "number of stories"), threshold needs a
  number or named event, confidence 20–80, 7-day cooldown per thread, one retry then skip. Weekly: "wrong"
  only after the window closes. Quiz: 4 allowed types; evidence/force answers checked in code.
  Remember?: past stories ↔ patterns, built from stored evidence; nicknames are only labels.
- Reading, politics neutrality + fact-check, writing level, design, start page credit: unchanged.

## Open questions / parked
- Low recall in the first days (see above). Options if it persists: show candidates as "possible patterns
  (1 event so far)", or run the verify pass at minimal again (it drops ~40%).
- Automation (fixes.md future work): Task Scheduler on the laptop vs personal API key + Actions; check
  with Anand whether this stays on Foundry. "Explain like I'm…" dial, re-teach, world funding feed parked.
- Repo is public; user may make it private (Pages on a private repo needs a paid plan).

## Log (last 5)
- 2026-10-29: User found v1 confusing. Feasibility check: ~70% of stories readable in full.
- 2026-10-29: Built v2: read phase (robots-aware), plain explanations, teaching cards, Remember?.
- 2026-10-29: Raised level to college student; politics neutrality + fact-check; start page with credit.
- 2026-10-30: fixes.md Phases 1–6: quality report, events, verify, merges/splits, statuses, developing
  stories, falsifiable calls, checked quiz. Several calibration rounds on claim rules and models.
- 2026-10-30: Phase 7 rebuild of 27–29 Oct: 2 solid patterns (voter rolls, Middle East oil), no
  catch-alls or look-alikes, attach rate 0.00–0.08. Committed locally, not pushed.
