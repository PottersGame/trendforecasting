"""
Fashion Trend Forecasting — API routes.

All endpoints return JSON.

Core Endpoints
──────────────
GET  /api/dashboard          Overall dashboard summary
GET  /api/trends             Scored & ranked fashion trends
GET  /api/news               Latest fashion news
GET  /api/news/<tag>         News filtered by tag
GET  /api/reddit             Top Reddit fashion posts
GET  /api/reddit/keywords    Trending Reddit keywords
GET  /api/reddit/activity    Per-subreddit engagement stats
GET  /api/google-trends      Google Trends interest-over-time
GET  /api/aesthetics         Aesthetic group interest scores
GET  /api/colors             Color trend palette
GET  /api/brands             Brand mention counts
GET  /api/calendar           Fashion event calendar
GET  /api/wikipedia          Trending Wikipedia fashion articles
GET  /api/keywords           Merged keyword frequency

TikTok
──────
GET  /api/tiktok             Fashion TikTok posts / hashtag signals
GET  /api/tiktok/keywords    Trending keywords from TikTok
GET  /api/tiktok/hashtags    Per-category TikTok hashtag summary

Pinterest
─────────
GET  /api/pinterest          Fashion Pinterest pins
GET  /api/pinterest/keywords Trending keywords from Pinterest
GET  /api/pinterest/boards   Per-board Pinterest activity

Search (RAG)
────────────
GET  /api/search?q=<query>   Search DB + AI analysis
GET  /api/search/news?q=     Search stored news articles
GET  /api/search/reddit?q=   Search stored Reddit posts

Forecasting
───────────
GET  /api/forecast           All trend forecasts (ML from DB)
GET  /api/forecast/<name>    Single-trend forecast
GET  /api/forecast/leaderboard Top trends by 7-day forecast

AI Endpoints
────────────
GET  /api/ai/trend/<name>    AI analysis for one trend
GET  /api/ai/tip/<name>      Style tip for a trend
GET  /api/ai/overview        AI overview of top trends
GET  /api/ai/season          AI seasonal outlook
GET  /api/ai/news-analysis   AI analysis of latest headlines
GET  /api/ai/models          Available Ollama models

Database
────────
GET  /api/db/stats           Database statistics
POST /api/db/ingest          Fetch all sources and save to DB
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
    get_related_queries, get_status as google_trends_status,
    refresh_aesthetic_groups, discover_trending_keywords,
)
from app.data_sources.wikipedia_fashion  import (
    get_top_fashion_articles, get_fashion_designer_articles,
)
from app.data_sources.tiktok_fashion     import (
    get_tiktok_fashion_posts, get_tiktok_trending_keywords,
    get_tiktok_hashtag_summary,
)
from app.data_sources.pinterest_fashion  import (
    get_pinterest_fashion_pins, get_pinterest_trending_keywords,
    get_pinterest_board_activity,
)
from app.models import (
    score_trends, score_brands, get_color_trends,
    get_current_season, get_fashion_calendar,
)
from app.models.forecaster import (
    get_forecasts, get_trend_forecast, trend_leaderboard,
)
from app.ai.fashion_analyzer import (
    analyse_trend, analyse_top_trends,
    analyse_seasonal_outlook, generate_style_tip,
    analyse_news_headlines, search_and_analyse,
    get_ollama_models,
)
from app import database as db
from app.utils import cache
from app.api.auth import require_api_key

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_text_pool() -> list:
    pool = []
    for a in get_fashion_news(limit=100):
        pool.append(a.get('title', ''))
        pool.append(a.get('description', ''))
    for p in get_all_fashion_posts(limit_per_sub=20):
        pool.append(p.get('title', ''))
    for p in get_tiktok_fashion_posts(limit=50):
        pool.append(p.get('title', ''))
        pool += p.get('keywords', [])
    for p in get_pinterest_fashion_pins(limit=60):
        pool.append(p.get('title', ''))
        pool.append(p.get('description', ''))
    return pool


def _cached_text_pool() -> list:
    hit = cache.get('text_pool')
    if hit is not None:
        return hit
    pool = _build_text_pool()
    cache.set('text_pool', pool, ttl=300)
    return pool


def _ingest_all() -> dict:
    """Fetch everything and persist to DB. Returns summary counts."""
    news   = get_fashion_news(limit=100)
    reddit = get_all_fashion_posts(limit_per_sub=25)
    text_pool = [a.get('title','') + ' ' + a.get('description','') for a in news] + \
                [p.get('title','') for p in reddit]

    trends  = score_trends(text_pool)
    brands  = score_brands(text_pool)
    kw_news = extract_trending_keywords(news, top_n=40)
    kw_reddit = reddit_keywords(limit=40)

    # TikTok and Pinterest keyword signals
    kw_tiktok    = get_tiktok_trending_keywords(limit=30)
    kw_pinterest = get_pinterest_trending_keywords(limit=30)

    # Merge keywords from all sources
    merged: dict = {}
    for kw in kw_news:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count'] * 2
    for kw in kw_reddit:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    for kw in kw_tiktok:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    for kw in kw_pinterest:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    kw_merged = [{'word': w, 'count': c} for w, c in
                 sorted(merged.items(), key=lambda x: x[1], reverse=True)[:50]]

    n_news   = db.save_news_articles(news)
    n_reddit = db.save_reddit_posts(reddit)
    db.save_trend_snapshot(trends)
    db.save_keyword_snapshot(kw_merged, source='merged')
    db.save_brand_snapshot(brands)

    # Google Trends (best-effort — may be rate-limited)
    try:
        for group, keywords in list(refresh_aesthetic_groups().items())[:3]:
            data = get_aesthetic_group_interest(group)
            dates = data.get('dates', [])
            for kw, vals in data.get('data', {}).items():
                if dates and vals:
                    db.save_google_trends(kw, dates, vals, group)
    except Exception:
        pass

    # Recompute forecasts now that we have fresh snapshots
    try:
        from app.models.forecaster import compute_forecasts
        cache.delete('forecasts_computed')
        compute_forecasts()
    except Exception:
        pass

    return {
        'new_news':       n_news,
        'new_reddit':     n_reddit,
        'trends_saved':   len(trends),
        'keywords_saved': len(kw_merged),
    }


# ── Dashboard ──────────────────────────────────────────────────────────────────

@api_bp.route('/dashboard')
def dashboard():
    hit = cache.get('dashboard')
    if hit:
        return jsonify(hit)

    text_pool = _cached_text_pool()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        f_news     = ex.submit(get_fashion_news, 60)
        f_reddit   = ex.submit(get_all_fashion_posts, 15)
        f_trends   = ex.submit(score_trends, text_pool)
        f_brands   = ex.submit(score_brands, text_pool)
        f_keywords = ex.submit(reddit_keywords, 40)
        f_wiki     = ex.submit(get_top_fashion_articles)
        f_activity = ex.submit(get_subreddit_activity)
        f_calendar = ex.submit(get_fashion_calendar)

    news      = f_news.result()
    reddit    = f_reddit.result()
    trends    = f_trends.result()
    brands    = f_brands.result()
    keywords  = f_keywords.result()
    wiki      = f_wiki.result()
    activity  = f_activity.result()
    cal       = f_calendar.result()
    season    = get_current_season()
    colors    = get_color_trends()

    # Best-effort AI overview (non-blocking)
    ai_overview = ''
    ai_model    = 'rule-based'
    try:
        ai_overview, ai_model = analyse_top_trends(trends[:5])
    except Exception:
        pass

    # DB stats for dashboard KPIs
    try:
        db_stats = db.get_db_stats()
    except Exception:
        db_stats = {}

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
        'ai_model':     ai_model,
        'db_stats':     db_stats,
    }
    cache.set('dashboard', data, ttl=300)
    return jsonify(data)


# ── Trends ─────────────────────────────────────────────────────────────────────

@api_bp.route('/trends')
def trends():
    text_pool = _cached_text_pool()
    return jsonify(score_trends(text_pool))


# ── News ───────────────────────────────────────────────────────────────────────

@api_bp.route('/news')
def news():
    limit = min(int(request.args.get('limit', 60)), 120)
    return jsonify(get_fashion_news(limit=limit))


@api_bp.route('/news/<tag>')
def news_by_tag(tag):
    limit = min(int(request.args.get('limit', 20)), 60)
    return jsonify(get_news_by_tag(tag, limit=limit))


# ── Reddit ─────────────────────────────────────────────────────────────────────

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


# ── Google Trends ──────────────────────────────────────────────────────────────

@api_bp.route('/google-trends')
def google_trends():
    keywords = request.args.get('keywords', '')
    group    = request.args.get('group', '')
    geo      = request.args.get('geo', '')
    tf       = request.args.get('timeframe', 'today 3-m')

    if group and group in refresh_aesthetic_groups():
        return jsonify(get_aesthetic_group_interest(group))
    if keywords:
        kw_list = [k.strip() for k in keywords.split(',') if k.strip()][:5]
        return jsonify(get_interest_over_time(kw_list, timeframe=tf, geo=geo))
    return jsonify(get_aesthetic_group_interest('aesthetics'))


@api_bp.route('/google-trends/status')
def google_trends_check():
    """Check whether the Google Trends integration is operational."""
    return jsonify(google_trends_status())


@api_bp.route('/aesthetics')
def aesthetics():
    return jsonify(get_all_group_scores())


@api_bp.route('/aesthetics/<group>')
def aesthetic_group(group):
    return jsonify(get_aesthetic_group_interest(group))


@api_bp.route('/aesthetic-groups')
def aesthetic_groups_list():
    """Return the currently active (dynamically discovered) keyword groups."""
    return jsonify(refresh_aesthetic_groups())


@api_bp.route('/discover-trends')
def discover_trends_endpoint():
    """Return top trending fashion keywords discovered from all live sources."""
    limit = min(int(request.args.get('limit', 40)), 100)
    return jsonify(discover_trending_keywords(limit=limit))


# ── Colors / Brands / Calendar / Wikipedia ────────────────────────────────────

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


@api_bp.route('/keywords')
def keywords():
    news_data    = get_fashion_news(limit=80)
    kw_news      = extract_trending_keywords(news_data, top_n=30)
    kw_reddit    = reddit_keywords(limit=30)
    kw_tiktok    = get_tiktok_trending_keywords(limit=20)
    kw_pinterest = get_pinterest_trending_keywords(limit=20)
    merged: dict = {}
    for kw in kw_news:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count'] * 2
    for kw in kw_reddit:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    for kw in kw_tiktok:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    for kw in kw_pinterest:
        merged[kw['word']] = merged.get(kw['word'], 0) + kw['count']
    sorted_kw = sorted(merged.items(), key=lambda x: x[1], reverse=True)
    return jsonify([{'word': w, 'count': c} for w, c in sorted_kw[:40]])


# ── TikTok ─────────────────────────────────────────────────────────────────────

@api_bp.route('/tiktok')
def tiktok():
    """Fashion TikTok posts / hashtag trend signals."""
    limit = min(int(request.args.get('limit', 50)), 100)
    return jsonify(get_tiktok_fashion_posts(limit=limit))


@api_bp.route('/tiktok/keywords')
def tiktok_keywords():
    """Trending keywords extracted from TikTok fashion posts."""
    limit = min(int(request.args.get('limit', 30)), 60)
    return jsonify(get_tiktok_trending_keywords(limit=limit))


@api_bp.route('/tiktok/hashtags')
def tiktok_hashtags():
    """Per-category TikTok hashtag summary."""
    return jsonify(get_tiktok_hashtag_summary())


# ── Pinterest ──────────────────────────────────────────────────────────────────

@api_bp.route('/pinterest')
def pinterest():
    """Fashion Pinterest pins."""
    limit = min(int(request.args.get('limit', 60)), 120)
    return jsonify(get_pinterest_fashion_pins(limit=limit))


@api_bp.route('/pinterest/keywords')
def pinterest_keywords():
    """Trending keywords extracted from Pinterest fashion pins."""
    limit = min(int(request.args.get('limit', 30)), 60)
    return jsonify(get_pinterest_trending_keywords(limit=limit))


@api_bp.route('/pinterest/boards')
def pinterest_boards():
    """Per-board Pinterest activity stats."""
    return jsonify(get_pinterest_board_activity())


# ── SEARCH (RAG) ───────────────────────────────────────────────────────────────

@api_bp.route('/search')
@require_api_key
def search():
    """
    Search our DB for a query, inject results into the LLM, return AI analysis.
    Also returns the raw matching records.
    """
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Missing q parameter'}), 400

    raw_results = db.search_all(query, limit=10)
    analysis, model = search_and_analyse(query)

    return jsonify({
        'query':    query,
        'analysis': analysis,
        'model':    model,
        'news':     raw_results.get('news', []),
        'reddit':   raw_results.get('reddit', []),
    })


@api_bp.route('/search/news')
def search_news():
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 10)), 50)
    if not query:
        return jsonify(db.get_recent_news(limit=limit))
    return jsonify(db.search_news(query, limit=limit))


@api_bp.route('/search/reddit')
def search_reddit():
    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 10)), 50)
    if not query:
        return jsonify(db.get_top_reddit_posts(limit=limit))
    return jsonify(db.search_reddit(query, limit=limit))


@api_bp.route('/search/keywords')
def search_db_keywords():
    """Top keywords from DB history (more stable than live counts)."""
    days  = int(request.args.get('days', 7))
    limit = min(int(request.args.get('limit', 40)), 100)
    return jsonify(db.get_top_keywords_from_db(days=days, limit=limit))


# ── FORECASTING ────────────────────────────────────────────────────────────────

@api_bp.route('/forecast')
def forecast():
    """ML-computed trend forecasts using historical DB data."""
    try:
        return jsonify(get_forecasts())
    except Exception as e:
        return jsonify({'error': str(e), 'forecasts': db.get_latest_forecasts()})


@api_bp.route('/forecast/leaderboard')
def forecast_leaderboard():
    limit = min(int(request.args.get('limit', 10)), 20)
    try:
        return jsonify(trend_leaderboard(limit=limit))
    except Exception as e:
        return jsonify({'error': str(e)})


@api_bp.route('/forecast/<path:name>')
def forecast_single(name):
    result = get_trend_forecast(name)
    if not result:
        return jsonify({'error': f'No forecast found for "{name}"'}), 404
    return jsonify(result)


# ── AI ─────────────────────────────────────────────────────────────────────────

@api_bp.route('/ai/trend/<path:name>')
@require_api_key
def ai_trend(name):
    text, model = analyse_trend(name)
    return jsonify({'trend': name, 'analysis': text, 'model': model})


@api_bp.route('/ai/tip/<path:name>')
@require_api_key
def ai_tip(name):
    text, model = generate_style_tip(name)
    return jsonify({'trend': name, 'tip': text, 'model': model})


@api_bp.route('/ai/overview')
@require_api_key
def ai_overview():
    text_pool = _cached_text_pool()
    trends    = score_trends(text_pool)
    text, model = analyse_top_trends(trends[:5])
    return jsonify({'analysis': text, 'model': model})


@api_bp.route('/ai/season')
@require_api_key
def ai_season():
    season = request.args.get('season', get_current_season())
    text, model = analyse_seasonal_outlook(season)
    return jsonify({'season': season, 'analysis': text, 'model': model})


@api_bp.route('/ai/news-analysis')
@require_api_key
def ai_news():
    news_data = get_fashion_news(limit=20)
    headlines = [a['title'] for a in news_data]
    text, model = analyse_news_headlines(headlines)
    return jsonify({'analysis': text, 'model': model})


@api_bp.route('/ai/models')
@require_api_key
def ai_models():
    """List available AI models and their status."""
    host   = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
    models = get_ollama_models(host)
    return jsonify({
        'ollama_host':      host,
        'ollama_model':     current_app.config.get('OLLAMA_MODEL', 'llama3'),
        'available':        models,
        'groq_enabled':     bool(current_app.config.get('GROQ_API_KEY')),
        'gemini_enabled':   bool(current_app.config.get('GEMINI_API_KEY')),
        'openai_enabled':   bool(current_app.config.get('OPENAI_API_KEY')),
        'ollama_running':   bool(models),
        'priority_chain':   ['groq', 'gemini', 'openai', 'ollama', 'rule-based'],
    })


# ── DATABASE ───────────────────────────────────────────────────────────────────

@api_bp.route('/db/stats')
def db_stats():
    return jsonify(db.get_db_stats())


@api_bp.route('/db/ingest', methods=['POST', 'GET'])
@require_api_key
def db_ingest():
    """
    Trigger a full data ingest: fetch all sources, save to DB,
    and recompute forecasts. Safe to call repeatedly.
    """
    try:
        result = _ingest_all()
        result['status'] = 'ok'
        result['db_stats'] = db.get_db_stats()
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/db/history/<path:trend>')
def db_history(trend):
    days = int(request.args.get('days', 30))
    return jsonify(db.get_trend_history(trend, days=days))


@api_bp.route('/db/history')
def db_all_history():
    days = int(request.args.get('days', 14))
    return jsonify(db.get_all_trend_history(days=days))


@api_bp.route('/related-queries')
def related_queries():
    keyword = request.args.get('keyword', 'quiet luxury')
    return jsonify(get_related_queries(keyword))


@api_bp.route('/trending-searches')
def trending_searches():
    return jsonify(get_trending_fashion_searches())


@api_bp.route('/sources')
def sources():
    results = {}
    checks = [
        ('fashion_news', lambda: bool(get_fashion_news(limit=3))),
        ('reddit',       lambda: bool(get_all_fashion_posts(limit_per_sub=3))),
        ('wikipedia',    lambda: bool(get_top_fashion_articles())),
        ('tiktok',       lambda: bool(get_tiktok_fashion_posts(limit=3))),
        ('pinterest',    lambda: bool(get_pinterest_fashion_pins(limit=3))),
        ('database',     lambda: bool(db.get_db_stats())),
    ]
    for name, fn in checks:
        try:
            results[name] = fn()
        except Exception:
            results[name] = False
    return jsonify(results)


# ── API KEY MANAGEMENT ─────────────────────────────────────────────────────────

@api_bp.route('/keys/register', methods=['POST'])
def keys_register():
    """
    Register a new API user and return their key.
    Body: { "email": "user@example.com", "plan": "free" }
    """
    import secrets as _secrets
    data  = request.get_json(silent=True) or {}
    email = (data.get('email') or request.form.get('email', '')).strip().lower()
    plan  = (data.get('plan')  or request.form.get('plan', 'free')).strip().lower()

    if not email or '@' not in email:
        return jsonify({'error': 'A valid email address is required.'}), 400

    if plan not in ('free', 'pro', 'enterprise'):
        plan = 'free'

    # Check for existing user
    existing = db.get_api_user_by_email(email)
    if existing:
        return jsonify({
            'error': 'Email already registered.',
            'message': 'An API key already exists for this email. Contact support to retrieve it.',
        }), 409

    api_key = 'rw_' + _secrets.token_urlsafe(32)
    user = db.create_api_user(email, api_key, plan)
    if not user:
        return jsonify({'error': 'Registration failed. Please try again.'}), 500

    daily_limit = user['daily_limit']
    return jsonify({
        'success': True,
        'email':       email,
        'api_key':     api_key,
        'plan':        plan,
        'daily_limit': daily_limit,
        'message': (
            f'Welcome! Your {"free" if plan == "free" else plan} API key has been created. '
            f'You can make {daily_limit if daily_limit else "unlimited"} requests per day. '
            'Pass the key in the "X-API-Key" header or as "Authorization: Bearer <key>".'
        ),
    }), 201


@api_bp.route('/keys/verify', methods=['GET', 'POST'])
def keys_verify():
    """Verify an API key and return usage info."""
    from app.api.auth import _extract_token
    token = _extract_token()
    if not token:
        # Also accept ?key= query param for convenience
        token = request.args.get('key', '').strip()

    if not token:
        return jsonify({'error': 'No API key provided.'}), 400

    user = db.get_api_user_by_key(token)
    if not user:
        return jsonify({'valid': False, 'error': 'API key not found.'}), 404

    return jsonify({
        'valid':          True,
        'plan':           user['plan'],
        'requests_today': user['requests_today'],
        'daily_limit':    user['daily_limit'],
        'created_at':     user['created_at'],
        'last_used':      user.get('last_used'),
    })


@api_bp.route('/keys/stats')
@require_api_key
def keys_stats():
    """Admin: summary of all registered API users."""
    return jsonify(db.get_api_users_stats())

