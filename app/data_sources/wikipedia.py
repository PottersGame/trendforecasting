"""Wikipedia trending articles - uses the Wikimedia REST API (no auth required)."""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
from app.utils import cache


WIKI_API = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access'
WIKI_SEARCH = 'https://en.wikipedia.org/w/api.php'


def get_trending_articles(days_back: int = 1) -> List[Dict[str, Any]]:
    """Fetch the most viewed Wikipedia articles for recent days."""
    cache_key = f'wiki_trending_{days_back}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    articles = []
    try:
        target = datetime.utcnow() - timedelta(days=days_back)
        year = target.strftime('%Y')
        month = target.strftime('%m')
        day = target.strftime('%d')

        url = f'{WIKI_API}/{year}/{month}/{day}'
        headers = {'User-Agent': 'TrendForecasting/1.0 (educational project)'}
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code == 200:
            data = r.json()
            items = data.get('items', [{}])[0].get('articles', [])
            for item in items[:50]:
                title = item.get('article', '').replace('_', ' ')
                if title and not title.startswith('Special:') and not title.startswith('Wikipedia:'):
                    articles.append({
                        'title': title,
                        'views': item.get('views', 0),
                        'rank': item.get('rank', 0),
                        'url': f"https://en.wikipedia.org/wiki/{item.get('article', '')}",
                        'source': 'Wikipedia',
                    })

    except Exception as e:
        pass

    # Fallback to yesterday if today isn't available
    if not articles and days_back == 1:
        return get_trending_articles(days_back=2)

    cache.set(cache_key, articles, ttl=3600)
    return articles


def get_article_summary(title: str) -> Dict[str, Any]:
    """Get a summary of a Wikipedia article."""
    cache_key = f'wiki_summary_{title}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(" ", "_")}'
        headers = {'User-Agent': 'TrendForecasting/1.0 (educational project)'}
        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code == 200:
            data = r.json()
            result = {
                'title': data.get('title', ''),
                'extract': data.get('extract', ''),
                'thumbnail': data.get('thumbnail', {}).get('source', ''),
                'url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
            }
            cache.set(cache_key, result, ttl=3600)
            return result
    except Exception:
        pass

    return {}


def get_category_trends(categories: List[str]) -> Dict[str, List[Dict]]:
    """Get trending articles per category."""
    all_articles = get_trending_articles()
    result = {}

    for category in categories:
        # Simple keyword matching
        cat_lower = category.lower()
        matching = [
            a for a in all_articles
            if any(kw in a['title'].lower() for kw in [cat_lower] + _get_keywords(cat_lower))
        ]
        result[category] = matching[:10]

    return result


def _get_keywords(category: str) -> List[str]:
    """Get related keywords for a category."""
    keywords_map = {
        'fashion': ['clothing', 'style', 'designer', 'runway', 'couture', 'apparel', 'outfit', 'trend'],
        'technology': ['tech', 'software', 'hardware', 'computer', 'ai', 'robot', 'internet', 'digital'],
        'science': ['research', 'study', 'discovery', 'experiment', 'physics', 'biology', 'chemistry'],
        'politics': ['election', 'government', 'president', 'congress', 'senate', 'policy', 'vote'],
        'sports': ['football', 'basketball', 'baseball', 'soccer', 'tennis', 'olympics', 'championship'],
        'entertainment': ['movie', 'film', 'music', 'celebrity', 'award', 'actor', 'singer', 'show'],
        'business': ['company', 'market', 'stock', 'economy', 'finance', 'investment', 'startup'],
    }
    return keywords_map.get(category, [])
