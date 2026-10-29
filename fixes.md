# fixes.md: pattern quality pass

Review of the 27–29 Oct editions. The UI, reading, fact-check and teaching cards are good. **The L2 layer is
the weak point**: stories get forced into patterns, single events pass as patterns, every pattern says
"Heating up", and the predictions and quiz don't test anything real. This file fixes that in phases.

Read `CONTEXT.md` first. Follow the existing rules: the model proposes and code enforces, the model never
writes links, prompts live in `digest/prompts/`, everything tunable goes in `config.yaml`. At the end,
update `CONTEXT.md` as `CLAUDE.md` asks.

### Evidence from the current data (what we're fixing)

| Problem | Example (29 Oct) |
|---|---|
| Forced attachment | Gemini 4 Carbon benchmarks → **Power & Siting Crunch** ("increases pressure for compute… power"). Touchscreen MacBook Pro → **Heavy-AI Cash**. Let's Game Now (esports) and "Fed holds rates" → **AI Trade** ("macro pause that shapes capital flows"). |
| Catch-all threads | AI Trade has 14 clues, Heavy-AI Cash has 17, after about a week. |
| Events passing as patterns | **Slow Math** = one Israeli election. **Refinery Shock** = one strike on one refinery. |
| Status means nothing | All 7 active threads are `heating`. With about a week of history, `this_week > last_week` is almost always true. |
| Overlap | AI Trade ("money rotating into AI/tech") vs Heavy-AI Cash ("money into AI hardware"). |
| Predictions can't fail | "Expect another large power-supply deal for AI data centres within about 90 days." That's near-certain. 2 of 3 calls are on the same thread. |
| Quiz tests vocabulary | "What does 'Roll Tightening' mean?" tests our nickname. Distractors like "election coalitions are becoming easier to form" are obviously wrong. |

---

## Phase 1: Measure first (baseline)

**Do**
- Add `python -m digest.quality [--date D | --from A --until B]`. No LLM. It reads `data/threads/DATE.json`, `data/selected/` and `data/calls.json` and prints:
  - attach rate (share of selected items attached to any thread)
  - evidence per thread, and **distinct events** per thread (Phase 2 adds event keys; until then, count distinct titles)
  - status distribution (how many heating / active / cooling / new)
  - pairs of active threads with similar claims (rapidfuzz `token_set_ratio` on claims, plus shared forces)
  - calls per thread
- Save the current output for 27–29 Oct to `data/quality/baseline.txt` before changing anything.

**Don't**
- Don't change any pipeline behaviour in this phase.

**✅ Checkpoint 1:** the baseline shows roughly what the table above says: attach rate near 90%+, all heating, the AI Trade / Heavy-AI Cash pair flagged.

---

## Phase 2: Events vs patterns (single stories are not L2)

A pattern needs evidence from **different events**. Ten articles about one election are one event.

**Do**
- In `prompts/threads.md` and the threads JSON schema, every attachment and every new-thread evidence item gets an `event` field: a short stable key for the underlying event, such as `israel-election-2026` or `saudi-refinery-strike-oct26`. Pass existing threads' event keys in the prompt so the model reuses them.
- In `threads.py` (code-enforced):
  - A new thread or candidate promotion needs evidence from **≥2 distinct events** (config: `threads.min_events_for_new_thread: 2`). Two articles on one event don't count. Replace the current item-count rule with this.
  - Store `event` on each evidence entry. Expose `distinct_events` on each thread.
- Add a **Developing stories** lane: an event with ≥3 articles across the selected and context items that isn't evidence for any thread becomes a story card group ("Israel election: 4 updates"), not a pattern. Build it in code from the event keys. Render it in the News tab, above the section filters or after the Big picture. No L2/L3 tags on it.
- Existing threads whose evidence is one event (Slow Math, Refinery Shock) become dormant when the state is rebuilt (Phase 7).

**Don't**
- Don't do event grouping with embeddings. The model already sees the items; a key plus a code check is enough.
- Don't delete event-only threads by hand. Rebuilding with the new rules handles them.

**✅ Checkpoint 2:** rerun threads for 29 Oct only (`--from 2026-10-29 --until 2026-10-29`, threads step onward). Slow Math and Refinery Shock are not active patterns; the Israel election shows up as a developing story; every active thread has ≥2 distinct events.

