"""
Fashion News RSS aggregator.

Pulls from free, public RSS feeds of major fashion publications:
Vogue, Elle, Harper's Bazaar, WWD, Hypebeast, Refinery29, Fashionista,
Who What Wear, Business of Fashion, and InStyle.
No API keys required.
"""

import requests
import xml.etree.ElementTree as ET
import re
from typing import List, Dict, Any
from app.utils import cache

HEADERS = {
    'User-Agent': 'FashionTrendForecasting/1.0 (educational research project)',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}

# (display_name, rss_url, category_tags)
FASHION_FEEDS: List[tuple] = [
    ('Vogue',              'https://www.vogue.com/feed/rss',                    ['luxury', 'runway', 'beauty']),
    ('Elle',               'https://www.elle.com/rss/all.xml/',                 ['style', 'beauty', 'culture']),
    ("Harper's Bazaar",    'https://www.harpersbazaar.com/rss/all.xml/',        ['luxury', 'runway', 'beauty']),
    ('WWD',                'https://wwd.com/feed/',                             ['industry', 'retail', 'runway']),
    ('Hypebeast',          'https://hypebeast.com/feed',                        ['streetwear', 'sneakers', 'drops']),
    ('Refinery29',         'https://www.refinery29.com/en-us/rss.xml',          ['style', 'beauty', 'culture']),
    ('Fashionista',        'https://fashionista.com/rss',                       ['industry', 'style', 'runway']),
    ('Who What Wear',      'https://www.whowhatwear.com/rss',                   ['style', 'trends', 'shopping']),
    ('Business of Fashion','https://www.businessoffashion.com/feed',            ['industry', 'business', 'sustainability']),
    ('InStyle',            'https://www.instyle.com/rss/all.xml',               ['style', 'beauty', 'celebrity']),
    ('Hypebaenews',        'https://hypebae.com/feed',                          ['streetwear', 'women', 'beauty']),
    ('Complex Style',      'https://www.complex.com/style/rss',                 ['streetwear', 'sneakers', 'celebrity']),
    ('GQ',                 'https://www.gq.com/feed/rss',                       ['menswear', 'style', 'grooming']),
    ('Highsnobiety',       'https://www.highsnobiety.com/rss',                  ['streetwear', 'luxury', 'sneakers']),
    ('The Cut',            'https://www.thecut.com/rss/index.xml',              ['style', 'beauty', 'culture']),
    ('Teen Vogue',         'https://www.teenvogue.com/feed/rss',                ['style', 'beauty', 'sustainable']),
    ('Nylon',              'https://www.nylon.com/rss',                         ['style', 'beauty', 'culture']),
    ('Dazed',              'https://www.dazeddigital.com/rss',                  ['culture', 'streetwear', 'beauty']),
    ('i-D Magazine',       'https://i-d.vice.com/rss',                          ['culture', 'style', 'diversity']),
    ('Marie Claire',       'https://www.marieclaire.com/rss/all.xml/',          ['style', 'beauty', 'celebrity']),
]

_STRIP_TAGS = re.compile(r'<[^>]+>')
_WHITESPACE = re.compile(r'\s+')


def _clean(text: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    text = _STRIP_TAGS.sub(' ', text or '')
    return _WHITESPACE.sub(' ', text).strip()


def _parse_feed(name: str, url: str, tags: List[str]) -> List[Dict[str, Any]]:
    """Fetch and parse one RSS / Atom feed. Returns up to 15 articles."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []

    articles: List[Dict[str, Any]] = []

    # RSS <item> elements
    for item in root.findall('.//item'):
        title = _clean(item.findtext('title', ''))
        link  = _clean(item.findtext('link', ''))
        desc  = _clean(item.findtext('description', ''))[:300]
        date  = _clean(item.findtext('pubDate', ''))
        img   = ''
        # Try <media:content> or <enclosure> for thumbnail
        for child in item:
            if child.tag.endswith('}content') and child.get('url'):
                img = child.get('url', '')
                break
            if child.tag == 'enclosure' and child.get('type', '').startswith('image'):
                img = child.get('url', '')
                break
        if title and link:
            articles.append({
                'title': title,
                'url': link,
                'description': desc,
                'published': date,
                'image': img,
                'source': name,
                'tags': tags,
            })
        if len(articles) >= 15:
            break

    # Atom <entry> elements (fallback)
    if not articles:
        atom_ns = 'http://www.w3.org/2005/Atom'
        for entry in root.findall(f'.//{{{atom_ns}}}entry'):
            title_el = entry.find(f'{{{atom_ns}}}title')
            link_el  = entry.find(f'{{{atom_ns}}}link')
            sum_el   = entry.find(f'{{{atom_ns}}}summary')
            title = _clean(title_el.text if title_el is not None else '')
            link  = link_el.get('href', '') if link_el is not None else ''
            desc  = _clean(sum_el.text if sum_el is not None else '')[:300]
            if title and link:
                articles.append({
                    'title': title,
                    'url': link,
                    'description': desc,
                    'published': '',
                    'image': '',
                    'source': name,
                    'tags': tags,
                })
            if len(articles) >= 15:
                break

    return articles


def get_fashion_news(limit: int = 60) -> List[Dict[str, Any]]:
    """Return the latest fashion news from all configured feeds."""
    cache_key = f'fashion_news_{limit}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    all_articles: List[Dict[str, Any]] = []
    for name, url, tags in FASHION_FEEDS:
        all_articles.extend(_parse_feed(name, url, tags))

    result = all_articles[:limit]
    cache.set(cache_key, result, ttl=600)
    return result


def get_news_by_tag(tag: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return fashion news filtered by a tag (e.g. 'streetwear', 'luxury')."""
    all_news = get_fashion_news(limit=200)
    filtered = [a for a in all_news if tag in a.get('tags', [])]
    return filtered[:limit]


def get_news_by_source(source_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Return news from a single publication."""
    all_news = get_fashion_news(limit=200)
    return [a for a in all_news if a['source'] == source_name][:limit]


def extract_trending_keywords(articles: List[Dict[str, Any]], top_n: int = 30) -> List[Dict[str, Any]]:
    """
    Count word frequency across article titles and descriptions.
    Returns the top_n most-mentioned fashion-relevant words.
    """
    STOP = {
        'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
        'from','as','is','was','are','were','be','been','being','have','has','had',
        'do','does','did','will','would','could','should','may','might','not','its',
        'it','this','that','these','those','all','more','other','than','then','can',
        'just','also','get','first','two','new','says','said','after','before',
        'about','over','into','out','up','down','how','why','when','where','what',
        'who','which','like','one','year','make','way','time','look','see','know',
        'your','their','our','my','his','her','you','we','they','i','best','here',
        'some','now','there','want','need','take','very','even','still','back',
    }
    freq: Dict[str, int] = {}
    for art in articles:
        text = f"{art.get('title','')} {art.get('description','')}".lower()
        for word in re.findall(r"[a-z']{3,}", text):
            word = word.strip("'")
            if word not in STOP and len(word) > 2:
                freq[word] = freq.get(word, 0) + 1

    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [{'word': w, 'count': c} for w, c in sorted_words[:top_n]]
