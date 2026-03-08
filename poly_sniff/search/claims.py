import html
import re
import requests
from urllib.parse import urlparse
from .config import RESEARCHTOOLS_URL


_PAYWALL_TITLES = {
    'subscribe to read', 'subscribe to continue', 'subscription required',
    'sign in to read', 'log in to continue', 'register to read',
    'premium content', 'subscribers only', 'already a subscriber',
    'please log in', 'sign in', 'create a free account',
}


def _clean_text(text: str) -> str:
    """Decode HTML entities and normalize whitespace."""
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _is_paywall_title(title: str) -> bool:
    """Detect common paywall/gate titles."""
    lower = title.lower().strip()
    return any(p in lower for p in _PAYWALL_TITLES) or len(lower) < 5


def _extract_topic_from_url(url: str) -> list[str]:
    """Extract topic hints from URL path segments.

    News URLs often embed article slugs:
    ft.com/content/d08d89bb-... → nothing useful (UUID)
    nytimes.com/2024/01/trump-tariffs-china → ['trump tariffs china']
    reuters.com/world/us/us-tariffs-hit-china-2024 → ['us tariffs hit china']
    """
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    segments = path.split('/')

    topics = []
    for seg in segments:
        # Skip UUIDs, dates, short segments, common path parts
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}', seg):
            continue
        if re.match(r'^\d{4}$', seg) or re.match(r'^\d{1,2}$', seg):
            continue
        if seg in ('content', 'article', 'story', 'news', 'world', 'us',
                    'politics', 'business', 'opinion', 'live', 'interactive',
                    'video', 'en', 'uk', 'europe', 'asia', 'americas'):
            continue
        if len(seg) < 4:
            continue

        # Convert slug to readable text: "trump-tariffs-china" → "trump tariffs china"
        readable = seg.replace('-', ' ').replace('_', ' ')
        # Remove trailing numbers (often IDs)
        readable = re.sub(r'\s+\d+$', '', readable)
        if len(readable) > 5:
            topics.append(readable)

    return topics


def _split_compound(text: str) -> list[str]:
    """Split compound sentences on conjunctions, semicolons, and 'while/as' clauses."""
    parts = []
    for chunk in re.split(r'[;]|\s+while\s+|\s+as\s+(?=[A-Z])', text):
        chunk = chunk.strip().strip(',').strip()
        if len(chunk) >= 15:
            parts.append(chunk)
    return parts if len(parts) > 1 else [text]


def _extract_claims(title: str, description: str) -> list[str]:
    """Extract claim-like statements from title and description.

    Handles compound titles (split on ' as ', ' while '), HTML entities,
    and long description sentences by splitting on conjunctions.
    """
    claims = []
    seen = set()

    def _add(text: str):
        text = _clean_text(text)
        key = text.lower()
        if len(text) >= 10 and key not in seen:
            seen.add(key)
            claims.append(text)

    # Split compound titles: "X hits Y as Z announces W"
    if title:
        title = _clean_text(title)
        # Remove site name suffixes
        title = re.sub(r'\s*[:|]\s*(NPR|CNN|BBC|Reuters|AP News|The Guardian|Financial Times|FT|WSJ|NYT).*$', '', title)
        parts = _split_compound(title)
        for p in parts:
            _add(p)

    if description:
        description = _clean_text(description)
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', description)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue
            # Split compound sentences
            for part in _split_compound(sentence):
                _add(part)

    return claims[:15]


