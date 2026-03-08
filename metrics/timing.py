import pandas as pd


def add_hours_before_resolution(
    transactions_df: pd.DataFrame, resolution_time: pd.Timestamp
) -> pd.DataFrame:
    """Add hoursBeforeResolution column to transactions DataFrame."""
    df = transactions_df.copy()
    df['hoursBeforeResolution'] = (
        (resolution_time - df['timestamp_est']).dt.total_seconds() / 3600
    )
    return df


def compute(transactions_df: pd.DataFrame, late_window: int = 24) -> pd.DataFrame:
    """Compute lastTradeHoursBeforeResolution and lateVolumeRatio.

    Requires hoursBeforeResolution column (added by add_hours_before_resolution).

    lastTradeHoursBeforeResolution: minimum hoursBeforeResolution per user
        (i.e. how close to resolution their last trade was).
    lateVolumeRatio: fraction of USDC volume placed within late_window hours
        of resolution.
    """
    user_timing = (
        transactions_df.groupby('proxyWallet')['hoursBeforeResolution']
        .min()
        .reset_index()
    )
    user_timing.columns = ['proxyWallet', 'lastTradeHoursBeforeResolution']

    all_wallets = transactions_df['proxyWallet'].unique()

    late_num = (
        transactions_df[transactions_df['hoursBeforeResolution'] <= late_window]
        .groupby('proxyWallet')['usdcSize']
        .sum()
        .reindex(all_wallets, fill_value=0)
    )
    late_denom = transactions_df.groupby('proxyWallet')['usdcSize'].sum()

    user_late = (late_num / late_denom.replace(0, float('nan'))).fillna(0)
    user_late_volume = user_late.reset_index()
    user_late_volume.columns = ['proxyWallet', 'lateVolumeRatio']

    return user_timing.merge(user_late_volume, on='proxyWallet')
