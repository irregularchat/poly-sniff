import re
import requests
from collections import Counter
from .config import POLYMARKET_GAMMA_API, MAX_CANDIDATES


SEARXNG_URL = 'https://search.irregularchat.com'

# Words to strip from search queries
_STOP_WORDS = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'will', 'be', 'been',
               'being', 'have', 'has', 'had', 'do', 'does', 'did', 'to', 'of', 'in',
               'for', 'on', 'with', 'at', 'by', 'from', 'that', 'this', 'it', 'and',
               'or', 'but', 'not', 'if', 'so', 'can', 'could', 'would', 'should',
               'their', 'they', 'its', 'his', 'her', 'our', 'your', 'who', 'what',
               'which', 'when', 'where', 'how', 'than', 'then', 'also', 'into',
               'about', 'after', 'before', 'between', 'under', 'over', 'through',
               'first', 'time', 'early', 'late', 'very', 'just', 'more', 'most',
               'some', 'any', 'each', 'every', 'showing', 'videos', 'close',
               'reported', 'officials', 'according', 'said', 'says', 'told',
               'next', 'month', 'year', 'day', 'week', 'following', 'due',
               'currently', 'experience', 'affect', 'remain', 'residents',
               'warned', 'possibility', 'potential', 'expected'}

_ENTITY_NOISE = {'red', 'cross', 'crescent', 'society', 'organization', 'association',
                 'department', 'ministry', 'office', 'bureau', 'committee', 'council',
                 'group', 'force', 'forces', 'army', 'navy', 'military', 'police',
                 'national', 'international', 'united', 'states', 'general', 'president',
                 'prime', 'minister', 'secretary', 'director', 'chief', 'spokesman',
                 'new', 'old', 'north', 'south', 'east', 'west', 'central',
                 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                 'january', 'february', 'march', 'april', 'may', 'june', 'july',
                 'august', 'september', 'october', 'november', 'december'}


def _extract_slug_from_url(url: str) -> str | None:
    """Extract event slug from a polymarket.com URL."""
    match = re.search(r'polymarket\.com/(?:[a-z]{2}/)?(?:event|predictions)/([^/?#]+)', url)
    return match.group(1) if match else None


def _to_search_query(claim: str, max_words: int = 8) -> str:
    """Extract key terms from a claim for search engine queries."""
    words = [w for w in re.sub(r'[^\w\s-]', '', claim).split()
             if w.lower() not in _STOP_WORDS and len(w) > 2]
    return ' '.join(words[:max_words])


