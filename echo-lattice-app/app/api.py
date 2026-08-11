from flask import Blueprint, current_app, jsonify, request, session
import json
import pathlib
import sqlite3
import secrets
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode
from functools import wraps

bp = Blueprint('api', __name__, url_prefix='/api')

# Paths - compute relative to this file to avoid current_app usage at import time
# file layout: <root>/digital-products-store/echo-lattice-app/app/api.py
BASE_DIR = pathlib.Path(__file__).resolve().parents[2]
PRODUCTS_PATH = BASE_DIR / 'digital-products-store' / 'digital-products-store' / 'data' / 'products.json'
DB_DIR = BASE_DIR / 'data'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'users.db'

# init_db should be invoked from the application factory via init_app(app)

# Config flags (safe defaults for dev)
ALLOW_REGISTRATION = os.environ.get('ALLOW_REGISTRATION', '1') == '1'
# Disable auto-create-by-login by default for safety in production
ALLOW_AUTO_REGISTER = os.environ.get('ALLOW_AUTO_REGISTER', '0') == '1'
# Rate limiting defaults
RATE_LIMIT_MAX = int(os.environ.get('RATE_LIMIT_MAX', '5'))
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', '60'))

# Simple in-memory rate limiter: { key: [timestamps...] }
_rate_limiter = {}


def _rate_limited(key, max_requests=RATE_LIMIT_MAX, window=RATE_LIMIT_WINDOW):
    now = datetime.utcnow().timestamp()
    arr = _rate_limiter.get(key, [])
    # Filter to window
    arr = [t for t in arr if now - t < window]
    arr.append(now)
    _rate_limiter[key] = arr
    return len(arr) > max_requests


