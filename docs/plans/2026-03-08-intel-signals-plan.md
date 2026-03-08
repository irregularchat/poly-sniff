# Intel Signals Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add confidence ratings and anomaly detection to poly_sniff — `--sniff` batch-analyzes all matched markets, `--confidence` shows price/signal columns, `scan` subcommand discovers anomalous markets by topic tag.

**Architecture:** Three layers — (1) `metrics/signal.py` computes per-market signal strength from existing per-user metrics, (2) `scan.py` orchestrates tag-based discovery → batch sniff → ranked display, (3) `__main__.py` wires new flags and subcommand into CLI. Both search `--sniff` and `scan` converge on the same sniff pipeline.

**Tech Stack:** Python 3.10+, pandas, requests, tabulate (all existing deps).

---

### Task 1: Add config defaults for scan and signal

**Files:**
- Modify: `poly_sniff/config.py`

**Step 1: Add new constants**

```python
# Scraper defaults
SCRAPER_LIMIT = 20

# Default position side
POSITION_SIDE = 'Yes'

# Late window default (hours before resolution counted as "late")
LATE_WINDOW_HOURS = 24

# Flagging thresholds
MIN_DIRECTIONAL = 0.85
MIN_DOMINANT = 0.90
MAX_CONVICTION = 0
MIN_LATE_VOLUME = 0.50

# Scan defaults
SCAN_MAX_MARKETS = 10
SCAN_MIN_VOLUME = 10000
```

**Step 2: Verify import works**

Run: `cd /Users/sac/Git/poly-sniff && python -c "from poly_sniff import config; print(config.SCAN_MAX_MARKETS)"`
Expected: `10`

**Step 3: Commit**

```bash
git add poly_sniff/config.py
git commit -m "feat(config): add scan defaults (max markets, min volume)"
```

---

### Task 2: Create `metrics/signal.py` — signal strength computation

**Files:**
- Create: `poly_sniff/metrics/signal.py`
- Create: `tests/test_signal.py`

**Step 1: Write failing tests**

Create `tests/test_signal.py`:

```python
import pandas as pd
import pytest
from poly_sniff.metrics.signal import compute_signal


def _make_df(rows):
    """Helper: build a metrics DataFrame from simplified row dicts."""
    return pd.DataFrame(rows)


class TestComputeSignal:
    def test_quiet_no_flagged(self):
        """No flagged users, normal metrics → QUIET."""
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.5,
             'userDominantSideRatio': 0.6, 'userPriceConvictionScore': 0.1,
             'lateVolumeRatio': 0.1},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.4,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'QUIET'
        assert result['flagged_count'] == 0

    def test_moderate_one_flagged(self):
        """One user passes all thresholds → MODERATE."""
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.6},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.4,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'MODERATE'
        assert result['flagged_count'] == 1

    def test_strong_two_flagged(self):
        """Two users pass all thresholds → STRONG."""
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.6},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.88,
             'userDominantSideRatio': 0.92, 'userPriceConvictionScore': -0.05,
             'lateVolumeRatio': 0.55},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'STRONG'
        assert result['flagged_count'] == 2

    def test_strong_one_flagged_high_late_volume(self):
        """One flagged + max_late_volume >= 0.7 → STRONG."""
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.75},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.4,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'STRONG'
        assert result['flagged_count'] == 1

    def test_moderate_elevated_metrics_no_flagged(self):
        """No flagged users but elevated aggregate metrics → MODERATE."""
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.80,
             'userDominantSideRatio': 0.70, 'userPriceConvictionScore': 0.1,
             'lateVolumeRatio': 0.35},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.78,
             'userDominantSideRatio': 0.65, 'userPriceConvictionScore': 0.05,
             'lateVolumeRatio': 0.40},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'MODERATE'

    def test_anomaly_score_ordering(self):
        """STRONG markets score higher than QUIET."""
        strong_df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.8},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.88,
             'userDominantSideRatio': 0.92, 'userPriceConvictionScore': -0.05,
             'lateVolumeRatio': 0.7},
        ])
        quiet_df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.3,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        strong = compute_signal(strong_df)
        quiet = compute_signal(quiet_df)
        assert strong['anomaly_score'] > quiet['anomaly_score']

    def test_empty_dataframe(self):
        """Empty DataFrame → QUIET with zero scores."""
        df = pd.DataFrame(columns=['proxyWallet', 'userDirectionalConsistency',
                                    'userDominantSideRatio', 'userPriceConvictionScore',
                                    'lateVolumeRatio'])
        result = compute_signal(df)
        assert result['signal_level'] == 'QUIET'
        assert result['flagged_count'] == 0
        assert result['anomaly_score'] == 0

    def test_result_keys(self):
        """Result dict has all expected keys."""
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.5,
             'userDominantSideRatio': 0.6, 'userPriceConvictionScore': 0.1,
             'lateVolumeRatio': 0.1},
        ])
        result = compute_signal(df)
        assert set(result.keys()) == {
            'signal_level', 'anomaly_score', 'flagged_count',
            'avg_directional', 'avg_late_volume', 'max_late_volume',
        }
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/sac/Git/poly-sniff && python -m pytest tests/test_signal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'poly_sniff.metrics.signal'`

