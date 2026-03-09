"""
Reddit fashion community data source.

Uses the public Reddit JSON API — no credentials needed.
Covers the biggest fashion subreddits: r/femalefashionadvice,
r/malefashionadvice, r/streetwear, r/frugalmalefashion, r/Sneakers,
r/handbags, r/VintageFashion, r/sustainability, r/beauty, and more.
"""

import requests
import re
from typing import List, Dict, Any
from app.utils import cache

HEADERS = {'User-Agent': 'FashionTrendForecasting/1.0 (educational)'}

# (subreddit, display_label, category)
FASHION_SUBS: List[tuple] = [
    ('femalefashionadvice', 'Female Fashion Advice', 'style'),
    ('malefashionadvice',   'Male Fashion Advice',   'style'),
    ('streetwear',          'Streetwear',            'streetwear'),
    ('frugalmalefashion',   'Frugal Male Fashion',   'style'),
    ('sneakers',            'Sneakers',              'streetwear'),
    ('handbags',            'Handbags',              'accessories'),
    ('VintageFashion',      'Vintage Fashion',       'vintage'),
    ('femalefashion',       'Female Fashion',        'style'),
    ('mensfashion',         'Men\'s Fashion',        'style'),
    ('Flipping',            'Fashion Resale',        'vintage'),
    ('Sustainable_Fashion', 'Sustainable Fashion',   'sustainable'),
    ('beauty',              'Beauty',                'beauty'),
    ('SkincareAddiction',   'Skincare',              'beauty'),
    ('Depop',               'Depop Resale',          'vintage'),
    ('findfashion',         'Find Fashion',          'style'),
]

_STRIP_TAGS = re.compile(r'<[^>]+>')


def _clean(text: str) -> str:
    return _STRIP_TAGS.sub('', text or '').strip()[:280]


def _fetch_sub(sub: str, category: str, label: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Hot posts from one subreddit."""
    cache_key = f'reddit_{sub}_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    url = f'https://www.reddit.com/r/{sub}/hot.json?limit={limit}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        posts = []
        for child in r.json().get('data', {}).get('children', []):
            p = child.get('data', {})
            if p.get('stickied') or p.get('pinned'):
                continue
            # image thumbnail
            img = ''
            preview = p.get('preview', {})
            if preview:
                imgs = preview.get('images', [])
                if imgs:
                    src = imgs[0].get('source', {})
                    img = src.get('url', '').replace('&amp;', '&')

            posts.append({
                'title':        p.get('title', ''),
                'subreddit':    p.get('subreddit', sub),
                'label':        label,
                'category':     category,
                'score':        p.get('score', 0),
                'upvote_ratio': round(p.get('upvote_ratio', 0) * 100),
                'comments':     p.get('num_comments', 0),
                'url':          p.get('url', ''),
                'permalink':    f"https://www.reddit.com{p.get('permalink', '')}",
                'image':        img,
                'flair':        p.get('link_flair_text', '') or '',
                'source':       'Reddit',
            })
        cache.set(cache_key, posts, ttl=300)
        return posts
    except Exception:
        return []


def get_all_fashion_posts(limit_per_sub: int = 20) -> List[Dict[str, Any]]:
    """Hot posts from every fashion subreddit, sorted by score."""
    cache_key = f'reddit_fashion_all_{limit_per_sub}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    all_posts: List[Dict[str, Any]] = []
    for sub, label, cat in FASHION_SUBS:
        all_posts.extend(_fetch_sub(sub, cat, label, limit=limit_per_sub))

    all_posts.sort(key=lambda x: x['score'], reverse=True)
    cache.set(cache_key, all_posts, ttl=300)
    return all_posts


def get_posts_by_category(category: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Hot posts filtered by category."""
    all_posts = get_all_fashion_posts(limit_per_sub=20)
    filtered = [p for p in all_posts if p['category'] == category]
    return filtered[:limit]


def get_subreddit_activity() -> List[Dict[str, Any]]:
    """
    Return per-subreddit aggregate stats:
    total score, average score, post count.
    """
    cache_key = 'reddit_activity'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    stats: Dict[str, Dict] = {}
    for sub, label, cat in FASHION_SUBS:
        posts = _fetch_sub(sub, cat, label, limit=20)
        if not posts:
            continue
        scores = [p['score'] for p in posts]
        stats[sub] = {
            'subreddit': sub,
            'label': label,
            'category': cat,
            'post_count': len(posts),
            'total_score': sum(scores),
            'avg_score': round(sum(scores) / len(scores)) if scores else 0,
            'max_score': max(scores, default=0),
        }

    result = sorted(stats.values(), key=lambda x: x['total_score'], reverse=True)
    cache.set(cache_key, result, ttl=600)
    return result


def get_trending_keywords(limit: int = 40) -> List[Dict[str, Any]]:
    """Most frequent fashion keywords across all subreddit post titles."""
    STOP = {
        'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
        'from','as','is','was','are','were','be','been','have','has','had','do',
        'does','did','will','would','could','should','may','might','not','it',
        'this','that','these','those','all','more','other','than','then','can',
        'just','also','get','my','your','his','her','our','their','i','we','you',
        'they','he','she','am','new','want','need','any','some','what','how','why',
        'when','where','who','which','got','did','after','before','about','over',
        'into','out','up','down','first','one','two','three','looking','help',
        'please','anyone','like','know','think','been','here','there','still',
        'back','good','great','love','best','buy','wear','wearing','wore',
    }
    posts = get_all_fashion_posts(limit_per_sub=25)
    freq: Dict[str, int] = {}
    for p in posts:
        for word in re.findall(r"[a-z]{3,}", p['title'].lower()):
            if word not in STOP:
                freq[word] = freq.get(word, 0) + 1
    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [{'word': w, 'count': c} for w, c in sorted_kw[:limit]]


def get_top_posts(limit: int = 10) -> List[Dict[str, Any]]:
    """Return the single most-upvoted post from each category."""
    all_posts = get_all_fashion_posts(limit_per_sub=20)
    best: Dict[str, Dict] = {}
    for p in all_posts:
        cat = p['category']
        if cat not in best or p['score'] > best[cat]['score']:
            best[cat] = p
    return sorted(best.values(), key=lambda x: x['score'], reverse=True)[:limit]
