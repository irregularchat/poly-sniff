import pandas as pd


def compute(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Compute userDominantSideRatio and userDominantSide.

    Bullish volume = BUY Yes + SELL No (USDC).
    Bearish volume = BUY No + SELL Yes (USDC).
    userDominantSideRatio = max(bullish, bearish) / total. Range 0.5–1.
    userDominantSide = 'bullish' | 'bearish' | 'neutral'.
    """
    df = transactions_df.copy()

    is_bullish = (
        ((df['side'] == 'BUY') & (df['outcome'] == 'Yes'))
        | ((df['side'] == 'SELL') & (df['outcome'] == 'No'))
    )
    is_bearish = (
        ((df['side'] == 'BUY') & (df['outcome'] == 'No'))
        | ((df['side'] == 'SELL') & (df['outcome'] == 'Yes'))
    )

    df['_bullish_vol'] = df['usdcSize'].where(is_bullish, 0)
    df['_bearish_vol'] = df['usdcSize'].where(is_bearish, 0)

    user_vols = df.groupby('proxyWallet').agg(
        bullish_vol=('_bullish_vol', 'sum'),
        bearish_vol=('_bearish_vol', 'sum'),
    ).reset_index()

    total = user_vols['bullish_vol'] + user_vols['bearish_vol']
    user_vols['userDominantSideRatio'] = (
        user_vols[['bullish_vol', 'bearish_vol']].max(axis=1)
        / total.replace(0, float('nan'))
    ).fillna(0)

    user_vols['userDominantSide'] = user_vols.apply(
        lambda x: (
            'neutral' if (x['bullish_vol'] + x['bearish_vol']) == 0
            else ('bullish' if x['bullish_vol'] >= x['bearish_vol'] else 'bearish')
        ),
        axis=1,
    )

    return user_vols[['proxyWallet', 'userDominantSideRatio', 'userDominantSide']]
