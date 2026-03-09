"""
Pinterest fashion data source.

Uses the Pinterest API v5 when an access token is available
(PINTEREST_ACCESS_TOKEN environment variable).
Falls back to public Pinterest board RSS feeds when no credentials are set.

To enable live API data, create a Pinterest app at
https://developers.pinterest.com/ and set:
    PINTEREST_ACCESS_TOKEN=your_access_token

Without credentials the module still returns pin data by parsing the public
RSS feeds of curated fashion brand / publisher Pinterest boards.
"""

import os
import re
import xml.etree.ElementTree as ET
import requests
from typing import Any, Dict, List

from app.utils import cache

# ── Pinterest API v5 ──────────────────────────────────────────────────────────

_PINTEREST_API_BASE = 'https://api.pinterest.com/v5'

_HEADERS = {
    'User-Agent': 'FashionTrendForecasting/1.0 (educational research)',
    'Accept':     'application/json',
}

_RSS_HEADERS = {
    'User-Agent': 'FashionTrendForecasting/1.0 (educational research)',
    'Accept':     'application/rss+xml, application/xml, text/xml, */*',
}

# ── Curated public Pinterest board RSS feeds ──────────────────────────────────
# (board_slug, display_name, category_tags, rss_url)

PINTEREST_BOARDS: List[tuple] = [
    ('vogue',           'Vogue',             ['luxury', 'runway'],     'https://www.pinterest.com/vogue/feed.rss'),
    ('ellemag',         'Elle Magazine',     ['style', 'beauty'],      'https://www.pinterest.com/ellemag/feed.rss'),
    ('refinery29',      'Refinery29',        ['style', 'culture'],     'https://www.pinterest.com/refinery29/feed.rss'),
    ('harpersbazaarus', "Harper's Bazaar",   ['luxury', 'beauty'],     'https://www.pinterest.com/harpersbazaarus/feed.rss'),
    ('whowhatwear',     'Who What Wear',     ['style', 'trends'],      'https://www.pinterest.com/whowhatwear/feed.rss'),
    ('anthropologie',   'Anthropologie',     ['style', 'boho'],        'https://www.pinterest.com/anthropologie/feed.rss'),
    ('nordstrom',       'Nordstrom',         ['style', 'shopping'],    'https://www.pinterest.com/nordstrom/feed.rss'),
    ('net_a_porter',    'Net-a-Porter',      ['luxury', 'shopping'],   'https://www.pinterest.com/net_a_porter/feed.rss'),
    ('modcloth',        'ModCloth',          ['vintage', 'style'],     'https://www.pinterest.com/modcloth/feed.rss'),
    ('forever21',       'Forever 21',        ['style', 'streetwear'],  'https://www.pinterest.com/forever21/feed.rss'),
]

# Fashion terms used when searching via the Pinterest API
FASHION_SEARCH_TERMS: List[str] = [
    'quiet luxury outfit',
    'y2k fashion',
    'balletcore aesthetic',
    'mob wife aesthetic',
    'dark academia fashion',
    'cottagecore style',
    'streetwear outfit',
    'sustainable fashion',
    'clean girl aesthetic',
    'dopamine dressing',
    'coquette aesthetic',
    'gorpcore outfit',
]

_STRIP_TAGS = re.compile(r'<[^>]+>')
_WHITESPACE  = re.compile(r'\s+')


def _clean(text: str) -> str:
    text = _STRIP_TAGS.sub(' ', text or '')
    return _WHITESPACE.sub(' ', text).strip()


# ── RSS fallback ──────────────────────────────────────────────────────────────

def _parse_board_rss(
    slug: str,
    display: str,
    tags: List[str],
    url: str,
) -> List[Dict[str, Any]]:
    """Fetch and parse one Pinterest board RSS feed. Returns up to 15 pins."""
    try:
        r = requests.get(url, headers=_RSS_HEADERS, timeout=8)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []

    pins: List[Dict[str, Any]] = []
    for item in root.findall('.//item'):
        title = _clean(item.findtext('title', ''))
        link  = _clean(item.findtext('link', ''))
        desc  = _clean(item.findtext('description', ''))[:300]
        date  = _clean(item.findtext('pubDate', ''))
        img   = ''
        for child in item:
            if child.tag.endswith('}content') and child.get('url'):
                img = child.get('url', '')
                break
            if child.tag == 'enclosure' and child.get('type', '').startswith('image'):
                img = child.get('url', '')
                break
        if title and link:
            pins.append({
                'title':       title,
                'url':         link,
                'description': desc,
                'published':   date,
                'image':       img,
                'board':       slug,
                'source_name': display,
                'tags':        tags,
                'saves':       0,
                'source':      'Pinterest',
            })
        if len(pins) >= 15:
            break
    return pins


