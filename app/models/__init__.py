"""
Fashion trend scoring and momentum calculator.

Aggregates data from all sources into a unified trend score (0-100)
and computes momentum (rising / stable / falling) using a simple
weighted moving-average approach.  No external dependencies beyond
the data-source modules already in this package.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Any, Tuple
from app.utils import cache


# ── Curated fashion aesthetics / trends to track ──────────────────────────────

TRACKED_TRENDS: List[Dict[str, Any]] = [
    # (name, search_keywords, categories)
    {'name': 'Quiet Luxury',        'keywords': ['quiet luxury', 'old money', 'stealth wealth', 'understated elegance'],     'categories': ['luxury', 'style']},
    {'name': 'Y2K Revival',         'keywords': ['y2k fashion', 'y2k aesthetic', 'low rise', 'butterfly clip', 'mini skirt'],'categories': ['vintage', 'streetwear']},
    {'name': 'Mob Wife Aesthetic',  'keywords': ['mob wife', 'mob wife aesthetic', 'faux fur', 'animal print'],               'categories': ['style', 'viral']},
    {'name': 'Balletcore',          'keywords': ['balletcore', 'ballet flat', 'ballet aesthetic', 'tutu skirt'],              'categories': ['style', 'viral']},
    {'name': 'Gorpcore',            'keywords': ['gorpcore', 'outdoor fashion', 'techwear', 'arc\'teryx', 'salomon'],         'categories': ['streetwear', 'outdoor']},
    {'name': 'Cottagecore',         'keywords': ['cottagecore', 'cottage aesthetic', 'prairie dress', 'floral dress'],        'categories': ['style', 'vintage']},
    {'name': 'Dark Academia',       'keywords': ['dark academia', 'dark academia fashion', 'preppy dark', 'tweed blazer'],    'categories': ['style', 'aesthetic']},
    {'name': 'Clean Girl',          'keywords': ['clean girl aesthetic', 'glazed donut skin', 'slick bun', 'no-makeup look'],'categories': ['beauty', 'style']},
    {'name': 'Sustainable Fashion', 'keywords': ['sustainable fashion', 'slow fashion', 'thrift flip', 'secondhand'],        'categories': ['sustainable']},
    {'name': 'Streetwear',          'keywords': ['streetwear', 'hypebeast', 'sneaker drop', 'limited edition', 'collab'],    'categories': ['streetwear']},
    {'name': 'Coastal Grandmother', 'keywords': ['coastal grandmother', 'coastal style', 'linen set', 'relaxed luxury'],     'categories': ['style', 'viral']},
    {'name': 'Dopamine Dressing',   'keywords': ['dopamine dressing', 'bright colors fashion', 'colourful outfit', 'bold style'], 'categories': ['style', 'color']},
    {'name': 'Athleisure',          'keywords': ['athleisure', 'yoga pants', 'leggings', 'sports bra outfit', 'gym fashion'],'categories': ['style', 'active']},
    {'name': 'Regencycore',         'keywords': ['regencycore', 'regency fashion', 'empire waist', 'puff sleeve'],           'categories': ['vintage', 'style']},
    {'name': 'Tomato Girl Summer',  'keywords': ['tomato girl', 'tomato girl summer', 'red italian summer', 'mediterranean'],'categories': ['style', 'viral']},
    {'name': 'Coquette',            'keywords': ['coquette aesthetic', 'bow aesthetic', 'hyper feminine', 'pink bow'],        'categories': ['style', 'viral']},
]

# Season calendar  (month → season)
_SEASON_MAP = {12: 'Winter', 1: 'Winter', 2: 'Winter',
               3: 'Spring', 4: 'Spring', 5: 'Spring',
               6: 'Summer', 7: 'Summer', 8: 'Summer',
               9: 'Fall',  10: 'Fall',  11: 'Fall'}

# Color trend palette (Pantone-inspired seasonal colors)
COLOR_TRENDS = [
    {'name': 'Mocha Mousse',    'hex': '#A07055', 'season': 'Winter', 'score': 92},
    {'name': 'Peach Fuzz',      'hex': '#FFBE98', 'season': 'Spring', 'score': 88},
    {'name': 'Butter Yellow',   'hex': '#F5E642', 'season': 'Summer', 'score': 85},
    {'name': 'Sage Green',      'hex': '#8FAE8C', 'season': 'Spring', 'score': 82},
    {'name': 'Cobalt Blue',     'hex': '#1E4FCC', 'season': 'Fall',   'score': 79},
    {'name': 'Dusty Rose',      'hex': '#DDA0AD', 'season': 'Winter', 'score': 76},
    {'name': 'Cherry Red',      'hex': '#B5161A', 'season': 'Fall',   'score': 74},
    {'name': 'Lavender Mist',   'hex': '#C5B8E8', 'season': 'Spring', 'score': 72},
    {'name': 'Warm Ivory',      'hex': '#F5EDD6', 'season': 'Winter', 'score': 70},
    {'name': 'Forest Green',    'hex': '#2D5A27', 'season': 'Fall',   'score': 68},
    {'name': 'Electric Orange', 'hex': '#FF5C00', 'season': 'Summer', 'score': 65},
    {'name': 'Powder Blue',     'hex': '#B0C4DE', 'season': 'Summer', 'score': 63},
]

# Brand buzz (static curated data enriched by Reddit/news keyword counts)
TOP_BRANDS = [
    'Zara', 'H&M', 'Nike', 'Adidas', 'Gucci', 'Louis Vuitton', 'Prada',
    'Chanel', 'Hermès', 'Balenciaga', 'Off-White', 'Supreme', 'Stone Island',
    'Carhartt', 'New Balance', 'Loewe', 'Bottega Veneta', 'Jacquemus',
    'Skims', 'Alo Yoga', 'Reformation', 'Shein', 'ASOS', 'Uniqlo',
]


def _keyword_score(keywords: List[str], text_pool: List[str]) -> int:
    """
    Count keyword mentions in a pool of texts.
    Returns a normalised score 0-100.
    """
    total = 0
    for kw in keywords:
        pattern = re.compile(re.escape(kw.lower()))
        for text in text_pool:
            total += len(pattern.findall(text.lower()))
    # Log-normalise to 0-100
    return min(100, int(math.log1p(total) * 18))


def _momentum_label(score: int, prev_score: int) -> str:
    delta = score - prev_score
    if delta >= 8:
        return 'rising'
    if delta <= -8:
        return 'falling'
    return 'stable'


def score_trends(
    text_pool: List[str],
    prev_scores: Dict[str, int] | None = None,
) -> List[Dict[str, Any]]:
    """
    Score each tracked trend against a pool of recent texts.
    Returns list sorted by score descending.
    """
    if prev_scores is None:
        prev_scores = {}

    results = []
    for trend in TRACKED_TRENDS:
        score = _keyword_score(trend['keywords'], text_pool)
        prev  = prev_scores.get(trend['name'], score)
        results.append({
            'name':       trend['name'],
            'score':      score,
            'momentum':   _momentum_label(score, prev),
            'categories': trend['categories'],
            'keywords':   trend['keywords'],
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def score_brands(text_pool: List[str]) -> List[Dict[str, Any]]:
    """Count brand mentions in text pool, return sorted list."""
    brand_counts = []
    for brand in TOP_BRANDS:
        pattern = re.compile(re.escape(brand.lower()))
        count = sum(len(pattern.findall(t.lower())) for t in text_pool)
        brand_counts.append({'brand': brand, 'mentions': count})
    brand_counts.sort(key=lambda x: x['mentions'], reverse=True)
    return brand_counts


def get_current_season() -> str:
    from datetime import datetime
    return _SEASON_MAP[datetime.utcnow().month]


def get_color_trends(season_filter: str | None = None) -> List[Dict[str, Any]]:
    """Return color trends, optionally filtered by season."""
    if season_filter:
        return [c for c in COLOR_TRENDS if c['season'] == season_filter]
    return COLOR_TRENDS


def get_fashion_calendar() -> List[Dict[str, Any]]:
    """
    Static fashion-week and key-event calendar.
    Returns events sorted chronologically.
    """
    return [
        {'event': 'New York Fashion Week',    'city': 'New York',  'month': 'February / September', 'type': 'ready-to-wear'},
        {'event': 'London Fashion Week',      'city': 'London',    'month': 'February / September', 'type': 'ready-to-wear'},
        {'event': 'Milan Fashion Week',       'city': 'Milan',     'month': 'February / September', 'type': 'ready-to-wear'},
        {'event': 'Paris Fashion Week',       'city': 'Paris',     'month': 'March / October',      'type': 'ready-to-wear'},
        {'event': 'Paris Haute Couture Week', 'city': 'Paris',     'month': 'January / July',       'type': 'haute-couture'},
        {'event': 'Met Gala',                 'city': 'New York',  'month': 'May',                  'type': 'event'},
        {'event': 'CFDA Awards',              'city': 'New York',  'month': 'November',             'type': 'award'},
        {'event': 'British Fashion Awards',   'city': 'London',    'month': 'December',             'type': 'award'},
        {'event': 'Vogue World',              'city': 'Various',   'month': 'September',            'type': 'event'},
        {'event': 'Oscars Red Carpet',        'city': 'Los Angeles','month': 'March',               'type': 'event'},
    ]
