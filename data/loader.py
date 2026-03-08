import pandas as pd


def parse_profiles(profile_rows: list) -> pd.DataFrame:
    """Build profiles DataFrame from raw scraper output."""
    return pd.DataFrame(profile_rows)


def parse_transactions(transaction_rows: list) -> pd.DataFrame:
    """Build transactions DataFrame, discarding any non-dict rows."""
    valid_rows = [row for row in transaction_rows if isinstance(row, dict)]
    return pd.DataFrame(valid_rows)
