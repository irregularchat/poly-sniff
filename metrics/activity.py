import pandas as pd


def compute(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-user activity metrics.

    tradeCount: number of trades in this market.
    totalUsdcVolume: total USDC traded.
    avgTradeSize: mean USDC per trade.
    maxTradeSize: largest single trade in USDC.
    accountAgeAtFirstTrade: days between joinDate_est and earliest trade in market.
    marketConcentrationRatio: totalUsdcVolume / trades_general (lifetime trade count).
        High values flag users who concentrated an outsized share of their activity
        in this single market.
    """
    user_activity = transactions_df.groupby('proxyWallet').agg(
        tradeCount=('size', 'count'),
        totalUsdcVolume=('usdcSize', 'sum'),
        avgTradeSize=('usdcSize', 'mean'),
        maxTradeSize=('usdcSize', 'max'),
    ).reset_index()

    # accountAgeAtFirstTrade: days from account creation to first trade here
    user_dates = transactions_df.groupby('proxyWallet').agg(
        _firstTrade=('timestamp_est', 'min'),
        joinDate_est=('joinDate_est', 'first'),
    ).reset_index()
    user_dates['accountAgeAtFirstTrade'] = (
        user_dates['_firstTrade'] - user_dates['joinDate_est']
    ).dt.days
    user_activity = user_activity.merge(
        user_dates[['proxyWallet', 'accountAgeAtFirstTrade']], on='proxyWallet'
    )

    # marketConcentrationRatio: totalUsdcVolume / lifetime trades_general
    trades_general = (
        transactions_df.groupby('proxyWallet')['trades_general']
        .agg('first')
        .reset_index()
    )
    user_activity = user_activity.merge(trades_general, on='proxyWallet')
    denom = user_activity['trades_general'].replace(0, float('nan'))
    user_activity['marketConcentrationRatio'] = user_activity['totalUsdcVolume'] / denom
    user_activity.drop(columns=['trades_general'], inplace=True)

    return user_activity
