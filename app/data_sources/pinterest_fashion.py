"""
Pinterest fashion data source — web scraping.

Collects fashion pin data from Pinterest without any API credentials by:

  1. Scraping public RSS feeds of curated fashion brand / publisher Pinterest
     boards (Vogue, Elle, Refinery29, Harper's Bazaar, Who What Wear, etc.).
  2. Querying Pinterest's public JSON search endpoint for fashion-related
     keywords — no authentication required.

Both methods are attempted on every call; results are merged and cached.
"""

import json
import re
import xml.etree.ElementTree as ET
import requests
from typing import Any, Dict, List
from urllib.parse import quote

from app.utils import cache

# ── Request headers ───────────────────────────────────────────────────────────

_RSS_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/121.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}

_JSON_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/121.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.pinterest.com/',
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

# Fashion search queries used for the public JSON search scraper
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

# Pinterest public search JSON endpoint
_PINTEREST_SEARCH_URL = 'https://www.pinterest.com/resource/BaseSearchResource/get/'


def _clean(text: str) -> str:
    text = _STRIP_TAGS.sub(' ', text or '')
    return _WHITESPACE.sub(' ', text).strip()


# ── RSS board scraper ─────────────────────────────────────────────────────────

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


def _scrape_all_boards() -> List[Dict[str, Any]]:
    """Fetch RSS feeds from every board in PINTEREST_BOARDS."""
    all_pins: List[Dict[str, Any]] = []
    for slug, display, tags, url in PINTEREST_BOARDS:
        all_pins.extend(_parse_board_rss(slug, display, tags, url))
    return all_pins


# ── Pinterest public JSON search scraper ─────────────────────────────────────

def _search_pins_public(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Scrape Pinterest's public search JSON endpoint for a fashion query.
    No authentication required — Pinterest returns public pin data as JSON
    when the ``X-Requested-With`` header is present.
    """
    try:
        data_param = json.dumps({
            'options': {
                'query':     query,
                'scope':     'pins',
                'bookmarks': [],
            },
            'context': {},
        })
        resp = requests.get(
            _PINTEREST_SEARCH_URL,
            headers=_JSON_HEADERS,
            params={
                'source_url': f'/search/pins/?q={quote(query)}&rs=typed',
                'data':       data_param,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        resource_response = resp.json().get('resource_response', {})
        results = resource_response.get('data', {}).get('results', [])

        pins: List[Dict[str, Any]] = []
        for pin in results[:limit]:
            # Title comes from 'title' or 'description' field
            desc  = pin.get('description') or pin.get('title') or ''
            img   = ''
            imgs  = pin.get('images', {})
            if imgs:
                img_obj = (
                    imgs.get('736x')
                    or imgs.get('474x')
                    or next(iter(imgs.values()), {})
                )
                img = img_obj.get('url', '') if isinstance(img_obj, dict) else ''
            pin_id = pin.get('id', '')
            saves  = pin.get('save_count', 0) or 0
            pins.append({
                'title':       desc[:280],
                'url':         f'https://www.pinterest.com/pin/{pin_id}/' if pin_id else '',
                'description': desc[:300],
                'published':   pin.get('created_at', ''),
                'image':       img,
                'board':       query.replace(' ', '_'),
                'source_name': 'Pinterest Search',
                'tags':        ['fashion'],
                'saves':       int(saves),
                'source':      'Pinterest',
            })
        return pins
    except Exception:
        return []


def _scrape_search_results() -> List[Dict[str, Any]]:
    """Run the public JSON search scraper for all curated fashion terms."""
    all_pins: List[Dict[str, Any]] = []
    for query in FASHION_SEARCH_TERMS:
        all_pins.extend(_search_pins_public(query, limit=10))
    return all_pins


# ── Public API ────────────────────────────────────────────────────────────────

def get_pinterest_fashion_pins(limit: int = 60) -> List[Dict[str, Any]]:
    """
    Return fashion-related Pinterest pins using web scraping.

    Scraping strategy (both run on every call; results are merged):
      1. Public board RSS feeds — parses the public RSS of 10 curated fashion
         brand / publisher boards (Vogue, Elle, Refinery29, etc.).
      2. Public JSON search API — queries Pinterest's search endpoint for 12
         curated fashion terms without any authentication.

    Results are merged, deduplicated by URL, and cached for 10 minutes.
    """
    cache_key = f'pinterest_fashion_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    all_pins: List[Dict[str, Any]] = []

    # Both scrapers run in parallel-friendly order; merge and dedup by URL
    all_pins.extend(_scrape_all_boards())
    all_pins.extend(_scrape_search_results())

    seen_urls = set()
    unique_pins: List[Dict[str, Any]] = []
    for p in all_pins:
        url = p.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_pins.append(p)

    result = unique_pins[:limit]
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