---

## Phase 3: Precision over recall ("no pattern" is a good answer)

**Do**
- In `prompts/threads.md`, make `none` the default. Add the rule: *attach only if the story is direct evidence for the claim as written: it shows the claimed thing happening. "Could affect", "shapes", "increases pressure on", or "related to" don't count.*
- Replace the free-text `note` with two fields:
  - `mechanism`: one sentence, "This story shows <claim> because <specific fact from the story>."
  - `strength`: `direct | indirect`. Only `direct` is stored as evidence. `indirect` is dropped and logged.
- Add a cheap **verify pass** (`write`-style second pass, gpt-5-mini, minimal reasoning, one call): for each proposed attachment, given the headline, the item text (first ~120 words), the thread claim and the mechanism, answer `{keep: bool, reason}`. Code drops rejected ones. Log the drop rate in `llm_usage.jsonl` under the tag `threads:verify`.
- Cap: a single thread can take at most `threads.max_new_evidence_per_day: 4` items a day (keep the highest-confidence ones).
- Track the attach rate in `data/threads/DATE.json` (`today.attach_rate`). Target **0.4–0.6**. Show "No pattern yet" on cards without hesitation; that's honest.

**Don't**
- Don't lower `edition_size` to make the attach rate look better.
- Don't let the verify pass rewrite mechanisms. It's keep/drop only.

**✅ Checkpoint 3:** rerun 29 Oct. Gemini 4 Carbon is not under Power & Siting, the MacBook Pro is not under Heavy-AI Cash, Let's Game Now and "Fed holds" are not under AI Trade. The attach rate is between 0.4 and 0.6. Read every remaining `mechanism`: each should make sense to a reader without squinting.

---

## Phase 4: Sharper claims, real merges

**Do**
- Claim rules in `prompts/threads.md`, checked by `claim_ok()` where possible: a claim names **who** (actor type), **what** (the shift) and **direction**, in ≤25 words. Examples: "Hyperscalers are signing long-term nuclear and gas power deals to secure data-centre capacity" is good; "Investors are rotating back into AI" is too broad.
- Before the threads call, code finds **overlap pairs** among active threads (claim similarity ≥ `threads.overlap_similarity: 70` and at least one shared force). Pass them to the prompt as `overlap_pairs`, and require a decision for each: `merge` (keep/absorb) or `distinct` with a one-line difference. Code applies merges as today.
- When a thread's evidence spans clearly different sub-stories (≥10 events in 14 days), ask the model whether to **split** it into two narrower threads. Add `splits` to the schema; code moves the evidence and keeps the old id as `split_into`.
- Rewrite `teach` cards only for new, merged or split threads (the existing "write once" rule still holds otherwise).

**Don't**
- Don't let merges or splits happen silently. Record them in `today.merges` / `today.splits` and show them in the weekly edition.

**✅ Checkpoint 4:** AI Trade and Heavy-AI Cash are either merged, or both are rewritten into clearly different, narrower claims. No two active threads read the same.

---

## Phase 5: Status that means something

**Do**
- Rewrite `compute_status()` in `threads.py`, counting **distinct events**, not items:
  - **`new`**: created < 7 days ago.
  - **`building`**: < 14 days of history (not enough baseline to call it heating).
  - **`heating`**: events in the last 7 days ≥ 2 **and** ≥ 1.5× the thread's average weekly events over its history (excluding this week).
  - **`cooling`**: events in the last 7 days ≤ 0.5× that average.
  - **`active`**: otherwise. **`dormant`**: unchanged rules.
  - Put the thresholds in config (`threads.heating_ratio: 1.5`, `threads.cooling_ratio: 0.5`, `threads.min_history_days: 14`).
- Add `new` / `building` badge styles to the templates. "Patterns that moved today" shows at most 3, ordered by today's direct evidence.

**Don't**
- Don't fake history by counting `data/context/` lookback items as evidence when computing the baseline.

