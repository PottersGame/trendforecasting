"""
Google Trends integration for fashion keywords.

Uses pytrends (unofficial Google Trends API wrapper) — free, no key required.
Discovers trending fashion terms dynamically from Reddit, news, TikTok and
Pinterest, then queries Google Trends for interest data.
"""

import logging
import re
import time
import random
from typing import List, Dict, Any, Optional
from app.utils import cache

logger = logging.getLogger(__name__)

# ── urllib3 2.x compatibility patch for pytrends ──────────────────────────────
# pytrends uses Retry(method_whitelist=...) which was removed in urllib3 ≥2.0;
# the argument was renamed to `allowed_methods`.  We patch the Retry class once
# at import time so all subsequent uses (including inside pytrends) work with
# both urllib3 1.x and 2.x.
try:
    from urllib3.util.retry import Retry as _Retry  # type: ignore
    if not getattr(_Retry.__init__, '_mw_compat_patched', False):
        _orig_retry_init = _Retry.__init__

        def _compat_retry_init(self, *args, method_whitelist=None,  # type: ignore
                               allowed_methods=None, **kwargs):
            # Honour the old kwarg by forwarding it as the new one
            if method_whitelist is not None and allowed_methods is None:
                allowed_methods = method_whitelist
            _orig_retry_init(self, *args, allowed_methods=allowed_methods,
                             **kwargs)

        _compat_retry_init._mw_compat_patched = True
        _Retry.__init__ = _compat_retry_init  # type: ignore
except Exception:
    pass  # If urllib3 isn't present the import of pytrends will fail anyway

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

# ── Keyword-category matchers for dynamic grouping ───────────────────────────
# Each entry maps a group name to a set of indicator words.  A candidate
# keyword is assigned to the first group whose indicator words appear in it.
_GROUP_MATCHERS: Dict[str, List[str]] = {
    'luxury':     ['luxury', 'hermès', 'chanel', 'gucci', 'prada', 'lv',
                   'dior', 'balenciaga', 'designer', 'couture'],
    'sustainable': ['sustainab', 'eco', 'thrift', 'vintage', 'upcycl',
                    'secondhand', 'slow fashion', 'resale', 'depop'],
    'streetwear': ['streetwear', 'sneaker', 'hypebeast', 'drop', 'techwear',
                   'hype', 'kicks', 'jordan', 'nike', 'adidas', 'supreme'],
    'aesthetics': ['aesthetic', 'academia', 'cottagecore', 'mob wife',
                   'clean girl', 'quiet luxury', 'old money', 'balletcore',
                   'gorpcore', 'coastal', 'coquette', 'y2k', 'grunge',
                   'preppy', 'bohemian', 'minimalist'],
    'seasonal':   ['spring', 'summer', 'fall', 'winter', 'autumn',
                   'fashion week', 'runway', 'collection', 'ss', 'fw'],
    'beauty':     ['beauty', 'makeup', 'skincare', 'hair', 'nail',
                   'glam', 'glow'],
    'trending':   [],  # catch-all — every discovered keyword goes here too
}

# Minimum fallback keywords per group (used only when all live sources fail)
_FALLBACK_GROUPS: Dict[str, List[str]] = {
    'aesthetics':  ['quiet luxury', 'dark academia', 'coquette aesthetic',
                    'mob wife aesthetic', 'clean girl aesthetic'],
    'streetwear':  ['streetwear', 'sneaker culture', 'hypebeast', 'techwear',
                    'drop culture'],
    'sustainable': ['sustainable fashion', 'slow fashion', 'thrift shopping',
                    'vintage clothing', 'upcycled fashion'],
    'luxury':      ['luxury fashion', 'designer fashion', 'haute couture',
                    'fashion week', 'runway fashion'],
    'trending':    ['fashion trend', 'viral fashion', 'new fashion',
                    'fashion 2025', 'style trend'],
}

# Module-level cache for the dynamically built groups
# (refreshed at most every 30 minutes — same TTL as Google Trends data)
AESTHETIC_GROUPS: Dict[str, List[str]] = dict(_FALLBACK_GROUPS)


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