**Step 3: Implement `metrics/signal.py`**

```python
from poly_sniff import config


def compute_signal(
    metrics_df,
    min_directional: float = None,
    min_dominant: float = None,
    max_conviction: float = None,
    min_late_volume: float = None,
) -> dict:
    """Compute per-market signal strength from per-user metrics.

    Args:
        metrics_df: DataFrame with one row per user, containing columns:
            userDirectionalConsistency, userDominantSideRatio,
            userPriceConvictionScore, lateVolumeRatio
        Threshold args override config defaults.

    Returns:
        dict with keys: signal_level, anomaly_score, flagged_count,
        avg_directional, avg_late_volume, max_late_volume
    """
    min_dir = min_directional if min_directional is not None else config.MIN_DIRECTIONAL
    min_dom = min_dominant if min_dominant is not None else config.MIN_DOMINANT
    max_conv = max_conviction if max_conviction is not None else config.MAX_CONVICTION
    min_late = min_late_volume if min_late_volume is not None else config.MIN_LATE_VOLUME

    if metrics_df.empty:
        return {
            'signal_level': 'QUIET',
            'anomaly_score': 0,
            'flagged_count': 0,
            'avg_directional': 0,
            'avg_late_volume': 0,
            'max_late_volume': 0,
        }

    # Deduplicate to one row per user
    users = metrics_df.drop_duplicates(subset=['proxyWallet'])

    # Count flagged users (same conjunctive filter as output.flag_users)
    flagged_mask = (
        (users['userDirectionalConsistency'] >= min_dir)
        & (users['userDominantSideRatio'] >= min_dom)
        & (users['userPriceConvictionScore'] < max_conv)
        & (users['lateVolumeRatio'] >= min_late)
    )
    flagged_count = int(flagged_mask.sum())

    avg_directional = float(users['userDirectionalConsistency'].mean())
    avg_late_volume = float(users['lateVolumeRatio'].mean())
    max_late_volume = float(users['lateVolumeRatio'].max())

    # Determine signal level
    if flagged_count >= 2 or (flagged_count >= 1 and max_late_volume >= 0.7):
        signal_level = 'STRONG'
    elif flagged_count == 1 or (avg_directional >= 0.75 and avg_late_volume >= 0.3):
        signal_level = 'MODERATE'
    else:
        signal_level = 'QUIET'

    anomaly_score = (flagged_count * 10) + (avg_directional * 5) + (max_late_volume * 5)

    return {
        'signal_level': signal_level,
        'anomaly_score': round(anomaly_score, 2),
        'flagged_count': flagged_count,
        'avg_directional': round(avg_directional, 3),
        'avg_late_volume': round(avg_late_volume, 3),
        'max_late_volume': round(max_late_volume, 3),
    }
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/sac/Git/poly-sniff && python -m pytest tests/test_signal.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add poly_sniff/metrics/signal.py tests/test_signal.py
git commit -m "feat(metrics): add signal strength computation with tests"
```

