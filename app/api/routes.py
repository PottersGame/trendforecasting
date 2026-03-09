"""
Fashion Trend Forecasting — API routes.

All endpoints return JSON and are cached at the data-source level.
No authentication required.

Endpoints
─────────
GET /api/dashboard          Overall dashboard summary
GET /api/trends             Scored & ranked fashion trends
GET /api/news               Latest fashion news
GET /api/news/<tag>         News filtered by tag
GET /api/reddit             Top Reddit fashion posts
GET /api/reddit/keywords    Trending Reddit keywords
GET /api/reddit/activity    Per-subreddit engagement stats
GET /api/google-trends      Google Trends interest-over-time
GET /api/aesthetics         Aesthetic group interest scores
GET /api/colors             Color trend palette
GET /api/brands             Brand mention counts
GET /api/calendar           Fashion event calendar
GET /api/wikipedia          Trending Wikipedia fashion articles
GET /api/ai/trend/<name>    AI analysis for one trend
GET /api/ai/overview        AI overview of top trends
GET /api/ai/season          AI seasonal outlook
GET /api/ai/news-analysis   AI analysis of news headlines
GET /api/sources            Data-source health check
"""

from __future__ import annotations

import concurrent.futures
from flask import Blueprint, jsonify, request, current_app

from app.data_sources.fashion_news       import (
    get_fashion_news, get_news_by_tag, extract_trending_keywords,
)
from app.data_sources.reddit_fashion     import (
    get_all_fashion_posts, get_posts_by_category,
    get_subreddit_activity, get_trending_keywords as reddit_keywords,
    get_top_posts,
)
from app.data_sources.google_trends_fashion import (
    get_interest_over_time, get_trending_fashion_searches,
    get_aesthetic_group_interest, get_all_group_scores,
    get_related_queries, AESTHETIC_GROUPS,
)
from app.data_sources.wikipedia_fashion  import (
    get_top_fashion_articles, get_fashion_designer_articles,
)
from app.models import (
    score_trends, score_brands, get_color_trends,
    get_current_season, get_fashion_calendar,
)
from app.ai.fashion_analyzer import (
    analyse_trend, analyse_top_trends,
    analyse_seasonal_outlook, generate_style_tip,
    analyse_news_headlines,
)
from app.utils import cache

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_text_pool() -> list[str]:
    """Collect all titles/descriptions from news + Reddit for keyword scoring."""
    pool: list[str] = []
    for art in get_fashion_news(limit=100):
        pool.append(art.get('title', ''))
        pool.append(art.get('description', ''))
    for post in get_all_fashion_posts(limit_per_sub=20):
        pool.append(post.get('title', ''))
    return pool


def _cached_text_pool() -> list[str]:
    hit = cache.get('text_pool')
    if hit is not None:
        return hit
    pool = _build_text_pool()
    cache.set('text_pool', pool, ttl=300)
    return pool


# ── Routes ─────────────────────────────────────────────────────────────────────

@api_bp.route('/dashboard')
def dashboard():
    """All-in-one dashboard payload."""
    hit = cache.get('dashboard')
    if hit is not None:
        return jsonify(hit)

    text_pool = _cached_text_pool()

    # Fetch everything concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        f_news       = ex.submit(get_fashion_news,       60)
        f_reddit     = ex.submit(get_all_fashion_posts,  15)
        f_trends     = ex.submit(score_trends,           text_pool)
        f_brands     = ex.submit(score_brands,           text_pool)
        f_keywords   = ex.submit(reddit_keywords,        40)
        f_wiki       = ex.submit(get_top_fashion_articles)
        f_activity   = ex.submit(get_subreddit_activity)
        f_calendar   = ex.submit(get_fashion_calendar)

    news       = f_news.result()
    reddit     = f_reddit.result()
    trends     = f_trends.result()
    brands     = f_brands.result()
    keywords   = f_keywords.result()
    wiki       = f_wiki.result()
    activity   = f_activity.result()
    cal        = f_calendar.result()
    season     = get_current_season()
    colors     = get_color_trends()

    # AI overview (non-blocking — skip if too slow)
    ai_overview = ''
    try:
        ai_overview = analyse_top_trends(trends[:5])
    except Exception:
        pass

    data = {
        'season':       season,
        'top_trends':   trends[:10],
        'top_news':     news[:12],
        'top_reddit':   reddit[:12],
        'top_brands':   brands[:15],
        'keywords':     keywords[:30],
        'wiki_articles': wiki[:8],
        'activity':     activity[:10],
        'calendar':     cal,
        'colors':       colors,
        'ai_overview':  ai_overview,
        'source_count': 4,
    }

    cache.set('dashboard', data, ttl=300)
    return jsonify(data)


@api_bp.route('/trends')
def trends():
    """Scored and ranked fashion trends."""
    text_pool = _cached_text_pool()
    data = score_trends(text_pool)
    return jsonify(data)


