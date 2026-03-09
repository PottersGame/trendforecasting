"""
Fashion Trends SQLite database.

Stores all fetched data persistently so the AI can forecast from real
historical data rather than only live snapshots.

Tables
──────
fashion_news       – article titles, sources, tags, published date
reddit_posts       – post titles, subreddits, scores, comment counts
trend_snapshots    – scored trend values sampled over time  ← used for forecasting
keyword_snapshots  – keyword frequency over time
brand_snapshots    – brand mention counts over time
google_trends_data – raw interest-over-time values per keyword per date
ai_analyses        – cached LLM outputs with model attribution
forecasts          – computed ML projections (written by forecaster.py)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

# ── Path ────────────────────────────────────────────────────────────────────
_DB_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DB_PATH  = os.path.join(_DB_DIR, 'fashion_trends.db')
os.makedirs(_DB_DIR, exist_ok=True)

_lock = threading.Lock()   # single-writer guard for SQLite in WAL mode


# ── Schema ───────────────────────────────────────────────────────────────────
_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS fashion_news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    url         TEXT    UNIQUE,
    description TEXT,
    source      TEXT,
    tags        TEXT,          -- JSON array, e.g. '["luxury","runway"]'
    published   TEXT,
    fetched_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS reddit_posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reddit_id   TEXT    UNIQUE,
    title       TEXT    NOT NULL,
    subreddit   TEXT,
    category    TEXT,
    score       INTEGER DEFAULT 0,
    comments    INTEGER DEFAULT 0,
    url         TEXT,
    permalink   TEXT,
    fetched_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS trend_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_name  TEXT    NOT NULL,
    score       INTEGER NOT NULL,
    momentum    TEXT,
    snapshot_at TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS keyword_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT    NOT NULL,
    count       INTEGER NOT NULL,
    source      TEXT,           -- 'reddit' | 'news' | 'merged'
    snapshot_at TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS brand_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    brand       TEXT    NOT NULL,
    mentions    INTEGER NOT NULL,
    snapshot_at TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS google_trends_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    value       INTEGER NOT NULL,
    group_name  TEXT,
    fetched_at  TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(keyword, date)
);

CREATE TABLE IF NOT EXISTS ai_analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_type TEXT    NOT NULL,  -- 'trend'|'overview'|'season'|'news'|'search'
    subject       TEXT,
    content       TEXT    NOT NULL,
    model_used    TEXT    DEFAULT 'rule-based',
    created_at    TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS forecasts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_name       TEXT    NOT NULL,
    current_score    REAL,
    forecast_7d      REAL,
    forecast_14d     REAL,
    forecast_30d     REAL,
    direction        TEXT,   -- 'rising'|'stable'|'falling'
    confidence       REAL,   -- 0-1
    data_points_used INTEGER,
    computed_at      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS api_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT    UNIQUE NOT NULL,
    api_key         TEXT    UNIQUE NOT NULL,
    plan            TEXT    DEFAULT 'free',   -- 'free' | 'pro' | 'enterprise'
    requests_today  INTEGER DEFAULT 0,
    daily_limit     INTEGER DEFAULT 100,      -- requests per day (free=100, pro=5000)
    last_reset      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    created_at      TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_used       TEXT
);

-- Index for fast key lookup
CREATE INDEX IF NOT EXISTS idx_api_users_key   ON api_users(api_key);
CREATE INDEX IF NOT EXISTS idx_api_users_email ON api_users(email);

CREATE INDEX IF NOT EXISTS idx_news_fetched       ON fashion_news(fetched_at);
CREATE INDEX IF NOT EXISTS idx_news_source        ON fashion_news(source);
CREATE INDEX IF NOT EXISTS idx_reddit_fetched     ON reddit_posts(fetched_at);
CREATE INDEX IF NOT EXISTS idx_reddit_category    ON reddit_posts(category);
CREATE INDEX IF NOT EXISTS idx_trend_snap_name    ON trend_snapshots(trend_name);
CREATE INDEX IF NOT EXISTS idx_trend_snap_at      ON trend_snapshots(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_kw_snap_keyword    ON keyword_snapshots(keyword);
CREATE INDEX IF NOT EXISTS idx_brand_snap_brand   ON brand_snapshots(brand);
CREATE INDEX IF NOT EXISTS idx_gtdata_keyword     ON google_trends_data(keyword, date);
CREATE INDEX IF NOT EXISTS idx_ai_type            ON ai_analyses(analysis_type, subject);
CREATE INDEX IF NOT EXISTS idx_forecast_trend     ON forecasts(trend_name);
"""


