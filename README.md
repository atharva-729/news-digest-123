# L1-L2-L3 News Digest

> Headlines tell you what happened. this digest tells you what it's evidence of.

A personal, automated daily newsletter that reads ~200 headlines a morning and turns them into a short, fun read organised around **patterns that persist across days**, not a pile of disconnected events.

**Idea credit:** the L1/L2/L3 framework comes from an Instagram reel by [@neworderindia](https://www.instagram.com/neworderindia/). This project is an implementation of that idea, so credit them visibly in the README and in every newsletter footer.

---

## The framework (read this first; everything else follows from it)

| Level | What it is | Example | Lifespan |
|---|---|---|---|
| **L1 — Headline** | Smallest unit of information, one event | "Nvidia reports record data-centre revenue" | 1 day |
| **L2 — Thread** | A pattern that many L1s are evidence for | "AI infra is now bottlenecked by power, not chips" | Weeks to months |
| **L3 — Force** | The deep driver underneath the patterns | Technology · Capital · Geopolitics · Regulation · Demographics | Permanent |

The key design decision is that **L2 threads are stored and carry over between days**. Each morning, new L1s are attached as evidence to existing threads, or start a new one. The newsletter reports *what changed in the threads*, not just what happened. Without this memory it's just another digest.

---

## Section mix (applies to L1 selection only)

| Section | Share | Contents |
|---|---|---|
| `tech` | 50% | AI, hardware/semis, big-tech company moves, tech-related finance (earnings, tech stocks), **startups & funding — India vs world, which sectors are getting money**, manufacturing |
| `politics_india` | 15% | Indian politics & policy |
| `politics_world` | 10% | International politics, geopolitics |
| `markets` | 10% | Oil/commodities, non-tech stocks, central banks (RBI, Fed, BoJ, ECB…), macro policy |
| `sports` | 5% | Global sports highlights |
| `fun` | 10% | Trivia / something genuinely fun from the period |

Rules:
- Percentages = share of **L1 items shown**, not of words.
- Tech-related finance goes in `tech`, not `markets`.
- An item lives in exactly one section. L2 threads **can and should cross sections**; that's the point.
- The mix lives in `config.yaml`, never hardcoded.

---

## Stack (keep it boring)

- **Python 3.11+**, plain scripts. No web framework.
- **feedparser** for RSS, **httpx** for fetching.
- **LLM Foundry** (OpenAI-compatible chat completions, `gpt-5-mini`) with strict structured JSON output. Model name lives in config. (Originally Gemini's free tier; switched on 2026-10-28 because the work laptop's proxy and the free-tier quota made it unreliable.)
  - Optional: the Claude API for the final writing step only, behind a config switch. Pro/Gemini subscriptions do *not* give API keys.
- **State = JSON files in the repo** (`data/threads.json`, `data/items/YYYY-MM-DD.json`, `data/calls.json`). No database.
- **Jinja2** for the HTML newsletter.
- Runs locally (`python run.py daily --push`); no CI, so no secrets on GitHub. **GitHub Pages** serves `docs/` from `main`. **Email** via Gmail SMTP with an app password.

Secrets (`FOUNDRY_TOKEN`, `SMTP_USER`, `SMTP_APP_PASSWORD`, `MAIL_TO`) go only in a local `.env` (git-ignored), never on GitHub.

---

## Repo layout (target)

```
l1l2l3-news-digest/
├── config.yaml            # section mix, feeds, model, edition size, thread rules
├── digest/
│   ├── ingest.py          # Phase 1
│   ├── select.py          # Phase 2
│   ├── threads.py         # Phase 3
│   ├── write.py           # Phase 4
│   ├── deliver.py         # Phase 5
│   ├── llm.py             # single wrapper around the model API
│   └── prompts/           # prompts as .md files, not inline strings
├── templates/newsletter.html.j2
├── data/                  # committed state
├── docs/                  # generated archive, served by GitHub Pages
└── run.py                 # `python run.py daily --push` / `python run.py weekly --push`
```

---

## Phase 0 — Skeleton & config

**Do**
- Create the layout above, `requirements.txt`, `.env.example`, `.gitignore`.
- Write `config.yaml` with the section mix, an empty feeds list per section, `edition_size: 25` (total L1 items shown), model name, and thread settings (`dormant_after_days: 10`, `max_active_threads: 15`).
- Write `llm.py`: one function `generate_json(prompt, schema) -> dict` with retries and backoff, and one `generate_text(prompt) -> str`. Everything else calls these. This makes swapping Gemini ↔ Claude a one-file change.

**Don't**
- Don't build a CLI framework, plugin system, or abstract base classes. `run.py` with argparse is enough.

**✅ Checkpoint 0:** `python run.py --help` works, `llm.generate_json` returns valid JSON for a toy schema using the real API key.

---

## Phase 1 — L1 ingestion

**Do**
- Add 3–6 feeds per section to `config.yaml`. Starting candidates (verify each one actually returns items, drop dead ones):
  - tech: TechCrunch, The Verge, Ars Technica, Hacker News front page (hnrss), Google News RSS searches (e.g. `AI`, `semiconductors`, `startup funding`)
  - India startups: **Inc42**, **Entrackr**, YourStory feeds; Google News search `"raises" funding India startup` with `hl=en-IN&gl=IN`
  - manufacturing: Google News search for India manufacturing / PLI / semiconductor fab
  - politics_india: The Hindu, Indian Express, Google News India politics
  - politics_world: BBC World, Al Jazeera, Google News world
  - markets: Google News searches for RBI, Fed, crude oil, Sensex/Nifty, Bank of Japan; Mint / Economic Times markets feeds
  - sports: BBC Sport, ESPN, Google News sports
  - fun: Google News searches for "odd news" / "bizarre", plus anything quirky surfaced from other sections
- Fetch all feeds and normalise each item to `{id, section, title, summary, url, source, published_at}`. `id` = short hash of the canonical URL.
- Keep only items from the last 24h (weekly mode: 7 days).
- Dedupe: exact URL, then near-duplicate titles (simple token-set similarity like `rapidfuzz` ≥ 85). Keep the earliest or most authoritative source and record other sources in `also_covered_by`.
- Save to `data/items/YYYY-MM-DD.json`.

**Don't**
- Don't bypass paywalls or bot checks. Ingest stores title + RSS summary + link. (Changed 2026-10-29: after selection,
  the 25 picks are *read* (feed text, or the article page where robots.txt allows us and AI assistants that fetch
  for a user) so they can be explained simply. That text stays in the git-ignored `cache/`, is never published,
  and only our own explanation plus a link appears on the site.)
