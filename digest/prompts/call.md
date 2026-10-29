You write one prediction for a news digest's pattern tracker. A previous attempt was rejected:

{{problems}}

Previous attempt: {{previous}}

{{style}}

Write a new `call` about one thread in `call_candidates` (use its `id` as `thread_id`; prefer status new or
building). It must be able to fail:
- `prediction`: the testable statement in plain words.
- `measure`: a real-world outcome (a deal, price, vote, rule, filing), never how much news there is about it.
- `threshold`: a number or a named event. Never "more" or "another" on their own.
- `window_days`: 30–120. `could_fail_because`: one line. `confidence`: integer 20–80, your honest odds.

Input:
{{input}}
