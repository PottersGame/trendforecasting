"""
Google Trends integration for fashion keywords.

Uses pytrends (unofficial Google Trends API wrapper) — free, no key required.
Tracks viral fashion aesthetics, style terms, and seasonal searches.
"""

import time
import random
from typing import List, Dict, Any, Optional
from app.utils import cache

try:
    from pytrends.request import TrendReq
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

# ── Fashion keyword groups tracked ────────────────────────────────────────────

AESTHETIC_GROUPS: Dict[str, List[str]] = {
    'viral_aesthetics': [
        'quiet luxury', 'old money aesthetic', 'clean girl aesthetic',
        'mob wife aesthetic', 'dark academia',
    ],
    'style_movements': [
        'Y2K fashion', 'cottagecore', 'balletcore', 'gorpcore', 'coastal grandmother',
    ],
    'sustainable': [
        'sustainable fashion', 'slow fashion', 'thrift shopping',
        'vintage clothing', 'upcycled fashion',
    ],
    'streetwear': [
        'streetwear', 'sneaker culture', 'hypebeast', 'drop culture', 'techwear',
    ],
    'luxury': [
        'luxury fashion', 'Hermès', 'Chanel', 'Louis Vuitton', 'Bottega Veneta',
    ],
    'seasonal': [
        'spring fashion 2025', 'summer fashion 2025',
        'fall fashion 2025', 'winter fashion 2025', 'fashion week',
    ],
    'color_trends': [
        'peach fuzz pantone', 'mocha mousse', 'butter yellow fashion',
        'sage green fashion', 'cobalt blue fashion',
    ],
}

# Flat list used for trending-search calls
ALL_FASHION_KEYWORDS: List[str] = [
    kw for group in AESTHETIC_GROUPS.values() for kw in group
]


def _client() -> Optional[object]:
    if not _AVAILABLE:
        return None
    try:
        return TrendReq(hl='en-US', tz=0, timeout=(10, 25))
    except Exception:
        return None


def _jitter() -> None:
    """Small random sleep to avoid rate-limiting."""
    time.sleep(random.uniform(0.4, 1.2))


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_interest_over_time(
    keywords: List[str],
    timeframe: str = 'today 3-m',
    geo: str = '',
) -> Dict[str, Any]:
    """
    Return {dates: [...], data: {keyword: [values]}} for up to 5 keywords.
    Falls back to empty data when pytrends is unavailable or rate-limited.
    """
    kw_key = '_'.join(sorted(keywords[:5]))
    cache_key = f'gtrends_iot_{kw_key}_{timeframe}_{geo}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    result: Dict[str, Any] = {'keywords': keywords[:5], 'dates': [], 'data': {}}

    pt = _client()
    if not pt:
        return result

    try:
        _jitter()
        pt.build_payload(keywords[:5], timeframe=timeframe, geo=geo)
        df = pt.interest_over_time()
        if not df.empty:
            result['dates'] = [d.strftime('%Y-%m-%d') for d in df.index]
            for kw in keywords[:5]:
                if kw in df.columns:
                    result['data'][kw] = [int(v) for v in df[kw].tolist()]
        cache.set(cache_key, result, ttl=1800)
    except Exception:
        pass

    return result


def get_trending_fashion_searches() -> List[Dict[str, Any]]:
    """Daily trending searches filtered to fashion-relevant terms."""
    cache_key = 'gtrends_fashion_trending'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    results: List[Dict[str, Any]] = []
    pt = _client()
    if not pt:
        return results

    try:
        _jitter()
        df = pt.trending_searches(pn='united_states')
        if df is not None and not df.empty:
            fashion_terms = {
                'fashion','style','outfit','clothes','clothing','dress','shoes','bag',
                'luxury','trend','season','collection','designer','brand','wear',
                'beauty','makeup','skincare','hair','accessories','jewelry','watch',
                'vintage','thrift','sustainable','streetwear','sneakers','boots',
                'jeans','shirt','jacket','coat','suit','skirt','pants',
            }
            for i, row in df.iterrows():
                term = str(row.iloc[0]).lower() if hasattr(row, 'iloc') else str(row).lower()
                if any(ft in term for ft in fashion_terms):
                    results.append({'query': term, 'rank': i + 1, 'source': 'Google Trends'})
            cache.set(cache_key, results[:25], ttl=1800)
    except Exception:
        pass

    return results


def get_aesthetic_group_interest(group: str = 'viral_aesthetics') -> Dict[str, Any]:
    """Interest-over-time for one of the predefined keyword groups."""
    keywords = AESTHETIC_GROUPS.get(group, AESTHETIC_GROUPS['viral_aesthetics'])
    return get_interest_over_time(keywords[:5], timeframe='today 3-m')


def get_all_group_scores() -> Dict[str, float]:
    """
    Returns a dict {group_name: average_recent_score} for each aesthetic group.
    Uses the last 3 data points as 'current interest'.
    """
    cache_key = 'gtrends_all_group_scores'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    scores: Dict[str, float] = {}
    for group, keywords in AESTHETIC_GROUPS.items():
        data = get_interest_over_time(keywords[:5], timeframe='today 3-m')
        values_list = list(data.get('data', {}).values())
        if values_list:
            # Average of the last 3 points across all keywords
            recents = [v[-3:] for v in values_list if v]
            flat = [x for r in recents for x in r]
            scores[group] = round(sum(flat) / len(flat), 1) if flat else 0.0
        else:
            scores[group] = 0.0
        _jitter()  # pace requests

    cache.set(cache_key, scores, ttl=1800)
    return scores


def get_related_queries(keyword: str) -> Dict[str, List[Dict]]:
    """Rising and top related queries for a fashion keyword."""
    cache_key = f'gtrends_related_{keyword}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    result: Dict[str, List[Dict]] = {'rising': [], 'top': []}
    pt = _client()
    if not pt:
        return result

    try:
        _jitter()
        pt.build_payload([keyword], timeframe='today 3-m')
        queries = pt.related_queries()
        if keyword in queries:
            for kind in ('rising', 'top'):
                df = queries[keyword].get(kind)
                if df is not None and not df.empty:
                    result[kind] = [
                        {'query': row['query'], 'value': int(row['value'])}
                        for _, row in df.head(10).iterrows()
                    ]
        cache.set(cache_key, result, ttl=1800)
    except Exception:
        pass

    return result


def get_regional_interest(keyword: str) -> List[Dict[str, Any]]:
    """Country-level interest for a fashion keyword."""
    cache_key = f'gtrends_regional_{keyword}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    results: List[Dict[str, Any]] = []
    pt = _client()
    if not pt:
        return results

    try:
        _jitter()
        pt.build_payload([keyword], timeframe='today 3-m')
        df = pt.interest_by_region(resolution='COUNTRY', inc_low_vol=False, inc_geo_code=True)
        if not df.empty:
            df = df.reset_index().sort_values(keyword, ascending=False).head(20)
            for _, row in df.iterrows():
                results.append({
                    'country': row.get('geoName', ''),
                    'code':    row.get('geoCode', ''),
                    'value':   int(row.get(keyword, 0)),
                })
        cache.set(cache_key, results, ttl=1800)
    except Exception:
        pass

    return results
