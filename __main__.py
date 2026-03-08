import argparse

import pandas as pd

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


def run(args: argparse.Namespace) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Polymarket insider behavior detection tool',
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=40, width=100),
    )
    parser.add_argument(
        'market_slug',
        help='slug of the Polymarket market to analyze',
    )
    parser.add_argument(
        '--resolved-outcome',
        choices=['Yes', 'No'],
        default=None,
        help='If provided, only flags users whose dominant side matches the winning outcome',
    )
    parser.add_argument(
        '--position-side',
        choices=['Yes', 'No'],
        default=config.POSITION_SIDE,
        help="Which side's top position holders to scrape (default: Yes)",
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=config.SCRAPER_LIMIT,
        help='Number of top position holders to scrape (default: 20)',
    )
    parser.add_argument(
        '--late-window',
        type=int,
        default=config.LATE_WINDOW_HOURS,
        help='Hours before resolution that count as "late" trading (default: 24)',
    )
    parser.add_argument(
        '--min-directional',
        type=float,
        default=config.MIN_DIRECTIONAL,
        help='Minimum userDirectionalConsistency to flag (default: 0.85)',
    )
    parser.add_argument(
        '--min-dominant',
        type=float,
        default=config.MIN_DOMINANT,
        help='Minimum userDominantSideRatio to flag (default: 0.90)',
    )
    parser.add_argument(
        '--max-conviction',
        type=float,
        default=config.MAX_CONVICTION,
        help='Maximum userPriceConvictionScore to flag (default: 0)',
    )
    parser.add_argument(
        '--min-late-volume',
        type=float,
        default=config.MIN_LATE_VOLUME,
        help='Minimum lateVolumeRatio to flag (default: 0.50)',
    )
    parser.add_argument(
        '--export-profiles',
        action='store_true',
        help='Export profiles_df to profiles.xlsx',
    )
    parser.add_argument(
        '--export-transactions',
        action='store_true',
        help='Export transactions_df to transactions.xlsx',
    )
    parser.add_argument(
        '--export-scaffold',
        action='store_true',
        help='Export hourly scaffold to scaffold.xlsx',
    )
    parser.add_argument(
        '--export-flagged',
        action='store_true',
        help='Export flagged users table to flagged_users.xlsx',
    )
    parser.add_argument(
        '--export-all',
        action='store_true',
        help='Export all four xlsx files',
    )

    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
