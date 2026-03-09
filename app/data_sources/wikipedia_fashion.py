"""
Wikipedia fashion data source.

Fetches today's most-viewed English Wikipedia articles and filters for
fashion-relevant entries. Also retrieves full summaries for fashion topics.
No API key required.
"""

import requests
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from app.utils import cache

HEADERS = {'User-Agent': 'FashionTrendForecasting/1.0 (educational)'}

PAGEVIEWS_API = (
    'https://wikimedia.org/api/rest_v1/metrics/pageviews/top'
    '/en.wikipedia/all-access/{year}/{month}/{day}'
)

FASHION_KEYWORDS = {
    # explicit fashion nouns
    'fashion', 'style', 'clothing', 'clothes', 'apparel', 'outfit', 'dress',
    'couture', 'designer', 'brand', 'luxury', 'streetwear', 'sneaker', 'shoe',
    'boot', 'bag', 'handbag', 'accessory', 'jewelry', 'jewellery', 'watch',
    'hat', 'coat', 'jacket', 'suit', 'skirt', 'jeans', 'denim', 'silk', 'lace',
    'runway', 'collection', 'season', 'trend', 'aesthetic', 'vintage', 'retro',
    'thrift', 'upcycl', 'sustainable', 'eco', 'vogue', 'elle', 'bazaar',
    'gucci', 'prada', 'chanel', 'dior', 'hermès', 'hermes', 'versace',
    'armani', 'burberry', 'valentino', 'givenchy', 'balenciaga', 'bottega',
    'saint laurent', 'louis vuitton', 'fendi', 'off-white', 'supreme',
    'palace', 'stüssy', 'stussy', 'carhartt', 'nike', 'adidas', 'new balance',
    'beauty', 'makeup', 'cosmetic', 'skincare', 'perfume', 'fragrance',
    'model', 'supermodel', 'catwalk', 'fashion week', 'met gala',
}

_IGNORE = {
    'Main_Page', 'Special:', 'Wikipedia:', 'Help:', 'Portal:', 'File:',
    'Template:', 'Category:', 'Talk:', 'User:',
}


def _is_fashion(title: str) -> bool:
    title_l = title.lower().replace('_', ' ')
    return any(kw in title_l for kw in FASHION_KEYWORDS)


def _should_skip(title: str) -> bool:
    return any(title.startswith(prefix) for prefix in _IGNORE)


def get_top_fashion_articles(days_back: int = 1, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Return the top Wikipedia fashion articles by pageviews for a recent day.
    Falls back up to 3 days if today's data is unavailable yet.
    """
    cache_key = f'wiki_fashion_{days_back}_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    for offset in range(days_back, days_back + 3):
        target = datetime.utcnow() - timedelta(days=offset)
        url = PAGEVIEWS_API.format(
            year=target.strftime('%Y'),
            month=target.strftime('%m'),
            day=target.strftime('%d'),
        )
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            raw_articles = r.json().get('items', [{}])[0].get('articles', [])
        except Exception:
            continue

        results = []
        for item in raw_articles:
            raw_title = item.get('article', '')
            title = raw_title.replace('_', ' ')
            if _should_skip(raw_title):
                continue
            if _is_fashion(raw_title):
                results.append({
                    'title':  title,
                    'views':  item.get('views', 0),
                    'rank':   item.get('rank', 0),
                    'url':    f"https://en.wikipedia.org/wiki/{raw_title}",
                    'source': 'Wikipedia',
                    'date':   target.strftime('%Y-%m-%d'),
                })
        if results:
            results = results[:limit]
            cache.set(cache_key, results, ttl=3600)
            return results

    return []


def get_article_summary(title: str) -> Dict[str, Any]:
    """Fetch the Wikipedia REST summary for a title."""
    slug = title.replace(' ', '_')
    cache_key = f'wiki_summary_{slug}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    try:
        url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{slug}'
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            d = r.json()
            result = {
                'title':     d.get('title', ''),
                'extract':   d.get('extract', ''),
                'thumbnail': d.get('thumbnail', {}).get('source', ''),
                'url':       d.get('content_urls', {}).get('desktop', {}).get('page', ''),
            }
            cache.set(cache_key, result, ttl=86400)
            return result
    except Exception:
        pass
    return {}


def get_fashion_designer_articles() -> List[Dict[str, Any]]:
    """Dedicated lookup for famous designer / house Wikipedia pages."""
    designers = [
        'Coco Chanel', 'Christian Dior', 'Yves Saint Laurent', 'Gianni Versace',
        'Giorgio Armani', 'Valentino Garavani', 'Karl Lagerfeld', 'Virgil Abloh',
        'Alexander McQueen', 'Vivienne Westwood', 'Rei Kawakubo', 'Miuccia Prada',
    ]
    cache_key = 'wiki_designers'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    results = []
    for name in designers:
        summary = get_article_summary(name)
        if summary.get('extract'):
            results.append({
                'title':     summary['title'],
                'extract':   summary['extract'][:300],
                'thumbnail': summary['thumbnail'],
                'url':       summary['url'],
                'source':    'Wikipedia',
            })

    cache.set(cache_key, results, ttl=86400)
    return results
