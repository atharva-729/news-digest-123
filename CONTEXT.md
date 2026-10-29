# Project context (read this first)

Handoff file for anyone (human or AI) picking up this project. README.md is the spec; this file is the
current state. **Keep it under ~80 lines: rewrite sections in place, don't append. The log keeps only
the last 5 entries.**

## Where we are
- **Built:** Phases 0–6, then (2026-10-29) explained editions: every story is read and explained for a
  well-read college student; L2 patterns have stable teaching cards; spaced "Remember?" questions. Tabs: News /
  What it means / Play. Runs locally only; `--push` publishes to GitHub Pages.
- **Checkpoints not yet passed:** 3 (3–5 real mornings, then judge `data/threads.json`), 6 (needs a week).
- **Next:** run `python run.py daily --push` every morning. User wants feedback on readability first.

## How to run
- `python run.py daily` = ingest (+7-day lookback) → select → read → threads (+teach) → connect →
  write → deliver. `python run.py weekly` = write → deliver. `--from/--until X`, `--no-send`, `-v`, `--push`.
- Output: `data/items/`, `data/context/`, `data/selected/`, `data/read/` (metadata only),
  `data/threads/DATE.json`, `data/connect/`, `data/written/`, `data/calls.json`, `data/memory.json`
  (review schedule), `data/llm_usage.jsonl`, `docs/*.html` + `docs/assets/`. Article text: `cache/` (git-ignored).
- `python -m digest.usage` summarises LLM calls; LLM_USAGE.md explains each one (~12 calls, ~$0.06/day).
- Always run via `run.py` from the repo root (`digest/select.py` would shadow the stdlib `select`).

## Decisions made (and why)
- LLM: OpenAI-compatible gateway; `FOUNDRY_TOKEN` / `FOUNDRY_BASE_URL` only in local `.env` (repo is
  public). gpt-5-mini for select/threads/connect; gpt-5.4-mini for teach + writing. Strict JSON schemas.
  Replies with stray non-English script are retried with an "English only" note.
- Reading (`digest/articles.py`): feed text first; article page only if robots.txt allows our agent, "*"
  **and** ChatGPT-User / Claude-User / Perplexity-User (we are a user-triggered AI reader). Honest UA; no
  bot-check workarounds. Blocked: TechCrunch, The Verge, The Hindu, BBC, Al Jazeera, Reuters. Pages that
  refuse our UA (Ars, Inc42) fall back to their long feed text. Google News links are never decoded.
- Select prefers `full_story` items (user chose: prefer publisher feeds, else tag "Limited info").
  Limited = under 25 words of text. Added HT India/World/Sports and Indian Express World feeds.
- Writing level (user, 2026-10-29): sharp college student. Don't explain general knowledge (laptops,
  elections); do explain specifics (what a startup sells, who a lesser-known person is, niche terms).
  Plain headline, 2–4 sentences ≤ 65 words, one "why it matters". Facts only from the article.
- Politics: facts and attribution only, no motives/strategy/loaded words, in every prompt (cards, threads,
  teach, connect). Enforced by `write:factcheck` on politics/world cards against the article. Limited
  stories (headline only) get no model explanation at all; the card says why and links the original.
- "Last week" links: `same_pattern` only kept if the past story is evidence of the same thread (code check).
- Start page (`docs/index.html`) explains L1/L2/L3 with examples and credits @neworderindia; each edition
  has a "New here?" strip with the credit.
- L2 pedagogy: teaching card per pattern (one line, "it's like", why/L3, rule of thumb), written once and
  reused; "Remember?" questions built in code from those cards at 1/3/7/14/30-day gaps. L3 meanings
  are fixed text in config (`forces_explained`).
- Design: calm, 16px body, 20px headlines, no dropdowns, no rotated stickers, solid colours, light/dark.
- Earlier decisions still hold: per-day thread snapshots, same-story dedupe with reserves, quiz answers
  shuffled, truststore in `common.py`, credit to @neworderindia in every footer.

## Open questions / parked
- "Explain like I'm…" dial: user's idea, assessed as workable (difficulty slider + vibe switch); not built.
- A weak teaching card sticks until regenerated (e.g. "Governance Guardrails" spice-jar comparison);
  consider a manual "re-teach" option.
- Funding is often all-India; consider a world funding feed. gpt-5.4-mini price not in config yet.
- Repo https://github.com/atharva-729/news-digest-123 is public; Pages from `main` `/docs`; no Actions.

## Log (last 5)
- 2026-10-28: Pushed to GitHub (public). Endpoint moved to .env. Dropped Actions; site in docs/.
- 2026-10-28: Redesign v1: punchy cards, 3 tabs, L1/L2/L3 map, last-week connections, LLM usage logging.
- 2026-10-29: User found v1 confusing. Feasibility check: ~70% of stories readable in full.
- 2026-10-29: Built v2: read phase (robots-aware), plain explanations, teaching cards, Remember?,
  calmer design. Today: 23/25 stories explained from full text, 3 limited. Rebuilt 27–28 Oct + weekly.
- 2026-10-29: User feedback: too simple, politics biased ("Institutional Grip"). Raised level, added
  neutrality rules + politics fact-check, landing page with credit. Rebuilt all three days' patterns.
