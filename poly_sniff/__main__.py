import argparse
import sys

import pandas as pd
from tabulate import tabulate

pd.set_option('future.no_silent_downcasting', True)

from . import config
from .data import loader, preprocessing, scraper
from .metrics import activity, conviction, directional, dominance, timing
from . import scaffold as scaffold_module
from . import output


def _merge(transactions_df: pd.DataFrame, metric_df: pd.DataFrame) -> pd.DataFrame:
    """Drop pre-existing metric columns then left-merge metric_df by proxyWallet."""
    new_cols = [c for c in metric_df.columns if c != 'proxyWallet']
    transactions_df.drop(
        columns=[c for c in new_cols if c in transactions_df.columns], inplace=True
    )
    return transactions_df.merge(metric_df, on='proxyWallet', how='left')


def run_analyze(args: argparse.Namespace) -> None:
    # 1. Scrape
    print(f"\nFetching data for market '{args.market_slug}'...")
    condition_id, resolution_time = scraper.fetch_market_info(args.market_slug)
    print(f"  conditionId  : {condition_id}")
    print(f"  resolution   : {resolution_time}")
    profile_rows, transaction_rows = scraper.fetch(
        condition_id,
        position_side=args.position_side,
        limit=args.limit,
    )
    print(f"  holders      : {len(profile_rows)}")

    # 2. Load
    profiles_df = loader.parse_profiles(profile_rows)
    transactions_df = loader.parse_transactions(transaction_rows)
    print(f"  transactions : {len(transactions_df)}")

    # 3. Preprocess — merge profiles, compute base columns
    transactions_df = preprocessing.enrich(transactions_df, profiles_df)

    # 4. Add per-transaction timing column
    transactions_df = timing.add_hours_before_resolution(transactions_df, resolution_time)

    # 5. Compute per-user metrics
    print("\nComputing metrics...")
    directional_df = directional.compute(transactions_df)
    dominance_df = dominance.compute(transactions_df)
    conviction_df = conviction.compute(transactions_df)
    timing_df = timing.compute(transactions_df, late_window=args.late_window)
    activity_df = activity.compute(transactions_df)

    # 6. Merge metrics back — drop stale columns before each merge
    for metric_df in [directional_df, dominance_df, conviction_df, timing_df, activity_df]:
        transactions_df = _merge(transactions_df, metric_df)

    # 7. Flag users
    flagged_df = output.flag_users(
        transactions_df,
        min_directional=args.min_directional,
        min_dominant=args.min_dominant,
        max_conviction=args.max_conviction,
        min_late_volume=args.min_late_volume,
        resolved_outcome=args.resolved_outcome,
    )
    print(f"  flagged      : {len(flagged_df)} user(s)")

    # 8. Print to terminal
    print()
    output.print_table(flagged_df)

    # 9. Export xlsx files if requested
    do_export = args.export_all or any([
        args.export_profiles,
        args.export_transactions,
        args.export_scaffold,
        args.export_flagged,
    ])

    if do_export:
        output_dir = output.make_output_dir(condition_id)

        scaffold_df = None
        if args.export_all or args.export_scaffold:
            scaffold_df = scaffold_module.build(transactions_df)

        output.write_xlsx(
            output_dir,
            profiles_df=profiles_df if (args.export_all or args.export_profiles) else None,
            transactions_df=transactions_df if (args.export_all or args.export_transactions) else None,
            scaffold_df=scaffold_df,
            flagged_df=flagged_df if (args.export_all or args.export_flagged) else None,
        )
        print(f"\nExports written to: {output_dir}/")


