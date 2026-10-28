# Project context (read this first)

Handoff file for anyone (human or AI) picking up this project. README.md is the spec; this file is the
current state. **Keep it under ~80 lines: rewrite sections in place, don't append. The log keeps only
the last 5 entries.**

## Where we are
- **Built:** Phases 0–6 (ingest, select, threads, write, deliver, weekly). Runs locally only.
- **Checkpoints not yet passed:** 3 (needs 3–5 real mornings, then read `data/threads.json` for thread
  quality), 4 (open editions in a real email), 5 (needs secrets + a GitHub repo), 6 (needs a week).
- **Next:** run `python run.py daily --push` every morning; review threads after ~5 days.

## How to run
- `python run.py daily` = ingest → select → threads → write → deliver. `python run.py weekly` = write → deliver.
- `--from X` / `--until X` pick a phase range, reusing saved data. `--no-send` skips email. `-v` logs.
- Output: `data/items/`, `data/selected/`, `data/threads/DATE.json` (snapshot per day; `threads.json` =
  latest), `data/written/`, `data/weekly/`, `data/calls.json`, `docs/DATE.html`, `docs/weekly-DATE.html`,
  `docs/index.html`. `--push` commits data/ + docs/ and pushes, which updates GitHub Pages.
- Always run via `run.py` from the repo root (`digest/select.py` would shadow the stdlib `select`).

## Decisions made (and why)
- LLM: an OpenAI-compatible gateway; `FOUNDRY_TOKEN` and `FOUNDRY_BASE_URL` live only in the local
  `.env`, never in the repo (it's public). `gpt-5-mini`, fallbacks `gpt-5.4-nano`, `gpt-4.1-mini`. Strict JSON schemas (`llm._strict`
  closes every object), because non-strict let the model drop required fields. Select runs at
  `minimal` reasoning; threads and writing at `low` (minimal rarely grouped items into threads).
  A full daily is ~8 calls, roughly $0.03. Foundry seems to cache identical requests.
- Work laptop (corporate proxy): all feeds open except ESPN and Atlas Obscura (category block). Gmail SMTP 465
  is reachable. `llm.py` injects `truststore` for the TLS-inspection CA.
- Threads: state is a snapshot per day built on the latest earlier one, so reruns are idempotent and
  days can be back-filled in order. Code enforces: fixed forces, real item ids, ≥2 items or it stays a
  candidate (candidates lapse after `dormant_after_days`), status from evidence counts (this week vs
  last), never delete (merged → `merged_into`, over-cap → `parked_on`; both wake on new evidence).
  Cross-link must share a force and differ in sections; it's often dropped while threads are few.
- Select skips stories already picked in the previous 3 editions (title similarity ≥ 85).
- Calls: one per daily, review in 30–120 days. Weekly verdicts count only items dated after the call;
  no surviving evidence means "too early".
- Fun section items are shown in the Fun block (not in the section list), so the mix still holds.
- Funding country: model infers from clear signals; code backstops rupee amounts → India.
- Idea credit: @neworderindia, in README and every footer (`credit` in config).

## Open questions / parked
- Repo: https://github.com/atharva-729/news-digest-123 (public). Static site: Pages deploys from
  branch `main`, folder `/docs`. User decision: no GitHub Actions, because company secrets (the LLM
  token) must not go into GitHub. Every run happens on the work laptop.
- Email optional: only if SMTP_* are in local .env; suggested a separate sender-only Gmail account.
- Employer-IP / licence: user chose a public repo; company endpoint kept out of the code for that reason.
- Thread claims are long and compound; tighten the prompt after Checkpoint 3 if they read generic.

## Log (last 5)
- 2026-10-27: Built Phases 0–2. First run: 257 items, 25 picks, on budget. Fixed Entrackr URL,
  the fun feeds, the sports prompt (prefer results over policy) and funding-country inference.
- 2026-10-28: Switched LLM to LLM Foundry gpt-5-mini; probed feeds on work laptop (only ESPN, Atlas
  Obscura blocked). Run 2: 249 items, 25 picks, 26 s.
- 2026-10-28: Built Phases 3–6 + workflow. Back-filled threads for 10-27/10-28: 7 active threads,
  2 calls, daily ~6 min read, weekly renders. Fixed call-judging leak and cross-day repeat picks.
- 2026-10-28 10:56 IST: full rerun of 10-28 (not a new day). 242 items, 6 active threads, first
  valid cross-link. Funding was all-India (0 world), so the India/world rule wasn't met.
- 2026-10-28: Pushed to GitHub (public). Endpoint moved to .env. Dropped Actions; site now in docs/
  for branch-based Pages, `run.py --push` publishes.
