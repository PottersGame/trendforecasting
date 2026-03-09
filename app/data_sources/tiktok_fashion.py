"""
TikTok fashion data source — web scraping.

Scrapes TikTok's public hashtag pages and the TikTok Creative Center
trending hashtag endpoint to gather live fashion trend signals.
No API credentials or registration required.

Data collected per hashtag:
  - view_count / video_count scraped from the hashtag challenge page
  - Trending hashtag rank and metrics from TikTok Creative Center
  - Keyword signals extracted from tracked hashtag names and descriptions
"""

import json
import re
import requests
from typing import Any, Dict, List

from app.utils import cache

# ── Browser-like headers to avoid bot-detection blocks ───────────────────────

_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/121.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;'
        'q=0.9,image/avif,image/webp,*/*;q=0.8'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0',
}

_CC_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/121.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://ads.tiktok.com/',
}

# ── Curated fashion-relevant TikTok hashtags to track ────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hashtag_url(hashtag: str) -> str:
    """Return the canonical TikTok hashtag page URL."""
    return f'https://www.tiktok.com/tag/{hashtag.lower()}'



    """
    Parse abbreviated counts like '423.4B', '1.2M', '500K' from a text string.
    Returns 0 if no match found.
    """
    m = re.search(r'([\d.]+)\s*([KMBkmb])', text)
    if not m:
        return 0
    val = float(m.group(1))
    multiplier = {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}.get(
        m.group(2).lower(), 1
    )
    return int(val * multiplier)


# ── TikTok Creative Center scraper ───────────────────────────────────────────

_CC_HASHTAG_URL = (
    'https://ads.tiktok.com/business/creativecenter/api/v1/hashtag/rank/list/'
)
_CC_PARAMS = {
    'aid':              '7166',
    'cookie_enabled':   '1',
    'screen_width':     '1920',
    'screen_height':    '1080',
    'browser_language': 'en',
    'browser_platform': 'Win32',
    'browser_name':     'Chrome',
    'browser_version':  '121',
    'period':           '7',
    'industry_id':      '',
    'country_code':     'US',
    'limit':            '20',
}


