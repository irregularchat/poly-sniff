import pandas as pd
import requests


def fetch_market_info(market_slug: str) -> tuple:
    """Fetch conditionId and resolution time from the gamma API using market slug.

    Returns:
        (conditionId, resolution_time) where resolution_time is a US/Eastern
        timezone-naive pd.Timestamp.
    """
    market = requests.get(
        f"https://gamma-api.polymarket.com/markets/slug/{market_slug}"
    ).json()
    condition_id = market['conditionId']
    resolution_time = (
        pd.to_datetime(market['closedTime'])
        .tz_convert('US/Eastern')
        .tz_localize(None)
    )
    return condition_id, resolution_time


def fetch(market_conditionId: str, position_side: str = 'Yes', limit: int = 50):
    """Fetch top position holders, then profiles and transactions for each.

    Returns:
        profile_rows: list of dicts, one per holder
        transaction_rows: list of raw API response items (may include non-dicts)
    """
    top_position_holders = requests.get(
        f"https://data-api.polymarket.com/v1/market-positions"
        f"?market={market_conditionId}&limit={limit}&offset=0"
        f"&status=ALL&sortBy=TOTAL_PNL&sortDirection=DESC"
    ).json()

    side_idx = 0 if top_position_holders[0]['positions'][0]['outcome'] == position_side else 1
    holders = top_position_holders[side_idx]['positions']

    profile_rows = []
    transaction_rows = []

    for holder in holders:
        proxy_wallet = holder['proxyWallet']
        user_name = holder['name'] if bool(holder['name']) else 'ANONYMOUS USER'

        user_stats = requests.get(
            f"https://data-api.polymarket.com/v1/user-stats?proxyAddress={proxy_wallet}"
        ).json()

        leaderboard = requests.get(
            f"https://data-api.polymarket.com/v1/leaderboard"
            f"?timePeriod=all&orderBy=VOL&limit=1&offset=0&category=overall&user={proxy_wallet}"
        ).json()
        lb_entry = leaderboard[0] if leaderboard else {}

        profile_rows.append({
            'proxyWallet': proxy_wallet,
            'userName': user_name,
            'xUsername': lb_entry.get('xUsername'),
            'joinDate_utc': user_stats.get('joinDate'),
            'profileImage': holder.get('profileImage'),
            'verified': holder.get('verified'),
            'anonymousUser': bool(holder['name']),
            'views': user_stats.get('views'),
            'rank_general': lb_entry.get('rank'),
            'vol_general': lb_entry.get('vol'),
            'pnl_general': lb_entry.get('pnl'),
            'trades_general': user_stats.get('trades'),
            'largestWin_general': user_stats.get('largestWin'),
            'avgPrice_marketUser_specific': holder.get('avgPrice'),
            'totalBought_marketUser_specific': holder.get('totalBought'),
            'totalPnl_marketUser_specific': holder.get('totalPnl'),
            'realizedPnl_marketUser_specific': holder.get('realizedPnl'),
        })

        offset = 0
        while True:
            res = requests.get(
                f"https://data-api.polymarket.com/trades"
                f"?user={proxy_wallet}&market={market_conditionId}"
                f"&limit=100&offset={offset}&takerOnly=false"
            ).json()
            transaction_rows.extend(res)
            if len(res) < 100:
                break
            offset += 100

    return profile_rows, transaction_rows
