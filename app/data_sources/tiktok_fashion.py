"""
TikTok fashion data source.

Uses the TikTok Research API when credentials are available
(TIKTOK_CLIENT_KEY + TIKTOK_CLIENT_SECRET environment variables).
Falls back to curated trending hashtag data when no credentials are set.

Fashion hashtags tracked: #OOTD, #FashionTrend, #Y2KFashion, #QuietLuxury, etc.

To enable live data, apply for TikTok Research API access at
https://developers.tiktok.com/products/research-api/ and set:
    TIKTOK_CLIENT_KEY=your_client_key
    TIKTOK_CLIENT_SECRET=your_client_secret
"""

import os
import re
import requests
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.utils import cache

# ── TikTok Research API endpoints ────────────────────────────────────────────

_TIKTOK_AUTH_URL        = 'https://open.tiktokapis.com/v2/oauth/token/'
_TIKTOK_VIDEO_QUERY_URL = 'https://open.tiktokapis.com/v2/research/video/query/'

_HEADERS = {
    'User-Agent': 'FashionTrendForecasting/1.0 (educational research)',
}

# ── Curated fashion-relevant TikTok hashtags ─────────────────────────────────

FASHION_HASHTAGS: List[Dict[str, Any]] = [
    {'tag': 'OOTD',               'category': 'style',       'keywords': ['ootd', 'outfit of the day']},
    {'tag': 'FashionTikTok',      'category': 'style',       'keywords': ['fashion tiktok', 'fashiontiktok']},
    {'tag': 'OutfitInspo',        'category': 'style',       'keywords': ['outfit inspo', 'style inspiration']},
    {'tag': 'Y2KFashion',         'category': 'vintage',     'keywords': ['y2k fashion', 'y2k aesthetic']},
    {'tag': 'QuietLuxury',        'category': 'luxury',      'keywords': ['quiet luxury', 'old money aesthetic']},
    {'tag': 'Balletcore',         'category': 'aesthetic',   'keywords': ['balletcore', 'ballet aesthetic']},
    {'tag': 'Streetwear',         'category': 'streetwear',  'keywords': ['streetwear', 'streetstyle']},
    {'tag': 'ThriftFlip',         'category': 'sustainable', 'keywords': ['thrift flip', 'thrift haul', 'thrifting']},
    {'tag': 'FashionHaul',        'category': 'shopping',    'keywords': ['fashion haul', 'haul video', 'try on haul']},
    {'tag': 'CoquetteAesthetic',  'category': 'aesthetic',   'keywords': ['coquette aesthetic', 'bow aesthetic']},
    {'tag': 'DarkAcademia',       'category': 'aesthetic',   'keywords': ['dark academia', 'dark academia fashion']},
    {'tag': 'Cottagecore',        'category': 'aesthetic',   'keywords': ['cottagecore', 'cottage aesthetic']},
    {'tag': 'Gorpcore',           'category': 'outdoor',     'keywords': ['gorpcore', 'outdoor fashion']},
    {'tag': 'MobWifeAesthetic',   'category': 'viral',       'keywords': ['mob wife aesthetic', 'faux fur coat']},
    {'tag': 'CleanGirlAesthetic', 'category': 'beauty',      'keywords': ['clean girl aesthetic', 'glazed donut skin']},
    {'tag': 'AthleisureFashion',  'category': 'active',      'keywords': ['athleisure', 'gym outfit', 'yoga wear']},
    {'tag': 'SustainableFashion', 'category': 'sustainable', 'keywords': ['sustainable fashion', 'eco fashion']},
    {'tag': 'DopamineDressing',   'category': 'color',       'keywords': ['dopamine dressing', 'colorful outfit']},
    {'tag': 'Regencycore',        'category': 'vintage',     'keywords': ['regencycore', 'empire waist', 'puff sleeve']},
    {'tag': 'TomatoGirlSummer',   'category': 'viral',       'keywords': ['tomato girl', 'mediterranean aesthetic']},
]


# ── TikTok Research API helpers ───────────────────────────────────────────────

