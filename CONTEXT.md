# Project context (read this first)

Handoff file for anyone (human or AI) picking up this project. README.md is the spec; this file is the
current state. **Keep it under ~80 lines: rewrite sections in place, don't append. The log keeps only
the last 5 entries.**

## Where we are
- **Built:** Phases 0–6, explained editions (college-student level), teaching cards, "Remember?", and the
  fixes.md pattern-quality pass (events, direct-only evidence + verify, merges/splits, real statuses,
  developing stories, falsifiable predictions, checked quiz). Runs locally; `--push` publishes to Pages.
- **History backfilled** 6–26 Oct (`digest/backfill.py`: Google News day windows + paged Inc42/TechCrunch/
  Entrackr feeds; select + threads only, no edition pages). Now 11 active patterns with 2–5 events each
  (chip capital, IPO route, embodied AI, Nvidia detour, rate turn, roll checks…), real status mix.
- **Not pushed:** user shows the team next day, then makes the repo private. User pushes.
- **Still open:** attach rate 0.00–0.20/day (target 0.4–0.6): the verify pass and the model stay cautious.
  29 Oct has 0 links (proposals were plans/rumours or went to new candidates).
- **Next:** run `python run.py daily` each morning.

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
- LLM: gateway via local `.env` only. **All steps on gpt-5.4-mini** (user, 2026-10-30; $0.75/M in). It rejects
  reasoning "minimal": default is "none"; threads medium, verify/writing low. A fallback model that refuses
  a reasoning setting is retried without it. ~$0.20/day. Foundry caches identical requests: a rerun only
  changes anything if the prompt changes.
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
- 2026-10-29: Built v2: read phase (robots-aware), plain explanations, teaching cards, Remember?.
- 2026-10-29: Raised level to college student; politics neutrality + fact-check; start page with credit.
- 2026-10-30: fixes.md Phases 1–6: quality report, events, verify, merges/splits, statuses, developing
  stories, falsifiable calls, checked quiz. Several calibration rounds on claim rules and models.
- 2026-10-30: Phase 7 rebuild of 27–29 Oct: 2 solid patterns (voter rolls, Middle East oil), no
  catch-alls or look-alikes, attach rate 0.00–0.08. Committed locally, not pushed.
- 2026-10-30: Switched every step to gpt-5.4-mini; backfilled 21 days of history; rebuilt 27–29 Oct.
  11 patterns, statuses meaningful. Spent $3.74. Threads/verify prompts: "an instance counts" rule.
