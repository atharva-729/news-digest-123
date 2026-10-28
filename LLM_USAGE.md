# LLM usage

What calls a model, how often, and roughly what it costs. Measured on 2026-10-28 from
`data/llm_usage.jsonl` (37 calls while building and backfilling 27–28 Oct). Every call appends one line
there: step, model, input / cached / output / reasoning tokens, seconds, and estimated USD. Summarise any
time with `python -m digest.usage` (add `--since YYYY-MM-DD` to skip test runs).

Everything goes through `digest/llm.py` (one OpenAI-compatible endpoint, set in `.env`). Ingest, dedupe,
validation, status maths, rendering and delivery use no LLM at all.

## Per daily edition

| Step | What the model does | Model · reasoning | Calls | Tokens in / out per call | ~$ per call |
|---|---|---|---|---|---|
| `select` | Picks the day's 25 items (+2 reserves per section) from ~250, ids only, with a reason and funding tags | gpt-5-mini · minimal | 6 (one per section) | ~2.3k / ~0.2k | 0.001 |
| `threads` | Attaches picks to L2 threads, proposes new threads, merges and the cross-link | gpt-5-mini · low | 1 | ~4.3k / ~3.9k | 0.009 |
| `connect` | Links today to last week's ~300 headlines: thread backstory and throwbacks | gpt-5-mini · low | 1 | ~18k / ~2.5k | 0.009 |
| `write` | Punchy headlines, so-whats, TL;DR, the big one, force lines, call, quiz | gpt-5.4-mini · low | 1 | ~8.5k / ~2.1k | unpriced* |
| `write:retry` | Only if the writer skipped cards: rewrites just those | gpt-5.4-mini · low | 0–1 | ~2k / ~0.6k | unpriced* |

**Per day:** about 9 calls, ~45k tokens in and ~10k out. On gpt-5-mini list prices the non-writer steps
are about **$0.025/day**; the writer adds roughly $0.01–0.02 depending on gpt-5.4-mini's price.
**Ballpark: $0.04/day, about $1.20/month.** Weekly adds one `weekly` call (~3.3k in / ~0.5k out).

\* gpt-5.4-mini isn't in `model.prices` in `config.yaml` yet, so its cost logs as null. Add its price
there and the log fills in.

## Why these choices

- **Writer on a stronger model.** It's the only step where voice matters. gpt-5-mini kept restating
  headlines ("Live2.ai raises ₹130 Cr…"); gpt-5.4-mini wrote "Anthropic is pricing apocalypse into its
  IPO" with the same prompt, and was faster (14 s vs 42 s) with fewer output tokens.
- **Select at minimal reasoning.** It's ranking, not thinking; 6 calls a day, so it stays cheapest.
- **Threads and connect at low.** At minimal, the model rarely grouped items into threads.
- **Connect is the biggest input** (~18k tokens: 300 past headlines). Halving `lookback_max_items` in
  `config.yaml` halves it.

## Things to decide later

- Personal API key: which provider and model per step. The token counts above carry over to any provider;
  only the prices change. Only `llm.py` and `config.yaml` need to change.
- Whether the writer's quality is worth a bigger model, or whether `connect` can drop to minimal.
