# AI Discovery Prototyping

**Date:** 2026-03-08
**Version:** 0.5.0 → 0.5.1

## Problem

Current market discovery relies on regex entity extraction → Polymarket tag slugs. This misses markets that don't match extracted entities, and doesn't generate queries in the style bettors use ("Will X happen by Y?").

## Design

### New file: `poly_sniff/search/ai_discovery.py`

Three discovery strategies using GPT-5-mini, plus a comparison runner.

**Strategy A: `generate_market_queries(claims)`**
- Prompt GPT to generate 5-10 prediction market questions in Polymarket style
- Feed results to SearXNG and Gamma text search
- Catches markets phrased differently from the source claims

**Strategy B: `generate_smart_tags(claims)`**
- Prompt GPT to identify 3-6 optimal Polymarket tag slugs
- Replaces/supplements regex entity extraction
- More accurate than heuristic entity → tag mapping

**Strategy C: `semantic_discovery(claims, broad_candidates)`**
- Cast wider net (more tags), then GPT pre-filters for relevance (>30 score)
- Catches markets entity-tag approach would miss
- Runs before the existing LLM ranker

### Comparison mode: `--discovery-test`

Runs all three strategies + current approach on same input, shows:
- Candidate counts per strategy
- Overlap analysis (how many each shares with current)
- New unique discoveries per strategy
- Timing per strategy

### Dependencies

- `openai` — optional, lazy import with graceful error
- `OPENAI_API_KEY` in `.env`
- Model: `gpt-5-mini`

### Modified files

- `poly_sniff/__main__.py` — add `--discovery-test` flag to search
- `.env.example` — add `OPENAI_API_KEY`

### Out of scope

- Choosing a winner (that's after testing)
- Integrating winning strategy into default pipeline
- Parallel API calls
