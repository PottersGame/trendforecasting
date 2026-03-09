"""API-key authentication for protected endpoints.

Protected endpoints require a valid APP_API_KEY (admin) or a registered
user API key to be sent with every request.

Pass the key in one of two ways:
    Authorization: Bearer <key>
    X-API-Key: <key>
"""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request, current_app, session


def _extract_token() -> str:
    """Pull the bearer / X-API-Key token from the request headers."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
        if token:
            return token
    return request.headers.get('X-API-Key', '').strip()


def require_api_key(f):
    """Decorator: reject requests that don't carry a valid API key."""

    @wraps(f)
    def decorated(*args, **kwargs):
        admin_key = current_app.config.get('APP_API_KEY', '').strip()
        token = _extract_token()

        # 1) Check admin (env) key — always takes priority when configured
        if admin_key and token == admin_key:
            return f(*args, **kwargs)

        # 2) Check registered user keys in the database
        if token:
            try:
                from app.database import get_api_user_by_key, increment_api_user_usage
                user = get_api_user_by_key(token)
                if user:
                    allowed = increment_api_user_usage(token)
                    if not allowed:
                        return jsonify({
                            'error': 'Quota exceeded',
                            'message': (
                                'You have reached your daily request limit. '
                                'Upgrade your plan at /keys for a higher quota.'
                            ),
                        }), 429
                    return f(*args, **kwargs)
            except Exception:
                pass

        # 3) If no admin key is configured, allow through only when no DB users exist
        #    (fresh install / true dev mode with zero registered users)
        if not admin_key:
            try:
                from app.database import get_api_users_stats
                stats = get_api_users_stats()
                if stats.get('total_users', 0) == 0:
                    return f(*args, **kwargs)
            except Exception:
                return f(*args, **kwargs)

        return _unauthorized()

    return decorated


def require_admin(f):
    """Decorator: allow only logged-in admin users (session-based)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id') or not session.get('is_admin'):
            from flask import redirect, url_for
            # Pass the current path as a safe relative `next` parameter
            safe_next = request.path  # always a relative path starting with '/'
            return redirect(url_for('views.login', next=safe_next))
        return f(*args, **kwargs)

    return decorated


def _unauthorized():
    return jsonify({
        'error': 'Unauthorized',
        'message': (
            'A valid API key is required. '
            'Register for a free key at /keys or pass your key via '
            '"Authorization: Bearer <key>" or "X-API-Key: <key>" header.'
        ),
    }), 401
