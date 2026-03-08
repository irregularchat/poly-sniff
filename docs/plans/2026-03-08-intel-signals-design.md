# Intel Signals: Confidence Ratings + Anomaly Detection

**Date:** 2026-03-08
**Version:** 0.4.0 → 0.5.0

## Problem

poly_sniff today is reactive and narrow: you give it one market, it checks for insiders. The search→analyze pipeline only sniffs the top 1 match. There's no way to:

- Survey a topic area for unusual betting patterns (early warning)
- See market prices as confidence signals alongside behavioral analysis
- Batch-analyze all markets matching a news event

## Design

### 1. Enhanced Search: `--sniff` and `--confidence`

**`--sniff`** replaces `--analyze`. Runs insider metrics across **all** matched active markets (not just top 1).

For each active market in search results:
1. Fetch top position holders (default 20)
2. Run 4 behavioral metrics (directional, dominance, conviction, timing)
3. Count flagged users, compute signal strength

**`--confidence`** adds columns to search results for active markets:
- **Price** — Current Yes price as implied probability (e.g., `72%`)
- **24h Δ** — Price change in last 24 hours (e.g., `+8%`)
- **Signal** — Behavioral signal strength: `STRONG` / `MODERATE` / `QUIET` / `—`

Combined output example:
```
  #  Rel  Status  Price  24h Δ  Signal    Flagged  Market
  1   70  Active   72%    +8%   STRONG    3/20     Iran response to Israel by April 15?
  2   65  Active   45%    +2%   QUIET     0/20     Iran strikes nuclear facility?
  3   60  Resolved  —      —     —         —       Iran response by Friday?
```

When `--sniff` is used, detail sections print below for each market with flagged users (same format as current `analyze` output).

**Backward compat:** `--analyze` stays as alias for `--sniff` but only processes top 1. Deprecation warning printed.

### 2. `scan` Subcommand: On-demand Anomaly Detection

Surveillance mode. No article — give it topic tags, it finds markets with unusual patterns.

```bash
poly_sniff scan --tags iran,tariffs,china
poly_sniff scan --tags iran --min-directional 0.75 --limit 30
poly_sniff scan --markets "iran-response-by-apr-15,china-tariffs-2025"
```

**Pipeline:**
1. **Discovery** — For each tag, Gamma API `tag_slug` → active events. `--markets` skips discovery.
2. **Filter** — Active only. Optional `--min-volume` to skip illiquid markets.
3. **Batch sniff** — For each market, run insider analysis pipeline.
4. **Rank** — Sort by anomaly score (flagged count + aggregate behavioral metrics).
5. **Display** — Summary table + detail sections for anomalous markets.

**CLI flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--tags`, `-t` | — | Comma-separated Polymarket tag slugs |
| `--markets`, `-m` | — | Comma-separated market slugs (skip discovery) |
| `--min-volume` | `10000` | Skip markets below this USDC volume |
| `--max-markets` | `10` | Cap on markets to analyze (rate limit protection) |
| `--limit` | `20` | Top holders to scrape per market |
| Threshold flags | Same as analyze | `--min-directional`, `--min-dominant`, etc. |

**Rate limiting:** Each market ≈ 60 API calls (market info + 20 holders × 3 endpoints). Sequential with progress indicator. `--max-markets` default 10 caps at ~600 calls.

### 3. Signal Strength Computation

New module: `poly_sniff/metrics/signal.py`

For each market, after sniffing N holders:

```python
flagged_count = users passing all 4 thresholds
avg_directional = mean(userDirectionalConsistency)
avg_late_volume = mean(lateVolumeRatio)
max_late_volume = max(lateVolumeRatio)
```

**Signal levels:**

| Level | Criteria |
|-------|----------|
| `STRONG` | `flagged >= 2` OR (`flagged >= 1` AND `max_late_volume >= 0.7`) |
| `MODERATE` | `flagged == 1` OR (`avg_directional >= 0.75` AND `avg_late_volume >= 0.3`) |
| `QUIET` | Everything else |

**Anomaly score** (sort key):
```python
anomaly_score = (flagged_count * 10) + (avg_directional * 5) + (max_late_volume * 5)
```

### 4. Architecture

**New files:**
```
poly_sniff/metrics/signal.py   # Per-market signal strength
poly_sniff/scan.py             # scan subcommand logic
```

**Modified files:**
```
poly_sniff/__main__.py         # scan subcommand, --sniff/--confidence flags
poly_sniff/output.py           # Confidence columns, signal formatting
poly_sniff/search/polymarket.py # Price fetching helper
poly_sniff/config.py           # SCAN_MAX_MARKETS, MIN_VOLUME defaults
```

**No new dependencies.** pandas, requests, tabulate already installed.

## Out of Scope (Future)

- Continuous monitoring / cron-based alerting
- Structured export (JSON/XLSX) for signals
- Briefing-ready report generation (Markdown/HTML)
- Async/parallel API calls for scan performance
- Timeline view with price history + anomaly markers (XLSX export)
