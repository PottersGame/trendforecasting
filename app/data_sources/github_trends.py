"""GitHub trending repositories - uses the GitHub Search API (no auth needed for basic usage)."""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any
from app.utils import cache
from flask import current_app


GITHUB_API = 'https://api.github.com/search/repositories'


def get_trending_repos(language: str = '', period: str = 'weekly', limit: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch trending GitHub repositories.

    Args:
        language: Programming language filter (e.g., 'python', 'javascript')
        period: 'daily', 'weekly', or 'monthly'
        limit: Number of repos to return
    """
    cache_key = f'github_trending_{language}_{period}_{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Calculate date range
    days_map = {'daily': 1, 'weekly': 7, 'monthly': 30}
    days = days_map.get(period, 7)
    since_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    query = f'created:>{since_date}'
    if language:
        query += f' language:{language}'

    params = {
        'q': query,
        'sort': 'stars',
        'order': 'desc',
        'per_page': limit,
    }

    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'TrendForecasting/1.0',
    }

    try:
        # Use token if available
        token = current_app.config.get('GITHUB_TOKEN', '')
        if token:
            headers['Authorization'] = f'token {token}'

        r = requests.get(GITHUB_API, params=params, headers=headers, timeout=10)

        if r.status_code == 200:
            data = r.json()
            repos = []
            for repo in data.get('items', []):
                repos.append({
                    'name': repo.get('full_name', ''),
                    'description': repo.get('description', '') or 'No description',
                    'stars': repo.get('stargazers_count', 0),
                    'forks': repo.get('forks_count', 0),
                    'language': repo.get('language', 'Unknown'),
                    'url': repo.get('html_url', ''),
                    'created_at': repo.get('created_at', ''),
                    'topics': repo.get('topics', []),
                    'watchers': repo.get('watchers_count', 0),
                    'open_issues': repo.get('open_issues_count', 0),
                    'source': 'GitHub',
                })
            cache.set(cache_key, repos, ttl=600)
            return repos

    except Exception:
        pass

    return []


def get_language_stats(period: str = 'weekly') -> Dict[str, int]:
    """Get trending programming languages."""
    cache_key = f'github_langs_{period}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    languages = ['python', 'javascript', 'typescript', 'go', 'rust', 'java', 'c++', 'kotlin', 'swift', 'ruby']
    lang_counts = {}

    for lang in languages:
        repos = get_trending_repos(language=lang, period=period, limit=10)
        lang_counts[lang] = sum(r['stars'] for r in repos)

    cache.set(cache_key, lang_counts, ttl=600)
    return lang_counts


def get_topic_trends(topics: List[str], period: str = 'weekly') -> List[Dict[str, Any]]:
    """Get trending repos for specific topics."""
    cache_key = f'github_topics_{"-".join(sorted(topics))}_{period}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    days_map = {'daily': 1, 'weekly': 7, 'monthly': 30}
    days = days_map.get(period, 7)
    since_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    results = []
    for topic in topics[:5]:  # Limit to avoid rate limits
        query = f'topic:{topic} created:>{since_date}'
        params = {
            'q': query,
            'sort': 'stars',
            'order': 'desc',
            'per_page': 5,
        }
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'TrendForecasting/1.0',
        }
        try:
            r = requests.get(GITHUB_API, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for repo in data.get('items', []):
                    results.append({
                        'name': repo.get('full_name', ''),
                        'description': repo.get('description', '') or '',
                        'stars': repo.get('stargazers_count', 0),
                        'language': repo.get('language', 'Unknown'),
                        'url': repo.get('html_url', ''),
                        'topic': topic,
                        'source': 'GitHub',
                    })
        except Exception:
            pass

    cache.set(cache_key, results, ttl=600)
    return results
