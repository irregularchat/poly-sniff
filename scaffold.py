import pandas as pd


# Columns that are static per user — forward/back fill across the grid
_PROFILE_COLS = [
    # Market metadata
    'conditionId', 'title', 'slug', 'icon', 'eventSlug',
    # User profile
    'userName', 'pseudonym', 'anonymousUser', 'bio',
    'profileImage', 'profileImageOptimized',
    'joinDate_est', 'trades_general', 'xUsername',
    # User behavior metrics (one value per user per market)
    'userDirectionalConsistency', 'userWeightedDirectionalConsistency',
    'userDominantSideRatio', 'userDominantSide', 'userPriceConvictionScore',
    'tradeCount', 'totalUsdcVolume', 'avgTradeSize', 'maxTradeSize',
    'lastTradeHoursBeforeResolution', 'lateVolumeRatio',
    'accountAgeAtFirstTrade', 'marketConcentrationRatio',
]

# Transaction-level numerics — fill with 0 for empty hours
_TRANSACTION_NUMERIC_COLS = [
    'size', 'usdcSize', 'price',
    'netPosition', 'weightedPosition',
    'netYes', 'netNo', 'weightedNetYes', 'weightedNetNo',
]


def build(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Build hourly scaffold for Tableau visualization.

    Creates a full hour × wallet grid. User-level metrics are forward/back
    filled. Transaction numerics are zero-filled. Cumulative position columns
    are appended.
    """
    df = transactions_df.copy()

    # Floor timestamps to hour
    df['timestamp_est'] = pd.to_datetime(df['timestamp_est']).dt.floor('h')

    # Build aggregation dict from columns that exist in the DataFrame
    agg_dict = {}

    first_cols = [
        # Market metadata
        'conditionId', 'title', 'slug', 'icon', 'eventSlug',
        # User profile
        'userName', 'pseudonym', 'anonymousUser', 'bio',
        'profileImage', 'profileImageOptimized',
        'joinDate_est', 'trades_general', 'xUsername',
        # Transaction metadata
        'transactionHash', 'asset', 'outcomeIndex', 'side', 'outcome',
        # User metrics
        'userDirectionalConsistency', 'userWeightedDirectionalConsistency',
        'userDominantSideRatio', 'userDominantSide', 'userPriceConvictionScore',
        'tradeCount', 'totalUsdcVolume', 'avgTradeSize', 'maxTradeSize',
        'lastTradeHoursBeforeResolution', 'lateVolumeRatio',
        'accountAgeAtFirstTrade', 'marketConcentrationRatio',
        'avgPrice_marketUser_specific', 'totalBought_marketUser_specific',
        'totalPnl_marketUser_specific', 'realizedPnl_marketUser_specific',
    ]
    for col in first_cols:
        if col in df.columns:
            agg_dict[col] = 'first'

    sum_cols = [
        'size', 'usdcSize', 'netPosition', 'weightedPosition',
        'netYes', 'netNo', 'weightedNetYes', 'weightedNetNo',
    ]
    for col in sum_cols:
        if col in df.columns:
            agg_dict[col] = 'sum'

    if 'price' in df.columns:
        agg_dict['price'] = 'mean'

    if 'hoursBeforeResolution' in df.columns:
        agg_dict['hoursBeforeResolution'] = 'min'

    df = df.groupby(['timestamp_est', 'proxyWallet']).agg(agg_dict).reset_index()

    # Expand to full hour × wallet grid
    hours = pd.date_range(df['timestamp_est'].min(), df['timestamp_est'].max(), freq='h')
    wallets = df['proxyWallet'].unique()
    full_grid = pd.MultiIndex.from_product(
        [hours, wallets], names=['timestamp_est', 'proxyWallet']
    )

    df = (
        df.set_index(['timestamp_est', 'proxyWallet'])
        .reindex(full_grid)
        .reset_index()
    )

    # Forward/back fill user-level columns per wallet
    fill_cols = [c for c in _PROFILE_COLS if c in df.columns]
    df[fill_cols] = df.groupby('proxyWallet')[fill_cols].transform(
        lambda x: x.ffill().bfill()
    )

    # Zero-fill transaction numeric columns
    zero_cols = [c for c in _TRANSACTION_NUMERIC_COLS if c in df.columns]
    df[zero_cols] = df[zero_cols].fillna(0)

    # Cumulative position (requires sort by wallet then time)
    df = df.sort_values(['proxyWallet', 'timestamp_est']).reset_index(drop=True)
    df['cumNetPosition'] = df.groupby('proxyWallet')['netPosition'].cumsum()
    df['cumWeightedPosition'] = df.groupby('proxyWallet')['weightedPosition'].cumsum()

    return df