- Don't use the LLM here. Ingestion must be deterministic and cheap.
- Don't fail the whole run if one feed is down; log and continue.

**✅ Checkpoint 1:** one run produces 100–300 deduped items. Print counts per section. Every section has at least ~10 candidates. Eyeball 20 random items for junk.

---

## Phase 2 — Selection by mix

**Do**
- Compute per-section budgets from `edition_size × share` (round, then fix the total).
- For each section, one LLM call: given the candidates (id, title, summary, source), pick the top N by significance, and return **ids only** plus a one-line reason each. Use a JSON schema.
- Tech prompt must ensure startup/funding coverage: at least 2 funding items when available, with India and non-India both represented, and the sector of each funded company tagged.
- Move tech-related finance into `tech` if the feeds misfiled it.

**Don't**
- Don't let the model return URLs or titles; it returns ids, and code looks up everything else. **This is the main anti-hallucination rule for the whole project: the model never produces a link.**
- Don't pick "most clicky". The prompt should prefer items that are evidence of something larger.

**✅ Checkpoint 2:** selected items match the budget per section (±1). All returned ids exist in the day's file. Read the selection: would you have picked roughly the same?

---

## Phase 3 — L2 threads & L3 forces (the core)

**Thread schema** (`data/threads.json`):
```json
{
  "id": "t_ai_power_bottleneck",
  "title": "AI infra is now bottlenecked by power, not chips",
  "claim": "Specific, directional, falsifiable statement",
  "forces": ["technology", "capital"],
  "sections": ["tech", "markets"],
  "status": "active | heating | cooling | dormant",
  "created": "2026-10-28",
  "evidence": [{"date": "2026-10-28", "item_id": "a1b2c3", "note": "why this is evidence"}],
  "last_seen": "2026-10-28"
}
```

**Do**
- L3 forces are a **fixed list** in config: technology, capital, geopolitics, regulation, demographics. The model may not invent new ones.
- Daily LLM call: input = selected L1 items + all non-dormant threads (title + claim + last 3 evidence notes). Output per item: `attach_to: <thread_id>` or `new_thread: {...}` or `none`. Also output status changes.
- Thread quality rules, enforced in the prompt **and** checked in code:
  - A claim must be specific and directional. "AI is growing" is invalid; "Hyperscaler capex is shifting from GPUs to power and cooling" is valid.
  - A new thread needs **≥2 L1s** as evidence, or it's held in a `candidate_threads` list until a second item shows up.
  - Status is computed in code from evidence counts: more evidence this week than last → heating; none for `dormant_after_days` → dormant.
