import pandas as pd


def enrich(transactions_df: pd.DataFrame, profiles_df: pd.DataFrame) -> pd.DataFrame:
    """Merge profile data into transactions and compute base columns.

    Adds: timestamp_est, joinDate_est, usdcSize, yesBought, yesSold, noBought,
          noSold, netYes, netNo, weightedNetYes, weightedNetNo, netPosition,
          weightedPosition.
    """
    df = transactions_df.copy()

    # Convert unix timestamp to US/Eastern timezone-naive datetime
    df['timestamp'] = (
        pd.to_datetime(df['timestamp'], unit='s')
        .dt.tz_localize('UTC')
        .dt.tz_convert('US/Eastern')
        .dt.tz_localize(None)
    )
    df.rename(columns={'timestamp': 'timestamp_est'}, inplace=True)

    # Merge profile columns
    profile_merge_cols = [
        'proxyWallet', 'joinDate_utc', 'trades_general', 'xUsername',
        'anonymousUser', 'userName', 'avgPrice_marketUser_specific',
        'totalBought_marketUser_specific', 'totalPnl_marketUser_specific',
        'realizedPnl_marketUser_specific',
    ]
    df = df.merge(profiles_df[profile_merge_cols], on='proxyWallet', how='left')

    # Drop redundant name column from trades API if present
    df.drop(columns=['name'], inplace=True, errors='ignore')

    # Convert joinDate to US/Eastern timezone-naive datetime
    df['joinDate_utc'] = (
        pd.to_datetime(df['joinDate_utc'])
        .dt.tz_convert('US/Eastern')
        .dt.tz_localize(None)
    )
    df.rename(columns={'joinDate_utc': 'joinDate_est'}, inplace=True)

    # USDC value of each trade
    df['usdcSize'] = df['size'] * df['price']

    # Vectorized side/outcome boolean masks
    is_yes = df['outcome'] == 'Yes'
    is_no = df['outcome'] == 'No'
    is_buy = df['side'] == 'BUY'
    is_sell = df['side'] == 'SELL'

    df['yesBought'] = df['size'].where(is_yes & is_buy, 0)
    df['yesSold'] = df['size'].where(is_yes & is_sell, 0)
    df['noBought'] = df['size'].where(is_no & is_buy, 0)
    df['noSold'] = df['size'].where(is_no & is_sell, 0)

    df['netYes'] = (
        df['size'].where(is_yes & is_buy, 0)
        - df['size'].where(is_yes & is_sell, 0)
    )
    df['netNo'] = (
        df['size'].where(is_no & is_buy, 0)
        - df['size'].where(is_no & is_sell, 0)
    )

    df['weightedNetYes'] = df['netYes'] * df['price']
    df['weightedNetNo'] = df['netNo'] * df['price']

    # netPosition: +size for bullish (BUY Yes / SELL No), -size for bearish
    side_sign = df['side'].map({'BUY': 1, 'SELL': -1})
    outcome_sign = df['outcome'].map({'Yes': 1, 'No': -1})
    df['netPosition'] = df['size'] * side_sign * outcome_sign
    df['weightedPosition'] = df['netPosition'] * df['price']

    return df
