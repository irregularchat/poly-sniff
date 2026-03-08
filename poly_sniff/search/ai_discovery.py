"""AI-powered market discovery strategies using GPT-5-mini.

Three strategies for finding Polymarket markets from article claims:
A) Generate prediction-market-style queries
B) Generate optimal Polymarket tag slugs
C) Semantic pre-filtering of a broad candidate pool

Requires: openai package + OPENAI_API_KEY in .env
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

_MODELS = ['gpt-5-mini', 'gpt-4o-mini']


def _get_client():
    """Lazy-load OpenAI client. Raises ImportError or ValueError if unavailable."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai package required for --discovery-test. "
            "Install with: pip install openai"
        )

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not set. Add it to .env for --discovery-test."
        )

    return OpenAI(api_key=api_key)


def _chat(client, prompt: str, max_tokens: int = 4000) -> str:
    """Send a chat completion request, trying gpt-5-mini then falling back.

    GPT-5-mini is a reasoning model that consumes tokens on internal thinking.
    If it returns empty content, falls back to gpt-4o-mini.
    """
    for model in _MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                max_completion_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if content and content.strip():
                return content.strip()
            # Empty response (reasoning model ate all tokens) — try next
        except Exception:
            continue

    return ''


# ─── Strategy A: Generate market-style queries ───

def generate_market_queries(claims: list[str], title: str = '') -> list[str]:
    """Ask GPT to rephrase claims as Polymarket-style prediction questions.

    Returns list of prediction market questions.
    """
    client = _get_client()

    claims_text = '\n'.join(f'- {c}' for c in claims[:10])
    context = f'\nArticle title: {title}\n' if title else ''

    prompt = f"""Given these claims from a news article:
{claims_text}
{context}
Generate 5-10 prediction market questions in the style of Polymarket.
Polymarket questions are typically phrased as:
- "Will [event] happen by [date]?"
- "[Person] to [action] before [deadline]?"
- "[Country] [action] by [timeframe]?"
- "[Event] in [year]?"

Focus on near-term, binary, verifiable outcomes.
Return ONLY the questions, one per line. No numbering, no explanations."""

    t0 = time.time()
    result = _chat(client, prompt, max_tokens=2000)
    elapsed = time.time() - t0

    if not result:
        print(f"  Strategy A   : 0 queries ({elapsed:.1f}s) [empty response]")
        return []

    queries = [line.strip().strip('-').strip('•').strip()
               for line in result.split('\n')
               if line.strip() and len(line.strip()) > 10]

    print(f"  Strategy A   : {len(queries)} queries ({elapsed:.1f}s)")
    for q in queries[:5]:
        print(f"    → {q}")
    if len(queries) > 5:
        print(f"    ... +{len(queries) - 5} more")

    return queries


# ─── Strategy B: Generate smart tags + specific search phrases ───

def generate_smart_tags(claims: list[str], title: str = '') -> list[str]:
    """Ask GPT to identify optimal Polymarket tag slugs from claims.

    Returns list of tag slug strings.
    """
    result = generate_ai_search(claims, title)
    return result.get('tags', [])