def run_search(args: argparse.Namespace) -> None:
    from .search import claims, polymarket, ranker
    from .search.config import DEFAULT_MIN_RELEVANCE

    # 1. Extract claims
    all_claims = []

    if args.url:
        print(f"\nExtracting claims from URL: {args.url}")
        url_data = claims.extract_from_url(args.url)
        print(f"  title  : {url_data['title']}")
        print(f"  claims : {len(url_data['claims'])}")
        all_claims.extend(url_data['claims'])

    if args.claim:
        print(f"\nUsing claim: {args.claim}")
        text_data = claims.extract_from_text(args.claim)
        all_claims.extend(text_data['claims'])

    if not all_claims:
        print("Error: Provide --claim and/or --url to search.")
        sys.exit(1)

    # 2. Search Polymarket
    print(f"\nSearching Polymarket for matching markets...")
    candidates = polymarket.search_markets(all_claims)
    print(f"  candidates   : {len(candidates)}")

    if not candidates:
        print("\n  No matching markets found.")
        return

    # 3. Rank candidates — use best claim as primary, pass all for context
    primary_claim = args.claim or all_claims[0]
    # If primary claim looks like garbage (too short, URL-like), try next one
    if len(primary_claim) < 15 or primary_claim.startswith('http'):
        for c in all_claims[1:]:
            if len(c) >= 15 and not c.startswith('http'):
                primary_claim = c
                break
    print(f"\nRanking candidates by relevance...")
    ranked = ranker.rank_candidates(primary_claim, candidates, all_claims=all_claims)

    # Build slug→candidate lookup for enrichment
    candidate_map = {c['slug']: c for c in candidates}

    # 4. Filter by min relevance
    min_rel = args.min_relevance or DEFAULT_MIN_RELEVANCE
    filtered = [r for r in ranked if r.get('relevance', 0) >= min_rel]

    # 5. Display results
    top_n = args.top_n or 5
    display = filtered[:top_n]

    if not display:
        print(f"\n  No markets above {min_rel}% relevance threshold.")
        if ranked:
            print(f"  Best match: {ranked[0].get('title', '?')} ({ranked[0].get('relevance', 0)}%)")
        return

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

    table_data = []
    for i, r in enumerate(display, 1):
        slug = r.get('slug', '')
        table_data.append([
            i,
            r.get('relevance', 0),
            _market_status(slug),
            r.get('title', '')[:55],
            slug,
            (r.get('reasoning', '') or '')[:35],
        ])

    print(tabulate(
        table_data,
        headers=['#', 'Rel', 'Status', 'Market', 'Slug', 'Reasoning'],
        tablefmt='simple',
    ))

    # 6. Auto-analyze top match if requested
    if args.analyze and display:
        top_slug = display[0].get('slug', '')
        if top_slug:
            print(f"\n{'─'*80}")
            print(f"  Auto-analyzing top match: {top_slug}")
            print(f"{'─'*80}")
            args.market_slug = top_slug
            args.resolved_outcome = None
            args.position_side = config.POSITION_SIDE
            args.limit = config.SCRAPER_LIMIT
            args.late_window = config.LATE_WINDOW_HOURS
            args.min_directional = config.MIN_DIRECTIONAL
            args.min_dominant = config.MIN_DOMINANT
            args.max_conviction = config.MAX_CONVICTION
            args.min_late_volume = config.MIN_LATE_VOLUME
            args.export_all = False
            args.export_profiles = False
            args.export_transactions = False
            args.export_scaffold = False
            args.export_flagged = False
            run_analyze(args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Polymarket insider behavior detection tool',
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=40, width=100),
    )
    subparsers = parser.add_subparsers(dest='command')

    # --- analyze subcommand (default behavior) ---
    analyze_parser = subparsers.add_parser('analyze', help='Analyze a specific market for insider behavior')
    analyze_parser.add_argument(
        'market_slug',
        help='slug of the Polymarket market to analyze',
    )
    analyze_parser.add_argument(
        '--resolved-outcome',
        choices=['Yes', 'No'],
        default=None,
        help='If provided, only flags users whose dominant side matches the winning outcome',
    )
    analyze_parser.add_argument(
        '--position-side',
        choices=['Yes', 'No'],
        default=config.POSITION_SIDE,
        help="Which side's top position holders to scrape (default: Yes)",
    )
    analyze_parser.add_argument(
        '--limit',
        type=int,
        default=config.SCRAPER_LIMIT,
        help='Number of top position holders to scrape (default: 20)',
    )
    analyze_parser.add_argument(
        '--late-window',
        type=int,
        default=config.LATE_WINDOW_HOURS,
        help='Hours before resolution that count as "late" trading (default: 24)',
    )
    analyze_parser.add_argument(
        '--min-directional',
        type=float,
        default=config.MIN_DIRECTIONAL,
        help='Minimum userDirectionalConsistency to flag (default: 0.85)',
    )
    analyze_parser.add_argument(
        '--min-dominant',
        type=float,
        default=config.MIN_DOMINANT,
        help='Minimum userDominantSideRatio to flag (default: 0.90)',
    )
    analyze_parser.add_argument(
        '--max-conviction',
        type=float,
        default=config.MAX_CONVICTION,
        help='Maximum userPriceConvictionScore to flag (default: 0)',
    )
    analyze_parser.add_argument(
        '--min-late-volume',
        type=float,
        default=config.MIN_LATE_VOLUME,
        help='Minimum lateVolumeRatio to flag (default: 0.50)',
    )
    analyze_parser.add_argument('--export-profiles', action='store_true')
    analyze_parser.add_argument('--export-transactions', action='store_true')
    analyze_parser.add_argument('--export-scaffold', action='store_true')
    analyze_parser.add_argument('--export-flagged', action='store_true')
    analyze_parser.add_argument('--export-all', action='store_true')
    analyze_parser.set_defaults(func=run_analyze)

    # --- search subcommand ---
    search_parser = subparsers.add_parser('search', help='Search for Polymarket markets matching a claim')
    search_parser.add_argument(
        '--claim', '-c',
        help='Claim text to search for (e.g., "Will Biden drop out?")',
    )
    search_parser.add_argument(
        '--url', '-u',
        help='URL to extract claims from via researchtoolspy',
    )
    search_parser.add_argument(
        '--analyze', '-a',
        action='store_true',
        help='Automatically run insider analysis on the top matching market',
    )
    search_parser.add_argument(
        '--top-n', '-n',
        type=int,
        default=5,
        help='Number of top results to display (default: 5)',
    )
    search_parser.add_argument(
        '--min-relevance',
        type=int,
        default=50,
        help='Minimum relevance score to display (0-100, default: 50)',
    )
    search_parser.set_defaults(func=run_search)

    # Support legacy `poly_sniff <slug>` syntax by inserting 'analyze' if first arg
    # doesn't match a known subcommand or flag
    if len(sys.argv) > 1 and sys.argv[1] not in ('analyze', 'search', '-h', '--help'):
        sys.argv.insert(1, 'analyze')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
