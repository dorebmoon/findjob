import os
import asyncio
import threading
import base64
import json
import ast
import time
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from models import db, User, PlatformCredential, Message, Cipher
from scrapers import get_scraper, SCRAPERS

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'

cipher = Cipher(Config.ENCRYPTION_KEY)

# Background scheduler for periodic message checking
scheduler = BackgroundScheduler()


def _encode_cookies(cookies) -> str:
    """Serialize cookies to JSON before encryption."""
    try:
        return json.dumps(cookies, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps([])


def _decode_cookies(encrypted: str):
    """Decrypt and parse cookie blob. Falls back to ast.literal_eval for legacy rows."""
    if not encrypted:
        return []
    try:
        raw = cipher.decrypt(encrypted)
    except Exception:
        return []
    # New format: JSON.
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        pass
    # Legacy format: repr(list[dict]). Use ast.literal_eval — never eval.
    try:
        data = ast.literal_eval(raw)
        return data if isinstance(data, (list, tuple)) else []
    except (ValueError, SyntaxError, TypeError):
        return []

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── Auth Routes ─────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not username or not password:
            flash('请填写完整信息', 'error')
        elif len(password) < 6:
            flash('密码至少6位', 'error')
        elif password != confirm:
            flash('两次密码不一致', 'error')
        elif User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
        else:
            user = User(
                username=username,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('dashboard'))
    
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    platforms = Config.PLATFORMS
    credentials = {c.platform: c for c in current_user.credentials}
    return render_template('dashboard.html', platforms=platforms, credentials=credentials)


# ─── API: Platform Credentials ───────────────────────────────────────────────

@app.route('/api/credentials', methods=['POST'])
@login_required
def save_credential():
    data = request.get_json()
    platform = data.get('platform')
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not platform or platform not in Config.PLATFORMS:
        return jsonify({'success': False, 'message': '无效的平台'}), 400
    
    if not username or not password:
        return jsonify({'success': False, 'message': '请填写账号和密码'}), 400
    
    cred = PlatformCredential.query.filter_by(
        user_id=current_user.id, platform=platform
    ).first()
    
    if cred:
        cred.username = cipher.encrypt(username)
        cred.password = cipher.encrypt(password)
        cred.is_logged_in = False
    else:
        cred = PlatformCredential(
            user_id=current_user.id,
            platform=platform,
            username=cipher.encrypt(username),
            password=cipher.encrypt(password)
        )
        db.session.add(cred)
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'{Config.PLATFORMS[platform]["name"]} 账号已保存'})


@app.route('/api/credentials/<platform>', methods=['DELETE'])
@login_required
def delete_credential(platform):
    cred = PlatformCredential.query.filter_by(
        user_id=current_user.id, platform=platform
    ).first()
    if cred:
        db.session.delete(cred)
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/credentials/status')
@login_required
def credential_status():
    creds = {}
    for c in current_user.credentials:
        creds[c.platform] = {
            'username': cipher.decrypt(c.username)[:3] + '***',
            'is_logged_in': c.is_logged_in,
            'last_login': c.last_login.isoformat() if c.last_login else None,
            'last_check': c.last_check.isoformat() if c.last_check else None
        }
    return jsonify(creds)


# ─── API: Login to Platforms ─────────────────────────────────────────────────