def _extract_claims_via_api(url: str) -> dict | None:
    """Try AI-powered claim extraction via researchtoolspy /api/tools/extract-claims.

    Returns full response dict with claims, entities, summary, etc.
    """
    try:
        resp = requests.post(
            f"{RESEARCHTOOLS_URL}/api/tools/extract-claims",
            json={"url": url, "include_entities": True, "include_summary": True},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()
        # 422 = paywall/insufficient content — still may have og_metadata
        if resp.status_code == 422:
            data = resp.json()
            if data.get('og_metadata'):
                return data
    except requests.RequestException:
        pass
    return None


def extract_from_url(url: str) -> dict:
    """Extract claims from a URL via researchtoolspy.

    Tries AI-powered extraction first (/api/tools/extract-claims),
    falls back to metadata-based extraction (/api/tools/analyze-url),
    then URL topic extraction as last resort.
    """
    # Try AI-powered claim extraction first
    api_data = _extract_claims_via_api(url)

    if api_data:
        # Check if we got real claims vs error with og_metadata
        ai_claims = api_data.get('claims', [])
        title = api_data.get('title', '')
        paywalled = api_data.get('paywalled', False)

        # If we got an error response with og_metadata, use that
        if api_data.get('error') and api_data.get('og_metadata'):
            og = api_data['og_metadata']
            title = og.get('title', '')
            desc = og.get('description', '')
            print(f"  paywalled    : yes (using OG metadata)")
            print(f"  og title     : {title}")
            if title and not _is_paywall_title(title):
                claims = _extract_claims(title, desc)
                # Add URL-derived topics as extra search queries
                url_topics = _extract_topic_from_url(url)
                for t in url_topics:
                    if t not in claims:
                        claims.append(t)
                return {
                    'title': _clean_text(title),
                    'description': _clean_text(desc),
                    'claims': claims[:15],
                    'source_url': url,
                    'paywalled': True,
                }

        # Normal successful response with claims
        if ai_claims and isinstance(ai_claims, list) and len(ai_claims) > 0:
            claim_texts = [c.get('claim', c.get('text', '')) for c in ai_claims
                           if c.get('claim') or c.get('text')]

            # Extract suggested_market questions as additional search queries
            market_queries = [c.get('suggested_market', '') for c in ai_claims
                             if c.get('suggested_market')]

            # Check if the title looks like a paywall
            if _is_paywall_title(title) and claim_texts:
                # Claims came from garbage text — discard them
                print(f"  paywalled    : yes (garbage claims discarded)")
            elif claim_texts:
                source = api_data.get('content_source', 'api')
                word_count = api_data.get('word_count', 0)
                print(f"  ai claims    : {len(claim_texts)} ({source}, {word_count} words)")

                if paywalled:
                    print(f"  paywalled    : yes (partial content used)")

                if api_data.get('summary'):
                    print(f"  summary      : {api_data['summary'][:80]}...")

                # Combine claims + suggested market questions for broader search
                all_queries = claim_texts[:10]
                for mq in market_queries[:5]:
                    if mq and mq not in all_queries:
                        all_queries.append(mq)

                return {
                    'title': title or claim_texts[0],
                    'description': api_data.get('summary', ''),
                    'claims': all_queries[:15],
                    'source_url': url,
                    'entities': api_data.get('entities'),
                    'summary': api_data.get('summary'),
                    'word_count': word_count,
                    'paywalled': paywalled,
                }

    # Fall back to metadata-based extraction
    try:
        resp = requests.post(
            f"{RESEARCHTOOLS_URL}/api/tools/analyze-url",
            json={"url": url, "checkSEO": False},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        metadata = data.get('metadata', data)
        title = metadata.get('title', '')
        description = metadata.get('description', '')

        if not _is_paywall_title(title):
            return {
                'title': _clean_text(title),
                'description': _clean_text(description),
                'claims': _extract_claims(title, description),
                'source_url': url,
            }
        else:
            print(f"  analyze-url  : paywalled ({title})")
    except requests.RequestException as e:
        print(f"  Warning: Failed to analyze URL via researchtoolspy: {e}")

    # Last resort: extract topic hints from URL path
    url_topics = _extract_topic_from_url(url)
    if url_topics:
        print(f"  url topics   : {url_topics}")
        return {
            'title': url_topics[0],
            'description': '',
            'claims': url_topics,
            'source_url': url,
            'paywalled': True,
        }

    print(f"  Falling back to URL as claim text.")
    return {
        'title': url,
        'description': '',
        'claims': [url],
        'source_url': url,
    }


def extract_from_text(claim_text: str) -> dict:
    """Wrap direct claim text into the standard claims format."""
    return {
        'title': claim_text,
        'description': '',
        'claims': [claim_text],
        'source_url': None,
    }