# ── Pinterest API v5 ──────────────────────────────────────────────────────────

def _search_pins_api(
    query: str,
    access_token: str,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """Search Pinterest for pins using the v5 API."""
    try:
        resp = requests.get(
            f'{_PINTEREST_API_BASE}/pins/',
            headers={**_HEADERS, 'Authorization': f'Bearer {access_token}'},
            params={'query': query, 'page_size': limit},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        pins: List[Dict[str, Any]] = []
        for pin in resp.json().get('items', []):
            media  = pin.get('media') or {}
            images = media.get('images') or {}
            img = ''
            if images:
                img_obj = (
                    images.get('1200x')
                    or images.get('600x')
                    or next(iter(images.values()), {})
                )
                img = img_obj.get('url', '') if isinstance(img_obj, dict) else ''
            desc = pin.get('description') or pin.get('title') or ''
            pins.append({
                'title':       desc[:280],
                'url':         f"https://www.pinterest.com/pin/{pin.get('id', '')}",
                'description': desc[:300],
                'published':   pin.get('created_at', ''),
                'image':       img,
                'board':       query,
                'source_name': 'Pinterest Search',
                'tags':        ['fashion'],
                'saves':       pin.get('save_count', 0),
                'source':      'Pinterest',
            })
        return pins
    except Exception:
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_pinterest_fashion_pins(limit: int = 60) -> List[Dict[str, Any]]:
    """
    Return fashion-related Pinterest pins.

    When PINTEREST_ACCESS_TOKEN is set the Pinterest API v5 is queried for
    pins matching curated fashion search terms.
    Otherwise the module parses the public RSS feeds of curated fashion brand
    and publisher boards.
    """
    cache_key = f'pinterest_fashion_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    access_token = os.environ.get('PINTEREST_ACCESS_TOKEN', '')
    all_pins: List[Dict[str, Any]] = []

    if access_token:
        for query in FASHION_SEARCH_TERMS[:6]:
            all_pins.extend(_search_pins_api(query, access_token, limit=10))

    if not all_pins:
        for slug, display, tags, url in PINTEREST_BOARDS:
            all_pins.extend(_parse_board_rss(slug, display, tags, url))

    result = all_pins[:limit]
    cache.set(cache_key, result, ttl=600)
    return result


def get_pinterest_trending_keywords(limit: int = 30) -> List[Dict[str, Any]]:
    """Extract trending keywords from Pinterest fashion pins."""
    STOP = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'not', 'it', 'this', 'that', 'all',
        'more', 'than', 'can', 'just', 'get', 'new', 'like', 'my', 'your',
        'our', 'their', 'i', 'we', 'you', 'they', 'he', 'she', 'its', 'via',
        'me', 'him', 'her', 'us', 'them', 'too', 'also', 'even', 'still',
        'back', 'here', 'see', 'pin', 'pins', 'board', 'boards', 'save', 'saved',
    }
    pins = get_pinterest_fashion_pins(limit=200)
    freq: Dict[str, int] = {}
    for p in pins:
        text = f"{p.get('title', '')} {p.get('description', '')}".lower()
        for word in re.findall(r"[a-z']{3,}", text):
            word = word.strip("'")
            if word not in STOP and len(word) > 2:
                freq[word] = freq.get(word, 0) + 1
    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [{'word': w, 'count': c} for w, c in sorted_kw[:limit]]


def get_pinterest_board_activity() -> List[Dict[str, Any]]:
    """Return per-board aggregate stats (pin count, total saves)."""
    cache_key = 'pinterest_board_activity'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    pins = get_pinterest_fashion_pins(limit=200)
    stats: Dict[str, Dict[str, Any]] = {}
    for p in pins:
        board = p['board']
        if board not in stats:
            stats[board] = {
                'board':       board,
                'source_name': p.get('source_name', board),
                'tags':        p.get('tags', []),
                'pin_count':   0,
                'total_saves': 0,
            }
        stats[board]['pin_count']   += 1
        stats[board]['total_saves'] += p.get('saves', 0)

    result = sorted(stats.values(), key=lambda x: x['pin_count'], reverse=True)
    cache.set(cache_key, result, ttl=600)
    return result
