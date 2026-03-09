"""Simple API-key authentication for protected endpoints.

Protected endpoints require a valid APP_API_KEY to be sent with every
request.  If APP_API_KEY is not configured the server runs in open
development mode and all endpoints are accessible without a key.

Pass the key in one of two ways:
    Authorization: Bearer <key>
    X-API-Key: <key>
"""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request, current_app


def require_api_key(f):
    """Decorator: reject requests that don't carry a valid APP_API_KEY."""

    @wraps(f)
    def decorated(*args, **kwargs):
        expected = current_app.config.get('APP_API_KEY', '').strip()
        if not expected:
            # No key configured — open (dev) mode; skip auth check.
            return f(*args, **kwargs)

        # Accept key via Authorization: Bearer <key>  OR  X-API-Key header.
        token = ''
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
        if not token:
            token = request.headers.get('X-API-Key', '').strip()

        if not token or token != expected:
            return jsonify({
                'error': 'Unauthorized',
                'message': (
                    'A valid API key is required to access this endpoint. '
                    'Pass it via the "Authorization: Bearer <key>" header '
                    'or "X-API-Key: <key>" header.'
                ),
            }), 401

        return f(*args, **kwargs)

    return decorated
