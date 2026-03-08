import os
import pandas as pd
from datetime import datetime

try:
    from tabulate import tabulate
    _HAS_TABULATE = True
except ImportError:
    _HAS_TABULATE = False

_METRIC_COLS = [
    'userDirectionalConsistency',
    'userWeightedDirectionalConsistency',
    'userDominantSideRatio',
    'userDominantSide',
    'userPriceConvictionScore',
    'tradeCount',
    'totalUsdcVolume',
    'avgTradeSize',
    'maxTradeSize',
    'lastTradeHoursBeforeResolution',
    'lateVolumeRatio',
    'accountAgeAtFirstTrade',
    'marketConcentrationRatio',
]


def flag_users(
    transactions_df: pd.DataFrame,
    min_directional: float,
    min_dominant: float,
    max_conviction: float,
    min_late_volume: float,
    resolved_outcome: str = None,
) -> pd.DataFrame:
    """Apply conjunctive flagging filter and return one row per flagged user.

    If resolved_outcome is 'Yes', keeps only bullish users.
    If resolved_outcome is 'No', keeps only bearish users.
    """
    mask = (
        (transactions_df['userDirectionalConsistency'] >= min_directional)
        & (transactions_df['userDominantSideRatio'] >= min_dominant)
        & (transactions_df['userPriceConvictionScore'] < max_conviction)
        & (transactions_df['lateVolumeRatio'] >= min_late_volume)
    )

    if resolved_outcome == 'Yes':
        mask = mask & (transactions_df['userDominantSide'] == 'bullish')
    elif resolved_outcome == 'No':
        mask = mask & (transactions_df['userDominantSide'] == 'bearish')

    base_cols = ['proxyWallet', 'userName', 'joinDate_est', 'xUsername']
    metric_cols = [c for c in _METRIC_COLS if c in transactions_df.columns]

    return (
        transactions_df.loc[mask, base_cols + metric_cols]
        .drop_duplicates(subset=['proxyWallet'])
        .reset_index(drop=True)
    )


def print_table(flagged_df: pd.DataFrame) -> None:
    """Print flagged users table to terminal."""
    if flagged_df.empty:
        print("No users flagged.")
        return

    display = flagged_df[['userName', 'proxyWallet', 'joinDate_est', 'xUsername']].copy()
    display['proxyWallet'] = display['proxyWallet'].str[:7] + '...'
    display['joinDate_est'] = pd.to_datetime(display['joinDate_est']).dt.strftime('%Y-%m-%d')
    display.columns = ['User', 'Wallet', 'Joined', 'X']

    if _HAS_TABULATE:
        print(tabulate(display, headers='keys', tablefmt='rounded_grid', showindex=False))
    else:
        print(display.to_string(index=False))


def make_output_dir(condition_id: str) -> str:
    """Create and return the timestamped output folder path."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = f"output_{condition_id[:7]}_{timestamp}"
    os.makedirs(folder, exist_ok=True)
    return folder


def write_xlsx(
    output_dir: str,
    profiles_df: pd.DataFrame = None,
    transactions_df: pd.DataFrame = None,
    scaffold_df: pd.DataFrame = None,
    flagged_df: pd.DataFrame = None,
) -> None:
    """Write any non-None DataFrames to xlsx in output_dir."""
    if profiles_df is not None:
        profiles_df.to_excel(os.path.join(output_dir, 'profiles.xlsx'), index=False)
    if transactions_df is not None:
        transactions_df.to_excel(os.path.join(output_dir, 'transactions.xlsx'), index=False)
    if scaffold_df is not None:
        scaffold_df.to_excel(os.path.join(output_dir, 'scaffold.xlsx'), index=False)
    if flagged_df is not None:
        flagged_df.to_excel(os.path.join(output_dir, 'flagged_users.xlsx'), index=False)
