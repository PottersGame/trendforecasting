"""Flask application factory."""

import os
from flask import Flask
from flask_cors import CORS
from config import Config

# Resolve root-level template and static directories
_ROOT = os.path.dirname(os.path.dirname(__file__))
_TEMPLATES = os.path.join(_ROOT, 'templates')
_STATIC    = os.path.join(_ROOT, 'static')


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=_TEMPLATES,
        static_folder=_STATIC,
    )
    app.config.from_object(config_class)

    CORS(app)

    from app.api.routes import api_bp
    app.register_blueprint(api_bp)

    from app.views import views_bp
    app.register_blueprint(views_bp)

    return app
