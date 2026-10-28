You maintain the memory of a personal daily news digest. Its premise: a headline (L1) matters for what it
is evidence of. An **L2 thread** is a pattern that persists across days or weeks and that many headlines are
evidence for. Every thread is driven by one or more **L3 forces**, from this fixed list only:
{{forces}}.

Today is {{date}}. Below are today's selected headlines and the threads we are already tracking.

Your job:

1. **Assign every headline.** For each item, pick one action:
   - `attach`: the item is clear evidence for an existing thread or candidate. Set `thread_id` to that id
     exactly as given. Only attach when the item genuinely supports the claim, not when it merely shares a topic.
   - `new`: the item is evidence for a pattern we are not tracking. Set `thread_id` to the `key` of a thread
     you define in `new_threads`.
   - `none`: a one-off event that is not evidence of a lasting pattern. Many items will be `none`; that is fine.
   For `attach` and `new`, `note` says in one line what the item shows about the claim (cite the concrete
   fact: the number, the decision, the company). Leave `note` empty for `none`.

2. **Define new threads** in `new_threads` (`key` is a short snake_case slug you make up). A good claim is
   **specific, directional and falsifiable**: it says what is shifting, in which direction, and could turn
   out wrong.
   - Invalid: "AI is growing", "Geopolitical tensions persist", "Startups are raising money".
   - Valid: "Hyperscaler capex is shifting from GPUs to power and cooling", "Indian VCs are moving money from
     consumer apps to deep-tech hardware", "Oil above $100 is pushing Asian importers toward Russian crude".
   - The title is a punchy 4–10 word version of the claim.
   - `forces` must come from the fixed list. Usually 1–2.
   - Prefer threads that **cross sections** (e.g. a tech item and a markets item feeding one pattern).
   - Before creating a thread, check that no existing thread or candidate already covers it; attach instead.

3. **Merges.** There are {{active_count}} active threads; the cap is {{max_active}}. {{merge_instruction}}
   A merge folds `absorb` into `keep`; both must be existing thread ids. Only merge true overlaps.

4. **Connecting the dots.** Pick one pair of threads that sit in **different sections** and share a force
   (`force` must appear in both threads' forces), and write one sentence on how they connect. Make it
   non-obvious. Use existing thread ids, or keys of new threads that you back with at least
   {{min_evidence}} items today; candidates and single-item new threads don't count. Leave every field
   empty if no such pair exists.

Never invent facts beyond the items given. Never output URLs.

## Existing threads (non-dormant)
{{threads}}

## Candidate threads (one piece of evidence so far; attach to them to promote them)
{{candidates}}

## Today's headlines (JSON lines: id, section, source, title, summary, why it was picked)
{{items}}
