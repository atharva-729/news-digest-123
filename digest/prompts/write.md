You write the top of a daily news digest and its quiz. The story cards are already written (in the input).
The digest's idea: a headline (L1) matters for what it is evidence of, a pattern that keeps happening (L2),
driven by a deep force (L3: technology, capital = money, geopolitics = countries competing, regulation =
rules, demographics = who people are).

{{style}}

Today is {{date}}. Write these fields from the JSON input below. Everything must trace to the input.

**Highlights.** Fields with a `highlight`: copy the 2–5 most important words **exactly as they appear** in
that field's `text`. Empty string if nothing deserves it.

- `tldr`: exactly 3 lines: the three things worth knowing today, biggest first. Each a full, plain sentence,
  ≤ 16 words, about a different story or pattern. Say the news itself; don't use pattern names here.
  With `highlight`.
- `hero`: "The big picture": 2–3 plain sentences (≤ 55 words) on the biggest pattern movement today: what
  the pattern is (use its `one_line` idea), and which of today's stories pushed it. Use the pattern's name.
  With `highlight`.
- `scoreboard`: one entry per thread in `thread_moves` (same ids): ≤ 15 plain words on which story moved it
  today. Don't start with "New:" or "Heating:".
- `forces`: one entry per force in `forces_today` (same names): ≤ 20 plain words on what that force did
  today across its patterns.
- `pulse_india`, `pulse_world`: ≤ 25 words each, which kinds of startups got money in India vs elsewhere,
  only from `funding`. Explain sector words. Empty string if that side has no rounds.
- `dots`: ≤ 45 plain words on how the two patterns in `cross_link` connect. Empty string if it's null.
- `call`: one prediction that **can fail**, about a thread in `call_candidates` (prefer ones with status
  new or building). Fields:
  - `prediction`: the testable statement in plain words.
  - `measure`: a **real-world outcome** we will check in the news: a deal signed, a price level, a vote, a
    rule taking effect, a filing ("number of US utility power deals naming a data-centre buyer"). Never how
    much news there is ("number of stories about X" can't fail).
  - `threshold`: a number or a named event ("at least 3", "Constellation signs a second hyperscaler contract").
    Never "more" or "another" on their own.
  - `window_days`: 30–120. `could_fail_because`: one line on what would make it wrong.
  - `confidence`: integer 20–80, your honest odds. Not near-certain (no "expect more deals"), not a wild guess.
- `quiz`: exactly 3 multiple-choice questions, each one of these types only:
  1. `evidence`: "Which of today's stories is evidence for <pattern>?" `thread_id` = that pattern's id; the 3
     `options` are today's story headlines **copied exactly** from `stories`; only the right one has that
     `pattern_id`.
  2. `force`: "Which force connects <story A> and <story B>?" `item_ids` = the two stories' ids (both must have
     a pattern); `options` are force names from `forces`.
  3. `weaken`: "Which headline would weaken <pattern>?" `thread_id` set; options are plausible hypothetical
     headlines; exactly one cuts against the pattern.
  4. `why`: "Why does <story> matter?" `item_ids` = [that story]; every option is a plausible reading, only
     one matches the story's `why`.
  Every wrong option must be something a reader who skimmed could believe. No absurd options. `answer_index`
  (0–2) is the correct option; `why` (≤ 20 words) explains it. Leave `thread_id`/`item_ids` empty when unused.

Never output URLs or ids other than the ones given.

Input:
{{input}}
