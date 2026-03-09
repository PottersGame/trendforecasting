"""Hacker News data source - uses the official Firebase API (no auth required)."""

import requests
import concurrent.futures
from typing import List, Dict, Any, Optional
from app.utils import cache


HN_BASE = 'https://hacker-news.firebaseio.com/v0'


def _fetch_item(item_id: int) -> Optional[Dict]:
    """Fetch a single HN item."""
    try:
        r = requests.get(f'{HN_BASE}/item/{item_id}.json', timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def get_top_stories(limit: int = 30) -> List[Dict[str, Any]]:
    """Fetch top stories from Hacker News."""
    cache_key = f'hn_top_{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get(f'{HN_BASE}/topstories.json', timeout=10)
        ids = r.json()[:limit]

        stories = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(_fetch_item, ids))

        for item in results:
            if item and item.get('type') == 'story':
                stories.append({
                    'id': item.get('id'),
                    'title': item.get('title', ''),
                    'url': item.get('url', f"https://news.ycombinator.com/item?id={item.get('id')}"),
                    'score': item.get('score', 0),
                    'comments': item.get('descendants', 0),
                    'author': item.get('by', 'unknown'),
                    'time': item.get('time', 0),
                    'source': 'Hacker News',
                })

        stories.sort(key=lambda x: x['score'], reverse=True)
        cache.set(cache_key, stories, ttl=300)
        return stories

    except Exception as e:
        return []


def get_trending_topics_hn(limit: int = 30) -> List[Dict[str, Any]]:
    """Extract trending topics from HN top stories."""
    stories = get_top_stories(limit)
    return stories


def get_ask_hn(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch Ask HN stories."""
    cache_key = f'hn_ask_{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get(f'{HN_BASE}/askstories.json', timeout=10)
        ids = r.json()[:limit]

        stories = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(_fetch_item, ids))

        for item in results:
            if item:
                stories.append({
                    'id': item.get('id'),
                    'title': item.get('title', ''),
                    'url': f"https://news.ycombinator.com/item?id={item.get('id')}",
                    'score': item.get('score', 0),
                    'comments': item.get('descendants', 0),
                    'source': 'Hacker News Ask',
                })

        cache.set(cache_key, stories, ttl=300)
        return stories

    except Exception:
        return []