**✅ Checkpoint 5:** on rebuilt 27–29 Oct data, statuses are mostly `new` or `building` (correct, since there's only ~a week of history). Nothing says `heating` without passing the ratio test.

---

## Phase 6: Predictions that can fail, quiz that tests understanding

**Predictions (`prompts/write.md`, `write.py`, `calls.json`)**

**Do**
- New `call` schema: `prediction`, `measure` (what we count or check, from news), `threshold` (a number or a named event), `window_days` (30–120), `could_fail_because` (one line), `confidence` (integer 20–80; not near-certain, not a wild guess).
- Code rejects a call if: there's no number or named event in `threshold`, `confidence` is outside 20–80, or the thread has had a call in the last `calls.cooldown_days: 7`. On rejection, retry once; if it still fails, skip the call that day. Skipping is fine.
- Prefer threads with `new`/`building` status that haven't had a call yet.
- The weekly review judges against `measure` and `threshold` and keeps `too early` when the window hasn't closed.

**Don't**
- Don't allow "expect more X" or "another X" without a number or a named event.

**Quiz: "Did today make sense?" (`prompts/write.md`)**

**Do**
- Allowed question types only:
  1. "Which of today's stories is evidence for <pattern>?" (options = 3 of today's real headlines)
  2. "Which force connects <story A> and <story B>?" (options = L3 forces)
  3. "Which headline would **weaken** <pattern>?" (options = plausible hypothetical headlines)
  4. "Why does <story> matter?", where every option is a plausible reading of a real story from today, only one correct.
- Rule: every wrong option must be something a reader who skimmed could believe. No absurd options.

**Quiz: "Remember?" (built in code, `write.remember()`)**

**Do**
- Keep the spaced schedule (1/3/7/14/30). Change the question types, still built only from stored data so nothing can be made up:
  - "Which of these past stories was evidence for <pattern>?" The correct answer is from the thread's `evidence` titles; distractors are from other threads' evidence.
  - "<past headline> was evidence of which pattern?" The options are pattern one-liners (not nicknames).
- Use nicknames only as labels next to the one-liner, never as the thing being tested.

**✅ Checkpoint 6:** rebuild the 29 Oct write step. The call has a number or named event and a confidence between 20 and 80. No quiz question has an obviously wrong option. Remember? questions are about stories and patterns, not nicknames.

---

## Phase 7: Rebuild and compare

**Do**
- Back up the current state to `data/archive/pre-fixes/` (threads.json, threads/, calls.json, memory.json, written/).
- Rebuild 27–29 Oct from scratch with the new rules: `python run.py daily --from 2026-10-27 --until 2026-10-29 --no-send`, then the weekly for 28 Oct. Reset `threads.json`, `calls.json` and `memory.json` first so old threads don't carry over.
- Run `python -m digest.quality --from 2026-10-27 --until 2026-10-29`, save it to `data/quality/after.txt`, and print a before/after table: attach rate, threads, events per thread, status mix, overlap pairs, calls per thread.
- Update `LLM_USAGE.md` with the new `threads:verify` step and the per-day cost.

**Don't**
- Don't `--push` until the user has looked at the rebuilt editions locally.

**✅ Checkpoint 7 (the real one):** open the rebuilt 29 Oct edition and read the "What it means" tab as a reader. Every pattern should be specific, backed by ≥2 different events, and every clue should obviously belong. **If a pattern still feels vague, fix `prompts/threads.md` and rerun this phase.** Then update `CONTEXT.md`.

---

## Global don'ts

- Don't add embeddings, a vector DB, or new infrastructure. These are prompt, schema and code-check changes.
- Don't change the design system, reading rules (robots.txt), politics neutrality rules or fact-check pass.
- Don't let the model emit links, invent forces, or set status. Code still does all three.
- Don't raise the cost much: the only new LLM call is `threads:verify` (one cheap call a day).

---

## Future work (not in this pass)

- **Automation.** There's no scheduler today, and the Foundry token is local-only, so GitHub Actions can't run it. Options:
  1. Windows Task Scheduler on the laptop runs `python run.py daily --push` each morning (laptop must be on and online).
  2. Move to a personal API key (provider and model per step in `config.yaml`; only `llm.py` changes), then a GitHub Actions cron with secrets.
  Decide after the quality pass, and after checking with Anand whether this stays on Foundry (work) or moves to a personal key (personal/open source).
- Manual "re-teach" for weak teaching cards (already parked in `CONTEXT.md`).
- A world startup-funding feed, so the India-vs-world comparison isn't all India.
- "Explain like I'm…" dial (parked).
