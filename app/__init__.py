"""Flask application factory."""

import os
from flask import Flask
from flask_cors import CORS
from config import Config

# Resolve root-level template and static directories
_ROOT = os.path.dirname(os.path.dirname(__file__))
_TEMPLATES = os.path.join(_ROOT, 'templates')
_STATIC    = os.path.join(_ROOT, 'static')


def _start_scheduler(app: Flask) -> None:
    """Start a background APScheduler job that ingests data periodically.

    Controlled by the ``SCRAPE_INTERVAL_MINUTES`` config value (0 = off).
    Does nothing when APScheduler is not installed.
    """
    interval = app.config.get('SCRAPE_INTERVAL_MINUTES', 0)
    if not interval or interval <= 0:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        app.logger.warning(
            'APScheduler not installed; automatic ingestion is disabled. '
            'Run: pip install APScheduler'
        )
        return

    def _ingest_job() -> None:
        # Import lazily to avoid circular-import issues at module load time.
        with app.app_context():
            try:
                from app.api.routes import _ingest_all  # noqa: PLC0415
                result = _ingest_all()
                app.logger.info('Scheduled ingest completed: %s', result)
            except Exception as exc:  # noqa: BLE001
                app.logger.exception('Scheduled ingest failed: %s', exc)

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(_ingest_job, 'interval', minutes=interval, id='auto_ingest')
    scheduler.start()
    app.logger.info(
        'Background scheduler started — ingesting every %d minutes.', interval
    )


def _bootstrap_admin(app: Flask) -> None:
    """Create the initial admin user if ADMIN_EMAIL and ADMIN_PASSWORD are set."""
    email    = app.config.get('ADMIN_EMAIL', '').strip()
    password = app.config.get('ADMIN_PASSWORD', '').strip()
    if not email or not password:
        return

    with app.app_context():
        try:
            import secrets as _secrets
            from werkzeug.security import generate_password_hash
            from app.database import get_api_user_by_email, create_api_user
            if get_api_user_by_email(email):
                return  # already exists — don't overwrite
            pw_hash = generate_password_hash(password)
            api_key = 'rw_' + _secrets.token_urlsafe(32)
            create_api_user(
                email, api_key, plan='enterprise',
                password_hash=pw_hash, is_admin=True,
            )
            app.logger.info('Admin account created for %s', email)
        except Exception as exc:
            app.logger.exception('Failed to bootstrap admin account: %s', exc)


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=_TEMPLATES,
        static_folder=_STATIC,
    )
    app.config.from_object(config_class)

    # Harden session cookie for production
    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config.setdefault('SESSION_COOKIE_SAMESITE', 'Lax')
    # Mark the session cookie as Secure when not in debug mode so it is only
    # sent over HTTPS in production deployments.
    if not app.config.get('DEBUG'):
        app.config.setdefault('SESSION_COOKIE_SECURE', True)

    CORS(app)

    # Gzip/Brotli response compression for faster page loads
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass

    # Add basic security headers to every response
    @app.after_request
    def _add_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        return response

    from app.api.routes import api_bp
    app.register_blueprint(api_bp)

    from app.views import views_bp
    app.register_blueprint(views_bp)

    _start_scheduler(app)
    _bootstrap_admin(app)

    return app
