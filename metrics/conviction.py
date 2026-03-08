import pandas as pd


def compute(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Compute userPriceConvictionScore.

    USDC-weighted average of (price - 0.50) flipped by side.
    Negative = contrarian/informed (buying before market agrees).
    Positive = following consensus.
    """
    df = transactions_df.copy()
    df['_conviction_num'] = (
        (df['price'] - 0.50)
        * df['usdcSize']
        * df['side'].map({'BUY': 1, 'SELL': -1})
    )

    user_num = df.groupby('proxyWallet')['_conviction_num'].sum()
    user_denom = df.groupby('proxyWallet')['usdcSize'].sum()

    user_conviction = (user_num / user_denom.replace(0, float('nan'))).fillna(0)
    result = user_conviction.reset_index()
    result.columns = ['proxyWallet', 'userPriceConvictionScore']
    return result
