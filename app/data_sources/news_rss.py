"""News RSS feeds aggregator - free, no API key required."""

import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from datetime import datetime
from app.utils import cache


# Free RSS feeds from major news sources
RSS_FEEDS = {
    'technology': [
        ('TechCrunch', 'https://techcrunch.com/feed/'),
        ('The Verge', 'https://www.theverge.com/rss/index.xml'),
        ('Wired', 'https://www.wired.com/feed/rss'),
        ('Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index'),
    ],
    'business': [
        ('Reuters Business', 'https://feeds.reuters.com/reuters/businessNews'),
        ('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
        ('FT', 'https://www.ft.com/rss/home'),
    ],
    'science': [
        ('Scientific American', 'https://rss.sciam.com/ScientificAmerican-Global'),
        ('NASA', 'https://www.nasa.gov/rss/dyn/breaking_news.rss'),
        ('Nature News', 'https://www.nature.com/nature.rss'),
    ],
    'general': [
        ('BBC News', 'https://feeds.bbci.co.uk/news/rss.xml'),
        ('Reuters', 'https://feeds.reuters.com/reuters/topNews'),
        ('NPR', 'https://feeds.npr.org/1001/rss.xml'),
        ('AP News', 'https://rsshub.app/apnews/topics/apf-topnews'),
    ],
    'fashion': [
        ('Vogue', 'https://www.vogue.com/feed/rss'),
        ('Elle', 'https://www.elle.com/rss/all.xml/'),
        ('WWD', 'https://wwd.com/feed/'),
    ],
}

HEADERS = {
    'User-Agent': 'TrendForecasting/1.0 (educational project)',
    'Accept': 'application/rss+xml, application/xml, text/xml',
}


def _parse_feed(feed_name: str, url: str) -> List[Dict[str, Any]]:
    """Parse an RSS feed and return articles."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return []

        root = ET.fromstring(r.content)

        # Handle both RSS and Atom feeds
        articles = []
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        # Try RSS format
        for item in root.findall('.//item'):
            title = item.findtext('title', '').strip()
            link = item.findtext('link', '').strip()
            description = item.findtext('description', '').strip()
            pub_date = item.findtext('pubDate', '').strip()

            # Clean description (remove HTML)
            if description:
                description = ET.fromstring(f'<root>{description}</root>').text or description
                description = description[:200]

            if title and link:
                articles.append({
                    'title': title,
                    'url': link,
                    'description': description[:200] if description else '',
                    'published': pub_date,
                    'source': feed_name,
                })

        # Try Atom format if no items found
        if not articles:
            for entry in root.findall('.//atom:entry', ns) or root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                title_el = entry.find('{http://www.w3.org/2005/Atom}title')
                link_el = entry.find('{http://www.w3.org/2005/Atom}link')
                summary_el = entry.find('{http://www.w3.org/2005/Atom}summary')

                title = title_el.text if title_el is not None else ''
                link = link_el.get('href', '') if link_el is not None else ''
                summary = summary_el.text if summary_el is not None else ''

                if title and link:
                    articles.append({
                        'title': title.strip(),
                        'url': link,
                        'description': summary[:200] if summary else '',
                        'published': '',
                        'source': feed_name,
                    })

        return articles[:10]

    except Exception:
        return []


def get_news_by_category(category: str = 'general', limit: int = 30) -> List[Dict[str, Any]]:
    """Get news articles from RSS feeds for a category."""
    cache_key = f'news_{category}_{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    feeds = RSS_FEEDS.get(category, RSS_FEEDS['general'])
    all_articles = []

    for feed_name, feed_url in feeds[:3]:  # Limit requests
        articles = _parse_feed(feed_name, feed_url)
        all_articles.extend(articles)

    all_articles = all_articles[:limit]
    cache.set(cache_key, all_articles, ttl=600)
    return all_articles


def get_all_news(limit_per_category: int = 10) -> Dict[str, List[Dict]]:
    """Get news from all categories."""
    cache_key = f'news_all_{limit_per_category}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {}
    for category in RSS_FEEDS:
        result[category] = get_news_by_category(category, limit=limit_per_category)

    cache.set(cache_key, result, ttl=600)
    return result


def extract_trending_topics(articles: List[Dict[str, Any]], top_n: int = 20) -> List[Dict[str, Any]]:
    """Extract trending topics from a list of articles."""
    word_freq: Dict[str, int] = {}

    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'new', 'says', 'said',
        'after', 'before', 'about', 'over', 'into', 'out', 'up', 'down',
        'how', 'why', 'when', 'where', 'what', 'who', 'which', 'its', 'it',
        'this', 'that', 'these', 'those', 'not', 'all', 'more', 'other',
        'than', 'then', 'can', 'just', 'also', 'get', 'first', 'two',
    }

    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        words = text.lower().split()
        for word in words:
            word = ''.join(c for c in word if c.isalpha())
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [{'word': w, 'count': c, 'relevance': min(c * 10, 100)} for w, c in sorted_words[:top_n]]
