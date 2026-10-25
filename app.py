"""日常工作台: one private workspace shared by your browsers."""
import argparse
import getpass
import hashlib
import json
import os
import secrets
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from storage import Store

ROOT = Path(__file__).resolve().parent


def write_private(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)


def validate(data):
    item = {'kind': 'task', 'title': '', 'content': '', 'url': '', 'due_date': '', 'completed': False, **data}
    if item['kind'] not in ('task', 'note', 'link'):
        raise ValueError('请选择待办、笔记或链接。')
    for key, limit in [('title', 160), ('content', 50000), ('url', 2048), ('due_date', 10)]:
        if not isinstance(item[key], str) or len(item[key]) > limit:
            raise ValueError('内容格式不正确或过长。')
    item['title'] = item['title'].strip()
    if not item['title']:
        raise ValueError('请填写标题。')
    if type(item['completed']) is not bool:
        raise ValueError('完成状态格式不正确。')
    if item['due_date']:
        try:
            if date.fromisoformat(item['due_date']).isoformat() != item['due_date']:
                raise ValueError()
        except ValueError:
            raise ValueError('请选择有效日期。') from None
    if item['kind'] == 'link':
        try:
            url = urlsplit(item['url'])
            url.port  # Access validates numeric port and its permitted range.
            valid = (url.scheme in ('http', 'https') and url.hostname and not url.username and not url.password
                     and not any(char.isspace() or ord(char) < 32 for char in url.netloc)
                     and '\\' not in url.netloc)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('请填写以 https:// 或 http:// 开头的网址，且不要包含密码。')
    return item