---

### Task 3: Add price fetching helper to `search/polymarket.py`

**Files:**
- Modify: `poly_sniff/search/polymarket.py`

**Step 1: Add `fetch_market_prices` function**

Add at the bottom of `polymarket.py`, before the `search_markets` function:

```python
def fetch_market_prices(candidates: list[dict]) -> dict[str, dict]:
    """Fetch current prices for candidate markets from Gamma API.

    Returns dict keyed by slug with 'price' (current Yes probability)
    and 'price_24h_ago' (for delta computation, None if unavailable).
    """
    prices = {}
    for c in candidates:
        slug = c.get('slug', '')
        if not slug:
            continue

        # Try to get price from already-fetched market data
        markets = c.get('markets', [])
        if markets:
            try:
                outcome_prices = markets[0].get('outcomePrices')
                if outcome_prices:
                    if isinstance(outcome_prices, str):
                        import json
                        outcome_prices = json.loads(outcome_prices)
                    if isinstance(outcome_prices, list) and len(outcome_prices) >= 1:
                        prices[slug] = {
                            'price': float(outcome_prices[0]),
                            'price_24h_ago': None,
                        }
                        continue
            except (ValueError, IndexError, KeyError):
                pass

        # Fallback: fetch from Gamma API
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/markets",
                params={'slug': slug, 'limit': 1},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list):
                    market = data[0]
                    outcome_prices = market.get('outcomePrices')
                    if outcome_prices:
                        if isinstance(outcome_prices, str):
                            import json
                            outcome_prices = json.loads(outcome_prices)
                        if isinstance(outcome_prices, list) and len(outcome_prices) >= 1:
                            prices[slug] = {
                                'price': float(outcome_prices[0]),
                                'price_24h_ago': None,
                            }
        except requests.RequestException:
            pass

    return prices
```

**Step 2: Verify it imports**

Run: `cd /Users/sac/Git/poly-sniff && python -c "from poly_sniff.search.polymarket import fetch_market_prices; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add poly_sniff/search/polymarket.py
git commit -m "feat(search): add price fetching helper for confidence display"
```

---

### Task 4: Create sniff pipeline helper in `__main__.py`

Extract the core analyze pipeline into a reusable function that both `run_analyze`, `--sniff`, and `scan` can call.

**Files:**
- Modify: `poly_sniff/__main__.py`

**Step 1: Extract `_sniff_market` helper**

Add this function above `run_analyze`:

```python
def _sniff_market(market_slug: str, position_side: str = None,
                  limit: int = None, late_window: int = None,
                  min_directional: float = None, min_dominant: float = None,
                  max_conviction: float = None, min_late_volume: float = None,
                  resolved_outcome: str = None, verbose: bool = True) -> dict:
    """Run insider analysis on a single market. Returns dict with metrics and flagged users.

    Returns:
        {
            'slug': str,
            'flagged_df': DataFrame,
            'flagged_count': int,
            'holder_count': int,
            'signal': dict (from signal.compute_signal),
            'transactions_df': DataFrame,
            'profiles_df': DataFrame,
        }
        Returns None if market data cannot be fetched.
    """
    from .metrics import signal

    pos_side = position_side or config.POSITION_SIDE
    lim = limit or config.SCRAPER_LIMIT
    late_win = late_window or config.LATE_WINDOW_HOURS
    min_dir = min_directional if min_directional is not None else config.MIN_DIRECTIONAL
    min_dom = min_dominant if min_dominant is not None else config.MIN_DOMINANT
    max_conv = max_conviction if max_conviction is not None else config.MAX_CONVICTION
    min_late = min_late_volume if min_late_volume is not None else config.MIN_LATE_VOLUME

    try:
        condition_id, resolution_time = scraper.fetch_market_info(market_slug)
    except Exception as e:
        if verbose:
            print(f"  Skipping {market_slug}: {e}")
        return None

    try:
        profile_rows, transaction_rows = scraper.fetch(
            condition_id, position_side=pos_side, limit=lim,
        )
    except Exception as e:
        if verbose:
            print(f"  Skipping {market_slug}: {e}")
        return None

    if not profile_rows or not transaction_rows:
        return None

    profiles_df = loader.parse_profiles(profile_rows)
    transactions_df = loader.parse_transactions(transaction_rows)
    transactions_df = preprocessing.enrich(transactions_df, profiles_df)
    transactions_df = timing.add_hours_before_resolution(transactions_df, resolution_time)

    directional_df = directional.compute(transactions_df)
    dominance_df = dominance.compute(transactions_df)
    conviction_df = conviction.compute(transactions_df)
    timing_df = timing.compute(transactions_df, late_window=late_win)
    activity_df = activity.compute(transactions_df)

    for metric_df in [directional_df, dominance_df, conviction_df, timing_df, activity_df]:
        transactions_df = _merge(transactions_df, metric_df)

    flagged_df = output.flag_users(
        transactions_df,
        min_directional=min_dir, min_dominant=min_dom,
        max_conviction=max_conv, min_late_volume=min_late,
        resolved_outcome=resolved_outcome,
    )

    sig = signal.compute_signal(
        transactions_df, min_directional=min_dir, min_dominant=min_dom,
        max_conviction=max_conv, min_late_volume=min_late,
    )

    return {
        'slug': market_slug,
        'flagged_df': flagged_df,
        'flagged_count': len(flagged_df),
        'holder_count': len(profile_rows),
        'signal': sig,
        'transactions_df': transactions_df,
        'profiles_df': profiles_df,
    }
```

**Step 2: Verify import**

Run: `cd /Users/sac/Git/poly-sniff && python -c "from poly_sniff.__main__ import _sniff_market; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add poly_sniff/__main__.py
git commit -m "refactor: extract _sniff_market helper for reuse across commands"
```

---

### Task 5: Implement `--sniff` and `--confidence` on search

**Files:**
- Modify: `poly_sniff/__main__.py` (run_search function + argparse)

**Step 1: Add `--sniff` and `--confidence` flags to search parser**

In `main()`, add to `search_parser`:

```python
    search_parser.add_argument(
        '--sniff', '-s',
        action='store_true',
        help='Run insider analysis across all matched active markets',
    )
    search_parser.add_argument(
        '--confidence',
        action='store_true',
        help='Show price and behavioral signal columns for active markets',
    )
```

Keep `--analyze` but add deprecation:

```python
    search_parser.add_argument(
        '--analyze', '-a',
        action='store_true',
        help='(Deprecated: use --sniff) Analyze top match only',
    )
```

**Step 2: Rewrite the search results display and sniff logic in `run_search`**

Replace lines 193-214 (the auto-analyze block) and enhance the display section (lines 161-191) in `run_search`:

After the `display = filtered[:top_n]` line, replace everything from `print(f"\n{'='*80}")` through the end of `run_search` with:

```python
    # Fetch prices if --confidence
    prices = {}
    if args.confidence:
        from .search import polymarket as pm
        prices = pm.fetch_market_prices(candidates)

    print(f"\n{'='*80}")
    print(f"  Top {len(display)} matches for: \"{primary_claim}\"")
    print(f"{'='*80}\n")

    def _market_status(slug: str) -> str:
        c = candidate_map.get(slug, {})
        if c.get('closed') is True:
            return 'Resolved'
        if c.get('active') is True:
            return 'Active'
        if c.get('active') is False:
            return 'Inactive'
        return '—'

    def _is_active(slug: str) -> bool:
        c = candidate_map.get(slug, {})
        return c.get('active') is True and c.get('closed') is not True

    # Determine which markets to sniff
    sniff_results = {}
    sniff_slugs = []

    if args.sniff:
        sniff_slugs = [r.get('slug') for r in display if _is_active(r.get('slug', ''))]
    elif args.analyze:
        # Legacy --analyze: top 1 only
        print("  Note: --analyze is deprecated, use --sniff to analyze all matches.")
        top_slug = display[0].get('slug', '') if display else ''
        if top_slug and _is_active(top_slug):
            sniff_slugs = [top_slug]

    if sniff_slugs:
        print(f"\nSniffing {len(sniff_slugs)} active market(s) for insider patterns...\n")
        for i, slug in enumerate(sniff_slugs, 1):
            print(f"  [{i}/{len(sniff_slugs)}] {slug}...")
            result = _sniff_market(slug, verbose=True)
            if result:
                sniff_results[slug] = result

    # Build table
    headers = ['#', 'Rel', 'Status']
    if args.confidence:
        headers.extend(['Price', '24h Δ'])
    if sniff_results:
        headers.extend(['Signal', 'Flagged'])
    headers.extend(['Market', 'Slug', 'Reasoning'])

    table_data = []
    for i, r in enumerate(display, 1):
        slug = r.get('slug', '')
        row = [i, r.get('relevance', 0), _market_status(slug)]

        if args.confidence:
            p = prices.get(slug, {})
            price_val = p.get('price')
            if price_val is not None and _is_active(slug):
                row.append(f"{price_val:.0%}")
            else:
                row.append('—')
            row.append('—')  # 24h delta placeholder

        if sniff_results:
            sr = sniff_results.get(slug)
            if sr:
                row.append(sr['signal']['signal_level'])
                row.append(f"{sr['flagged_count']}/{sr['holder_count']}")
            else:
                row.append('—')
                row.append('—')

        row.extend([
            r.get('title', '')[:45],
            slug[:35],
            (r.get('reasoning', '') or '')[:30],
        ])
        table_data.append(row)

    print()
    print(tabulate(table_data, headers=headers, tablefmt='simple'))

    # Print detail sections for markets with flagged users
    if sniff_results:
        for slug, sr in sniff_results.items():
            if sr['flagged_count'] > 0:
                print(f"\n{'─'*80}")
                print(f"  {slug} — {sr['flagged_count']} flagged user(s)  "
                      f"[Signal: {sr['signal']['signal_level']}]")
                print(f"{'─'*80}")
                output.print_table(sr['flagged_df'])
```

**Step 3: Verify CLI parses new flags**

Run: `cd /Users/sac/Git/poly-sniff && python -m poly_sniff search --help`
Expected: Shows `--sniff`, `--confidence`, `--analyze` in help output

**Step 4: Commit**

```bash
git add poly_sniff/__main__.py
git commit -m "feat(search): add --sniff batch analysis and --confidence price columns"
```

---

### Task 6: Create `scan.py` — scan subcommand logic

**Files:**
- Create: `poly_sniff/scan.py`

**Step 1: Implement scan module**