def _fetch_creative_center_trends() -> List[Dict[str, Any]]:
    """
    Fetch trending hashtag list from the TikTok Creative Center public API.
    Returns normalised post objects for any hashtags that overlap with
    FASHION_HASHTAGS or contain fashion-related keywords.
    """
    fashion_tags_lower = {h['tag'].lower() for h in FASHION_HASHTAGS}
    fashion_kw = {
        'fashion', 'style', 'outfit', 'ootd', 'clothes', 'clothing',
        'wear', 'dress', 'aesthetic', 'beauty', 'makeup', 'skincare',
        'luxury', 'streetwear', 'vintage', 'thrift', 'sustainable',
    }
    try:
        resp = requests.get(
            _CC_HASHTAG_URL,
            headers=_CC_HEADERS,
            params=_CC_PARAMS,
            timeout=12,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = (
            data.get('data', {}).get('list', [])
            or data.get('data', [])
            or []
        )
        posts: List[Dict[str, Any]] = []
        for item in items:
            raw_tag = item.get('hashtag_name', '') or ''
            tag_lower = raw_tag.lower()
            # Keep only fashion-relevant entries
            if tag_lower not in fashion_tags_lower and not any(
                kw in tag_lower for kw in fashion_kw
            ):
                continue
            # Match to curated entry for category / keywords, or use defaults
            info = next(
                (h for h in FASHION_HASHTAGS if h['tag'].lower() == tag_lower),
                {'tag': raw_tag, 'category': 'style', 'keywords': [raw_tag]},
            )
            view_count  = int(item.get('video_views', 0) or 0)
            video_count = int(item.get('publish_cnt', 0) or 0)
            posts.append({
                'title':         f'#{raw_tag} — trending on TikTok',
                'hashtag':       raw_tag,
                'category':      info['category'],
                'keywords':      info['keywords'],
                'view_count':    view_count,
                'like_count':    0,
                'comment_count': 0,
                'share_count':   0,
                'video_count':   video_count,
                'score':         view_count,
                'hashtags':      [raw_tag],
                'url':           _hashtag_url(raw_tag),
                'source':        'TikTok',
            })
        return posts
    except Exception:
        return []


# ── TikTok hashtag page scraper ───────────────────────────────────────────────

def _scrape_hashtag_page(tag_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape a single TikTok hashtag page for view/video counts.

    Tries two extraction strategies in order:
      1. Parse the ``__UNIVERSAL_DATA_FOR_REHYDRATION__`` JSON block embedded
         in the page HTML (server-side rendered stats).
      2. Parse the ``og:title`` / ``og:description`` Open Graph meta tags
         which often contain abbreviated view counts like '423.4B views'.

    Returns a partial post dict with whatever counts could be extracted,
    or an empty dict on failure.
    """
    hashtag = tag_info['tag']
    url = _hashtag_url(hashtag)
    try:
        r = requests.get(url, headers=_BROWSER_HEADERS, timeout=12)
        if r.status_code != 200:
            return {}
        html = r.text

        # Strategy 1 — embedded JSON (most reliable when available)
        m = re.search(
            r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>'
            r'(\{.+?\})'
            r'</script>',
            html,
            re.DOTALL,
        )
        if m:
            try:
                data = json.loads(m.group(1))
                scope = data.get('__DEFAULT_SCOPE__', {})
                challenge = (
                    scope.get('webapp.challenge-detail', {})
                    .get('challengeInfo', {})
                    .get('challenge', {})
                )
                if challenge:
                    stats = challenge.get('stats', {})
                    return {
                        'view_count':  int(stats.get('viewCount', 0) or 0),
                        'video_count': int(stats.get('videoCount', 0) or 0),
                        'title':       challenge.get('desc', '') or f'#{hashtag}',
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # Strategy 2 — og meta tags
        og_title = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            html,
        )
        og_desc = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            html,
        )
        title_text = og_title.group(1) if og_title else ''
        desc_text  = og_desc.group(1)  if og_desc  else ''
        combined   = f'{title_text} {desc_text}'
        view_count = _parse_abbrev_count(combined)
        if view_count or title_text:
            return {
                'view_count':  view_count,
                'video_count': 0,
                'title':       title_text or f'#{hashtag} on TikTok',
            }
    except Exception:
        pass
    return {}


def _scrape_all_hashtags() -> List[Dict[str, Any]]:
    """Scrape TikTok hashtag pages for every entry in FASHION_HASHTAGS."""
    posts: List[Dict[str, Any]] = []
    for tag_info in FASHION_HASHTAGS:
        scraped = _scrape_hashtag_page(tag_info)
        view_count  = scraped.get('view_count', 0)
        video_count = scraped.get('video_count', 0)
        title       = scraped.get('title') or f"#{tag_info['tag']} on TikTok"
        posts.append({
            'title':         title,
            'hashtag':       tag_info['tag'],
            'category':      tag_info['category'],
            'keywords':      tag_info['keywords'],
            'view_count':    view_count,
            'like_count':    0,
            'comment_count': 0,
            'share_count':   0,
            'video_count':   video_count,
            'score':         view_count,
            'hashtags':      [tag_info['tag']],
            'url':           _hashtag_url(tag_info['tag']),
            'source':        'TikTok',
        })
    return posts


# ── Curated keyword-signal fallback ──────────────────────────────────────────

def _curated_hashtag_posts() -> List[Dict[str, Any]]:
    """
    Return curated TikTok fashion hashtag entries as keyword trend signals.
    Used as a last resort when all scraping attempts fail (e.g. network
    unavailable in CI / testing environments).
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
            'video_count':   0,
            'score':         0,
            'hashtags':      [h['tag']],
            'url':           _hashtag_url(h['tag']),
            'source':        'TikTok',
        }
        for h in FASHION_HASHTAGS
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def get_tiktok_fashion_posts(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return fashion-related TikTok posts and hashtag trend signals.

    Scraping strategy (in priority order):
      1. TikTok Creative Center public trending-hashtag API — no credentials
         needed; returns view counts and video counts for trending hashtags.
      2. Individual TikTok hashtag page scraping — parses embedded JSON or
         Open Graph meta tags for per-hashtag engagement stats.
      3. Curated keyword fallback — always available; provides keyword signals
         for trend scoring even when the network is unavailable.
    """
    cache_key = f'tiktok_fashion_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    posts: List[Dict[str, Any]] = []

    # Step 1: Try Creative Center API (fastest, covers top trending hashtags)
    posts = _fetch_creative_center_trends()

    # Step 2: If Creative Center didn't return our fashion hashtags, scrape pages
    if not posts:
        posts = _scrape_all_hashtags()
        # Keep only entries where we got real engagement data
        real = [p for p in posts if p.get('view_count', 0) > 0]
        if real:
            posts = real
        else:
            # Step 3: Nothing scraped successfully — use keyword fallback
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