- Cap active threads at `max_active_threads`. If over, the model must propose a merge.
- Also ask for **one cross-domain link** per day: two threads from different sections that share a force, with one sentence on the connection.

**Don't**
- Don't let the model delete threads. Dormant threads stay in the file; they can wake up.
- Don't store anything the model says about an item without an `item_id` that exists.
- Don't use embeddings or a vector DB yet. At <20 threads the LLM can hold them all in context. Revisit only if this becomes a client product.

**✅ Checkpoint 3 (most important one):** run Phases 1–3 for **3–5 real mornings**, then read `threads.json` yourself. Are the threads sharp and non-obvious? Are attachments sensible? If threads are generic, fix the prompt **before** moving on. Nothing downstream can rescue bad threads.

---

## Phase 4 — Writing the newsletter

**Edition structure (daily):**
1. **Big picture:** 2–3 sentences on the single biggest thread movement today.
2. **Thread scoreboard:** 🔥 heating / 🧊 cooling / 🆕 new, one line each, with the force(s) as small tags.
3. **Sections in mix order:** each L1 as a one-line take plus `→ evidence of: <thread>` when attached. Funding items show `company · amount · sector · country`.
4. **India vs world startup pulse** (tech section): which sectors raised money in India vs elsewhere in this period, built from the funding items only.
5. **Connecting the dots:** the cross-domain link from Phase 3.
6. **Making a call:** one testable prediction tied to a thread ("If this is real, expect X within ~3 months"). Append it to `data/calls.json` with a review date.
7. **Fun:** one trivia or fun item, **picked from the day's ingested items**, not invented.
8. **Quiz:** 3 questions about L2/L3 (e.g. "Which two threads did the Nvidia earnings feed?"), answers hidden in a `<details>` block.
9. Footer: idea credit to the reel creator, sources.

**Do**
- Tone: smart friend over chai, light humour, zero filler. Put the tone guide in `prompts/style.md`.
- Writer gets structured data (items, threads, link, call) and returns structured sections; Jinja2 renders the HTML. Links are inserted by the template from item ids.
- Target a 5–7 minute read.

**Don't**
- Don't let the writer add facts that aren't in the input items. Prompt it to say less rather than guess.
- Don't produce markdown and convert it. Render the HTML directly with inline CSS (email clients hate stylesheets).

**✅ Checkpoint 4:** generate 3 editions from saved Phase 3 data. Open them in a browser and in an actual email. Check that every link works, every claim traces to an item, the quiz answers are correct, and it's fun to read. Ask: would I open this tomorrow?

---

## Phase 5 — Delivery & schedule

**Do**
- `deliver.py`: send the HTML via Gmail SMTP (app password). Write the edition to `docs/YYYY-MM-DD.html` and update `docs/index.html` (a simple list of past editions).
- ~~GitHub Actions workflow~~ Dropped (2026-10-28): company LLM secrets must not go into GitHub. Instead `python run.py daily --push` runs locally and pushes `data/` + `docs/`; Pages deploys from branch `main`, folder `/docs`.
- Add a dry-run flag: `python run.py daily --no-send`.

**Don't**
- Don't add a subscriber system, unsubscribe links, or a mailing service. It's one recipient (you).
- Don't commit `.env` or put secrets in logs.

**✅ Checkpoint 5:** a manual `workflow_dispatch` run emails you and the Pages archive updates. Then let the cron run for 3 mornings untouched.

---

## Phase 6 — Weekly edition & calls review (after a week of dailies)

**Do**
- `python run.py weekly` on Sundays: no new headlines. Show how each thread moved over the week (evidence count, status changes), the threads that died or were born, and **review any calls due** (`right / wrong / too early`, judged against the week's items).
- Monthly (optional): a "map" page on the site showing threads grouped by force, built with a simple static chart.

**Don't**
- Don't let the weekly re-summarise headlines. It's thread-only.

**✅ Checkpoint 6:** first weekly edition reads like "here's what changed in the world this week", not like a longer daily.

---

## Global don'ts

- Don't over-engineer: no DB, no queue, no frontend framework, no agents framework.
- Don't let the model emit URLs, invent trivia, or invent forces.
- Don't store or republish full article text (it's read into `cache/` for explanations only, never committed).
- Don't make the repo public until the employer-IP question is cleared (see below).

## Later (only if it becomes a team/client project)

- Swap RSS for client-licensed feeds; the L2/L3 layer stays the same.
- Embeddings for thread matching once threads number in the hundreds.
- Multi-user configs (each reader sets their own mix).
- Licence: decide before going public. Check with your manager first, since the same idea may be pitched to clients.