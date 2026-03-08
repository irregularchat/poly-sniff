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