def rate_limit_endpoint(max_requests=RATE_LIMIT_MAX, window=RATE_LIMIT_WINDOW):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Use remote IP and endpoint name as key. If running behind a trusted proxy,
            # consider using X-Forwarded-For or configure Flask's ProxyFix in the app factory.
            try:
                ip = request.remote_addr or 'anon'
            except Exception:
                ip = 'anon'
            key = f"rl:{ip}:{fn.__name__}"
            if _rate_limited(key, max_requests, window):
                return jsonify({'error': 'rate_limited', 'message': 'Too many requests, slow down.'}), 429
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def _load_products():
    try:
        with open(PRODUCTS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _get_db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_db_conn()
    try:
        # Create users table with optional remember token columns for "remember me" functionality
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                country TEXT,
                created_at TEXT,
                remember_token_hash TEXT,
                remember_token_expires TEXT
            );
        ''')
        conn.commit()

        # Ensure columns exist for older DBs: add columns if missing
        cur = conn.execute("PRAGMA table_info('users')")
        cols = [row['name'] for row in cur.fetchall()]
        if 'remember_token_hash' not in cols:
            try:
                conn.execute("ALTER TABLE users ADD COLUMN remember_token_hash TEXT")
            except Exception:
                pass
        if 'remember_token_expires' not in cols:
            try:
                conn.execute("ALTER TABLE users ADD COLUMN remember_token_expires TEXT")
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()



def init_app(app):
    """Initialize module using the Flask application context.
    Call this from the application factory (create_app) before registering the blueprint.
    This sets up DB path overrides if provided via app.config and ensures the DB schema exists.
    """
    global DB_PATH, DB_DIR
    # Allow overriding the DB path from app config (useful for tests)
    cfg_db = app.config.get('DATABASE') or app.config.get('DB_PATH')
    if cfg_db:
        DB_PATH = pathlib.Path(cfg_db)
        DB_DIR = DB_PATH.parent
        DB_DIR.mkdir(parents=True, exist_ok=True)
    # Run DB initialization now that the app context/config is available
    init_db()


def _set_remember_token_for_user(user_id, days_valid=30):
    # generate a secure random token, store a hash and expiry in DB, and return the raw token
    token = secrets.token_urlsafe(32)
    token_hash = generate_password_hash(token)
    expires = (datetime.utcnow() + timedelta(days=days_valid)).isoformat()
    conn = _get_db_conn()
    try:
        conn.execute('UPDATE users SET remember_token_hash = ?, remember_token_expires = ? WHERE id = ?', (token_hash, expires, user_id))
        conn.commit()
    finally:
        conn.close()
    return token


def _clear_remember_token_for_user(user_id):
    conn = _get_db_conn()
    try:
        conn.execute('UPDATE users SET remember_token_hash = NULL, remember_token_expires = NULL WHERE id = ?', (user_id,))
        conn.commit()
    finally:
        conn.close()


def _get_user_by_remember_token(token):
    # Iterate users and compare token hash (acceptable for small dev DB). Check expiry.
    if not token:
        return None
    conn = _get_db_conn()
    try:
        cur = conn.execute('SELECT id, email, password_hash, country, created_at, remember_token_hash, remember_token_expires FROM users')
        rows = cur.fetchall()
        for row in rows:
            r = dict(row)
            if not r.get('remember_token_hash'):
                continue
            try:
                if check_password_hash(r['remember_token_hash'], token):
                    # check expiry
                    exp = r.get('remember_token_expires')
                    if exp:
                        try:
                            exp_dt = datetime.fromisoformat(exp)
                            if datetime.utcnow() > exp_dt:
                                continue
                        except Exception:
                            # if parse fails, accept (conservative)
                            pass
                    return {'id': r['id'], 'email': r['email'], 'country': r.get('country'), 'created_at': r.get('created_at')}
            except Exception:
                continue
        return None
    finally:
        conn.close()


def create_user(email, password, country='US'):
    pw_hash = generate_password_hash(password)
    conn = _get_db_conn()
    try:
        cur = conn.execute('INSERT INTO users (email, password_hash, country, created_at) VALUES (?, ?, ?, ?)',
                           (email, pw_hash, country, datetime.utcnow().isoformat()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    conn = _get_db_conn()
    try:
        cur = conn.execute('SELECT id, email, password_hash, country, created_at, remember_token_hash, remember_token_expires FROM users WHERE email = ?', (email,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


@bp.route('/products', methods=['GET'])
def get_products():
    products = _load_products()
    return jsonify(products)


@bp.route('/register', methods=['POST'])
@rate_limit_endpoint()
def api_register():
    if not ALLOW_REGISTRATION:
        return jsonify({'error': 'registration_disabled'}), 403
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    country = data.get('country') or 'US'
    # Default to remembering the user automatically unless explicitly set to false
    remember = True if 'remember' not in data else bool(data.get('remember', False))
    if not email or not password:
        return jsonify({'error': 'email_and_password_required'}), 400
    existing = get_user_by_email(email)
    if existing:
        return jsonify({'error': 'email_taken'}), 400
    try:
        uid = create_user(email, password, country)
        # Set session and CSRF token
        session['user'] = {'id': uid, 'email': email, 'country': country}
        session['csrf_token'] = secrets.token_urlsafe(32)
        session.modified = True
        resp = jsonify({'ok': True, 'user': session['user'], 'csrf_token': session['csrf_token']})
        # Optionally set remember-me cookie
        if remember:
            try:
                token = _set_remember_token_for_user(uid)
                resp.set_cookie('remember_token', token, httponly=True, samesite=current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'), secure=current_app.config.get('SESSION_COOKIE_SECURE', False), max_age=30*24*3600)
            except Exception:
                current_app.logger.exception('failed to set remember token')
        return resp
    except Exception as e:
        current_app.logger.exception('register failed')
        return jsonify({'error': 'registration_failed', 'message': str(e)}), 500


@bp.route('/login', methods=['POST'])
@rate_limit_endpoint()
def api_login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    country = data.get('country') or 'US'
    # Default to remembering the user automatically unless explicitly set to false
    remember = True if 'remember' not in data else bool(data.get('remember', False))
    if not email or not password:
        return jsonify({'error': 'email_and_password_required'}), 400

    user = get_user_by_email(email)
    if not user:
        if ALLOW_AUTO_REGISTER:
            # Create user automatically for developer convenience
            try:
                uid = create_user(email, password, country)
                user = {'id': uid, 'email': email, 'country': country}
            except Exception:
                return jsonify({'error': 'user_create_failed'}), 500
        else:
            return jsonify({'error': 'invalid_credentials'}), 401
    else:
        if not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'invalid_credentials'}), 401

    # Successful login: set session and CSRF token
    session['user'] = {'id': user['id'], 'email': user['email'], 'country': user.get('country', country)}
    session['csrf_token'] = secrets.token_urlsafe(32)
    session.modified = True
    resp = jsonify({'ok': True, 'user': session['user'], 'csrf_token': session['csrf_token']})

    # Set remember cookie if requested
    if remember:
        try:
            token = _set_remember_token_for_user(user['id'])
            resp.set_cookie('remember_token', token, httponly=True, samesite=current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'), secure=current_app.config.get('SESSION_COOKIE_SECURE', False), max_age=30*24*3600)
        except Exception:
            current_app.logger.exception('failed to set remember token')
    return resp


@bp.route('/logout', methods=['POST'])
def api_logout():
    # Clear server-side session
    uid = None
    if 'user' in session:
        uid = session['user'].get('id')
    session.pop('user', None)
    session.pop('csrf_token', None)
    session.modified = True

    # Clear remember token on server and cookie
    resp = jsonify({'ok': True})
    try:
        if uid:
            _clear_remember_token_for_user(uid)
    except Exception:
        current_app.logger.exception('failed to clear remember token')
    # Remove cookie by setting max_age=0
    resp.set_cookie('remember_token', '', max_age=0, httponly=True, samesite=current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'), secure=current_app.config.get('SESSION_COOKIE_SECURE', False))
    return resp


@bp.route('/user', methods=['GET'])
def api_user():
    if 'user' not in session:
        return jsonify({'error': 'not_authenticated'}), 401
    return jsonify({'user': session['user']})


@bp.route('/restore', methods=['GET'])
def api_restore():
    # Try to restore session from remember_token cookie if session is absent
    if 'user' in session:
        return jsonify({'user': session['user'], 'csrf_token': session.get('csrf_token')})
    token = request.cookies.get('remember_token')
    if not token:
        return jsonify({'error': 'no_restore_token'}), 401
    try:
        user = _get_user_by_remember_token(token)
        if not user:
            return jsonify({'error': 'invalid_restore_token'}), 401
        # set session
        session['user'] = {'id': user['id'], 'email': user['email'], 'country': user.get('country', 'US')}
        session['csrf_token'] = secrets.token_urlsafe(32)
        session.modified = True
        resp = jsonify({'user': session['user'], 'csrf_token': session['csrf_token']})
        # refresh cookie expiry by re-setting it
        try:
            resp.set_cookie('remember_token', token, httponly=True, samesite=current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'), secure=current_app.config.get('SESSION_COOKIE_SECURE', False), max_age=30*24*3600)
        except Exception:
            pass
        return resp
    except Exception:
        current_app.logger.exception('restore failed')
        return jsonify({'error': 'restore_failed'}), 500


# --- Social login endpoints (Google and Facebook) ---
@bp.route('/auth/google')
def auth_google():
    # Start Google OAuth flow or return instructions if not configured
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT') or (request.host_url.rstrip('/') + '/api/auth/google/callback')
    scope = 'openid email profile'
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    if not client_id or not os.environ.get('GOOGLE_CLIENT_SECRET'):
        return jsonify({'error': 'google_not_configured', 'message': 'Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in environment and restart server to enable Google login.'}), 501
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': scope,
        'state': state,
        'access_type': 'offline',
        'prompt': 'select_account'
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)
    return current_app.redirect(auth_url)


@bp.route('/auth/google/callback')
def auth_google_callback():
    # Handle Google callback, exchange code for token and get userinfo
    code = request.args.get('code')
    state = request.args.get('state')
    saved_state = session.pop('oauth_state', None)
    if state != saved_state:
        return jsonify({'error': 'invalid_state'}), 400
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT') or (request.host_url.rstrip('/') + '/api/auth/google/callback')
    if not client_id or not client_secret:
        return jsonify({'error': 'google_not_configured'}), 501
    # Exchange code
    token_url = 'https://oauth2.googleapis.com/token'
    data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    try:
        tok_res = requests.post(token_url, data=data, timeout=10)
        tok_res.raise_for_status()
        tok = tok_res.json()
        access_token = tok.get('access_token')
        if not access_token:
            return jsonify({'error': 'token_exchange_failed', 'details': tok}), 400
        # fetch userinfo
        userinfo_res = requests.get('https://www.googleapis.com/oauth2/v3/userinfo', headers={'Authorization': 'Bearer ' + access_token}, timeout=10)
        userinfo_res.raise_for_status()
        info = userinfo_res.json()
        email = info.get('email')
        if not email:
            return jsonify({'error': 'email_required'}), 400
        # find or create user
        user = get_user_by_email(email)
        if not user:
            # create with random password since OAuth used
            uid = create_user(email, secrets.token_urlsafe(16), info.get('locale', 'US'))
            user = {'id': uid, 'email': email, 'country': info.get('locale', 'US')}
        # Set session and remember token by default
        session['user'] = {'id': user['id'], 'email': user['email'], 'country': user.get('country', 'US')}
        session['csrf_token'] = secrets.token_urlsafe(32)
        session.modified = True
        resp = current_app.redirect('/')
        # set remember token
        try:
            token = _set_remember_token_for_user(user['id'])
            resp.set_cookie('remember_token', token, httponly=True, samesite=current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'), secure=current_app.config.get('SESSION_COOKIE_SECURE', False), max_age=30*24*3600)
        except Exception:
            current_app.logger.exception('failed to set remember token on oauth login')
        return resp
    except Exception as e:
        current_app.logger.exception('google oauth failed')
        return jsonify({'error': 'google_oauth_failed', 'message': str(e)}), 500


@bp.route('/auth/facebook')
def auth_facebook():
    client_id = os.environ.get('FACEBOOK_CLIENT_ID')
    redirect_uri = os.environ.get('FACEBOOK_REDIRECT') or (request.host_url.rstrip('/') + '/api/auth/facebook/callback')
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    if not client_id or not os.environ.get('FACEBOOK_CLIENT_SECRET'):
        return jsonify({'error': 'facebook_not_configured', 'message': 'Set FACEBOOK_CLIENT_ID and FACEBOOK_CLIENT_SECRET in environment and restart server to enable Facebook login.'}), 501
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'state': state,
        'scope': 'email,public_profile'
    }
    auth_url = 'https://www.facebook.com/v11.0/dialog/oauth?' + urlencode(params)
    return current_app.redirect(auth_url)


@bp.route('/auth/facebook/callback')
def auth_facebook_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    saved_state = session.pop('oauth_state', None)
    if state != saved_state:
        return jsonify({'error': 'invalid_state'}), 400
    client_id = os.environ.get('FACEBOOK_CLIENT_ID')
    client_secret = os.environ.get('FACEBOOK_CLIENT_SECRET')
    redirect_uri = os.environ.get('FACEBOOK_REDIRECT') or (request.host_url.rstrip('/') + '/api/auth/facebook/callback')
    if not client_id or not client_secret:
        return jsonify({'error': 'facebook_not_configured'}), 501
    token_url = 'https://graph.facebook.com/v11.0/oauth/access_token'
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'code': code
    }
    try:
        tok_res = requests.get(token_url, params=params, timeout=10)
        tok_res.raise_for_status()
        tok = tok_res.json()
        access_token = tok.get('access_token')
        if not access_token:
            return jsonify({'error': 'token_exchange_failed', 'details': tok}), 400
        # fetch user info
        userinfo_res = requests.get('https://graph.facebook.com/me', params={'fields': 'id,name,email', 'access_token': access_token}, timeout=10)
        userinfo_res.raise_for_status()
        info = userinfo_res.json()
        email = info.get('email')
        if not email:
            return jsonify({'error': 'email_required'}), 400
        user = get_user_by_email(email)
        if not user:
            uid = create_user(email, secrets.token_urlsafe(16), 'US')
            user = {'id': uid, 'email': email, 'country': 'US'}
        session['user'] = {'id': user['id'], 'email': user['email'], 'country': user.get('country', 'US')}
        session['csrf_token'] = secrets.token_urlsafe(32)
        session.modified = True
        resp = current_app.redirect('/')
        try:
            token = _set_remember_token_for_user(user['id'])
            resp.set_cookie('remember_token', token, httponly=True, samesite=current_app.config.get('SESSION_COOKIE_SAMESITE', 'Lax'), secure=current_app.config.get('SESSION_COOKIE_SECURE', False), max_age=30*24*3600)
        except Exception:
            current_app.logger.exception('failed to set remember token on oauth login')
        return resp
    except Exception as e:
        current_app.logger.exception('facebook oauth failed')
        return jsonify({'error': 'facebook_oauth_failed', 'message': str(e)}), 500


@bp.route('/cart', methods=['GET', 'POST', 'DELETE'])
def api_cart():
    if 'cart' not in session:
        session['cart'] = []
    if request.method == 'GET':
        products = _load_products()
        cart_items = [p for p in products if p.get('id') in session['cart']]
        return jsonify({'items': cart_items})

    if request.method == 'POST':
        # Require CSRF for state-changing operations
        header_token = request.headers.get('X-CSRF-Token')
        if 'csrf_token' not in session or not header_token or header_token != session['csrf_token']:
            return jsonify({'error': 'invalid_csrf'}), 403
        data = request.get_json() or {}
        pid = data.get('productId')
        if pid is None:
            return jsonify({'error': 'productId required'}), 400
        if pid not in session['cart']:
            session['cart'].append(pid)
            session.modified = True
        return jsonify({'cart': session['cart']})

    # DELETE expects ?productId=123
    if request.method == 'DELETE':
        header_token = request.headers.get('X-CSRF-Token')
        if 'csrf_token' not in session or not header_token or header_token != session['csrf_token']:
            return jsonify({'error': 'invalid_csrf'}), 403
        pid = request.args.get('productId', type=int)
        if pid is None:
            return jsonify({'error': 'productId required'}), 400
        if pid in session['cart']:
            session['cart'].remove(pid)
            session.modified = True
        return jsonify({'cart': session['cart']})


@bp.route('/checkout', methods=['POST'])
def api_checkout():
    # Payment processing is NOT implemented in this demo.
    # For security, refuse to process payments unless explicitly running in demo mode.
    data = request.get_json() or {}
    demo_mode = bool(data.get('demo', False))
    if not demo_mode:
        return jsonify({'error': 'payments_not_configured', 'message': 'Payment processing is not configured on this server. Integrate a payment gateway (Stripe, PayPal, etc.) on the server side before enabling real payments.'}), 501
    # Demo behavior: clear cart to simulate checkout
    session.pop('cart', None)
    session.modified = True
    return jsonify({'ok': True, 'demo': True})