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

_MODEL = 'gpt-5-mini'


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


def _chat(client, prompt: str, max_tokens: int = 1000) -> str:
    """Send a chat completion request and return the text response."""
    resp = client.chat.completions.create(
        model=_MODEL,
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


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
    result = _chat(client, prompt)
    elapsed = time.time() - t0

    queries = [line.strip().strip('-').strip('•').strip()
               for line in result.split('\n')
               if line.strip() and len(line.strip()) > 10]

    print(f"  Strategy A   : {len(queries)} queries ({elapsed:.1f}s)")
    for q in queries[:5]:
        print(f"    → {q}")
    if len(queries) > 5:
        print(f"    ... +{len(queries) - 5} more")

    return queries


# ─── Strategy B: Generate smart tag slugs ───

def generate_smart_tags(claims: list[str], title: str = '') -> list[str]:
    """Ask GPT to identify optimal Polymarket tag slugs from claims.

    Returns list of tag slug strings.
    """
    client = _get_client()

    claims_text = '\n'.join(f'- {c}' for c in claims[:10])
    context = f'\nArticle title: {title}\n' if title else ''

    prompt = f"""Given these claims from a news article:
{claims_text}
{context}
Polymarket categorizes prediction markets with topic tag slugs like:
iran, israel, tariffs, china, trump, ukraine, bitcoin, fed-rate, elections,
supreme-court, nato, oil, russia, north-korea, ai, tech, crypto, sports,
middle-east, europe, climate, congress, senate, housing, inflation, jobs,
gaza, hamas, hezbollah, syria, turkey, india, japan, korea, taiwan,
trade-war, sanctions, nuclear, military, war, peace, ceasefire, etc.

Identify the 3-6 most relevant tag slugs for finding related Polymarket prediction markets.
Return ONLY the slugs, one per line. Lowercase, hyphenated. No explanations."""

    t0 = time.time()
    result = _chat(client, prompt, max_tokens=200)
    elapsed = time.time() - t0

    tags = [line.strip().lower().replace(' ', '-')
            for line in result.split('\n')
            if line.strip() and len(line.strip()) > 1]
    # Clean up any bullets or numbering
    tags = [t.lstrip('-').lstrip('•').lstrip('.').lstrip('0123456789').strip()
            for t in tags]
    tags = [t for t in tags if t and len(t) > 1]

    print(f"  Strategy B   : {len(tags)} tags ({elapsed:.1f}s)")
    print(f"    → {', '.join(tags)}")

    return tags


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

Which of these prediction markets are potentially related? Score each 0-100.
Only return markets scoring above {threshold}.

Markets:
{cand_text}

Return ONLY lines in format: NUMBER: SCORE
Example: 3: 75
No explanations. Only include markets above {threshold}."""

    t0 = time.time()
    result = _chat(client, prompt, max_tokens=500)
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

        for q in queries[:5]:
            # Try SearXNG with the generated query
            searx_results = _search_via_searxng(q, limit=5)
            for c in searx_results:
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
