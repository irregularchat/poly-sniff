# poly_sniff

A CLI tool that sniffs out suspicious betting behavior on [Polymarket](https://polymarket.com) prediction markets. It scrapes transaction data for a given market, computes behavioral metrics for each user, and flags those whose trading patterns are suggestive of insider knowledge.

## How it works

poly_sniff pulls the top position holders for a market, retrieves their full transaction histories, and runs four behavioral metrics against each user. Users who pass *all four* thresholds simultaneously are flagged and printed to terminal.

The core idea: an insider doesn't hedge, doesn't follow the crowd, and tends to act late. poly_sniff looks for exactly that — unidirectional conviction, contrarian pricing, capital concentration on one side, and disproportionate activity near resolution.

## Installation

```bash
# Install globally from GitHub
pip install git+https://github.com/agile-enigma/poly_sniff.git

# Or clone and install locally
git clone https://github.com/agile-enigma/poly_sniff.git
cd poly_sniff
pip install .

# Or editable install for development
pip install -e .
```

After installation, `poly_sniff` is available as a global command.

## Quick start

```bash
poly_sniff will-x-happen-by-date
```

## Usage

```
poly_sniff <market_slug> [options]
```

### Required

| Argument | Description |
|----------|-------------|
| `market_slug` | Slug of the Polymarket market to analyze (from the market URL) |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--resolved-outcome` | — | `Yes` or `No`. Only flag users whose dominant side matches the winning outcome. |
| `--position-side` | `Yes` | Which side's top position holders to scrape. |
| `--limit` | `20` | Number of top position holders to scrape. |
| `--late-window` | `24` | Hours before resolution that count as "late" trading. |
| `--min-directional` | `0.85` | Minimum userDirectionalConsistency to flag. |
| `--min-dominant` | `0.90` | Minimum userDominantSideRatio to flag. |
| `--max-conviction` | `0` | Maximum userPriceConvictionScore to flag. |
| `--min-late-volume` | `0.50` | Minimum lateVolumeRatio to flag. |
| `--export-profiles` | — | Export user profiles to `profiles.xlsx`. |
| `--export-transactions` | — | Export transaction data to `transactions.xlsx`. |
| `--export-scaffold` | — | Export hourly scaffold to `scaffold.xlsx`. |
| `--export-flagged` | — | Export flagged users with all metrics to `flagged_users.xlsx`. |
| `--export-all` | — | Export all four xlsx files. |

### Examples

```bash
# Basic run — prints flagged users to terminal
poly_sniff will-x-happen-by-date

# Scrape top 50 No-side holders, flag only those who bet on the winning side
poly_sniff will-x-happen-by-date --position-side No --limit 50 --resolved-outcome No

# Loosen thresholds to cast a wider net
poly_sniff will-x-happen-by-date --min-directional 0.75 --min-dominant 0.80 --min-late-volume 0.30

# Export everything for further analysis in Tableau
poly_sniff will-x-happen-by-date --export-all
```

## Terminal output

Flagged users are printed as a table:

```
userName     proxyWallet   joinDate_est          xUsername
───────────  ────────────  ────────────────────  ──────────
suspectuser  0xa3f91...    2025-02-28 09:14:00   @suspect
anonwhale    0x7cb02...    2025-03-01 01:30:00   —
```

## Exports

When any `--export-*` flag is set, xlsx files are placed in a timestamped folder:

```
output_will-x_20250307_141523/
├── profiles.xlsx
├── transactions.xlsx
├── scaffold.xlsx
└── flagged_users.xlsx
```

The `flagged_users.xlsx` includes all metric values for each flagged user, not just the summary columns shown in terminal.

## Detection metrics

poly_sniff uses four behavioral metrics. A user must trip *all four* to be flagged — any single metric alone could be innocent, but the combination is hard to explain away.

### Directional consistency

`abs(sum(netPosition)) / sum(abs(netPosition))`

Measures whether a user's trades all point in the same direction. A score of 1.0 means every trade was unidirectional. An insider doesn't flip back and forth — they know the answer and bet accordingly.

### Dominant side ratio

Fraction of total USDC volume on the user's dominant side. Buying Yes and selling No both count as bullish; buying No and selling Yes both count as bearish. A ratio above 0.90 means the user committed nearly all their capital to one direction.

### Price conviction score

USDC-weighted average of `(price - 0.50)`, flipped by trade side. A negative score means the user was buying at prices where the market hadn't yet moved in their direction — they were contrarian. Insiders trade *before* the market catches up, so they show up as contrarian. Someone buying Yes at 0.30 who turns out to be right is far more suspicious than someone buying Yes at 0.80.

### Late volume ratio

Fraction of the user's total USDC volume placed within the final hours before market resolution (configurable via `--late-window`). Insiders often act close to resolution because that's when they receive or confirm their information.

### Resolved outcome filter

When `--resolved-outcome` is provided, an additional filter is applied: only users whose dominant side matches the winning outcome are flagged. Someone who bet heavily on the losing side with high confidence isn't an insider — they're just wrong.

## Scaffold export

The `--export-scaffold` option produces an hourly time-series grid (every hour × every user) suitable for Tableau line chart visualization. It includes cumulative position columns (`cumNetPosition`, `cumWeightedPosition`) that show how each user's directional exposure built up over time. An insider's cumulative position will look like a steady ramp in one direction, especially steepening near the end.

## Requirements

- Python 3.10+
- pandas
- openpyxl
- requests

## Disclaimer

This tool is for research and analysis purposes. Flagged users are not necessarily engaged in insider trading — the metrics identify behavioral patterns that *warrant further investigation*, not proof of wrongdoing.

## License

MIT
