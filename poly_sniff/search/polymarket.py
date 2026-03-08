import re
import requests
from .config import POLYMARKET_GAMMA_API, MAX_CANDIDATES, RESEARCHTOOLS_URL


SEARXNG_URL = 'https://search.irregularchat.com'


def _extract_slug_from_url(url: str) -> str | None:
    """Extract event slug from a polymarket.com URL."""
    match = re.search(r'polymarket\.com/(?:[a-z]{2}/)?event/([^/?#]+)', url)
    return match.group(1) if match else None


def _search_via_searxng(query: str, limit: int = 10) -> list[dict]:
    """Search Polymarket via SearXNG for semantic matching."""
    try:
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                'q': f'{query} site:polymarket.com',
                'format': 'json',
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        results = resp.json().get('results', [])
        candidates = []

        for r in results[:limit]:
            url = r.get('url', '')
            slug = _extract_slug_from_url(url)
            if not slug:
                continue

            candidates.append({
                'slug': slug,
                'title': r.get('title', '').replace(' | Polymarket', '').replace(' Predictions & Odds', '').strip(),
                'description': r.get('content', '')[:500],
                'source': 'searxng',
                'url': url,
            })

        return candidates
    except requests.RequestException:
        return []


def _enrich_from_gamma(candidates: list[dict]) -> list[dict]:
    """Enrich SearXNG candidates with Gamma API event data."""
    enriched = []
    for c in candidates:
        slug = c['slug']
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/events",
                params={'slug': slug, 'limit': 1},
                timeout=10,
            )
            if resp.status_code == 200:
                events = resp.json()
                if events and isinstance(events, list) and len(events) > 0:
                    event = events[0]
                    c.update({
                        'title': event.get('title', c['title']),
                        'description': (event.get('description', '') or '')[:500] or c.get('description', ''),
                        'active': event.get('active'),
                        'closed': event.get('closed'),
                        'startDate': event.get('startDate'),
                        'endDate': event.get('endDate'),
                        'liquidity': event.get('liquidity'),
                        'volume': event.get('volume'),
                        'markets': [
                            {
                                'slug': m.get('slug', slug),
                                'question': m.get('question', ''),
                                'outcomePrices': m.get('outcomePrices'),
                            }
                            for m in (event.get('markets') or [])
                        ],
                    })
        except requests.RequestException:
            pass
        enriched.append(c)

    return enriched


def _search_via_gamma(query: str, limit: int = 10) -> list[dict]:
    """Fallback: search directly via Gamma API."""
    try:
        resp = requests.get(
            f"{POLYMARKET_GAMMA_API}/events",
            params={
                'title': query,
                'closed': 'false',
                'limit': limit,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        events = resp.json()
        if not isinstance(events, list):
            return []

        return [
            {
                'slug': e.get('slug', ''),
                'title': e.get('title', ''),
                'description': (e.get('description', '') or '')[:500],
                'active': e.get('active'),
                'closed': e.get('closed'),
                'startDate': e.get('startDate'),
                'endDate': e.get('endDate'),
                'liquidity': e.get('liquidity'),
                'volume': e.get('volume'),
                'source': 'gamma',
                'markets': [
                    {
                        'slug': m.get('slug', e.get('slug', '')),
                        'question': m.get('question', ''),
                        'outcomePrices': m.get('outcomePrices'),
                    }
                    for m in (e.get('markets') or [])
                ],
            }
            for e in events if e.get('slug')
        ]
    except requests.RequestException:
        return []


def search_markets(claims: list[str], limit_per_query: int = 10) -> list[dict]:
    """Search Polymarket for markets matching the given claims.

    Uses SearXNG for semantic search, then enriches with Gamma API data.
    Falls back to Gamma API directly if SearXNG is unavailable.
    """
    seen_slugs = set()
    candidates = []

    # Primary: SearXNG semantic search
    for claim in claims[:3]:
        for c in _search_via_searxng(claim, limit=limit_per_query):
            if c['slug'] not in seen_slugs:
                seen_slugs.add(c['slug'])
                candidates.append(c)
            if len(candidates) >= MAX_CANDIDATES:
                break

    # Enrich SearXNG results with Gamma API data
    if candidates:
        print(f"  searxng hits  : {len(candidates)}")
        candidates = _enrich_from_gamma(candidates)

    # Fallback: Gamma API direct search if SearXNG returned nothing
    if not candidates:
        print(f"  searxng       : unavailable, using Gamma API fallback")
        for claim in claims[:3]:
            for c in _search_via_gamma(claim, limit=limit_per_query):
                if c['slug'] not in seen_slugs:
                    seen_slugs.add(c['slug'])
                    candidates.append(c)
                if len(candidates) >= MAX_CANDIDATES:
                    break

    return candidates