def _extract_key_entities(text: str) -> list[str]:
    """Extract key named entities (countries, cities, people) from text."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    all_words = []
    for sent in sentences:
        words = sent.split()
        for w in words:
            clean = re.sub(r"[^\w'-]", '', w)
            if not clean or len(clean) < 3:
                continue
            if clean[0].isupper() and clean.lower() not in _STOP_WORDS and clean.lower() not in _ENTITY_NOISE:
                # Normalize possessives: "Iran's" → "Iran"
                clean = re.sub(r"'s$", '', clean)
                all_words.append(clean)

    counts = Counter(w.lower() for w in all_words)

    seen = set()
    result = []
    for entity, _ in counts.most_common():
        for w in all_words:
            if w.lower() == entity and entity not in seen:
                seen.add(entity)
                result.append(w)
                break

    return result


def _entities_to_tag_slugs(entities: list[str]) -> list[str]:
    """Convert extracted entities to likely Polymarket tag slugs.

    Polymarket uses lowercase hyphenated tag slugs like 'iran', 'israel',
    'middle-east', 'ukraine', 'china', 'tariffs'.
    """
    tags = []
    seen = set()
    for entity in entities:
        slug = entity.lower().replace(' ', '-').replace("'", '').replace('"', '')
        if slug not in seen and len(slug) > 2:
            seen.add(slug)
            tags.append(slug)
    return tags


# ─── Gamma API tag-based search (primary, most reliable) ───

def _search_via_gamma_tags(tag_slugs: list[str], limit: int = 20) -> list[dict]:
    """Search Polymarket events by tag slugs via Gamma API.

    This is the most reliable search method — Polymarket categorizes
    events by topic tags like 'iran', 'israel', 'tariffs'.
    """
    seen_slugs = set()
    candidates = []

    for tag in tag_slugs:
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/events",
                params={'tag_slug': tag, 'limit': limit},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            events = resp.json()
            if not isinstance(events, list):
                continue

            for e in events:
                slug = e.get('slug', '')
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                candidates.append({
                    'slug': slug,
                    'title': e.get('title', ''),
                    'description': (e.get('description', '') or '')[:500],
                    'active': e.get('active'),
                    'closed': e.get('closed'),
                    'startDate': e.get('startDate'),
                    'endDate': e.get('endDate'),
                    'liquidity': e.get('liquidity'),
                    'volume': e.get('volume'),
                    'source': f'gamma-tag:{tag}',
                    'markets': [
                        {
                            'slug': m.get('slug', slug),
                            'question': m.get('question', ''),
                            'outcomePrices': m.get('outcomePrices'),
                        }
                        for m in (e.get('markets') or [])
                    ],
                })

                if len(candidates) >= MAX_CANDIDATES:
                    return candidates

        except requests.RequestException:
            continue

    return candidates


# ─── SearXNG search (supplementary, intermittent) ───

def _search_via_searxng(query: str, limit: int = 10) -> list[dict]:
    """Search Polymarket via SearXNG with 'polymarket' keyword."""
    search_q = _to_search_query(query, max_words=6) if len(query) > 60 else query
    if not search_q.strip():
        search_q = query[:60]

    try:
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                'q': f'polymarket {search_q}',
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
                'title': r.get('title', '')
                    .replace(' | Polymarket', '')
                    .replace(' Predictions & Odds', '')
                    .replace(' - Polymarket', '')
                    .strip(),
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
        # Skip if already has Gamma data (from tag search)
        if c.get('source', '').startswith('gamma'):
            enriched.append(c)
            continue

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


def _build_searxng_queries(claims: list[str]) -> list[str]:
    """Generate SearXNG query variants from claims."""
    queries = []
    seen = set()

    def _add(q: str):
        q = q.strip()
        if q and q.lower() not in seen and len(q) > 3:
            seen.add(q.lower())
            queries.append(q)

    # Extract entities
    entities = _extract_key_entities(' '.join(claims))
    if len(entities) >= 2:
        _add(' '.join(entities[:3]))

    # Suggested_market questions
    for claim in claims:
        if claim.startswith('Will ') or '?' in claim:
            _add(_to_search_query(claim, max_words=5))
        if len(queries) >= 6:
            break

    # Regular claims
    for claim in claims[:5]:
        if claim.startswith('Will ') or '?' in claim:
            continue
        _add(_to_search_query(claim, max_words=4))
        if len(queries) >= 8:
            break

    return queries[:8]


def fetch_market_prices(candidates: list[dict]) -> dict[str, dict]:
    """Fetch current prices for candidate markets from Gamma API.

    Returns dict keyed by slug with 'price' (current Yes probability)
    and 'price_24h_ago' (for delta computation, None if unavailable).
    """
    import json as _json

    prices = {}
    for c in candidates:
        slug = c.get('slug', '')
        if not slug:
            continue

        # Try to get price from already-fetched market data
        markets = c.get('markets', [])
        if markets:
            try:
                outcome_prices = markets[0].get('outcomePrices')
                if outcome_prices:
                    if isinstance(outcome_prices, str):
                        outcome_prices = _json.loads(outcome_prices)
                    if isinstance(outcome_prices, list) and len(outcome_prices) >= 1:
                        prices[slug] = {
                            'price': float(outcome_prices[0]),
                            'price_24h_ago': None,
                        }
                        continue
            except (ValueError, IndexError, KeyError):
                pass

        # Fallback: fetch from Gamma API
        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/markets",
                params={'slug': slug, 'limit': 1},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list):
                    market = data[0]
                    outcome_prices = market.get('outcomePrices')
                    if outcome_prices:
                        if isinstance(outcome_prices, str):
                            outcome_prices = _json.loads(outcome_prices)
                        if isinstance(outcome_prices, list) and len(outcome_prices) >= 1:
                            prices[slug] = {
                                'price': float(outcome_prices[0]),
                                'price_24h_ago': None,
                            }
        except requests.RequestException:
            pass

    return prices


def _get_ai_search(claims: list[str]) -> dict:
    """Try to get AI-generated tags and search phrases. Returns empty dict if unavailable."""
    try:
        from .ai_discovery import generate_ai_search
        return generate_ai_search(claims)
    except ImportError:
        return {}
    except ValueError as e:
        print(f"  ai search    : skipped ({e})")
        return {}
    except Exception as e:
        print(f"  ai search    : unavailable ({e})")
        return {}


def search_markets(claims: list[str], limit_per_query: int = 10) -> list[dict]:
    """Search Polymarket for markets matching the given claims.

    AI-heavy strategy (when OPENAI_API_KEY available):
    1. AI generates tags + bettor-oriented phrases (PRIMARY)
    2. AI tags → Gamma tag_slug search (broad discovery)
    3. AI phrases → SearXNG search (nuanced discovery)
    4. Entity extraction tags → Gamma (fallback/supplement)
    5. SearXNG keyword search (final supplement)

    Without AI:
    1. Entity extraction tags → Gamma
    2. SearXNG keyword search
    """
    seen_slugs = set()
    candidates = []

    def _add_candidates(results: list[dict]) -> int:
        count = 0
        for c in results:
            if c['slug'] not in seen_slugs:
                seen_slugs.add(c['slug'])
                candidates.append(c)
                count += 1
            if len(candidates) >= MAX_CANDIDATES:
                break
        return count

    # 1. AI SMART SEARCH (primary when available)
    ai_search = _get_ai_search(claims)
    ai_tags = ai_search.get('tags', [])
    ai_phrases = ai_search.get('phrases', [])
    searched_tags = set()

    if ai_tags:
        # Search ALL AI tags via Gamma (up to 8)
        ai_tag_results = _search_via_gamma_tags(ai_tags[:8])
        ai_count = _add_candidates(ai_tag_results)
        searched_tags.update(ai_tags[:8])
        if ai_count:
            print(f"  ai tags      : {ai_count} events from {', '.join(ai_tags[:8])}")

    # 2. AI PHRASES → SearXNG (nuanced, bettor-oriented search)
    if ai_phrases:
        ai_searx_count = 0
        for phrase in ai_phrases[:8]:
            results = _search_via_searxng(phrase, limit=8)
            ai_searx_count += _add_candidates(results)
            if len(candidates) >= MAX_CANDIDATES:
                break
        if ai_searx_count:
            print(f"  ai phrases   : +{ai_searx_count} via search ({', '.join(ai_phrases[:4])})")

    # 3. ENTITY EXTRACTION (supplement / fallback if no AI)
    entities = _extract_key_entities(' '.join(claims))
    tag_slugs = _entities_to_tag_slugs(entities)
    new_entity_tags = [t for t in tag_slugs if t not in searched_tags]

    if new_entity_tags:
        entity_results = _search_via_gamma_tags(new_entity_tags[:6])
        entity_count = _add_candidates(entity_results)
        if entity_count:
            print(f"  entity tags  : +{entity_count} from {', '.join(new_entity_tags[:6])}")

    # 4. SEARXNG KEYWORD SEARCH (final supplement)
    searxng_queries = _build_searxng_queries(claims)
    searxng_count = 0
    for query in searxng_queries:
        results = _search_via_searxng(query, limit=limit_per_query)
        searxng_count += _add_candidates(results)
        if len(candidates) >= MAX_CANDIDATES:
            break

    if searxng_count > 0:
        print(f"  searxng      : +{searxng_count} additional")
        candidates = _enrich_from_gamma(candidates)
    elif not candidates:
        print(f"  search       : no results found")

    return candidates
