# Project context (read this first)

Handoff file for anyone (human or AI) picking up this project. README.md is the spec; this file is the
current state. **Keep it under ~80 lines: rewrite sections in place, don't append. The log keeps only
the last 5 entries.**

## Where we are
- **Built:** Phases 0–6 plus a redesign (2026-10-28): the edition is now a web page for short attention
  spans, with tabs Feed (punchy L1 cards) / What it means (L1, L2, L3 + map + connections) / Play (call,
  quiz). Runs locally only; `--push` publishes to GitHub Pages.
- **Checkpoints not yet passed:** 3 (3–5 real mornings, then judge `data/threads.json`), 6 (needs a week).
- **Next:** run `python run.py daily --push` every morning; review threads and LLM spend after ~5 days.

## How to run
- `python run.py daily` = ingest (+7-day lookback) → select → threads → connect → write → deliver.
  `python run.py weekly` = write → deliver. `--from/--until X` reuse saved data. `--no-send`, `-v`, `--push`.
- Output: `data/items/`, `data/context/` (last week), `data/selected/`, `data/threads/DATE.json`
  (snapshot per day; `threads.json` = latest), `data/connect/`, `data/written/`, `data/calls.json`,
  `data/llm_usage.jsonl`, `docs/*.html` + `docs/assets/` (copied from `templates/static/`).
- `python -m digest.usage` summarises LLM calls; LLM_USAGE.md explains each one and the cost.
- Always run via `run.py` from the repo root (`digest/select.py` would shadow the stdlib `select`).

## Decisions made (and why)
- LLM: OpenAI-compatible gateway; `FOUNDRY_TOKEN` / `FOUNDRY_BASE_URL` only in local `.env` (repo is
  public). gpt-5-mini for select (minimal), threads and connect (low); **writer on gpt-5.4-mini** (low)
  because gpt-5-mini kept restating headlines. Strict JSON schemas. ~9 calls/day, ~$0.04/day.
- Design: solid colours only (no gradients), thick borders, hard shadows, yellow highlighter marks chosen
  by the model but verified in code (must be an exact substring). Light/dark via tokens + toggle.
  Archivo + Space Mono from Google Fonts. Takes are AI-written; real headline kept as "Boring version" link.
- Connections: `connect` reads ~300 balanced headlines from the previous 7 days (Google News `when:7d`
  plus our saved days, capped per feed per day), adds up to 3 backstory clues per thread (dated when
  published) and 3–6 today↔last-week throwbacks. All ids checked.
- Select returns 2 ranked reserves per section; code drops same-story pairs (fuzzy title ≥ 70, or a
  shared amount/percentage plus a shared name), and skips stories picked in the previous 3 editions.
- Writer skips cards sometimes in a long answer: a `write:retry` call fills just those. Quiz options are
  shuffled in code so answers don't all sit in slot A.
- Threads: per-day snapshots (idempotent reruns); code enforces fixed forces, real ids, ≥2 items, status
  from evidence counts, never delete. New threads get a `nickname` and a plain-English line.
- truststore is injected in `common.py` (every module), so feeds work without importing `llm.py`.
- Work laptop proxy: all feeds open except ESPN and Atlas Obscura.
- Idea credit: @neworderindia, in README and every footer (`credit` in config).

## Open questions / parked
- Repo: https://github.com/atharva-729/news-digest-123 (public). Pages from `main` `/docs`. No Actions:
  company secrets must not go to GitHub.
- LLM spend/provider to be discussed (user may buy a personal API key); see LLM_USAGE.md.
  gpt-5.4-mini's price isn't in `model.prices` yet, so its cost logs as null.
- Funding is often all-India (Google News is India-edition); consider a world funding feed.
- Email optional (teaser linking to the page); suggested a separate sender-only Gmail.

## Log (last 5)
- 2026-10-28: Built Phases 3–6 + workflow. Fixed call-judging leak and cross-day repeat picks.
- 2026-10-28 10:56 IST: full rerun of 10-28 (not a new day); first valid cross-link.
- 2026-10-28: Pushed to GitHub (public). Endpoint moved to .env. Dropped Actions; site in docs/.
- 2026-10-28: Redesign: punchy cards, 3 tabs, L1/L2/L3 map, last-week connections, light/dark, quiz,
  LLM usage logging. Writer moved to gpt-5.4-mini. Regenerated 27–28 Oct and the weekly.