# ── Connection ───────────────────────────────────────────────────────────────
@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create all tables and indexes if they don't exist."""
    with _lock, _conn() as con:
        con.executescript(_SCHEMA)


# ── Writers ──────────────────────────────────────────────────────────────────
def save_news_articles(articles: List[Dict[str, Any]]) -> int:
    """Upsert fashion news articles. Returns count of newly inserted rows."""
    inserted = 0
    sql = """
        INSERT OR IGNORE INTO fashion_news (title, url, description, source, tags, published)
        VALUES (:title, :url, :description, :source, :tags, :published)
    """
    with _lock, _conn() as con:
        for a in articles:
            tags = json.dumps(a.get('tags', []))
            cur = con.execute(sql, {
                'title':       a.get('title', '')[:500],
                'url':         a.get('url', ''),
                'description': a.get('description', '')[:1000],
                'source':      a.get('source', ''),
                'tags':        tags,
                'published':   a.get('published', ''),
            })
            inserted += cur.rowcount
    return inserted


def save_reddit_posts(posts: List[Dict[str, Any]]) -> int:
    """Upsert Reddit posts. Returns count of newly inserted rows."""
    inserted = 0
    sql = """
        INSERT OR IGNORE INTO reddit_posts
            (reddit_id, title, subreddit, category, score, comments, url, permalink)
        VALUES (:reddit_id, :title, :subreddit, :category, :score, :comments, :url, :permalink)
    """
    with _lock, _conn() as con:
        for p in posts:
            # Derive a stable ID from permalink (or url)
            rid = p.get('permalink', p.get('url', ''))[-60:]
            cur = con.execute(sql, {
                'reddit_id': rid,
                'title':     p.get('title', '')[:500],
                'subreddit': p.get('subreddit', ''),
                'category':  p.get('category', ''),
                'score':     p.get('score', 0),
                'comments':  p.get('comments', 0),
                'url':       p.get('url', ''),
                'permalink': p.get('permalink', ''),
            })
            inserted += cur.rowcount
    return inserted


def save_trend_snapshot(trends: List[Dict[str, Any]]) -> None:
    """Insert one snapshot row per trend (time-series data)."""
    sql = """
        INSERT INTO trend_snapshots (trend_name, score, momentum)
        VALUES (:trend_name, :score, :momentum)
    """
    with _lock, _conn() as con:
        for t in trends:
            con.execute(sql, {
                'trend_name': t.get('name', ''),
                'score':      int(t.get('score', 0)),
                'momentum':   t.get('momentum', 'stable'),
            })


def save_keyword_snapshot(keywords: List[Dict[str, Any]], source: str = 'merged') -> None:
    """Insert keyword frequency snapshot."""
    sql = """
        INSERT INTO keyword_snapshots (keyword, count, source)
        VALUES (:keyword, :count, :source)
    """
    with _lock, _conn() as con:
        for kw in keywords:
            con.execute(sql, {
                'keyword': kw.get('word', ''),
                'count':   int(kw.get('count', 0)),
                'source':  source,
            })


def save_brand_snapshot(brands: List[Dict[str, Any]]) -> None:
    """Insert brand mention snapshot."""
    sql = """
        INSERT INTO brand_snapshots (brand, mentions)
        VALUES (:brand, :mentions)
    """
    with _lock, _conn() as con:
        for b in brands:
            con.execute(sql, {
                'brand':    b.get('brand', ''),
                'mentions': int(b.get('mentions', 0)),
            })


