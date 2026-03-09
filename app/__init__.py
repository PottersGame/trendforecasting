"""Flask application factory."""

from flask import Flask
from flask_cors import CORS
from config import Config


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app)

    from app.api.routes import api_bp
    app.register_blueprint(api_bp)

    from app.views import views_bp
    app.register_blueprint(views_bp)

    return app
