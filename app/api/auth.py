"""Simple API-key authentication for protected endpoints.

Protected endpoints require a valid APP_API_KEY (admin) or a registered
user API key to be sent with every request.

If APP_API_KEY is not configured the server runs in open development mode
and all endpoints are accessible without a key.

Pass the key in one of two ways:
    Authorization: Bearer <key>
    X-API-Key: <key>
"""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request, current_app


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
        expected = current_app.config.get('APP_API_KEY', '').strip()
        if not expected:
            # No admin key configured — open (dev) mode; skip auth check.
            return f(*args, **kwargs)

        token = _extract_token()

        if not token:
            return _unauthorized()

        # 1) Check admin (env) key
        if token == expected:
            return f(*args, **kwargs)

        # 2) Check registered user keys in the database
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

        return _unauthorized()

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