# ── Dynamic keyword discovery ─────────────────────────────────────────────────

def discover_trending_keywords(limit: int = 60) -> List[str]:
    """
    Mine the top fashion keywords from Reddit, news RSS feeds, TikTok and
    Pinterest data sources, then deduplicate and rank them.

    Imported lazily to avoid circular imports at module load time.
    Falls back to an empty list if all sources are unavailable.
    """
    cache_key = f'gtrends_discovered_kw_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    freq: Dict[str, int] = {}

    # Source weights: news headlines carry the most signal (×3), Reddit and
    # TikTok are medium (×2), and Pinterest is treated as supplementary (×1).
    _WEIGHT_REDDIT    = 2
    _WEIGHT_NEWS      = 3
    _WEIGHT_TIKTOK    = 2
    _WEIGHT_PINTEREST = 1

    # ── Reddit ────────────────────────────────────────────────────────────────
    try:
        from app.data_sources.reddit_fashion import get_trending_keywords as _reddit_kw
        for item in _reddit_kw(limit=50):
            w = item.get('word', '').strip().lower()
            if w:
                freq[w] = freq.get(w, 0) + item.get('count', 1) * _WEIGHT_REDDIT
    except Exception as exc:
        logger.debug("Reddit keyword discovery failed: %s", exc)

    # ── Fashion news ──────────────────────────────────────────────────────────
    try:
        from app.data_sources.fashion_news import (
            get_fashion_news, extract_trending_keywords as _news_kw,
        )
        news = get_fashion_news(limit=80)
        for item in _news_kw(news, top_n=50):
            w = item.get('word', '').strip().lower()
            if w:
                freq[w] = freq.get(w, 0) + item.get('count', 1) * _WEIGHT_NEWS
    except Exception as exc:
        logger.debug("News keyword discovery failed: %s", exc)

    # ── TikTok ────────────────────────────────────────────────────────────────
    try:
        from app.data_sources.tiktok_fashion import get_tiktok_trending_keywords as _tiktok_kw
        for item in _tiktok_kw(limit=40):
            w = item.get('word', '').strip().lower()
            if w:
                freq[w] = freq.get(w, 0) + item.get('count', 1) * _WEIGHT_TIKTOK
    except Exception as exc:
        logger.debug("TikTok keyword discovery failed: %s", exc)

    # ── Pinterest ─────────────────────────────────────────────────────────────
    try:
        from app.data_sources.pinterest_fashion import get_pinterest_trending_keywords as _pin_kw
        for item in _pin_kw(limit=40):
            w = item.get('word', '').strip().lower()
            if w:
                freq[w] = freq.get(w, 0) + item.get('count', 1) * _WEIGHT_PINTEREST
    except Exception as exc:
        logger.debug("Pinterest keyword discovery failed: %s", exc)

    # Filter out very short / non-alphabetic tokens and generic noise words
    _STOP = {
        'fashion', 'style', 'wear', 'wearing', 'wore', 'clothes', 'clothing',
        'outfit', 'dress', 'shop', 'brand', 'new', 'look', 'love', 'best',
        'good', 'great', 'the', 'and', 'for', 'this', 'that', 'with', 'from',
        'one', 'all', 'get', 'buy', 'via', 'can', 'how', 'what', 'just',
        'tiktok', 'trending', 'trend', 'video', 'post', 'share', 'like',
        'follow', 'comment', 'viral', 'fyp', 'foryou', 'reels', 'reel',
        'instagram', 'pinterest', 'reddit', 'youtube', 'twitter',
    }
    keywords = [
        w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)
        if len(w) >= 4 and re.search(r'[a-z]', w) and w not in _STOP
    ][:limit]

    cache.set(cache_key, keywords, ttl=1800)
    return keywords


def _jitter() -> None:
    """Small random sleep to avoid rate-limiting."""
    time.sleep(random.uniform(0.4, 1.2))


