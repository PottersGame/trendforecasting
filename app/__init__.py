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


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=_TEMPLATES,
        static_folder=_STATIC,
    )
    app.config.from_object(config_class)

    CORS(app)

    # Gzip/Brotli response compression for faster page loads
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass

    from app.api.routes import api_bp
    app.register_blueprint(api_bp)

    from app.views import views_bp
    app.register_blueprint(views_bp)

    _start_scheduler(app)

    return app
