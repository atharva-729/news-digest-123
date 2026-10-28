How to write a card. The reader reads the headline to know what happened, then the explanation to get the
gist without opening the article.

- `emoji`: one emoji for the topic.
- `headline`: what happened, in plain words, ≤ 14 words. Who did what. A 10-year-old should get it.
  - If the main actor is little known, say what they are: "A Bengaluru startup that…", "An insurance-software firm…".
  - No wordplay, no metaphors, no slang, no unexplained jargon, no questions.
  - Good (original → headline):
    - "Simplismart raises $14 Mn from Dallas Venture Capital, NVIDIA and others" → "Nvidia and other investors put $14 million into a startup that makes AI cheaper to run"
    - "RBI keeps repo rate unchanged at 5.5%" → "RBI leaves its main interest rate unchanged at 5.5%"
    - "Fleetwood 1-1 Arsenal (5-3 pens): champions dumped out of Carabao Cup" → "Small club Fleetwood knocks champions Arsenal out of a cup on penalties"
    - "Govt plans further easing of FDI rules for investments linked to China" → "India plans to relax its rules on investment from companies with Chinese links"
- `explain`: 2–4 short sentences, ≤ 70 words. In order, as the story allows:
  1. What happened, with the key details (who, what, how much, where).
  2. For a company: what it actually does, in everyday terms (what you could do with its product).
  3. Any jargon explained in plain words.
  Only facts from the item's `article` text. If `limited` is true, we only have the headline: write 1–2
  sentences that restate it plainly and explain its key term; don't guess details.
- `why`: why it matters, one sentence, ≤ 25 words. Connect to the bigger pattern (`pattern`) when the item
  has one, in plain words, without naming the pattern. Lead with the consequence or who it affects, and vary
  how you start: never begin with "This", "It shows", "It highlights" or "It reflects".
  Good: "Investors are still paying for tools that help small shops sell faster."
- `highlight`: the 2–5 most important words copied **exactly** from `why`. Empty string if none.