def _assign_group(keyword: str) -> str:
    """Return the best matching group name for a keyword."""
    kw_lower = keyword.lower()
    for group, indicators in _GROUP_MATCHERS.items():
        if group == 'trending':
            continue
        if any(ind in kw_lower for ind in indicators):
            return group
    return 'trending'


def refresh_aesthetic_groups(force: bool = False) -> Dict[str, List[str]]:
    """
    Rebuild ``AESTHETIC_GROUPS`` from live data sources.

    Results are cached for 30 minutes.  Pass ``force=True`` to bypass the
    cache and always re-discover.  Falls back to ``_FALLBACK_GROUPS`` when
    no live keywords can be discovered.
    """
    global AESTHETIC_GROUPS

    cache_key = 'gtrends_aesthetic_groups'
    if not force:
        hit = cache.get(cache_key)
        if hit is not None:
            AESTHETIC_GROUPS = hit
            return hit

    keywords = discover_trending_keywords(limit=80)

    if not keywords:
        logger.info("No dynamic keywords discovered — using fallback groups")
        AESTHETIC_GROUPS = dict(_FALLBACK_GROUPS)
        cache.set(cache_key, AESTHETIC_GROUPS, ttl=1800)
        return AESTHETIC_GROUPS

    # Also pull today's Google Trends trending searches and add fashion ones
    pt = _client()
    if pt:
        try:
            _jitter()
            df = pt.trending_searches(pn='united_states')
            if df is not None and not df.empty:
                _FASHION_SIGNALS = {
                    'fashion', 'style', 'outfit', 'trend', 'wear', 'clothing',
                    'dress', 'shoes', 'bag', 'luxury', 'beauty', 'makeup',
                    'vintage', 'thrift', 'streetwear', 'sneaker', 'aesthetic',
                }
                for _, row in df.iterrows():
                    term = str(row.iloc[0]).strip().lower()
                    if any(sig in term for sig in _FASHION_SIGNALS):
                        keywords.append(term)
        except Exception as exc:
            logger.debug("Could not fetch trending searches for group refresh: %s", exc)

    # Deduplicate while preserving order
    seen: set = set()
    unique_kw: List[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_kw.append(kw)

    # Assign each keyword to a group
    groups: Dict[str, List[str]] = {g: [] for g in _GROUP_MATCHERS}
    for kw in unique_kw:
        grp = _assign_group(kw)
        groups[grp].append(kw)
        groups['trending'].append(kw)  # all keywords feed the catch-all group

    # Google Trends accepts at most 5 keywords per payload — keep exactly 5.
    result: Dict[str, List[str]] = {}
    for grp, kws in groups.items():
        if kws:
            result[grp] = kws[:5]  # hard Google Trends limit: max 5 keywords
        elif grp in _FALLBACK_GROUPS:
            result[grp] = _FALLBACK_GROUPS[grp][:5]

    # Ensure every fallback group is represented
    for grp, kws in _FALLBACK_GROUPS.items():
        if grp not in result:
            result[grp] = kws[:5]

    AESTHETIC_GROUPS = result
    cache.set(cache_key, result, ttl=1800)
    logger.info(
        "Aesthetic groups refreshed: %s",
        {g: len(v) for g, v in result.items()},
    )
    return result


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


def get_aesthetic_group_interest(group: str = 'aesthetics') -> Dict[str, Any]:
    """Interest-over-time for one of the dynamically-built keyword groups."""
    groups = refresh_aesthetic_groups()
    # Accept the old default name as an alias for 'aesthetics'
    if group == 'viral_aesthetics':
        group = 'aesthetics'
    keywords = groups.get(group) or groups.get('aesthetics') or list(groups.values())[0]
    return get_interest_over_time(keywords[:5], timeframe='today 3-m')


def get_all_group_scores() -> Dict[str, float]:
    """
    Returns a dict {group_name: average_recent_score} for each aesthetic group.
    Uses the last 3 data points as 'current interest'.
    Groups are refreshed from live data sources before scoring.
    """
    cache_key = 'gtrends_all_group_scores'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    groups = refresh_aesthetic_groups()

    scores: Dict[str, float] = {}
    for group, keywords in groups.items():
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
