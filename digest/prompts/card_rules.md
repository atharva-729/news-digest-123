How to write a card. The reader reads the headline to know what happened, then the explanation to get the
gist without opening the article.

- `emoji`: one emoji for the topic.
- `headline`: what happened, in plain words, ≤ 14 words. Who did what.
  - If the main actor is little known, say what they are: "Bengaluru retail-supply startup Zorit…",
    "Insurance-software maker Guidewire…".
  - No wordplay, no metaphors, no slang, no questions.
  - Good (original → headline):
    - "Simplismart raises $14 Mn from Dallas Venture Capital, NVIDIA and others" → "Nvidia backs Simplismart, a startup that cuts the cost of running AI models, in a $14M round"
    - "RBI keeps repo rate unchanged at 5.5%" → "RBI holds its key lending rate at 5.5%"
    - "Fleetwood 1-1 Arsenal (5-3 pens): champions dumped out of Carabao Cup" → "League Two side Fleetwood knocks champions Arsenal out of the Carabao Cup on penalties"
- `explain`: 2–4 sentences, ≤ 65 words. What happened with the key specifics (who, what, how much, where),
  then the context a well-read generalist wouldn't have:
  - For a company: what it actually sells or does, for whom, and anything notable about it (stage, scale,
    backers) that the article gives.
  - For a person or body that isn't widely known: who they are, in a clause.
  - Niche terms explained in a short clause. Don't explain general-knowledge things.
  Only facts from the item's `article` text. If `limited` is true, we only have the headline: write 1–2
  sentences with what the headline says and the specific context a reader needs (e.g. who the company is,
  if the input says); don't guess details, and never comment on what the input does or doesn't contain.
- `why`: why it matters, one sentence, ≤ 25 words. Connect to the bigger pattern (`pattern`) when the item
  has one, without naming the pattern. Lead with the consequence or who it affects, and vary how you start:
  never begin with "This", "It shows", "It highlights" or "It reflects".
  **Politics, courts, elections, policing, conflicts:** the `why` must be a factual consequence or next step
  the article reports (seats now held, what the ruling requires, when the vote is), not an interpretation
  of anyone's intentions or strategy.
- `highlight`: the 2–5 most important words copied **exactly** from `why`. Empty string if none.
