"""Reddit public data source - uses the public Reddit JSON API (no auth required)."""

import requests
from typing import List, Dict, Any
from app.utils import cache


REDDIT_BASE = 'https://www.reddit.com'
HEADERS = {
    'User-Agent': 'TrendForecasting/1.0 (educational project)',
}

TREND_SUBREDDITS = {
    'fashion': ['r/femalefashionadvice', 'r/malefashionadvice', 'r/streetwear', 'r/frugalmalefashion'],
    'technology': ['r/technology', 'r/programming', 'r/MachineLearning', 'r/artificial'],
    'social': ['r/worldnews', 'r/news', 'r/todayilearned', 'r/interestingasfuck'],
    'business': ['r/wallstreetbets', 'r/investing', 'r/stocks', 'r/entrepreneur'],
    'science': ['r/science', 'r/Futurology', 'r/space', 'r/Physics'],
    'entertainment': ['r/movies', 'r/Music', 'r/gaming', 'r/television'],
    'health': ['r/Health', 'r/nutrition', 'r/fitness', 'r/medicine'],
}


def get_subreddit_hot(subreddit: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Fetch hot posts from a subreddit."""
    sub = subreddit.replace('r/', '')
    cache_key = f'reddit_{sub}_{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        url = f'{REDDIT_BASE}/r/{sub}/hot.json?limit={limit}'
        r = requests.get(url, headers=HEADERS, timeout=10)

        if r.status_code == 200:
            data = r.json()
            posts = []
            for post in data.get('data', {}).get('children', []):
                p = post.get('data', {})
                if not p.get('stickied', False):
                    posts.append({
                        'title': p.get('title', ''),
                        'subreddit': p.get('subreddit', sub),
                        'score': p.get('score', 0),
                        'upvote_ratio': p.get('upvote_ratio', 0),
                        'num_comments': p.get('num_comments', 0),
                        'url': p.get('url', ''),
                        'permalink': f"https://www.reddit.com{p.get('permalink', '')}",
                        'author': p.get('author', 'unknown'),
                        'created_utc': p.get('created_utc', 0),
                        'is_self': p.get('is_self', False),
                        'selftext': p.get('selftext', '')[:200],
                        'source': 'Reddit',
                    })
            cache.set(cache_key, posts, ttl=300)
            return posts

    except Exception:
        pass

    return []


def get_trending_by_category(category: str = 'technology', limit: int = 30) -> List[Dict[str, Any]]:
    """Get trending posts from a category."""
    subreddits = TREND_SUBREDDITS.get(category, [])
    if not subreddits:
        return []

    all_posts = []
    for sub in subreddits[:2]:  # Limit requests
        posts = get_subreddit_hot(sub, limit=15)
        all_posts.extend(posts)

    all_posts.sort(key=lambda x: x['score'], reverse=True)
    return all_posts[:limit]


def get_all_trending(limit: int = 10) -> Dict[str, List[Dict]]:
    """Get trending posts across all categories."""
    cache_key = f'reddit_all_{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {}
    for category in TREND_SUBREDDITS:
        result[category] = get_trending_by_category(category, limit=limit)

    cache.set(cache_key, result, ttl=300)
    return result


def get_trending_keywords(category: str = 'technology', limit: int = 20) -> List[Dict[str, Any]]:
    """Extract trending keywords from Reddit posts."""
    posts = get_trending_by_category(category, limit=50)
    word_freq: Dict[str, int] = {}

    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
                  'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                  'would', 'could', 'should', 'may', 'might', 'shall', 'can', 'need',
                  'it', 'this', 'that', 'i', 'you', 'he', 'she', 'we', 'they', 'my',
                  'your', 'his', 'her', 'our', 'their', 'its', 'what', 'which', 'who'}

    for post in posts:
        words = post['title'].lower().split()
        for word in words:
            word = ''.join(c for c in word if c.isalpha())
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [{'word': w, 'count': c} for w, c in sorted_words[:limit]]
