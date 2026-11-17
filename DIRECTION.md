# Direction: poly_sniff

A Python CLI for Polymarket research and a hard fork of an upstream insider-detection tool. It
finds markets that match a news article or claim, scans topic areas for anomalous betting, and
flags traders whose patterns suggest insider knowledge.

Status: dormant (last change 2026-03-08). Built in two days (35 commits, v0.5.0).

## Where it is heading
- Claim-to-market search: claims extracted via a researchtoolspy instance, market discovery
  through the Gamma API and SearXNG, and LLM re-ranking (6a3579c, 9f41eb3,
  docs/plans/2026-03-08-claim-search-design.md).
- AI-heavy discovery: GPT-generated tag slugs and bettor-style phrases (b916abe, cd54eae,
  docs/plans/2026-03-08-ai-discovery-design.md).
- Intel signals: `--sniff` batch analysis, `--confidence` columns and a `scan` subcommand
  (4f59633, e40de80, docs/plans/2026-03-08-intel-signals-design.md).

## Priorities
1. Tests beyond `tests/test_signal.py` for the search and scan pipelines (inferred).
2. Settle the AI model. `ai_discovery.py` references both `gpt-5-mini` and `gpt-4o-mini` (inferred).
3. The AI discovery design targets v0.5.1. The version is still 0.5.0 (pyproject.toml,
   ai-discovery design).

## Non-goals and constraints
- Requires a researchtoolspy instance. The OpenAI key is optional, and search falls back to
  entity and keyword matching without it (README.md, 6024c2b).
- Python 3.10+, pandas, requests and tabulate; no new heavy dependencies
  (intel-signals plan "Tech Stack").

## Decisions
- 2026-03-08: Gamma `tag_slug` is the primary search, replacing the unreliable SearXNG
  `site:` filter (9f41eb3).
- 2026-03-08: `--sniff` replaces `--analyze` (intel-signals design).
- 2026-03-08: Restructured into the `poly_sniff` package with subcommands (1310209).

## Open questions for the owner
1. The README advertises paywall bypass through archive and cache mirrors, in a public repo.
   Keep that feature public?
2. Should the fork track upstream, or diverge for good?

## Related documents
- README.md, docs/plans/ (three designs and one implementation plan)
- To resume: tests, then the v0.5.1 AI-discovery comparison.