@api_bp.route('/news')
def news():
    limit = min(int(request.args.get('limit', 60)), 120)
    return jsonify(get_fashion_news(limit=limit))


@api_bp.route('/news/<tag>')
def news_by_tag(tag: str):
    limit = min(int(request.args.get('limit', 20)), 60)
    return jsonify(get_news_by_tag(tag, limit=limit))


@api_bp.route('/reddit')
def reddit():
    category = request.args.get('category', '')
    limit    = min(int(request.args.get('limit', 40)), 100)
    if category:
        return jsonify(get_posts_by_category(category, limit=limit))
    return jsonify(get_all_fashion_posts(limit_per_sub=20)[:limit])


@api_bp.route('/reddit/keywords')
def reddit_kw():
    return jsonify(reddit_keywords(limit=40))


@api_bp.route('/reddit/activity')
def reddit_activity():
    return jsonify(get_subreddit_activity())


@api_bp.route('/reddit/top')
def reddit_top():
    return jsonify(get_top_posts(limit=10))


@api_bp.route('/google-trends')
def google_trends():
    keywords = request.args.get('keywords', '')
    group    = request.args.get('group', '')
    geo      = request.args.get('geo', '')
    tf       = request.args.get('timeframe', 'today 3-m')

    if group and group in AESTHETIC_GROUPS:
        return jsonify(get_aesthetic_group_interest(group))
    if keywords:
        kw_list = [k.strip() for k in keywords.split(',') if k.strip()][:5]
        return jsonify(get_interest_over_time(kw_list, timeframe=tf, geo=geo))
    # Default: viral aesthetics
    return jsonify(get_aesthetic_group_interest('viral_aesthetics'))


@api_bp.route('/aesthetics')
def aesthetics():
    scores = get_all_group_scores()
    return jsonify(scores)


@api_bp.route('/aesthetics/<group>')
def aesthetic_group(group: str):
    return jsonify(get_aesthetic_group_interest(group))


@api_bp.route('/colors')
def colors():
    season = request.args.get('season', '')
    return jsonify(get_color_trends(season_filter=season or None))


@api_bp.route('/brands')
def brands():
    text_pool = _cached_text_pool()
    return jsonify(score_brands(text_pool))


@api_bp.route('/calendar')
def calendar():
    return jsonify(get_fashion_calendar())


@api_bp.route('/wikipedia')
def wikipedia():
    limit = min(int(request.args.get('limit', 20)), 50)
    data  = get_top_fashion_articles(limit=limit)
    if not data:
        data = get_fashion_designer_articles()
    return jsonify(data)


@api_bp.route('/ai/trend/<path:name>')
def ai_trend(name: str):
    return jsonify({'trend': name, 'analysis': analyse_trend(name)})


@api_bp.route('/ai/tip/<path:name>')
def ai_tip(name: str):
    return jsonify({'trend': name, 'tip': generate_style_tip(name)})


@api_bp.route('/ai/overview')
def ai_overview():
    text_pool = _cached_text_pool()
    trends    = score_trends(text_pool)
    return jsonify({'analysis': analyse_top_trends(trends[:5])})


@api_bp.route('/ai/season')
def ai_season():
    season = request.args.get('season', get_current_season())
    return jsonify({'season': season, 'analysis': analyse_seasonal_outlook(season)})


@api_bp.route('/ai/news-analysis')
def ai_news():
    news     = get_fashion_news(limit=20)
    headlines = [a['title'] for a in news]
    return jsonify({'analysis': analyse_news_headlines(headlines)})


@api_bp.route('/related-queries')
def related_queries():
    keyword = request.args.get('keyword', 'quiet luxury')
    return jsonify(get_related_queries(keyword))


@api_bp.route('/trending-searches')
def trending_searches():
    return jsonify(get_trending_fashion_searches())


@api_bp.route('/keywords')
def keywords():
    news     = get_fashion_news(limit=80)
    kw_news  = extract_trending_keywords(news, top_n=30)
    kw_reddit = reddit_keywords(limit=30)
    # Merge and re-sort
    merged: dict[str, int] = {}
    for kw in kw_news:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count'] * 2
    for kw in kw_reddit:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    sorted_kw = sorted(merged.items(), key=lambda x: x[1], reverse=True)
    return jsonify([{'word': w, 'count': c} for w, c in sorted_kw[:40]])


@api_bp.route('/sources')
def sources():
    """Report which data sources are reachable."""
    results: dict[str, bool] = {}
    checks = [
        ('fashion_news',   lambda: bool(get_fashion_news(limit=3))),
        ('reddit',         lambda: bool(get_all_fashion_posts(limit_per_sub=3))),
        ('wikipedia',      lambda: bool(get_top_fashion_articles())),
    ]
    for name, fn in checks:
        try:
            results[name] = fn()
        except Exception:
            results[name] = False

    return jsonify(results)
