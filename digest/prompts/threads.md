You maintain the memory of a personal daily news digest. Its premise: a headline (L1) matters for what it
is evidence of. An **L2 thread** is a pattern that persists across days or weeks and that **several different
events** are evidence for. Every thread is driven by one or more **L3 forces**, from this fixed list only:
{{forces}}.

Today is {{date}}. Below are today's selected headlines and the threads we are already tracking.

**Events vs patterns.** An event is one thing that happened (one election, one strike on one refinery, one
funding round, one product launch). Many articles can cover one event. A pattern needs evidence from at
least {{min_events}} **different** events. A single big event is never a pattern on its own, however many
articles it gets.

Your job:

0. **First, look across today's stories (and the candidates) for recurring shifts**: who is getting funded
   and for what, which rules governments or courts are changing, where energy and supply are moving, what
   companies are buying or building. These are what threads and candidates are for.

1. **Assign every headline.** For every item give:
   - `event`: a short, stable lowercase key for the underlying event, like `israel-election-2026`,
     `saudi-refinery-strike-oct26`, `simplismart-series-b`. An event is the whole story, not each update about
     it: the turnout, polls, counting, results and coalition talks of one election are all
     `israel-election-2026`; a funding round and later coverage of it are one key; a court case and its
     hearings are one key. **Reuse a key from "Recent event keys" when the item is about the same story**;
     make a new one only for a genuinely separate event. No dates or sub-topics in keys.
   - `action`:
     - `attach`: the item is **direct evidence** for an existing thread or candidate: it shows the claimed thing
       happening. "Could affect", "shapes", "increases pressure on", "is related to" or "same industry" do
       **not** count. Set `thread_id` to the id exactly as given.
     - `new`: the item is direct evidence for a pattern we don't track yet. Set `thread_id` to the `key` of a
       thread you define in `new_threads`.
     Check every story against **every** existing thread and candidate, not only those that share its topic
     words: a story is evidence when it is an instance of the claim, even if it's worded differently (a firm
     buying chips from a non-Nvidia supplier is an instance of "developers moving away from Nvidia").
     - `none`: one-off news that doesn't show a recurring shift. There's no quota either way: link a story
       when it plainly shows a recurring shift, leave it `none` when it doesn't.
   - For `attach` and `new`: `mechanism` is one sentence, "This story shows <claim> because <specific fact
     from the story>." and `strength` is `direct` or `indirect`. Only `direct` is kept; be honest.
     For `none`: empty `thread_id` and `mechanism`, `strength` "indirect".

2. **Define new threads** in `new_threads` (`key` is a short snake_case slug). When an item is direct evidence
   for a **specific shift that should recur** and no existing thread or candidate covers it, propose it, even
   with only one event today: code keeps it as a candidate until a second, different event arrives, so a good
   proposal costs nothing. Don't propose threads for one-off events (a single launch, a single crime, a single
   match); those stay `none`.
   - The claim names **who** (the type of actor), **what** shift, and **which direction**, in ≤ 25 words. It
     must describe a **change** (moving from X to Y, rising, falling, tightening, more/fewer), not a steady
     state ("X is funding Y", "X is investing in Y" are steady states). **One shift per claim**: don't list
     three things ("A, B and C"); if they're different shifts, they're different threads. No tags like
     "(rising)". It could turn out wrong.
     - Too broad or static: "Investors are rotating back into AI", "VCs are funding Indian AI startups",
       "AI is growing", "Geopolitical tensions persist".
     - Good: "Hyperscalers are signing long-term nuclear and gas power deals to secure data-centre capacity",
       "Indian VCs are moving money from consumer apps to deep-tech hardware".
   - `title`: a clear 4–10 word version of the claim. `nickname`: a 2–4 word handle a reader remembers.
     `plain`: the pattern in plain English, ≤ 15 words. `forces`: from the fixed list, usually 1–2.
   - Before creating a thread, check that no existing thread or candidate covers it; attach instead.
   - **Political threads (parties, elections, governments, courts, protests) must be strictly factual.** The
     claim describes only what the evidence shows: results, votes, rulings, laws, official actions, who said
     what. No motives, strategy or judgement ("tightening grip", "consolidating control", "power grab",
     "crackdown", "polarisation") unless the sources themselves report it. Nicknames are neutral descriptions
     ("BJP's council poll wins", not "Institutional Grip"). Test: would supporters and critics both accept the
     claim as a fair summary of the evidence?

3. **Look-alike pairs.** For every pair in "Look-alike pairs" decide: `merge` (set `keep` and `absorb` to the
   two ids) when they describe the same shift, or `distinct` with a one-line `difference` that a reader
   would find obvious. If you can't state an obvious difference, merge. There are {{active_count}} active
   threads; the cap is {{max_active}}. {{merge_instruction}}

4. **Candidate merges.** Candidates often describe the same shift in different words (for example "AI labs
   compete for electricity" and "hyperscalers lock in nuclear power" are one shift: AI firms scrambling for
   power). In `candidate_merges`, combine such pairs (`keep`, `absorb`: candidate ids, `reason`: one line naming
   the shared shift). Don't merge candidates that merely share a topic.

5. **Splits.** Threads in "Split candidates" have collected many different events. If their events clearly
   fall into two narrower patterns, propose a split: two new narrower threads (same fields as `new_threads`),
   each with the list of `events` (keys from that thread) that belong to it. Otherwise leave `splits` empty.

6. **Connecting the dots.** Pick one pair of threads that sit in **different sections** and share a force
   (`force` must appear in both threads' forces), and write one sentence on how they connect. Use existing
   thread ids, or keys of new threads you back with evidence from {{min_events}} events today. Leave every
   field empty if no such pair exists.

Never invent facts beyond the items given. Never output URLs.

## Existing threads (non-dormant; with their event keys)
{{threads}}

## Candidate threads (not enough different events yet; attach to them to promote them)
{{candidates}}

## Look-alike pairs (decide merge or distinct for each)
{{overlaps}}

## Split candidates
{{splits}}

## Recent event keys (reuse when an item is about the same event)
{{events}}

## Today's headlines (JSON lines: id, section, source, title, summary, why it was picked)
{{items}}