```python
import argparse
from tabulate import tabulate

from . import config
from .search.polymarket import _search_via_gamma_tags
from .search.config import POLYMARKET_GAMMA_API
from .__main__ import _sniff_market
from . import output


def run_scan(args: argparse.Namespace) -> None:
    """Scan topic tags or specific markets for behavioral anomalies."""
    markets_to_scan = []

    if args.tags:
        tag_list = [t.strip() for t in args.tags.split(',') if t.strip()]
        print(f"\nDiscovering active markets for tags: {', '.join(tag_list)}")

        candidates = _search_via_gamma_tags(tag_list, limit=30)

        # Filter: active only, above min volume
        for c in candidates:
            if c.get('closed') is True or c.get('active') is not True:
                continue
            vol = c.get('volume')
            if vol is not None:
                try:
                    if float(vol) < args.min_volume:
                        continue
                except (ValueError, TypeError):
                    pass
            markets_to_scan.append({
                'slug': c['slug'],
                'title': c.get('title', ''),
            })

        print(f"  found        : {len(candidates)} events")
        print(f"  active       : {len(markets_to_scan)} (above ${args.min_volume:,.0f} volume)")

    elif args.markets:
        slug_list = [s.strip() for s in args.markets.split(',') if s.strip()]
        markets_to_scan = [{'slug': s, 'title': ''} for s in slug_list]
        print(f"\nScanning {len(markets_to_scan)} specified market(s)")

    else:
        print("Error: Provide --tags or --markets to scan.")
        return

    if not markets_to_scan:
        print("\n  No active markets found matching criteria.")
        return

    # Cap at max_markets
    if len(markets_to_scan) > args.max_markets:
        print(f"  capping at   : {args.max_markets} markets (use --max-markets to change)")
        markets_to_scan = markets_to_scan[:args.max_markets]

    # Batch sniff
    print(f"\nAnalyzing {len(markets_to_scan)} market(s) for insider patterns...\n")
    results = []

    for i, m in enumerate(markets_to_scan, 1):
        slug = m['slug']
        print(f"  [{i}/{len(markets_to_scan)}] {slug}...")
        sr = _sniff_market(
            slug,
            limit=args.limit,
            min_directional=args.min_directional,
            min_dominant=args.min_dominant,
            max_conviction=args.max_conviction,
            min_late_volume=args.min_late_volume,
            verbose=True,
        )
        if sr:
            sr['title'] = m.get('title', '') or sr.get('slug', '')
            results.append(sr)

    if not results:
        print("\n  No market data could be retrieved.")
        return

    # Sort by anomaly score descending
    results.sort(key=lambda r: r['signal']['anomaly_score'], reverse=True)

    # Summary table
    anomaly_count = sum(1 for r in results if r['signal']['signal_level'] != 'QUIET')

    print(f"\n{'='*80}")
    print(f"  Scan complete: {anomaly_count} of {len(results)} markets with anomalies")
    print(f"{'='*80}\n")

    table_data = []
    for i, r in enumerate(results, 1):
        table_data.append([
            i,
            f"{r['flagged_count']}/{r['holder_count']}",
            r['signal']['signal_level'],
            r['title'][:50],
            r['slug'][:35],
        ])

    print(tabulate(
        table_data,
        headers=['#', 'Flagged', 'Signal', 'Market', 'Slug'],
        tablefmt='simple',
    ))

    # Detail sections for markets with anomalies
    for r in results:
        if r['flagged_count'] > 0:
            print(f"\n{'─'*80}")
            print(f"  {r['slug']} — {r['flagged_count']} flagged user(s)  "
                  f"[Signal: {r['signal']['signal_level']}]")
            print(f"{'─'*80}")
            output.print_table(r['flagged_df'])
```

**Step 2: Verify import**

Run: `cd /Users/sac/Git/poly-sniff && python -c "from poly_sniff.scan import run_scan; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add poly_sniff/scan.py
git commit -m "feat(scan): add scan module for tag-based anomaly detection"
```

---

### Task 7: Wire `scan` subcommand into CLI

**Files:**
- Modify: `poly_sniff/__main__.py`

**Step 1: Add scan subparser in `main()`**

After the search parser section, add:

```python
    # --- scan subcommand ---
    scan_parser = subparsers.add_parser('scan', help='Scan topic areas for behavioral anomalies')
    scan_parser.add_argument(
        '--tags', '-t',
        help='Comma-separated Polymarket tag slugs (e.g., iran,tariffs,china)',
    )
    scan_parser.add_argument(
        '--markets', '-m',
        help='Comma-separated market slugs to scan directly',
    )
    scan_parser.add_argument(
        '--min-volume',
        type=float,
        default=config.SCAN_MIN_VOLUME,
        help=f'Skip markets below this USDC volume (default: {config.SCAN_MIN_VOLUME})',
    )
    scan_parser.add_argument(
        '--max-markets',
        type=int,
        default=config.SCAN_MAX_MARKETS,
        help=f'Maximum markets to analyze (default: {config.SCAN_MAX_MARKETS})',
    )
    scan_parser.add_argument(
        '--limit',
        type=int,
        default=config.SCRAPER_LIMIT,
        help='Number of top position holders to scrape per market (default: 20)',
    )
    scan_parser.add_argument(
        '--min-directional',
        type=float,
        default=config.MIN_DIRECTIONAL,
        help='Minimum userDirectionalConsistency to flag',
    )
    scan_parser.add_argument(
        '--min-dominant',
        type=float,
        default=config.MIN_DOMINANT,
        help='Minimum userDominantSideRatio to flag',
    )
    scan_parser.add_argument(
        '--max-conviction',
        type=float,
        default=config.MAX_CONVICTION,
        help='Maximum userPriceConvictionScore to flag',
    )
    scan_parser.add_argument(
        '--min-late-volume',
        type=float,
        default=config.MIN_LATE_VOLUME,
        help='Minimum lateVolumeRatio to flag',
    )

    from .scan import run_scan
    scan_parser.set_defaults(func=run_scan)
```

**Step 2: Update legacy command detection**

Update the legacy argv detection to include 'scan':

```python
    if len(sys.argv) > 1 and sys.argv[1] not in ('analyze', 'search', 'scan', '-h', '--help'):
        sys.argv.insert(1, 'analyze')
```

**Step 3: Verify CLI**

Run: `cd /Users/sac/Git/poly-sniff && python -m poly_sniff scan --help`
Expected: Shows scan subcommand help with `--tags`, `--markets`, `--min-volume`, etc.

**Step 4: Commit**

```bash
git add poly_sniff/__main__.py
git commit -m "feat(cli): wire scan subcommand into argparse"
```

---

### Task 8: Fix circular import — move `_sniff_market` to own module

**Problem:** `scan.py` imports `_sniff_market` from `__main__.py`, but `__main__.py` may import `scan.py` — circular import risk. Also `_sniff_market` is better as a shared utility.

**Files:**
- Create: `poly_sniff/sniff.py`
- Modify: `poly_sniff/__main__.py` — import from sniff.py
- Modify: `poly_sniff/scan.py` — import from sniff.py

**Step 1: Move `_sniff_market` and `_merge` to `poly_sniff/sniff.py`**

