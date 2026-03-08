import pandas as pd


def compute(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """Compute userDirectionalConsistency and userWeightedDirectionalConsistency.

    userDirectionalConsistency  = abs(sum(netPosition)) / sum(abs(netPosition))
    userWeightedDirectionalConsistency = abs(sum(weightedPosition)) / sum(abs(weightedPosition))

    Range 0–1. 1.0 means all trades point the same direction.
    """
    user_directional = (
        transactions_df.groupby('proxyWallet')['netPosition']
        .agg(lambda x: abs(x.sum()) / x.abs().sum() if x.abs().sum() != 0 else 0)
        .reset_index()
    )
    user_directional.columns = ['proxyWallet', 'userDirectionalConsistency']

    user_weighted = (
        transactions_df.groupby('proxyWallet')['weightedPosition']
        .agg(lambda x: abs(x.sum()) / x.abs().sum() if x.abs().sum() != 0 else 0)
        .reset_index()
    )
    user_weighted.columns = ['proxyWallet', 'userWeightedDirectionalConsistency']

    return user_directional.merge(user_weighted, on='proxyWallet')
