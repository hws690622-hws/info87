import json
import tempfile
import unittest
import os
import subprocess
import sys
from pathlib import Path

from app import create_app


class WorkbenchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app(Path(self.tmp.name), password='a-test-password-long-enough')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def send(self, method, path, data=None, client=None, **kwargs):
        return (client or self.client).open(path, method=method, json=data,
                                          headers={'X-Workbench': '1', **kwargs})

    def login(self, client=None):
        return self.send('POST', '/api/login', {'password': 'a-test-password-long-enough'}, client)

    def add(self, **extra):
        return self.send('POST', '/api/entries', {'kind': 'task', 'title': '写工作总结', **extra})

    def test_private_records_require_login_and_logout_revokes_access(self):
        for path in ['/api/entries', '/api/export']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get('/api/entries').get_json(), [])
        self.assertEqual(self.send('POST', '/api/logout', {}).status_code, 200)
        self.assertEqual(self.client.get('/api/entries').status_code, 401)

    def test_login_rejects_wrong_password_and_rate_limits(self):
        for _ in range(10):
            self.assertEqual(self.send('POST', '/api/login', {'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_mutations_require_same_origin_json_header(self):
        self.assertEqual(self.client.post('/api/login', json={'password': 'x'}).status_code, 403)
        self.assertEqual(self.send('POST', '/api/login', {}, Origin='https://evil.example').status_code, 403)
        self.assertEqual(self.send('POST', '/api/login', []).status_code, 400)

    def test_create_update_complete_export_and_delete(self):
        self.login()
        task = self.add(due_date='2026-10-26').get_json()
        self.assertEqual(task['title'], '写工作总结')
        self.assertEqual(task['version'], 1)
        done = self.send('PATCH', f"/api/entries/{task['id']}", {'version': 1, 'completed': True})
        self.assertEqual(done.status_code, 200)
        self.assertTrue(done.get_json()['completed'])
        self.assertEqual(done.get_json()['version'], 2)
        note = self.add(kind='note', title='会议笔记', content='<script>private</script>').get_json()
        link = self.add(kind='link', title='文档', url='https://example.com/docs').get_json()
        export = self.client.get('/api/export')
        self.assertEqual(export.status_code, 200)
        self.assertEqual(len(export.get_json()['entries']), 3)
        self.assertIn('attachment', export.headers['Content-Disposition'])
        self.assertEqual(self.send('DELETE', f"/api/entries/{task['id']}", {}, **{'If-Match':'2'}).status_code, 200)
        self.assertEqual(len(self.client.get('/api/entries').get_json()), 2)

    def test_other_device_sees_data_and_cannot_overwrite_newer_version(self):
        self.login()
        task = self.add().get_json()
        second = self.app.test_client()
        self.login(second)
        self.assertEqual(second.get('/api/entries').get_json()[0]['title'], '写工作总结')
        path = f"/api/entries/{task['id']}"
        self.assertEqual(self.send('PATCH', path, {'version':1, 'title':'新版'}).status_code, 200)
        self.assertEqual(self.send('PATCH', path, {'version':1, 'title':'旧版'}, second).status_code, 409)
        self.assertEqual(self.send('DELETE', path, {}, second, **{'If-Match':'1'}).status_code, 409)
        self.assertEqual(second.get('/api/entries').get_json()[0]['title'], '新版')

    def test_invalid_records_do_not_change_storage(self):
        self.login()
        for extra in [{'title':''}, {'kind':'other'}, {'due_date':'2026-02-30'},
                      {'kind':'link','url':'javascript:alert(1)'}, {'completed':'false'},
                      {'kind':'link','url':'https://user:pass@example.com'}, {'title':'x'*161}]:
            with self.subTest(extra=extra):
                self.assertEqual(self.add(**extra).status_code, 400)
        self.assertEqual(self.client.get('/api/entries').get_json(), [])
        self.assertEqual(self.send('PATCH', '/api/entries/999', {'version':1}).status_code, 404)

    def test_restart_keeps_data_and_password(self):
        self.login()
        self.add(kind='note', content='办公室和家里共用')
        restarted = create_app(Path(self.tmp.name)).test_client()
        self.assertEqual(self.login(restarted).status_code, 200)
        self.assertEqual(restarted.get('/api/entries').get_json()[0]['content'], '办公室和家里共用')

    def test_generated_password_and_state_stay_private(self):
        other = Path(self.tmp.name) / 'fresh'
        fresh = create_app(other).test_client()
        password = (other / 'password.txt').read_text().strip()
        self.assertGreaterEqual(len(password), 24)
        self.assertEqual((other / 'password.txt').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.send('POST', '/api/login', {'password':password}, fresh).status_code, 200)
        self.assertEqual(fresh.get('/.data/password.txt').status_code, 404)

    def test_login_cookie_does_not_disclose_password_hash(self):
        self.login()
        cookie = self.client.get_cookie('session')
        payload = self.app.session_interface.get_signing_serializer(self.app).loads(cookie.value)
        self.assertNotIn('scrypt:', json.dumps(payload))
        self.assertNotEqual(payload.get('auth'), self.app.extensions['store'].setting('password_hash'))

    def test_password_change_invalidates_previous_login(self):
        self.login()
        create_app(Path(self.tmp.name), password='another-password-long-enough')
        self.assertEqual(self.client.get('/api/entries').status_code, 401)

    def test_https_proxy_can_submit_same_origin_requests(self):
        previous = os.environ.get('WORKBENCH_TRUST_PROXY')
        self.addCleanup(lambda: os.environ.pop('WORKBENCH_TRUST_PROXY', None) if previous is None else os.environ.__setitem__('WORKBENCH_TRUST_PROXY', previous))
        os.environ['WORKBENCH_TRUST_PROXY'] = '1'
        proxied = create_app(Path(self.tmp.name)).test_client()
        self.assertEqual(self.send('POST', '/api/login', {'password':'a-test-password-long-enough'}, proxied,
            Origin='https://localhost', **{'X-Forwarded-Proto':'https'}).status_code, 200)

    def test_live_backup_restores_records_and_has_private_permissions(self):
        self.login()
        self.add(title='备份中的记录')
        output = Path(self.tmp.name) / 'backup.sqlite3'
        env = {**os.environ, 'WORKBENCH_DATA_DIR':self.tmp.name}
        result = subprocess.run([sys.executable, 'app.py', 'backup', '--output', str(output)],
            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        import sqlite3
        with sqlite3.connect(output) as db:
            self.assertEqual(db.execute('SELECT title FROM entries').fetchone()[0], '备份中的记录')


if __name__ == '__main__':
    unittest.main()