def generate_ai_search(claims: list[str], title: str = '') -> dict:
    """Ask GPT to generate both broad tags and specific search phrases.

    Returns dict with:
        tags: list of Polymarket tag slugs (broad discovery)
        phrases: list of 2-4 word specific search phrases (nuanced discovery)
    """
    client = _get_client()

    claims_text = '\n'.join(f'- {c}' for c in claims[:10])
    context = f'\nArticle title: {title}\n' if title else ''

    prompt = f"""Given these claims from a news article:
{claims_text}
{context}
I need two things to find related Polymarket prediction markets:

1. TAGS: Polymarket uses topic tag slugs like: iran, israel, tariffs, china,
trump, ukraine, bitcoin, fed-rate, elections, supreme-court, nato, oil,
russia, ai, tech, crypto, middle-east, military, war, sanctions, etc.
Give me 5-8 relevant tag slugs. Include both obvious and tangential tags
(e.g., an Iran war article → iran, military, war, middle-east, oil, sanctions, us-military, nato).

2. PHRASES: Give me 5-8 search phrases (2-4 words each) that a BETTOR on
Polymarket would use to find prediction markets related to this article.
Do NOT use article-specific details (video titles, school names, memes).
Instead, think about the UNDERLYING geopolitical/economic events and
consequences that bettors would wager on. For example:
- Article about Iran Lego propaganda video → "iran retaliation", "iran us conflict", "iran propaganda war"
- Article about US soldier deaths in Iran → "us casualties iran", "military action iran"
- Article about AI company layoffs → "tech layoffs 2026", "ai industry decline"
- Article about Trump tariffs on China → "china tariff rate", "trade war escalation"

Return in this exact format:
TAGS:
tag1
tag2
tag3

PHRASES:
phrase one
phrase two
phrase three"""

    t0 = time.time()
    result = _chat(client, prompt, max_tokens=2000)
    elapsed = time.time() - t0

    tags = []
    phrases = []
    section = None

    for line in result.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith('TAGS'):
            section = 'tags'
            continue
        if line.upper().startswith('PHRASES') or line.upper().startswith('PHRASE'):
            section = 'phrases'
            continue

        # Clean up bullets/numbering
        clean = line.lstrip('-').lstrip('•').lstrip('.').lstrip('0123456789').strip()
        if not clean or len(clean) < 2:
            continue

        if section == 'tags':
            tag = clean.lower().replace(' ', '-')
            if len(tag) > 1:
                tags.append(tag)
        elif section == 'phrases':
            if len(clean) > 3:
                phrases.append(clean.lower())

    if not tags and not phrases:
        print(f"  ai search    : 0 results ({elapsed:.1f}s) [raw: {repr(result[:100])}]")
    else:
        if tags:
            print(f"  ai tags      : {', '.join(tags)} ({elapsed:.1f}s)")
        if phrases:
            print(f"  ai phrases   : {', '.join(phrases)}")

    return {'tags': tags, 'phrases': phrases}


# ─── Strategy C: Semantic pre-filter ───

def semantic_prefilter(claims: list[str], candidates: list[dict],
                       threshold: int = 30) -> list[dict]:
    """Ask GPT to score a broad candidate pool for relevance to claims.

    Returns candidates that score above threshold, with ai_score added.
    """
    if not candidates:
        return []

    client = _get_client()

    claims_text = '\n'.join(f'- {c}' for c in claims[:10])

    # Build numbered candidate list
    cand_lines = []
    for i, c in enumerate(candidates):
        title = c.get('title', c.get('slug', ''))
        cand_lines.append(f'{i}: {title}')
    cand_text = '\n'.join(cand_lines)

    prompt = f"""Given these claims from a news article:
{claims_text}

Score how related each prediction market is to these claims (0-100).
A market is related if it covers the same topic, region, actors, or consequences.
Even indirect connections count (e.g., an article about Iran attacks → a market about US military action in Iran).

Markets:
{cand_text}

Return ALL markets with score above {threshold} in format: NUMBER: SCORE
Example:
3: 75
7: 45
No explanations, just NUMBER: SCORE lines."""

    t0 = time.time()
    result = _chat(client, prompt, max_tokens=2000)
    elapsed = time.time() - t0

    # Parse scores
    scored = []
    for line in result.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':')
            try:
                idx = int(parts[0].strip())
                score = int(parts[1].strip())
                if 0 <= idx < len(candidates) and score >= threshold:
                    c = candidates[idx].copy()
                    c['ai_prescore'] = score
                    scored.append(c)
            except (ValueError, IndexError):
                continue

    scored.sort(key=lambda x: x.get('ai_prescore', 0), reverse=True)

    print(f"  Strategy C   : {len(scored)}/{len(candidates)} passed filter ({elapsed:.1f}s)")
    for c in scored[:3]:
        print(f"    → [{c['ai_prescore']}] {c.get('title', c['slug'])[:60]}")

    return scored


# ─── Comparison runner ───

