- Cover the breadth of the section: AI, hardware and semiconductors, big-tech moves, tech finance
  (earnings, tech stocks), startups and funding, manufacturing. Don't fill it with only AI.
- **Funding coverage is required.** Pick at least 2 funding rounds when available, with at least one Indian
  startup and at least one non-Indian startup. Prefer rounds that show which sectors money is flowing to.
- For every pick, fill `funding`. If the item is about a startup raising money, set `is_funding` to true and
  give company, amount (as written, e.g. "$15M", "Rs 130 Cr"), sector (short, e.g. "climate tech",
  "health tech", "B2B SaaS") and country (where the company is based). Take these from the
  candidate's title, summary and source. Clear signals count: a rupee/crore amount or an India-focused
  startup source (Inc42, Entrackr, YourStory) means India; a city or regional outlet (e.g. "London's",
  EU-Startups) points to that country. Leave a field empty only when nothing in the item points to it.
  Otherwise set `is_funding` to false and leave the other fields empty.
