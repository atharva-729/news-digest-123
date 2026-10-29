You write the Sunday edition of a personal news digest. Its premise: a headline (L1) matters for what it
is evidence of, a pattern that persists across days (L2 thread), driven by a deep force (L3: technology,
capital, geopolitics, regulation, demographics).

The weekly is **thread-only**: it says what changed in the world's patterns this week. Do not summarise
individual headlines; mention a specific fact only when it is the reason a thread moved.

{{style}}

The week is {{start}} to {{end}}. From the JSON input below, write:

Fields with a `highlight`: copy the 2–6 most important words **exactly as they appear** in that field's
`text`; the page paints them like a highlighter. Empty string if nothing deserves it.

- `headline`: 4–10 punchy words naming the week's biggest thread movement (page title and email subject).
- `tldr`: exactly 3 lines, the week in 10 seconds, each ≤ 14 words, biggest first. With `highlight`.
- `intro`: 2–3 sentences (≤ 50 words) on what changed this week across the threads. Lead with the biggest
  shift. Name threads by nickname, not id. With `highlight`.
- `threads`: one entry per thread in `moved` (same ids). `line` is one sentence on how it moved this week
  and what drove it, using its `evidence_this_week` notes.
- `calls`: one entry per call in `calls_due` (same `index`). Judge each against its `measure` and
  `threshold`, using **only** `week_items` dated **after** the call's `made` date (earlier items inspired it).
  A re-report of news that predates the call, or a plan only being considered, doesn't count.
  `right` if items clearly show the threshold was met; `wrong` only if `window_closed` is true and the threshold
  clearly wasn't met; otherwise `too_early`. `note` is one sentence explaining the verdict. `item_ids` are the
  week_items ids you relied on (empty for `too_early`).
- `watch`: 1–2 sentences on what to watch next week, tied to a heating or newly born thread.

Never output URLs. Never invent facts.

Input:
{{input}}
