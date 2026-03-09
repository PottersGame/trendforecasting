"""
Google Trends integration for fashion keywords.

Uses pytrends (unofficial Google Trends API wrapper) — free, no key required.
Tracks viral fashion aesthetics, style terms, and seasonal searches.
"""

import logging
import time
import random
from typing import List, Dict, Any, Optional
from app.utils import cache

logger = logging.getLogger(__name__)

try:
    from pytrends.request import TrendReq
    from pytrends.exceptions import TooManyRequestsError, ResponseError
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    logger.warning(
        "pytrends is not installed. Google Trends data will be unavailable. "
        "Run: pip install pytrends>=4.9.2"
    )

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


def _unavailable_reason() -> str:
    """Human-readable reason why the Google Trends client is unavailable."""
    if not _AVAILABLE:
        return 'pytrends is not installed'
    return 'Could not connect to Google Trends'


def _client() -> Optional[object]:
    """
    Create a TrendReq client with retry / back-off settings.

    Returns None (and logs a warning) if pytrends is not installed or if the
    initial Google cookie request fails (e.g. network unavailable).
    """
    if not _AVAILABLE:
        return None
    try:
        return TrendReq(
            hl='en-US',
            tz=0,
            timeout=(10, 25),
            retries=3,
            backoff_factor=2,
        )
    except Exception as exc:
        logger.warning("Failed to initialise Google Trends client: %s", exc)
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
    Falls back to empty data (with an 'error' key) when pytrends is
    unavailable or rate-limited.
    """
    kw_key = '_'.join(sorted(keywords[:5]))
    cache_key = f'gtrends_iot_{kw_key}_{timeframe}_{geo}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    result: Dict[str, Any] = {'keywords': keywords[:5], 'dates': [], 'data': {}}

    pt = _client()
    if not pt:
        result['error'] = _unavailable_reason()
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
    except TooManyRequestsError as exc:
        logger.warning("Google Trends rate limit hit for %s: %s", keywords, exc)
        result['error'] = 'Google Trends rate limit reached — please retry later'
    except Exception as exc:
        logger.error("Google Trends interest_over_time failed for %s: %s", keywords, exc)
        result['error'] = str(exc)

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
        logger.warning(
            "Google Trends client unavailable (%s) — skipping trending searches",
            _unavailable_reason(),
        )
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
    except TooManyRequestsError as exc:
        logger.warning("Google Trends rate limit hit for trending searches: %s", exc)
    except Exception as exc:
        logger.error("Google Trends trending_searches failed: %s", exc)

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
        logger.warning(
            "Google Trends client unavailable (%s) — skipping related queries for '%s'",
            _unavailable_reason(),
            keyword,
        )
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
    except TooManyRequestsError as exc:
        logger.warning(
            "Google Trends rate limit hit for related queries '%s': %s", keyword, exc
        )
        result['error'] = 'Google Trends rate limit reached — please retry later'
    except Exception as exc:
        logger.error(
            "Google Trends related_queries failed for '%s': %s", keyword, exc
        )
        result['error'] = str(exc)

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
        logger.warning(
            "Google Trends client unavailable (%s) — skipping regional interest for '%s'",
            _unavailable_reason(),
            keyword,
        )
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
    except TooManyRequestsError as exc:
        logger.warning(
            "Google Trends rate limit hit for regional interest '%s': %s", keyword, exc
        )
    except Exception as exc:
        logger.error(
            "Google Trends interest_by_region failed for '%s': %s", keyword, exc
        )

    return results


def get_status() -> Dict[str, Any]:
    """
    Probe Google Trends connectivity.

    Returns a dict with keys:
      - available (bool): True if the pytrends library is installed
      - connected (bool): True if a TrendReq client could be initialised
                          (i.e. the Google cookie request succeeded)
      - error (str | None): human-readable reason when connected=False
    """
    status: Dict[str, Any] = {
        'available': _AVAILABLE,
        'connected': False,
        'error': None,
    }
    if not _AVAILABLE:
        status['error'] = (
            'pytrends is not installed. '
            'Run: pip install "pytrends>=4.9.2"'
        )
        return status

    pt = _client()
    if pt is None:
        status['error'] = (
            'Could not connect to Google Trends. '
            'Check your network connection or try again later.'
        )
        return status

    status['connected'] = True
    return status
