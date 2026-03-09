"""Views blueprint for serving HTML pages."""

from flask import Blueprint, render_template, redirect, url_for

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def landing():
    """Serve the marketing landing page."""
    return render_template('landing.html')


@views_bp.route('/dashboard')
def dashboard():
    """Serve the main analysis dashboard."""
    return render_template('index.html')


@views_bp.route('/keys')
def keys_portal():
    """Serve the API key registration / management portal."""
    return render_template('keys.html')