def run_async_in_thread(coro):
    """Run an async function in a new thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def do_platform_login(user_id: int, platform: str):
    """Perform login for a specific platform (runs in background thread)."""
    with app.app_context():
        cred = PlatformCredential.query.filter_by(
            user_id=user_id, platform=platform
        ).first()
        
        if not cred:
            return {'success': False, 'message': '未找到该平台的账号信息'}
        
        username = cipher.decrypt(cred.username)
        password = cipher.decrypt(cred.password)
        
        scraper = get_scraper(platform)
        
        async def _login():
            await scraper.start_browser(headless=False)
            try:
                page = await scraper._context.new_page()
                result = await scraper.login(username, password, page)
                
                if result.get('success'):
                    cred.is_logged_in = True
                    cred.last_login = datetime.utcnow()
                    if result.get('cookies'):
                        cred.cookie_data = cipher.encrypt(
                            _encode_cookies(result['cookies'])
                        )
                    db.session.commit()
                
                return result
            finally:
                await scraper.stop_browser()
        
        return run_async_in_thread(_login())


def do_login_all(user_id: int):
    """Login to all configured platforms for a user."""
    results = {}
    with app.app_context():
        creds = PlatformCredential.query.filter_by(user_id=user_id).all()
        platforms = [c.platform for c in creds]
    
    for platform in platforms:
        try:
            result = do_platform_login(user_id, platform)
            results[platform] = result
        except Exception as e:
            results[platform] = {'success': False, 'message': str(e)}
    
    return results


@app.route('/api/login/<platform>', methods=['POST'])
@login_required
def login_platform(platform):
    if platform not in Config.PLATFORMS:
        return jsonify({'success': False, 'message': '未知平台'}), 400
    
    cred = PlatformCredential.query.filter_by(
        user_id=current_user.id, platform=platform
    ).first()
    
    if not cred:
        return jsonify({'success': False, 'message': f'请先配置{Config.PLATFORMS[platform]["name"]}的账号密码'}), 400
    
    # Run login in background thread
    thread = threading.Thread(
        target=do_platform_login,
        args=(current_user.id, platform)
    )
    thread.start()
    
    return jsonify({
        'success': True,
        'message': f'正在登录 {Config.PLATFORMS[platform]["name"]}，请在弹出的浏览器窗口中完成操作...'
    })


@app.route('/api/login-all', methods=['POST'])
@login_required
def login_all():
    """Start login to all configured platforms."""
    creds = PlatformCredential.query.filter_by(user_id=current_user.id).all()
    
    if not creds:
        return jsonify({'success': False, 'message': '请先配置至少一个平台的账号密码'}), 400
    
    thread = threading.Thread(
        target=do_login_all,
        args=(current_user.id,)
    )
    thread.start()
    
    return jsonify({
        'success': True,
        'message': f'正在登录 {len(creds)} 个平台，请在弹出的浏览器窗口中完成操作...'
    })


# ─── API: Manual Login (Open Browser + Monitor) ──────────────────────────────

# Store manual login sessions: {user_id: {platform: {scraper, page, ...}}}
_manual_login_sessions = {}

def do_manual_login(user_id: int, platform: str):
    """Open persistent browser for manual login and monitor login status."""
    with app.app_context():
        scraper = get_scraper(platform)
        
        async def _login():
            # Use persistent context to save session/cookies to disk
            await scraper.start_browser(headless=False, persistent=True)
            try:
                page = await scraper._context.new_page()
                result = await scraper.open_login_page(page)
                
                # Store session for polling and confirm
                if user_id not in _manual_login_sessions:
                    _manual_login_sessions[user_id] = {}
                _manual_login_sessions[user_id][platform] = {
                    'page': page,
                    'scraper': scraper,
                    'open_result': result,
                    'login_success': False,
                    'login_timeout': False,
                    'confirm_requested': False,
                    'confirm_result': None,  # None | 'pending' | 'ok' | 'fail'
                    'done': False
                }
                
                if not result.get('success'):
                    await scraper.stop_browser()
                    return result
                
                # Poll for login status for up to 180 seconds.
                # We watch three signals, none of which disturbs the user's tab:
                #   1. The user's tab URL leaves the login/passport page
                #      (strongest signal for SMS/QR/CAPTCHA login)
                #   2. Platform auth cookies are issued
                #   3. The user clicks "I've completed login" → full probe on a
                #      NEW page (never on the user's active tab)
                for i in range(90):
                    await asyncio.sleep(2)

                    # Bail out if user closed the browser.
                    try:
                        if page.is_closed():
                            break
                    except Exception:
                        break

                    session = _manual_login_sessions.get(user_id, {}).get(platform, {})

                    # (1) URL-based detection on the user's tab (read-only).
                    url_ok = False
                    try:
                        current_url = page.url
                        if current_url and not scraper.is_login_url(current_url):
                            # They navigated away from the login page on their own.
                            url_ok = True
                    except Exception:
                        pass

                    # (2) Cookie-based detection.
                    try:
                        cookie_ok = await scraper.check_login_by_cookies()
                    except Exception:
                        cookie_ok = False

                    is_logged_in = url_ok or cookie_ok

                    # (3) Explicit user confirmation — probe on a fresh page.
                    if not is_logged_in and session.get('confirm_requested'):
                        _manual_login_sessions[user_id][platform]['confirm_result'] = 'pending'
                        probe = None
                        try:
                            probe = await scraper._context.new_page()
                            is_logged_in = await scraper.check_login_status(probe)
                        except Exception:
                            is_logged_in = False
                        finally:
                            if probe is not None:
                                try:
                                    await probe.close()
                                except Exception:
                                    pass
                        if not is_logged_in:
                            # Reset flag so user can try again later.
                            _manual_login_sessions[user_id][platform]['confirm_requested'] = False
                            _manual_login_sessions[user_id][platform]['confirm_result'] = 'fail'
                        else:
                            _manual_login_sessions[user_id][platform]['confirm_result'] = 'ok'
                    
                    if is_logged_in:
                        _save_login(user_id, platform)
                        _manual_login_sessions[user_id][platform]['login_success'] = True
                        _manual_login_sessions[user_id][platform]['done'] = True
                        # Give the browser a moment to persist cookies to disk
                        # before we close the context.
                        await asyncio.sleep(3)
                        try:
                            await scraper.stop_browser()
                        except Exception:
                            pass
                        if user_id in _manual_login_sessions and platform in _manual_login_sessions[user_id]:
                            del _manual_login_sessions[user_id][platform]
                        return {'success': True, 'message': '登录成功'}

                # Timeout
                if user_id in _manual_login_sessions and platform in _manual_login_sessions[user_id]:
                    _manual_login_sessions[user_id][platform]['login_timeout'] = True
                await scraper.stop_browser()
                if user_id in _manual_login_sessions and platform in _manual_login_sessions[user_id]:
                    del _manual_login_sessions[user_id][platform]
                return {'success': False, 'message': '登录超时'}
                    
            except Exception as e:
                try:
                    await scraper.stop_browser()
                except Exception:
                    pass
                if user_id in _manual_login_sessions and platform in _manual_login_sessions[user_id]:
                    del _manual_login_sessions[user_id][platform]
                return {'success': False, 'message': str(e)}
        
        return run_async_in_thread(_login())


def _save_login(user_id: int, platform: str):
    """Save login status to DB."""
    with app.app_context():
        cred = PlatformCredential.query.filter_by(
            user_id=user_id, platform=platform
        ).first()
        if not cred:
            cred = PlatformCredential(
                user_id=user_id,
                platform=platform,
                username=cipher.encrypt('manual_login'),
                password=cipher.encrypt('manual_login')
            )
            db.session.add(cred)
        cred.is_logged_in = True
        cred.last_login = datetime.utcnow()
        db.session.commit()


def do_manual_login_confirm(user_id: int, platform: str):
    """
    User clicked 'I've completed login'.
    Non-blocking: just signals the polling loop (or spawns a background probe
    if no session). The frontend keeps polling /status for the real result.
    """
    session = _manual_login_sessions.get(user_id, {}).get(platform)
    if session and not session.get('done'):
        # Nudge the polling loop to do a full page-based check on its next tick.
        session['confirm_requested'] = True
        session['confirm_result'] = 'pending'
        return {'success': True, 'message': '正在检测登录状态，请稍候...', 'async': True}

    # No active session — spin up a one-shot background probe. The frontend
    # polls /status which falls back to credential.is_logged_in for the result.
    def _background_probe():
        with app.app_context():
            scraper = get_scraper(platform)

            async def _check():
                # Open with persistent profile so we reuse the saved cookies.
                # Must be headless=False — Boss/Zhilian/Liepin flag headless and
                # redirect to login, which would falsely report "not logged in".
                await scraper.start_browser(headless=False, persistent=True)
                try:
                    if await scraper.check_login_by_cookies():
                        _save_login(user_id, platform)
                        return
                    probe = await scraper._context.new_page()
                    if await scraper.check_login_status(probe):
                        _save_login(user_id, platform)
                finally:
                    try:
                        await scraper.stop_browser()
                    except Exception:
                        pass

            run_async_in_thread(_check())

    threading.Thread(target=_background_probe, daemon=True).start()
    return {'success': True, 'message': '正在后台检测登录状态，请稍候...', 'async': True}


@app.route('/api/manual-login/<platform>', methods=['POST'])
@login_required
def manual_login_start(platform):
    """Open browser for manual login."""
    if platform not in Config.PLATFORMS:
        return jsonify({'success': False, 'message': '未知平台'}), 400
    
    thread = threading.Thread(
        target=do_manual_login,
        args=(current_user.id, platform)
    )
    thread.start()

    # Wait for browser to open
    time.sleep(5)
    
    session = _manual_login_sessions.get(current_user.id, {}).get(platform)
    if session and session.get('open_result', {}).get('success'):
        return jsonify({
            'success': True,
            'message': f'浏览器已打开 {Config.PLATFORMS[platform]["name"]} 登录页，请手动完成登录操作'
        })
    else:
        return jsonify({
            'success': False,
            'message': '打开浏览器失败，请重试'
        })


@app.route('/api/manual-login/<platform>/status', methods=['GET'])
@login_required
def manual_login_status(platform):
    """Check if manual login has been completed (auto-detected)."""
    if platform not in Config.PLATFORMS:
        return jsonify({'success': False, 'message': '未知平台'}), 400
    
    cred = PlatformCredential.query.filter_by(
        user_id=current_user.id, platform=platform
    ).first()
    
    is_logged_in = cred.is_logged_in if cred else False
    session_active = platform in _manual_login_sessions.get(current_user.id, {})
    session_data = _manual_login_sessions.get(current_user.id, {}).get(platform, {})

    confirm_result = session_data.get('confirm_result')
    confirm_pending = confirm_result == 'pending'
    confirm_failed = confirm_result == 'fail'

    if is_logged_in:
        msg = '登录成功'
    elif confirm_pending:
        msg = '正在检测登录状态...'
    elif confirm_failed:
        msg = '未检测到登录状态，请确认已在浏览器中完成登录'
    else:
        msg = '请在浏览器中完成操作...'

    return jsonify({
        'is_logged_in': is_logged_in,
        'session_active': session_active,
        'login_success': session_data.get('login_success', False),
        'login_timeout': session_data.get('login_timeout', False),
        'confirm_result': confirm_result,
        'message': msg
    })


@app.route('/api/manual-login/<platform>/confirm', methods=['POST'])
@login_required
def manual_login_confirm(platform):
    """
    User confirms they've logged in. Returns immediately; the real check
    runs in the existing manual-login polling loop (or in a one-shot
    background thread if no session is active). The client continues to
    poll /api/manual-login/<platform>/status for the outcome.
    """
    if platform not in Config.PLATFORMS:
        return jsonify({'success': False, 'message': '未知平台'}), 400

    result = do_manual_login_confirm(current_user.id, platform)
    return jsonify({
        'success': True,
        'async': True,
        'message': result.get('message', '正在检测登录状态...')
    })


# ─── API: Messages ───────────────────────────────────────────────────────────

def fetch_platform_messages(user_id: int, platform: str):
    """Fetch messages from a specific platform using persistent browser profile."""
    with app.app_context():
        cred = PlatformCredential.query.filter_by(
            user_id=user_id, platform=platform
        ).first()
        
        if not cred or not cred.is_logged_in:
            return []
        
        scraper = get_scraper(platform)
        
        async def _fetch():
            # Use non-headless + persistent context to reuse the saved login
            # session. Boss直聘 / 智联 / 猎聘 actively detect headless browsers
            # and redirect to login, which would wipe out a perfectly valid
            # session and incorrectly flip is_logged_in to False.
            await scraper.start_browser(headless=False, persistent=True)
            try:
                # Cheap offline check — don't navigate before we need to.
                cookie_ok = await scraper.check_login_by_cookies()

                if not cookie_ok:
                    # Fall back to stored cookies if available, but keep a
                    # conservative stance: don't immediately invalidate the
                    # credential on transient failures.
                    if cred.cookie_data:
                        try:
                            cookies = _decode_cookies(cred.cookie_data)
                            if cookies:
                                await scraper.load_cookies(cookies)
                                cookie_ok = await scraper.check_login_by_cookies()
                        except Exception:
                            pass

                page = await scraper._context.new_page()

                # A real UI/URL probe — but only if cookies look missing.
                if not cookie_ok:
                    try:
                        is_logged_in = await scraper.check_login_status(page)
                    except Exception:
                        is_logged_in = False

                    if not is_logged_in:
                        # Only flag the credential as logged-out if we also
                        # have zero auth cookies; that avoids flapping on
                        # temporary network/UI hiccups.
                        try:
                            cookies_now = await scraper.get_cookies()
                        except Exception:
                            cookies_now = []
                        if not cookies_now:
                            cred.is_logged_in = False
                            db.session.commit()
                        return []

                return await scraper.fetch_messages(page)
            finally:
                await scraper.stop_browser()
        
        return run_async_in_thread(_fetch())


def refresh_messages(user_id: int):
    """Refresh messages from all logged-in platforms."""
    with app.app_context():
        creds = PlatformCredential.query.filter_by(
            user_id=user_id, is_logged_in=True
        ).all()
    
    all_messages = []
    for cred in creds:
        try:
            msgs = fetch_platform_messages(user_id, cred.platform)
            for msg_data in msgs:
                msg = Message(
                    user_id=user_id,
                    platform=cred.platform,
                    sender_name=msg_data.get('sender_name', ''),
                    sender_company=msg_data.get('sender_company', ''),
                    content=msg_data.get('content', ''),
                    job_title=msg_data.get('job_title', ''),
                    salary_range=msg_data.get('salary_range', ''),
                    message_type=msg_data.get('message_type', 'chat'),
                    external_url=msg_data.get('external_url', ''),
                    received_at=datetime.fromisoformat(msg_data['received_at']) if msg_data.get('received_at') else datetime.utcnow()
                )
                db.session.add(msg)
                all_messages.append(msg_data)
            
            cred.last_check = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            print(f"Error fetching messages from {cred.platform}: {e}")
    
    return all_messages


@app.route('/api/messages')
@login_required
def get_messages():
    """Get all messages for current user."""
    platform = request.args.get('platform')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    query = Message.query.filter_by(user_id=current_user.id)
    
    if platform:
        query = query.filter_by(platform=platform)
    
    query = query.order_by(Message.received_at.desc())
    total = query.count()
    messages = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return jsonify({
        'messages': [{
            'id': m.id,
            'platform': m.platform,
            'platform_name': Config.PLATFORMS.get(m.platform, {}).get('name', m.platform),
            'platform_icon': Config.PLATFORMS.get(m.platform, {}).get('icon', '💼'),
            'platform_color': Config.PLATFORMS.get(m.platform, {}).get('color', '#666'),
            'sender_name': m.sender_name,
            'sender_company': m.sender_company,
            'content': m.content,
            'job_title': m.job_title,
            'salary_range': m.salary_range,
            'message_type': m.message_type,
            'is_read': m.is_read,
            'external_url': m.external_url,
            'received_at': m.received_at.isoformat() if m.received_at else None
        } for m in messages],
        'total': total,
        'page': page,
        'per_page': per_page
    })


@app.route('/api/messages/refresh', methods=['POST'])
@login_required
def refresh_all_messages():
    """Trigger message refresh from all platforms."""
    thread = threading.Thread(
        target=refresh_messages,
        args=(current_user.id,)
    )
    thread.start()
    return jsonify({'success': True, 'message': '正在刷新消息...'})


@app.route('/api/messages/<int:message_id>/read', methods=['POST'])
@login_required
def mark_message_read(message_id):
    """Mark a message as read."""
    msg = Message.query.filter_by(id=message_id, user_id=current_user.id).first()
    if msg:
        msg.is_read = True
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/messages/stats')
@login_required
def message_stats():
    """Get message statistics."""
    total = Message.query.filter_by(user_id=current_user.id).count()
    unread = Message.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    by_platform = {}
    for platform_key, platform_info in Config.PLATFORMS.items():
        count = Message.query.filter_by(
            user_id=current_user.id, platform=platform_key
        ).count()
        unread_count = Message.query.filter_by(
            user_id=current_user.id, platform=platform_key, is_read=False
        ).count()
        if count > 0:
            by_platform[platform_key] = {
                'name': platform_info['name'],
                'icon': platform_info['icon'],
                'total': count,
                'unread': unread_count
            }
    
    return jsonify({
        'total': total,
        'unread': unread,
        'by_platform': by_platform
    })


# ─── Platform Info API ───────────────────────────────────────────────────────

@app.route('/api/platforms')
@login_required
def get_platforms():
    """Get all platform info."""
    creds = {c.platform: c for c in current_user.credentials}
    platforms = []
    for key, info in Config.PLATFORMS.items():
        cred = creds.get(key)
        platforms.append({
            'key': key,
            'name': info['name'],
            'url': info['url'],
            'icon': info['icon'],
            'color': info['color'],
            'has_credential': cred is not None,
            'is_logged_in': cred.is_logged_in if cred else False,
            'last_login': cred.last_login.isoformat() if cred and cred.last_login else None,
            'username_preview': cipher.decrypt(cred.username)[:3] + '***' if cred else None
        })
    return jsonify(platforms)


# ─── Initialize DB ───────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

# ─── Demo Data ───────────────────────────────────────────────────────────────

@app.route('/api/demo-data', methods=['POST'])
@login_required
def load_demo_data():
    """Load demo messages for testing the UI."""
    demo_messages = [
        {
            'platform': 'boss',
            'sender_name': '李女士',
            'sender_company': '阿里巴巴',
            'sender_title': 'HR经理',
            'content': '您好，看到您的简历非常符合我们的Python开发工程师岗位，方便聊一下吗？',
            'job_title': 'Python高级开发工程师',
            'salary_range': '25K-40K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'boss',
            'sender_name': '王先生',
            'sender_company': '字节跳动',
            'sender_title': '技术主管',
            'content': '我们团队正在扩招全栈工程师，对您的经历很感兴趣，能否安排一次面试？',
            'job_title': '全栈工程师',
            'salary_range': '30K-50K',
            'message_type': 'invite',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'zhilian',
            'sender_name': '张经理',
            'sender_company': '腾讯科技',
            'sender_title': '招聘经理',
            'content': '您的简历通过了初筛，请问您近期是否有换工作的打算？',
            'job_title': '后端开发工程师',
            'salary_range': '28K-45K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'zhilian',
            'sender_name': '刘女士',
            'sender_company': '美团',
            'sender_title': 'HR',
            'content': '我们提供有竞争力的薪酬和福利，工作地点在北京，感兴趣吗？',
            'job_title': 'Java开发工程师',
            'salary_range': '25K-35K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'qiancheng',
            'sender_name': '陈先生',
            'sender_company': '华为技术',
            'sender_title': '项目经理',
            'content': '华为云部门正在招聘高级工程师，您的经验非常匹配，期待您的回复。',
            'job_title': '高级云平台工程师',
            'salary_range': '35K-55K',
            'message_type': 'invite',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'qiancheng',
            'sender_name': '赵女士',
            'sender_company': '小米科技',
            'sender_title': '人事专员',
            'content': '您好，小米IoT部门诚邀您加入我们的技术团队。',
            'job_title': 'IoT平台开发',
            'salary_range': '20K-35K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'tongcheng',
            'sender_name': '孙经理',
            'sender_company': '京东集团',
            'sender_title': 'HRBP',
            'content': '京东物流技术部正在招人，看了您的条件很合适，方便详谈吗？',
            'job_title': '物流系统开发工程师',
            'salary_range': '22K-38K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'tongcheng',
            'sender_name': '系统通知',
            'sender_company': '58同城',
            'content': '您的简历被 12 家企业浏览，3 家企业向您发出面试邀请。',
            'job_title': '',
            'salary_range': '',
            'message_type': 'system',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'yupao',
            'sender_name': '周先生',
            'sender_company': '网易',
            'sender_title': '技术总监',
            'content': '网易有道团队很期待像您这样的人才加入，我们的项目非常有前景。',
            'job_title': '算法工程师',
            'salary_range': '30K-50K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'liepin',
            'sender_name': '吴女士',
            'sender_company': '微软中国',
            'sender_title': 'Talent Acquisition',
            'content': 'Microsoft Azure team is hiring senior engineers. Your profile looks great for this role!',
            'job_title': 'Senior Software Engineer',
            'salary_range': '40K-70K',
            'message_type': 'invite',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'liepin',
            'sender_name': '黄先生',
            'sender_company': '蚂蚁集团',
            'sender_title': '招聘专家',
            'content': '蚂蚁金服技术团队期待您的加入，我们提供行业内顶尖的薪酬待遇。',
            'job_title': '区块链技术专家',
            'salary_range': '50K-80K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
        {
            'platform': 'boss',
            'sender_name': '马女士',
            'sender_company': '百度',
            'sender_title': 'HR',
            'content': '百度AI部门正在招募优秀人才，您的技术栈非常契合我们的需求。',
            'job_title': 'AI工程师',
            'salary_range': '30K-50K',
            'message_type': 'chat',
            'received_at': datetime.utcnow()
        },
    ]
    
    for msg_data in demo_messages:
        msg = Message(
            user_id=current_user.id,
            platform=msg_data['platform'],
            sender_name=msg_data['sender_name'],
            sender_company=msg_data['sender_company'],
            content=msg_data['content'],
            job_title=msg_data['job_title'],
            salary_range=msg_data['salary_range'],
            message_type=msg_data['message_type'],
            received_at=msg_data['received_at']
        )
        db.session.add(msg)
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'已加载 {len(demo_messages)} 条演示消息'})


if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