def save_google_trends(keyword: str, dates: List[str], values: List[int], group: str = '') -> None:
    """Upsert Google Trends interest-over-time data."""
    sql = """
        INSERT OR REPLACE INTO google_trends_data (keyword, date, value, group_name)
        VALUES (:keyword, :date, :value, :group)
    """
    with _lock, _conn() as con:
        for date, val in zip(dates, values):
            con.execute(sql, {'keyword': keyword, 'date': date, 'value': val, 'group': group})


def save_ai_analysis(
    analysis_type: str,
    subject: str,
    content: str,
    model_used: str = 'rule-based',
) -> None:
    """Persist an AI analysis to the database."""
    sql = """
        INSERT INTO ai_analyses (analysis_type, subject, content, model_used)
        VALUES (:t, :s, :c, :m)
    """
    with _lock, _conn() as con:
        con.execute(sql, {'t': analysis_type, 's': subject, 'c': content, 'm': model_used})


def save_forecast(forecast: Dict[str, Any]) -> None:
    """Upsert a trend forecast (replaces for same trend)."""
    # Delete old forecast for same trend, then insert fresh
    with _lock, _conn() as con:
        con.execute('DELETE FROM forecasts WHERE trend_name = ?', (forecast['trend_name'],))
        con.execute("""
            INSERT INTO forecasts
                (trend_name, current_score, forecast_7d, forecast_14d, forecast_30d,
                 direction, confidence, data_points_used)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            forecast['trend_name'],
            forecast.get('current_score', 0),
            forecast.get('forecast_7d', 0),
            forecast.get('forecast_14d', 0),
            forecast.get('forecast_30d', 0),
            forecast.get('direction', 'stable'),
            forecast.get('confidence', 0.5),
            forecast.get('data_points_used', 0),
        ))


# ── Readers ──────────────────────────────────────────────────────────────────
def get_trend_history(trend_name: str, days: int = 30) -> List[Dict[str, Any]]:
    """Return time-series of trend scores for the past N days."""
    sql = """
        SELECT trend_name, score, momentum, snapshot_at
        FROM   trend_snapshots
        WHERE  trend_name = ?
          AND  snapshot_at >= datetime('now', ?)
        ORDER  BY snapshot_at ASC
    """
    with _conn() as con:
        rows = con.execute(sql, (trend_name, f'-{days} days')).fetchall()
    return [dict(r) for r in rows]


def get_all_trend_history(days: int = 30) -> Dict[str, List[Dict]]:
    """Return time-series for every trend in the last N days."""
    sql = """
        SELECT trend_name, score, momentum, snapshot_at
        FROM   trend_snapshots
        WHERE  snapshot_at >= datetime('now', ?)
        ORDER  BY trend_name, snapshot_at ASC
    """
    with _conn() as con:
        rows = con.execute(sql, (f'-{days} days',)).fetchall()
    result: Dict[str, List[Dict]] = {}
    for r in rows:
        result.setdefault(r['trend_name'], []).append(dict(r))
    return result


def get_keyword_history(keyword: str, days: int = 30) -> List[Dict[str, Any]]:
    """Keyword frequency over time."""
    sql = """
        SELECT keyword, count, source, snapshot_at
        FROM   keyword_snapshots
        WHERE  keyword = ?
          AND  snapshot_at >= datetime('now', ?)
        ORDER  BY snapshot_at ASC
    """
    with _conn() as con:
        rows = con.execute(sql, (keyword, f'-{days} days')).fetchall()
    return [dict(r) for r in rows]


def get_latest_forecasts() -> List[Dict[str, Any]]:
    """Return the most recent computed forecast for every trend."""
    sql = """
        SELECT * FROM forecasts
        ORDER BY confidence DESC, forecast_7d DESC
    """
    with _conn() as con:
        rows = con.execute(sql).fetchall()
    return [dict(r) for r in rows]


def search_news(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Full-text keyword search over stored news articles."""
    pattern = f'%{query.lower()}%'
    sql = """
        SELECT title, url, description, source, tags, published, fetched_at
        FROM   fashion_news
        WHERE  lower(title) LIKE ?  OR  lower(description) LIKE ?
        ORDER  BY fetched_at DESC
        LIMIT  ?
    """
    with _conn() as con:
        rows = con.execute(sql, (pattern, pattern, limit)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d['tags'] = json.loads(d.get('tags') or '[]')
        except Exception:
            d['tags'] = []
        results.append(d)
    return results


def search_reddit(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Full-text keyword search over stored Reddit posts."""
    pattern = f'%{query.lower()}%'
    sql = """
        SELECT title, subreddit, category, score, comments, permalink, fetched_at
        FROM   reddit_posts
        WHERE  lower(title) LIKE ?
        ORDER  BY score DESC
        LIMIT  ?
    """
    with _conn() as con:
        rows = con.execute(sql, (pattern, limit)).fetchall()
    return [dict(r) for r in rows]


def search_all(query: str, limit: int = 8) -> Dict[str, List[Dict]]:
    """Search both news and Reddit for a query string."""
    return {
        'news':   search_news(query,   limit=limit),
        'reddit': search_reddit(query, limit=limit),
    }


def get_context_for_ai(subject: str, max_items: int = 8) -> str:
    """
    Build a text context block from DB records relevant to *subject*.
    Injected into LLM prompts as RAG context.
    """
    results = search_all(subject, limit=max_items)
    lines: List[str] = []

    news_items = results.get('news', [])
    if news_items:
        lines.append('## Recent news coverage:')
        for a in news_items[:5]:
            lines.append(f"- [{a['source']}] {a['title']}")

    reddit_items = results.get('reddit', [])
    if reddit_items:
        lines.append('\n## Reddit community discussion:')
        for p in reddit_items[:5]:
            lines.append(f"- [r/{p['subreddit']} | ↑{p['score']}] {p['title']}")

    return '\n'.join(lines)


def get_db_stats() -> Dict[str, Any]:
    """Summary statistics for the database."""
    queries = {
        'total_news':      'SELECT COUNT(*) FROM fashion_news',
        'total_reddit':    'SELECT COUNT(*) FROM reddit_posts',
        'trend_snapshots': 'SELECT COUNT(*) FROM trend_snapshots',
        'keyword_snapshots':'SELECT COUNT(*) FROM keyword_snapshots',
        'brand_snapshots': 'SELECT COUNT(*) FROM brand_snapshots',
        'google_data':     'SELECT COUNT(*) FROM google_trends_data',
        'ai_analyses':     'SELECT COUNT(*) FROM ai_analyses',
        'forecasts':       'SELECT COUNT(*) FROM forecasts',
        'oldest_snapshot': "SELECT MIN(snapshot_at) FROM trend_snapshots",
        'latest_snapshot': "SELECT MAX(snapshot_at) FROM trend_snapshots",
        'unique_sources':  "SELECT COUNT(DISTINCT source) FROM fashion_news",
        'unique_subs':     "SELECT COUNT(DISTINCT subreddit) FROM reddit_posts",
    }
    stats: Dict[str, Any] = {}
    with _conn() as con:
        for key, sql in queries.items():
            row = con.execute(sql).fetchone()
            stats[key] = row[0] if row else 0
    return stats


def get_recent_news(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch the most recently stored news articles."""
    sql = """
        SELECT title, url, description, source, tags, published, fetched_at
        FROM fashion_news
        ORDER BY fetched_at DESC
        LIMIT ?
    """
    with _conn() as con:
        rows = con.execute(sql, (limit,)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d['tags'] = json.loads(d.get('tags') or '[]')
        except Exception:
            d['tags'] = []
        results.append(d)
    return results


def get_top_reddit_posts(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch highest-scoring Reddit posts from the DB."""
    sql = """
        SELECT title, subreddit, category, score, comments, permalink, fetched_at
        FROM reddit_posts
        ORDER BY score DESC
        LIMIT ?
    """
    with _conn() as con:
        rows = con.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_top_keywords_from_db(days: int = 7, limit: int = 40) -> List[Dict[str, Any]]:
    """
    Aggregate keyword counts from the snapshots taken in the last N days.
    Returns the top keywords by total accumulated count.
    """
    sql = """
        SELECT keyword, SUM(count) AS total
        FROM   keyword_snapshots
        WHERE  snapshot_at >= datetime('now', ?)
        GROUP  BY keyword
        ORDER  BY total DESC
        LIMIT  ?
    """
    with _conn() as con:
        rows = con.execute(sql, (f'-{days} days', limit)).fetchall()
    return [{'word': r['keyword'], 'count': r['total']} for r in rows]


# ── API User Management ───────────────────────────────────────────────────────

def create_api_user(email: str, api_key: str, plan: str = 'free') -> Optional[Dict[str, Any]]:
    """Register a new API user. Returns user dict or None on duplicate email."""
    daily_limit = {'free': 100, 'pro': 5000, 'enterprise': 0}.get(plan, 100)
    sql = """
        INSERT INTO api_users (email, api_key, plan, daily_limit)
        VALUES (?, ?, ?, ?)
    """
    try:
        with _lock, _conn() as con:
            con.execute(sql, (email.lower().strip(), api_key, plan, daily_limit))
        return {'email': email, 'api_key': api_key, 'plan': plan, 'daily_limit': daily_limit}
    except Exception:
        return None


def get_api_user_by_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Look up a user by their API key."""
    sql = 'SELECT * FROM api_users WHERE api_key = ?'
    with _conn() as con:
        row = con.execute(sql, (api_key,)).fetchone()
    return dict(row) if row else None


def get_api_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Look up a user by email."""
    sql = 'SELECT * FROM api_users WHERE email = ?'
    with _conn() as con:
        row = con.execute(sql, (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def increment_api_user_usage(api_key: str) -> bool:
    """
    Increment request counter for the day.
    Resets counter if it's a new day.
    Returns True if allowed (under limit), False if quota exceeded.
    """
    user = get_api_user_by_key(api_key)
    if not user:
        return False

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    last_reset_str = user.get('last_reset', '')
    try:
        last_reset_date = last_reset_str[:10]
    except Exception:
        last_reset_date = ''

    if last_reset_date != today:
        # New day — reset counter
        with _lock, _conn() as con:
            con.execute(
                'UPDATE api_users SET requests_today=1, last_reset=?, last_used=? WHERE api_key=?',
                (now.isoformat()[:19] + 'Z', now.isoformat()[:19] + 'Z', api_key),
            )
        return True

    # Check limit (0 = unlimited for enterprise)
    daily_limit = user.get('daily_limit', 100)
    requests_today = user.get('requests_today', 0)
    if daily_limit > 0 and requests_today >= daily_limit:
        return False

    with _lock, _conn() as con:
        con.execute(
            'UPDATE api_users SET requests_today=requests_today+1, last_used=? WHERE api_key=?',
            (now.isoformat()[:19] + 'Z', api_key),
        )
    return True


def get_api_users_stats() -> Dict[str, Any]:
    """Summary stats about registered API users."""
    with _conn() as con:
        total = con.execute('SELECT COUNT(*) FROM api_users').fetchone()[0]
        by_plan = con.execute(
            'SELECT plan, COUNT(*) as cnt FROM api_users GROUP BY plan'
        ).fetchall()
    return {
        'total_users': total,
        'by_plan': {r['plan']: r['cnt'] for r in by_plan},
    }


# Initialise DB on import
init_db()