```python
"""Shared sniff pipeline — runs insider analysis on a single market."""

import pandas as pd

from . import config
from .data import loader, preprocessing, scraper
from .metrics import activity, conviction, directional, dominance, timing, signal
from . import output


def _merge(transactions_df: pd.DataFrame, metric_df: pd.DataFrame) -> pd.DataFrame:
    """Drop pre-existing metric columns then left-merge metric_df by proxyWallet."""
    new_cols = [c for c in metric_df.columns if c != 'proxyWallet']
    transactions_df.drop(
        columns=[c for c in new_cols if c in transactions_df.columns], inplace=True
    )
    return transactions_df.merge(metric_df, on='proxyWallet', how='left')


def sniff_market(market_slug: str, position_side: str = None,
                 limit: int = None, late_window: int = None,
                 min_directional: float = None, min_dominant: float = None,
                 max_conviction: float = None, min_late_volume: float = None,
                 resolved_outcome: str = None, verbose: bool = True) -> dict | None:
    """Run insider analysis on a single market.

    Returns dict with keys: slug, flagged_df, flagged_count, holder_count,
    signal, transactions_df, profiles_df. Returns None on failure.
    """
    pos_side = position_side or config.POSITION_SIDE
    lim = limit or config.SCRAPER_LIMIT
    late_win = late_window or config.LATE_WINDOW_HOURS
    min_dir = min_directional if min_directional is not None else config.MIN_DIRECTIONAL
    min_dom = min_dominant if min_dominant is not None else config.MIN_DOMINANT
    max_conv = max_conviction if max_conviction is not None else config.MAX_CONVICTION
    min_late = min_late_volume if min_late_volume is not None else config.MIN_LATE_VOLUME

    try:
        condition_id, resolution_time = scraper.fetch_market_info(market_slug)
    except Exception as e:
        if verbose:
            print(f"  Skipping {market_slug}: {e}")
        return None

    try:
        profile_rows, transaction_rows = scraper.fetch(
            condition_id, position_side=pos_side, limit=lim,
        )
    except Exception as e:
        if verbose:
            print(f"  Skipping {market_slug}: {e}")
        return None

    if not profile_rows or not transaction_rows:
        return None

    profiles_df = loader.parse_profiles(profile_rows)
    transactions_df = loader.parse_transactions(transaction_rows)
    transactions_df = preprocessing.enrich(transactions_df, profiles_df)
    transactions_df = timing.add_hours_before_resolution(transactions_df, resolution_time)

    directional_df = directional.compute(transactions_df)
    dominance_df = dominance.compute(transactions_df)
    conviction_df = conviction.compute(transactions_df)
    timing_df = timing.compute(transactions_df, late_window=late_win)
    activity_df = activity.compute(transactions_df)

    for metric_df in [directional_df, dominance_df, conviction_df, timing_df, activity_df]:
        transactions_df = _merge(transactions_df, metric_df)

    flagged_df = output.flag_users(
        transactions_df,
        min_directional=min_dir, min_dominant=min_dom,
        max_conviction=max_conv, min_late_volume=min_late,
        resolved_outcome=resolved_outcome,
    )

    sig = signal.compute_signal(
        transactions_df, min_directional=min_dir, min_dominant=min_dom,
        max_conviction=max_conv, min_late_volume=min_late,
    )

    return {
        'slug': market_slug,
        'flagged_df': flagged_df,
        'flagged_count': len(flagged_df),
        'holder_count': len(profile_rows),
        'signal': sig,
        'transactions_df': transactions_df,
        'profiles_df': profiles_df,
    }
```

**Step 2: Update `__main__.py` to import from `sniff.py`**

Replace `_merge` and remove `_sniff_market` from `__main__.py`. Import instead:

```python
from .sniff import _merge, sniff_market
```

In `run_search`, change `_sniff_market(slug, ...)` calls to `sniff_market(slug, ...)`.

In `run_analyze`, use the imported `_merge`.

**Step 3: Update `scan.py` to import from `sniff.py`**

```python
from .sniff import sniff_market
```

Replace `_sniff_market(...)` with `sniff_market(...)`.

**Step 4: Verify no circular imports**

Run: `cd /Users/sac/Git/poly-sniff && python -c "from poly_sniff.__main__ import main; print('OK')"`
Expected: `OK`

Run: `cd /Users/sac/Git/poly-sniff && python -m poly_sniff --help`
Expected: Shows help with analyze, search, scan subcommands

**Step 5: Commit**

```bash
git add poly_sniff/sniff.py poly_sniff/__main__.py poly_sniff/scan.py
git commit -m "refactor: move sniff pipeline to shared module, fix circular imports"
```

---

### Task 9: Version bump and final verification

**Files:**
- Modify: `pyproject.toml`

**Step 1: Bump version**

Change `version = "0.4.0"` to `version = "0.5.0"`.

**Step 2: Run test suite**

Run: `cd /Users/sac/Git/poly-sniff && python -m pytest tests/ -v`
Expected: All tests pass

**Step 3: Verify all three subcommands parse**

Run: `cd /Users/sac/Git/poly-sniff && python -m poly_sniff analyze --help && python -m poly_sniff search --help && python -m poly_sniff scan --help`
Expected: All three show help without errors

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.5.0 for intel signals release"
```

---

### Task 10: Update README

**Files:**
- Modify: `README.md`

**Step 1: Add scan section and update search options table**

Add `scan` subcommand docs after the search section. Update search options table with `--sniff` and `--confidence`. Add brief description of signal strength levels. Update architecture diagram to include `sniff.py`, `scan.py`, `metrics/signal.py`.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add scan subcommand and signal strength to README"
```