def run_comparison(claims: list[str], title: str = '',
                   existing_candidates: list[dict] = None) -> dict:
    """Run all three strategies and compare results.

    Args:
        claims: Extracted claims from article
        title: Article title for context
        existing_candidates: Candidates from current entity-tag approach

    Returns dict with results from each strategy and comparison stats.
    """
    from .polymarket import _search_via_gamma_tags, _search_via_searxng, \
        _extract_key_entities, _entities_to_tag_slugs

    existing_slugs = {c['slug'] for c in (existing_candidates or [])}

    print(f"\n{'─'*80}")
    print(f"  AI Discovery Strategy Comparison")
    print(f"{'─'*80}\n")

    results = {
        'current': {
            'candidates': existing_candidates or [],
            'slugs': existing_slugs,
            'count': len(existing_slugs),
        }
    }

    # Strategy A: Market-style queries → SearXNG + Gamma
    print("Strategy A: AI-generated market queries")
    try:
        queries = generate_market_queries(claims, title)
        a_candidates = []
        a_slugs = set()

        # Try SearXNG with generated queries
        for q in queries[:5]:
            searx_results = _search_via_searxng(q, limit=5)
            for c in searx_results:
                if c['slug'] not in a_slugs:
                    a_slugs.add(c['slug'])
                    a_candidates.append(c)

        # Also extract entities from AI queries and search Gamma tags
        ai_entities = _extract_key_entities(' '.join(queries))
        ai_tags = _entities_to_tag_slugs(ai_entities)
        if ai_tags:
            tag_results = _search_via_gamma_tags(ai_tags[:4])
            for c in tag_results:
                if c['slug'] not in a_slugs:
                    a_slugs.add(c['slug'])
                    a_candidates.append(c)

        results['strategy_a'] = {
            'queries': queries,
            'candidates': a_candidates,
            'slugs': a_slugs,
            'count': len(a_slugs),
            'new': len(a_slugs - existing_slugs),
        }
        print(f"  total        : {len(a_slugs)} candidates, {len(a_slugs - existing_slugs)} new\n")
    except (ImportError, ValueError) as e:
        print(f"  Error: {e}\n")
        results['strategy_a'] = {'error': str(e)}

    # Strategy B: Smart tags → Gamma tag_slug
    print("Strategy B: AI-generated tag slugs")
    try:
        smart_tags = generate_smart_tags(claims, title)
        b_candidates = _search_via_gamma_tags(smart_tags[:6])
        b_slugs = {c['slug'] for c in b_candidates}

        results['strategy_b'] = {
            'tags': smart_tags,
            'candidates': b_candidates,
            'slugs': b_slugs,
            'count': len(b_slugs),
            'new': len(b_slugs - existing_slugs),
        }
        print(f"  total        : {len(b_slugs)} candidates, {len(b_slugs - existing_slugs)} new\n")
    except (ImportError, ValueError) as e:
        print(f"  Error: {e}\n")
        results['strategy_b'] = {'error': str(e)}

    # Strategy C: Semantic pre-filter on broader pool
    print("Strategy C: Semantic pre-filter (wider net)")
    try:
        # Cast wider net: use current entities + any Strategy B tags
        all_tags = set()

        # Current entity tags
        entities = _extract_key_entities(' '.join(claims))
        current_tags = _entities_to_tag_slugs(entities)
        all_tags.update(current_tags[:6])

        # Add Strategy B tags if available
        if 'strategy_b' in results and 'tags' in results['strategy_b']:
            all_tags.update(results['strategy_b']['tags'][:4])

        broad_candidates = _search_via_gamma_tags(list(all_tags)[:10], limit=30)
        broad_slugs = {c['slug'] for c in broad_candidates}

        print(f"  broad pool   : {len(broad_candidates)} from {len(all_tags)} tags")

        filtered = semantic_prefilter(claims, broad_candidates)
        c_slugs = {c['slug'] for c in filtered}

        results['strategy_c'] = {
            'broad_count': len(broad_candidates),
            'candidates': filtered,
            'slugs': c_slugs,
            'count': len(c_slugs),
            'new': len(c_slugs - existing_slugs),
        }
        print(f"  total        : {len(c_slugs)} candidates, {len(c_slugs - existing_slugs)} new\n")
    except (ImportError, ValueError) as e:
        print(f"  Error: {e}\n")
        results['strategy_c'] = {'error': str(e)}

    # Summary comparison
    all_discovered = set()
    for key in ['current', 'strategy_a', 'strategy_b', 'strategy_c']:
        if key in results and 'slugs' in results[key]:
            all_discovered.update(results[key]['slugs'])

    print(f"{'='*80}")
    print(f"  Discovery Strategy Comparison")
    print(f"{'='*80}\n")

    print(f"  {'Strategy':<25} {'Found':>6} {'New':>6} {'Overlap w/current':>18}")
    print(f"  {'─'*55}")

    current_count = results['current']['count']
    print(f"  {'Current (entity tags)':<25} {current_count:>6} {'—':>6} {'—':>18}")

    for key, label in [('strategy_a', 'A: Market queries'),
                       ('strategy_b', 'B: Smart tags'),
                       ('strategy_c', 'C: Semantic filter')]:
        r = results.get(key, {})
        if 'error' in r:
            print(f"  {label:<25} {'ERR':>6}")
        elif 'slugs' in r:
            overlap = len(r['slugs'] & existing_slugs)
            print(f"  {label:<25} {r['count']:>6} {r.get('new', 0):>6} {overlap:>18}")

    print(f"\n  Combined unique markets : {len(all_discovered)}")

    return results
