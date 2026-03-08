# poly_sniff

> Hard fork of [agile-enigma/poly_sniff](https://github.com/agile-enigma/poly-sniff) — extended with claim-to-market search, AI-powered article analysis, and multi-source market discovery.

A CLI tool for [Polymarket](https://polymarket.com) prediction market intelligence. It does two things:

1. **Search** — Find relevant Polymarket markets from news articles or claim text, using AI claim extraction, entity-based tag search, and LLM relevance ranking.
2. **Analyze** — Detect suspicious betting behavior by scraping transaction data, computing behavioral metrics, and flagging users whose trading patterns suggest insider knowledge.

## What's new in this fork

This fork extends the original insider detection tool into a broader Polymarket research toolkit:

- **`search` subcommand** — Given a URL or claim text, extracts verifiable claims via GPT, discovers matching Polymarket markets via Gamma API tag search + SearXNG, and ranks them by relevance using LLM re-ranking.
- **Paywall bypass** — Scrapes paywalled articles via archive.ph, Wayback Machine, Google AMP/webcache fallbacks with browser profile rotation.
- **Entity extraction** — Identifies key entities (countries, people, orgs) from claims and maps them to Polymarket topic tags for reliable market discovery.
- **Multi-claim ranking** — Passes all extracted claims as context to the LLM ranker for better semantic matching.
- **Market status display** — Shows Active/Resolved status in search results.

## Installation

```bash
git clone https://github.com/irregularchat/poly-sniff.git
cd poly-sniff

python3 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
pip install -e .
```

### Configuration

Copy `.env.example` to `.env` and set your ResearchTools API URL:

```bash
cp .env.example .env
# Edit .env — default is https://researchtools.net
```

The search features require a running [researchtoolspy](https://github.com/gitayam/researchtoolspy) instance for AI claim extraction and LLM ranking. The analyze features work standalone.

## Usage

### Search for markets

Find Polymarket markets related to a news article or claim:

```bash
# Search from a news article URL
poly_sniff search --url "https://www.reuters.com/world/israel-strikes-iran-oil"

# Search from a direct claim
poly_sniff search --claim "Will Iran retaliate against Israel?"

# Combine both — URL claims + explicit claim
poly_sniff search --url "https://example.com/article" --claim "tariffs on China"

# Auto-analyze the top matching market for insider behavior
poly_sniff search --url "https://example.com/article" --analyze
```

#### Search options

| Flag | Default | Description |
|------|---------|-------------|
| `--url`, `-u` | — | URL to extract claims from via AI |
| `--claim`, `-c` | — | Direct claim text to search for |
| `--analyze`, `-a` | — | Auto-run insider analysis on the top match |
| `--top-n`, `-n` | `5` | Number of results to display |
| `--min-relevance` | `50` | Minimum relevance score (0-100) |

#### Example output

```
Extracting claims from URL: https://www.ft.com/content/...
  ai claims    : 11 (wayback, 842 words)
  summary      : Tehran residents warned of acid rain after Israeli attack...
  title  : Tehran residents warned of acid rain after oil storage attack
  claims : 15

Searching Polymarket for matching markets...
  entity tags  : tehran, israel, iran
  gamma tags   : 20 events
  candidates   : 20

Ranking candidates by relevance...

  #  Rel  Status    Market                                Slug                              Reasoning
  1   70  Active    Iran response to Israel by April 15?  iran-response-to-israel-by-apr-15  Directly related...
  2   70  Resolved  Iran response to Israel by Friday?    iran-response-to-israel-by-friday  Covers same topic...
```

### Analyze a market

Detect suspicious insider trading patterns on a specific market:

```bash
# Basic analysis — prints flagged users to terminal
poly_sniff analyze will-x-happen-by-date

# Legacy syntax also works (slug found after /event/ in market URL)
poly_sniff will-x-happen-by-date

# Scrape top 50 No-side holders, flag only those who bet on the winning side
poly_sniff analyze will-x-happen-by-date --position-side No --limit 50 --resolved-outcome No

# Loosen thresholds for a wider net
poly_sniff analyze will-x-happen-by-date --min-directional 0.75 --min-dominant 0.80

# Export everything for further analysis
poly_sniff analyze will-x-happen-by-date --export-all
```

The market slug is found after `/event/` in the Polymarket URL, e.g. `polymarket.com/event/will-x-happen-by-date`.

#### Analyze options

| Flag | Default | Description |
|------|---------|-------------|
| `--resolved-outcome` | — | `Yes` or `No`. Only flag users whose dominant side matches the winning outcome. |
| `--position-side` | `Yes` | Which side's top position holders to scrape. |
| `--limit` | `20` | Number of top position holders to scrape. |
| `--late-window` | `24` | Hours before resolution that count as "late" trading. |
| `--min-directional` | `0.85` | Minimum Directional Consistency to flag. |
| `--min-dominant` | `0.90` | Minimum Dominant Side Ratio to flag. |
| `--max-conviction` | `0` | Maximum Price Conviction Score to flag. |
| `--min-late-volume` | `0.50` | Minimum Late Volume Ratio to flag. |
| `--export-profiles` | — | Export user profiles to `profiles.xlsx`. |
| `--export-transactions` | — | Export transaction data to `transactions.xlsx`. |
| `--export-scaffold` | — | Export hourly scaffold to `scaffold.xlsx`. |
| `--export-flagged` | — | Export flagged users with all metrics to `flagged_users.xlsx`. |
| `--export-all` | — | Export all four xlsx files. |

## How search works

The search pipeline has four stages:

1. **Claim extraction** — The article URL is sent to the researchtoolspy `/api/tools/extract-claims` endpoint, which scrapes the content (with paywall bypass via archive.ph/Wayback/AMP), then uses GPT to extract 5-15 verifiable claims with categories, confidence scores, and suggested prediction market questions.

2. **Market discovery** — Key entities (countries, people, organizations) are extracted from claims and mapped to Polymarket tag slugs. The Gamma API `tag_slug` parameter returns categorized events reliably. SearXNG provides supplementary results.

3. **LLM ranking** — All candidates are sent to the `/api/tools/claim-match` endpoint with the full claim context. GPT scores each market's relevance (0-100) with reasoning.

4. **Display** — Results are filtered by relevance threshold and displayed with market status (Active/Resolved).

## How insider detection works

poly_sniff pulls the top position holders for a market, retrieves their full transaction histories within that market, and runs four behavioral metrics against each user.

Users are flagged through a conjunctive filter — all four conditions must be satisfied simultaneously. A user who passes only two or three criteria is not flagged. The core idea: an insider doesn't hedge, doesn't follow the crowd, and tends to act late.

### Detection metrics

| Metric | Formula | What it measures |
|--------|---------|-----------------|
| **Directional consistency** | `abs(sum(netPosition)) / sum(abs(netPosition))` | Whether all trades point the same direction. Score of 1.0 = purely unidirectional. |
| **Dominant side ratio** | Fraction of USDC on dominant side | Capital concentration. >0.90 means nearly all capital committed one way. |
| **Price conviction score** | USDC-weighted avg of `(price - 0.50)` | Contrarian pricing. Negative = buying before market moves their way. |
| **Late volume ratio** | Fraction of USDC in final hours | Timing. Insiders often act close to resolution when they confirm info. |

All thresholds are configurable via CLI flags. Defaults live in `config.py`.

When `--resolved-outcome` is provided, an additional filter is applied: only users whose dominant side matches the winning outcome are flagged (bullish for Yes, bearish for No). When omitted, users are flagged in both directions, which is useful for pre-resolution analysis.

## Architecture

```
poly_sniff/
├── __main__.py          # CLI entry point (analyze + search subcommands)
├── config.py            # Thresholds and defaults
├── output.py            # Flagging logic and table/xlsx output
├── scaffold.py          # Hourly time-series grid builder
├── data/
│   ├── loader.py        # Parse API responses into DataFrames
│   ├── preprocessing.py # Merge profiles, compute base columns
│   └── scraper.py       # Polymarket API scraping
├── metrics/
│   ├── activity.py      # Trade count and volume metrics
│   ├── conviction.py    # Price conviction scoring
│   ├── directional.py   # Directional consistency
│   ├── dominance.py     # Dominant side ratio
│   └── timing.py        # Late volume ratio
└── search/
    ├── config.py         # Search-specific config (API URLs, limits)
    ├── claims.py         # Claim extraction (AI + metadata + URL fallbacks)
    ├── polymarket.py     # Market search (Gamma tags + SearXNG)
    └── ranker.py         # LLM + keyword relevance ranking
```

## Requirements

- Python 3.10+
- pandas, openpyxl, requests, tabulate, python-dotenv
- For search features: a [researchtoolspy](https://github.com/gitayam/researchtoolspy) instance

## Mirrors

- GitHub: [irregularchat/poly-sniff](https://github.com/irregularchat/poly-sniff)
- GitLab: [irregulars/poly-sniff](https://git.irregularchat.com/irregulars/poly-sniff)
- Original: [agile-enigma/poly-sniff](https://github.com/agile-enigma/poly-sniff)

## Disclaimer

This tool is for research and analysis purposes. Flagged users are not necessarily engaged in insider trading — the metrics identify behavioral patterns that *warrant further investigation*, not proof of wrongdoing.

## License

MIT
