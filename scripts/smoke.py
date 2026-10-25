"""Live HTTP readiness check. Uses existing local credentials without printing them."""
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

base = os.environ.get('WORKBENCH_TEST_URL', 'http://127.0.0.1:8000')
directory = Path(os.environ.get('WORKBENCH_DATA_DIR', Path(__file__).resolve().parents[1] / '.data'))
password = os.environ.get('WORKBENCH_PASSWORD')
if password is None:
    password = (directory / 'password.txt').read_text().strip()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, method='GET', data=None, extra=None):
    headers = {'X-Workbench':'1', **(extra or {})}
    if data is not None:
        data = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    with opener.open(req, timeout=10) as response:
        return json.load(response)


assert call('/healthz')['status'] == 'ok'
try:
    call('/api/entries')
    raise AssertionError('Private records accessible without authentication')
except urllib.error.HTTPError as error:
    assert error.code == 401
assert call('/api/login', 'POST', {'password':password})['ok']
original = call('/api/entries')
entry = call('/api/entries', 'POST', {'kind':'task', 'title':'临时就绪验证'})
try:
    updated = call('/api/entries/' + str(entry['id']), 'PATCH', {'version':entry['version'], 'completed':True})
    assert updated['completed']
    assert any(item['id'] == entry['id'] for item in call('/api/entries'))
finally:
    latest = next(item for item in call('/api/entries') if item['id'] == entry['id'])
    assert call('/api/entries/' + str(entry['id']), 'DELETE', {}, {'If-Match':str(latest['version'])})['ok']
assert len(call('/api/entries')) == len(original)
assert call('/api/logout', 'POST', {})['ok']
print('PASS: database health, login protection, authenticated create/read/update/delete and logout')
