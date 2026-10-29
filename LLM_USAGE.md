# LLM usage

What calls a model, how often, and roughly what it costs. Measured on 2026-10-29 from
`data/llm_usage.jsonl`. Every call appends one line there: step, model, input / cached / output /
reasoning tokens, seconds, and estimated USD. Summarise any time with `python -m digest.usage`
(add `--since YYYY-MM-DD` to skip test runs).

Everything goes through `digest/llm.py` (one OpenAI-compatible endpoint, set in `.env`). Ingest, reading
articles, robots.txt checks, dedupe, validation, status maths, the "Remember?" questions, rendering and
delivery use no LLM at all.

## Per daily edition

| Step | What the model does | Model · reasoning | Calls | Tokens in / out per call |
|---|---|---|---|---|
| `select` | Picks 25 stories (+2 reserves per section) from ~270, ids only, preferring ones we can read in full | gpt-5-mini · minimal | 6 | ~2.9k / ~0.2k |
| `threads` | Attaches picks to L2 patterns, proposes new ones, merges and the cross-link | gpt-5-mini · low | 1 | ~4.9k / ~3.7k |
| `teach` | Writes the stable teaching card (one line, "it's like", why, rule of thumb) for new patterns only | gpt-5.4-mini · low | 0–1 | ~0.8k / ~0.2k |
| `connect` | Links today to ~300 of last week's headlines: pattern backstory and "last week → today" | gpt-5-mini · low | 1 | ~18k / ~2.9k |
| `write:cards1` | Explains the tech stories from the article text (headline, explanation, why it matters) | gpt-5.4-mini · low | 1 | ~7.6k / ~1.5k |
| `write:cards2` | Same for all other sections | gpt-5.4-mini · low | 1 | ~11.5k / ~1.4k |
| `write:page` | The day in 3 lines, the big picture, force lines, prediction, 2 quiz questions | gpt-5.4-mini · low | 1 | ~4.8k / ~0.7k |
| `write:factcheck` | Checks the ~7 politics/world cards against their articles; removes interpretation and speculation, adds attribution | gpt-5.4-mini · low | 1 | ~8k / ~1.6k |
| `write:retry` | Only if a card was skipped | gpt-5.4-mini · low | 0–1 | small |

**Per day:** about 13 calls, ~73k tokens in and ~14k out. The gpt-5-mini steps cost about **$0.026/day**
at list prices; the gpt-5.4-mini steps (~33k in / ~6k out) add roughly $0.03–0.05 depending on its price.
**Ballpark: $0.07/day, about $2/month.** Weekly adds one `weekly` call (~3.2k in / ~0.5k out).

gpt-5.4-mini isn't in `model.prices` in `config.yaml` yet, so its cost logs as null. Add its price there and
the log fills in.

## Why these choices

- **Explanations read the article.** The writer's input is the biggest it has been (~19k tokens for the
  cards), because explaining a story needs the story. Text is capped at 700 words per article
  (`read.max_words`).
- **Writer on a stronger model.** It's the step people read. gpt-5-mini restated headlines; gpt-5.4-mini
  explains plainly and is faster.
- **Teaching cards are written once per pattern**, not daily: cheap, and the same words every day is what
  makes a pattern memorable.
- **Select at minimal reasoning** (ranking, 6 calls); **threads and connect at low** (minimal rarely grouped
  stories into patterns).
- **Connect is the biggest single input** (~18k: 300 past headlines). Halving `lookback_max_items` halves it.
- **Fact-check for politics** (2026-10-29): prompt rules alone let interpretation through ("exposes dissent",
  "could strain ties"); a second pass against the article fixed 3–5 of 7 cards a day in testing.
- **Guard:** if an answer contains a non-English script the prompt didn't (seen once: a Russian word), the
  call is retried with an "English only" instruction.

## Things to decide later

- Personal API key: which provider and model per step. Token counts carry over to any provider; only
  prices change. Only `llm.py` and `config.yaml` need to change.
- The "explain like I'm…" dial (Kid / Simple / Normal / Expert + a vibe switch) would multiply the
  `write:cards` output by the number of levels: roughly +$0.03–0.10/day.
