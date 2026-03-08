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
