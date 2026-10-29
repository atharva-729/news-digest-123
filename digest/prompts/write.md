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
- `call`: one testable prediction tied to a thread in `open_threads`, in plain words: "If this pattern is
  real, expect X within about N months." Specific enough to be judged right or wrong later.
  `check_in_days` between 30 and 120.
- `quiz`: exactly 2 multiple-choice questions that check the reader **understood** today: why a story
  matters, which pattern it shows, or what a key word means. Not trivia about numbers or names. Each has 3
  `options` of the same kind, `answer_index` (0–2) for the one correct option, and `why` (≤ 20 words)
  explaining the answer. The answer must be checkable in the input.

Never output URLs or ids other than the ones given.

Input:
{{input}}
