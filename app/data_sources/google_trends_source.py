"""Google Trends data source using pytrends library."""

import time
import random
from typing import List, Dict, Any, Optional
from app.utils import cache

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False


# Default trending topics across categories
DEFAULT_TOPICS = {
    'fashion': ['sustainable fashion', 'streetwear', 'vintage clothing', 'athleisure', 'minimalist fashion'],
    'technology': ['artificial intelligence', 'blockchain', 'quantum computing', 'electric vehicles', 'metaverse'],
    'social': ['climate change', 'mental health', 'remote work', 'cryptocurrency', 'social media'],
    'health': ['intermittent fasting', 'plant-based diet', 'mindfulness', 'telehealth', 'fitness tracker'],
    'business': ['startup funding', 'e-commerce', 'supply chain', 'inflation', 'interest rates'],
}


def _get_pytrends_client() -> Optional[object]:
    """Get a pytrends client."""
    if not PYTRENDS_AVAILABLE:
        return None
    try:
        pt = TrendReq(hl='en-US', tz=360, timeout=(10, 25))
        return pt
    except Exception:
        return None


def get_interest_over_time(
    keywords: List[str],
    timeframe: str = 'today 3-m',
    geo: str = '',
) -> Dict[str, Any]:
    """Get interest over time for keywords from Google Trends."""
    cache_key = f'gtrends_iot_{"-".join(sorted(keywords))}_{timeframe}_{geo}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {'keywords': keywords, 'data': {}, 'dates': []}

    if not PYTRENDS_AVAILABLE:
        result['error'] = 'pytrends not available'
        return result

    try:
        pt = _get_pytrends_client()
        if not pt:
            return result

        # Add small delay to avoid rate limiting
        time.sleep(random.uniform(0.5, 1.5))

        pt.build_payload(keywords[:5], cat=0, timeframe=timeframe, geo=geo, gprop='')
        df = pt.interest_over_time()

        if not df.empty:
            result['dates'] = [d.strftime('%Y-%m-%d') for d in df.index]
            for kw in keywords[:5]:
                if kw in df.columns:
                    result['data'][kw] = df[kw].tolist()

        cache.set(cache_key, result, ttl=1800)

    except Exception as e:
        result['error'] = str(e)

    return result


def get_trending_searches() -> List[Dict[str, Any]]:
    """Get currently trending searches."""
    cache_key = 'gtrends_trending'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = []

    if not PYTRENDS_AVAILABLE:
        return results

    try:
        pt = _get_pytrends_client()
        if not pt:
            return results

        time.sleep(random.uniform(0.5, 1.5))
        df = pt.trending_searches(pn='united_states')

        if df is not None and not df.empty:
            for i, row in df.iterrows():
                results.append({
                    'query': str(row.iloc[0]) if hasattr(row, 'iloc') else str(row),
                    'rank': i + 1,
                    'source': 'Google Trends',
                })
            cache.set(cache_key, results[:30], ttl=1800)

    except Exception:
        pass

    return results


def get_related_queries(keyword: str) -> Dict[str, Any]:
    """Get related queries for a keyword."""
    cache_key = f'gtrends_related_{keyword}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {'rising': [], 'top': []}

    if not PYTRENDS_AVAILABLE:
        return result

    try:
        pt = _get_pytrends_client()
        if not pt:
            return result

        time.sleep(random.uniform(0.5, 1.5))
        pt.build_payload([keyword], cat=0, timeframe='today 3-m', geo='', gprop='')
        queries = pt.related_queries()

        if keyword in queries:
            rising_df = queries[keyword].get('rising')
            top_df = queries[keyword].get('top')

            if rising_df is not None and not rising_df.empty:
                result['rising'] = [
                    {'query': row['query'], 'value': int(row['value'])}
                    for _, row in rising_df.head(10).iterrows()
                ]
            if top_df is not None and not top_df.empty:
                result['top'] = [
                    {'query': row['query'], 'value': int(row['value'])}
                    for _, row in top_df.head(10).iterrows()
                ]

        cache.set(cache_key, result, ttl=1800)

    except Exception:
        pass

    return result


def get_category_interest(category: str) -> Dict[str, Any]:
    """Get interest over time for a category's default keywords."""
    keywords = DEFAULT_TOPICS.get(category, DEFAULT_TOPICS['technology'])
    return get_interest_over_time(keywords[:5], timeframe='today 3-m')


def get_regional_interest(keyword: str) -> List[Dict[str, Any]]:
    """Get regional interest for a keyword."""
    cache_key = f'gtrends_regional_{keyword}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = []

    if not PYTRENDS_AVAILABLE:
        return results

    try:
        pt = _get_pytrends_client()
        if not pt:
            return results

        time.sleep(random.uniform(0.5, 1.5))
        pt.build_payload([keyword], cat=0, timeframe='today 3-m', geo='', gprop='')
        df = pt.interest_by_region(resolution='COUNTRY', inc_low_vol=False, inc_geo_code=True)

        if not df.empty:
            df = df.reset_index()
            df = df.sort_values(keyword, ascending=False).head(20)
            for _, row in df.iterrows():
                results.append({
                    'country': row.get('geoName', ''),
                    'code': row.get('geoCode', ''),
                    'value': int(row.get(keyword, 0)),
                })
        cache.set(cache_key, results, ttl=1800)

    except Exception:
        pass

    return results
