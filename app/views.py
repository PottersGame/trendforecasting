"""Views blueprint for serving HTML pages."""

import secrets as _secrets
from functools import wraps

from flask import (
    Blueprint, render_template, redirect, url_for,
    request, session, flash,
)
from werkzeug.security import generate_password_hash, check_password_hash

views_bp = Blueprint('views', __name__)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('views.login', next=request.path))
        return f(*args, **kwargs)
    return decorated


def _admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id') or not session.get('is_admin'):
            return redirect(url_for('views.login', next=request.path))
        return f(*args, **kwargs)
    return decorated


# ── Public pages ──────────────────────────────────────────────────────────────

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


# ── Auth pages ────────────────────────────────────────────────────────────────

@views_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration page."""
    if session.get('user_id'):
        return redirect(url_for('views.account'))

    error = None
    if request.method == 'POST':
        import app.database as db
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        if not email or '@' not in email:
            error = 'A valid email address is required.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        else:
            existing = db.get_api_user_by_email(email)
            if existing:
                error = 'An account with this email already exists. Please log in.'
            else:
                pw_hash = generate_password_hash(password)
                api_key = 'rw_' + _secrets.token_urlsafe(32)
                user = db.create_api_user(
                    email, api_key, plan='free',
                    password_hash=pw_hash, is_admin=False,
                )
                if user:
                    session['user_id'] = email
                    session['is_admin'] = False
                    return redirect(url_for('views.account'))
                error = 'Registration failed. Please try again.'

    return render_template('signup.html', error=error)


@views_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login page."""
    if session.get('user_id'):
        return redirect(url_for('views.account'))

    error = None
    raw_next = request.args.get('next', '')
    # Validate next URL: must be a relative path starting with '/' and not '//'
    next_url = raw_next if (raw_next.startswith('/') and not raw_next.startswith('//')) else url_for('views.account')

    if request.method == 'POST':
        import app.database as db
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = db.get_api_user_by_email(email)
        if not user or not user.get('password_hash'):
            error = 'Invalid email or password.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'Invalid email or password.'
        else:
            session.clear()
            session['user_id']  = user['email']
            session['is_admin'] = bool(user.get('is_admin'))
            return redirect(next_url or url_for('views.account'))

    return render_template('login.html', error=error, next=next_url)


@views_bp.route('/logout')
def logout():
    """Clear session and redirect to landing."""
    session.clear()
    return redirect(url_for('views.landing'))


@views_bp.route('/account')
@_login_required
def account():
    """Logged-in user's account / API key management page."""
    import app.database as db
    user = db.get_api_user_by_email(session['user_id'])
    return render_template('keys.html', user=user)


# ── Admin console ─────────────────────────────────────────────────────────────

@views_bp.route('/admin')
@_admin_required
def admin_console():
    """Admin dashboard — manage users and API keys."""
    import app.database as db
    users = db.list_all_users()
    stats = db.get_api_users_stats()
    return render_template('admin.html', users=users, stats=stats)


@views_bp.route('/admin/update-plan', methods=['POST'])
@_admin_required
def admin_update_plan():
    """Admin action: change a user's plan."""
    import app.database as db
    user_id = int(request.form.get('user_id', 0))
    plan    = request.form.get('plan', 'free')
    if user_id:
        db.update_user_plan(user_id, plan)
    return redirect(url_for('views.admin_console'))


@views_bp.route('/admin/set-admin', methods=['POST'])
@_admin_required
def admin_set_admin():
    """Admin action: grant or revoke admin flag."""
    import app.database as db
    user_id  = int(request.form.get('user_id', 0))
    is_admin = request.form.get('is_admin') == '1'
    if user_id:
        db.set_user_admin(user_id, is_admin)
    return redirect(url_for('views.admin_console'))


@views_bp.route('/admin/delete-user', methods=['POST'])
@_admin_required
def admin_delete_user():
    """Admin action: delete a user."""
    import app.database as db
    user_id = int(request.form.get('user_id', 0))
    if user_id:
        db.delete_user(user_id)
    return redirect(url_for('views.admin_console'))