def create_app(data_dir=None, password=None):
    directory = Path(data_dir or os.environ.get('WORKBENCH_DATA_DIR', ROOT / '.data'))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    secret_path = directory / 'session.key'
    if not secret_path.exists():
        write_private(secret_path, secrets.token_hex(32))
    app = Flask(__name__)
    if os.environ.get('WORKBENCH_TRUST_PROXY') == '1':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    app.config.update(
        SECRET_KEY=secret_path.read_text().strip(),
        MAX_CONTENT_LENGTH=128 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=os.environ.get('WORKBENCH_SECURE_COOKIE') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    )
    store = Store(directory / 'workbench.sqlite3')
    (directory / 'workbench.sqlite3').chmod(0o600)
    app.extensions['store'] = store
    configured = password if password is not None else os.environ.get('WORKBENCH_PASSWORD')
    if configured is not None:
        if len(configured) < 12:
            raise ValueError('登录密码至少需要 12 个字符。')
        current = store.setting('password_hash')
        if not current or not check_password_hash(current, configured):
            store.setting('password_hash', generate_password_hash(configured))
    elif not store.setting('password_hash'):
        generated = secrets.token_urlsafe(24)
        write_private(directory / 'password.txt', generated + '\n')
        store.setting('password_hash', generate_password_hash(generated))

    def auth_version(password_hash):
        return hashlib.sha256(password_hash.encode()).hexdigest()

    def authenticated():
        return secrets.compare_digest(str(session.get('auth', '')), auth_version(store.setting('password_hash')))

    @app.before_request
    def protect():
        if request.path.startswith('/api/'):
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if request.headers.get('X-Workbench') != '1':
                    return jsonify(error='请求未通过安全检查，请刷新页面。'), 403
                origin = request.headers.get('Origin')
                if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
                    return jsonify(error='请从工作台页面提交操作。'), 403
                if not request.is_json:
                    return jsonify(error='需要 JSON 格式的请求。'), 400
                if not isinstance(request.get_json(), dict):
                    return jsonify(error='请求内容格式不正确。'), 400
            if request.path not in ('/api/login', '/api/logout', '/api/session') and not authenticated():
                return jsonify(error='请先登录。'), 401

    @app.after_request
    def headers(response):
        response.headers.update({
            'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error='请求无效或内容过大。' if error.code != 404 else '内容不存在。'), error.code

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/healthz')
    def health():
        with store.connect() as db:
            db.execute('SELECT 1 FROM entries LIMIT 1').fetchone()
        return jsonify(status='ok')

    @app.get('/api/session')
    def session_status():
        return jsonify(authenticated=authenticated())

    @app.post('/api/login')
    def login():
        supplied = request.get_json().get('password', '')
        if not isinstance(supplied, str) or len(supplied) > 1024:
            return jsonify(error='密码格式不正确。'), 400
        # BEGIN IMMEDIATE makes the shared rate limit atomic across concurrent requests.
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            limit = db.execute('SELECT * FROM login_limit WHERE id=1').fetchone()
            now = time.time()
            attempts = limit['attempts'] if limit and now - limit['since'] < 600 else 0
            since = limit['since'] if attempts else now
            if attempts >= 10:
                return jsonify(error='尝试次数过多，请在 10 分钟后重试。'), 429
            password_hash = db.execute("SELECT value FROM settings WHERE key='password_hash'").fetchone()['value']
            if not check_password_hash(password_hash, supplied):
                db.execute('INSERT OR REPLACE INTO login_limit VALUES (1,?,?)', (attempts + 1, since))
                return jsonify(error='密码不正确，请重试。'), 401
            db.execute('DELETE FROM login_limit')
        session.clear()
        session['auth'] = auth_version(password_hash)
        session.permanent = True
        return jsonify(ok=True)

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/entries')
    def listing():
        return jsonify(store.entries())

    @app.post('/api/entries')
    def add():
        try:
            item = validate(request.get_json())
        except ValueError as error:
            return jsonify(error=str(error)), 400
        return jsonify(store.add(item)), 201

    @app.route('/api/entries/<int:entry_id>', methods=['PATCH', 'DELETE'])
    def change(entry_id):
        current = store.get(entry_id)
        if not current:
            return jsonify(error='这条内容已不存在，请刷新。'), 404
        data = request.get_json()
        version = data.get('version') if request.method == 'PATCH' else request.headers.get('If-Match')
        try:
            if isinstance(version, bool) or str(int(version)) != str(version):
                raise ValueError()
            version = int(version)
        except (ValueError, TypeError):
            return jsonify(error='缺少有效的版本号，请刷新后重试。'), 400
        if request.method == 'DELETE':
            if store.delete(entry_id, version):
                return jsonify(ok=True)
        else:
            try:
                if 'kind' in data and data['kind'] != current['kind']:
                    raise ValueError('不能更改内容类型。')
                item = validate({**current, **data})
            except ValueError as error:
                return jsonify(error=str(error)), 400
            updated = store.update(entry_id, version, item)
            if updated:
                return jsonify(updated)
        return jsonify(error='另一台设备已修改这条内容。请保留当前文字，关闭编辑并刷新后重试。'), 409

    @app.get('/api/export')
    def export():
        response = jsonify(format='workbench-v1', exported_at=Store.now(), entries=store.entries())
        response.headers['Content-Disposition'] = 'attachment; filename="workbench-backup.json"'
        return response

    return app


def main():
    parser = argparse.ArgumentParser(description='日常工作台')
    parser.add_argument('command', nargs='?', choices=['serve', 'set-password', 'backup'], default='serve')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    parser.add_argument('--output', help='备份文件路径（仅 backup 命令）')
    args = parser.parse_args()
    if args.command == 'set-password':
        entered = getpass.getpass('设置密码（至少 12 位）: ')
        if entered != getpass.getpass('再次输入: '):
            parser.error('两次密码不一致。')
        create_app(password=entered)
        directory = Path(os.environ.get('WORKBENCH_DATA_DIR', ROOT / '.data'))
        (directory / 'password.txt').unlink(missing_ok=True)
        print('密码已更新，之前的登录会话已失效。')
    elif args.command == 'backup':
        if not args.output:
            parser.error('backup 需要 --output 指定新文件。')
        app = create_app()
        output = Path(args.output)
        write_private(output, '')
        try:
            with app.extensions['store'].connect() as source, sqlite3.connect(output) as target:
                source.backup(target)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        print('数据库备份已保存。')
    else:
        from waitress import serve
        app = create_app()
        print(f'日常工作台已启动，监听 {args.host}:{args.port}。', flush=True)
        proxy = {}
        if os.environ.get('WORKBENCH_TRUST_PROXY') == '1':
            # Enable only when access to this port is restricted to the trusted reverse proxy.
            proxy = {'trusted_proxy':'*', 'trusted_proxy_headers':{'x-forwarded-proto'}}
        serve(app, host=args.host, port=args.port, threads=4, max_request_body_size=128 * 1024, **proxy)


if __name__ == '__main__':
    main()