def _get_access_token(client_key: str, client_secret: str) -> str:
    """Exchange client credentials for a TikTok Research API access token."""
    try:
        resp = requests.post(
            _TIKTOK_AUTH_URL,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'client_key':    client_key,
                'client_secret': client_secret,
                'grant_type':    'client_credentials',
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get('access_token', '')
    except Exception:
        pass
    return ''


def _query_videos_by_hashtag(
    access_token: str,
    hashtag: str,
    max_count: int = 10,
) -> List[Dict[str, Any]]:
    """Query TikTok Research API for recent videos with a given hashtag."""
    today = datetime.now(timezone.utc).strftime('%Y%m%d')
    start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y%m%d')
    try:
        resp = requests.post(
            _TIKTOK_VIDEO_QUERY_URL,
            headers={
                'Authorization':  f'Bearer {access_token}',
                'Content-Type':   'application/json',
            },
            json={
                'query': {
                    'and': [
                        {
                            'operation':   'IN',
                            'field_name':  'hashtag_name',
                            'field_values': [hashtag],
                        },
                    ],
                },
                'start_date': start,
                'end_date':   today,
                'max_count':  max_count,
                'fields':     (
                    'id,video_description,hashtag_names,'
                    'like_count,comment_count,share_count,view_count,create_time'
                ),
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get('data', {}).get('videos', [])
    except Exception:
        pass
    return []


def _video_to_post(video: Dict[str, Any], tag_info: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a TikTok Research API video object to our standard post format."""
    desc = video.get('video_description', '') or ''
    return {
        'title':         desc[:280] if desc else f"#{tag_info['tag']} on TikTok",
        'hashtag':       tag_info['tag'],
        'category':      tag_info['category'],
        'keywords':      tag_info['keywords'],
        'view_count':    video.get('view_count', 0),
        'like_count':    video.get('like_count', 0),
        'comment_count': video.get('comment_count', 0),
        'share_count':   video.get('share_count', 0),
        'score':         video.get('like_count', 0) + video.get('comment_count', 0) * 2,
        'hashtags':      video.get('hashtag_names', []),
        'url':           f"https://www.tiktok.com/tag/{tag_info['tag']}",
        'source':        'TikTok',
    }


# ── Fallback data ─────────────────────────────────────────────────────────────

def _curated_hashtag_posts() -> List[Dict[str, Any]]:
    """
    Return curated TikTok fashion hashtag entries as trend signals.
    Used when API credentials are not configured.
    """
    return [
        {
            'title':         f"#{h['tag']} — trending on TikTok",
            'hashtag':       h['tag'],
            'category':      h['category'],
            'keywords':      h['keywords'],
            'view_count':    0,
            'like_count':    0,
            'comment_count': 0,
            'share_count':   0,
            'score':         0,
            'hashtags':      [h['tag']],
            'url':           f"https://www.tiktok.com/tag/{h['tag']}",
            'source':        'TikTok',
        }
        for h in FASHION_HASHTAGS
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def get_tiktok_fashion_posts(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return fashion-related TikTok posts.

    When TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET are set the TikTok
    Research API is queried for recent videos per tracked hashtag.
    Otherwise curated hashtag entries are returned as trend signals so the
    rest of the pipeline can still use TikTok keyword data.
    """
    cache_key = f'tiktok_fashion_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    client_key    = os.environ.get('TIKTOK_CLIENT_KEY', '')
    client_secret = os.environ.get('TIKTOK_CLIENT_SECRET', '')

    posts: List[Dict[str, Any]] = []

    if client_key and client_secret:
        token = _get_access_token(client_key, client_secret)
        if token:
            for tag_info in FASHION_HASHTAGS:
                videos = _query_videos_by_hashtag(token, tag_info['tag'], max_count=5)
                for v in videos:
                    posts.append(_video_to_post(v, tag_info))

    if not posts:
        posts = _curated_hashtag_posts()

    posts.sort(key=lambda x: x.get('score', 0), reverse=True)
    result = posts[:limit]
    cache.set(cache_key, result, ttl=600)
    return result


def get_tiktok_trending_keywords(limit: int = 30) -> List[Dict[str, Any]]:
    """Extract trending keywords from TikTok fashion posts."""
    STOP = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'not', 'it', 'this', 'that', 'all',
        'more', 'than', 'can', 'just', 'get', 'new', 'like', 'my', 'your',
        'our', 'their', 'i', 'we', 'you', 'they', 'he', 'she', 'so', 'very',
        'me', 'him', 'her', 'us', 'them', 'too', 'also', 'even', 'still',
        'back', 'here',
    }
    posts = get_tiktok_fashion_posts(limit=200)
    freq: Dict[str, int] = {}
    for p in posts:
        text = p.get('title', '') + ' ' + ' '.join(p.get('hashtags', []))
        for word in re.findall(r"[a-z']{3,}", text.lower()):
            word = word.strip("'")
            if word not in STOP and len(word) > 2:
                freq[word] = freq.get(word, 0) + 1
        for kw in p.get('keywords', []):
            for word in re.findall(r"[a-z']{3,}", kw.lower()):
                word = word.strip("'")
                if word not in STOP and len(word) > 2:
                    freq[word] = freq.get(word, 0) + 2
    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [{'word': w, 'count': c} for w, c in sorted_kw[:limit]]


def get_tiktok_hashtag_summary() -> List[Dict[str, Any]]:
    """Return per-category aggregated stats for tracked TikTok hashtags."""
    cache_key = 'tiktok_hashtag_summary'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    posts = get_tiktok_fashion_posts(limit=200)
    summary: Dict[str, Dict[str, Any]] = {}
    for p in posts:
        cat = p['category']
        if cat not in summary:
            summary[cat] = {
                'category':    cat,
                'post_count':  0,
                'total_score': 0,
                'hashtags':    [],
            }
        summary[cat]['post_count']  += 1
        summary[cat]['total_score'] += p.get('score', 0)
        if p['hashtag'] not in summary[cat]['hashtags']:
            summary[cat]['hashtags'].append(p['hashtag'])

    result = sorted(summary.values(), key=lambda x: x['total_score'], reverse=True)
    cache.set(cache_key, result, ttl=600)
    return result
