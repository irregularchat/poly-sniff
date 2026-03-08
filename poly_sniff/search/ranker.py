import re
import requests
from .config import RESEARCHTOOLS_URL


_STOP_WORDS = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'will', 'be', 'to', 'of',
               'in', 'for', 'on', 'with', 'at', 'by', 'from', 'that', 'this', 'and',
               'or', 'but', 'not', 'if', 'it', 'its', 'do', 'does', 'did', 'has', 'have',
               'had', 'been', 'being', 'would', 'could', 'should', 'can', 'may', 'might',
               'shall', 'as', 'so', 'than', 'what', 'who', 'how', 'when', 'where', 'which'}


def _stem(word: str) -> str:
    """Minimal suffix stripping for better fuzzy matching."""
    w = word.lower()
    for suffix in ('tion', 'sion', 'ment', 'ness', 'ious', 'ous', 'ing', 'ies',
                   'ied', 'ian', 'ans', "'s", 'es', 'ed', 'ly', 's'):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[:-len(suffix)]
    return w


def _tokenize(text: str) -> set[str]:
    """Tokenize text into stemmed, non-stop words."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return {_stem(w) for w in words if w not in _STOP_WORDS and len(w) > 2}


def _keyword_fallback(claim: str, candidates: list[dict], all_claims: list[str] = None) -> list[dict]:
    """Fuzzy keyword matching fallback when LLM ranking is unavailable."""
    # Combine all claims for broader matching
    combined = claim
    if all_claims:
        combined = ' '.join([claim] + all_claims[:10])
    claim_tokens = _tokenize(combined)

    results = []
    for c in candidates:
        text = f"{c.get('title', '')} {c.get('description', '')}"
        cand_tokens = _tokenize(text)

        # Exact stem overlap
        overlap = len(claim_tokens & cand_tokens)

        # Substring bonus: "iran" matches "iranian" after stemming
        substring_bonus = 0
        for ct in claim_tokens - cand_tokens:
            for tt in cand_tokens:
                if ct in tt or tt in ct:
                    substring_bonus += 0.5
                    break

        effective = overlap + substring_bonus
        score = min(100, int((effective / max(len(claim_tokens), 1)) * 100))

        matched = claim_tokens & cand_tokens
        results.append({
            'slug': c['slug'],
            'title': c.get('title', ''),
            'relevance': score,
            'reasoning': f"Keyword: {overlap}+{substring_bonus:.0f}/{len(claim_tokens)} ({', '.join(list(matched)[:3])})",
        })

    results.sort(key=lambda x: x['relevance'], reverse=True)
    return results


def rank_candidates(claim: str, candidates: list[dict],
                    all_claims: list[str] = None,
                    researchtools_url: str = None) -> list[dict]:
    """Rank candidate markets by relevance to the claim using LLM re-ranking.

    Args:
        claim: Primary claim to rank against.
        candidates: List of candidate markets with slug, title, description.
        all_claims: Additional claims for richer context (passed to LLM).
        researchtools_url: Override for the researchtoolspy API URL.
    """
    if not candidates:
        return []

    url = researchtools_url or RESEARCHTOOLS_URL

    payload = {
        'claim': claim,
        'candidates': [
            {
                'slug': c['slug'],
                'title': c.get('title', ''),
                'description': c.get('description', ''),
            }
            for c in candidates
        ],
    }

    # Pass additional claims for context
    if all_claims:
        payload['claims'] = all_claims[:10]

    try:
        resp = requests.post(
            f"{url}/api/tools/claim-match",
            json=payload,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get('results', [])
        results.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return results

    except requests.RequestException as e:
        print(f"  Warning: LLM ranking unavailable ({e}), using keyword fallback.")
        return _keyword_fallback(claim, candidates, all_claims)
