"""Optional real-browser check: pip install playwright, then provision Chromium."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

base = os.environ.get('WORKBENCH_TEST_URL', 'http://127.0.0.1:8000')
data_dir = Path(os.environ.get('WORKBENCH_DATA_DIR', Path(__file__).resolve().parents[1] / '.data'))
password = (data_dir / 'password.txt').read_text().strip()


def cleanup(context):
    records = context.request.get(base + '/api/entries').json()
    for record in records:
        if record['title'].startswith('浏览器验证：') or record['title'] == '手机添加的事项':
            response = context.request.delete(base + f"/api/entries/{record['id']}",
                headers={'X-Workbench':'1', 'If-Match':str(record['version']), 'Content-Type':'application/json'}, data='{}')
            assert response.ok

with sync_playwright() as p:
    launch = {'headless': True}
    if os.environ.get('CHROMIUM_EXECUTABLE'):
        launch['executable_path'] = os.environ['CHROMIUM_EXECUTABLE']
    browser = p.chromium.launch(**launch)
    desktop = browser.new_context(viewport={'width':1440, 'height':1000})
    page = desktop.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    page.get_by_label('登录密码').fill(password)
    page.get_by_role('button', name='进入工作台').click()
    expect(page.get_by_role('heading', name='把今天，安排从容。')).to_be_visible()
    cleanup(desktop)
    page.reload()
    page.get_by_role('button', name='新建待办').click()
    page.get_by_label('标题', exact=True).fill('浏览器验证：准备周报')
    page.get_by_role('button', name='保存', exact=True).click()
    task = page.locator('.entry').filter(has_text='浏览器验证：准备周报')
    expect(task).to_be_visible()
    task.get_by_role('checkbox').check()
    expect(task.get_by_role('checkbox')).to_be_checked()
    page.get_by_role('button', name='新建笔记').click()
    page.get_by_label('标题', exact=True).fill('浏览器验证：会议笔记')
    page.get_by_label('内容', exact=True).fill('<img src=x onerror=alert(1)> 这段文字应安全显示')
    page.get_by_role('button', name='保存', exact=True).click()
    expect(page.get_by_text('<img src=x onerror=alert(1)> 这段文字应安全显示', exact=True)).to_be_visible()
    assert page.locator('.entries img').count() == 0
    page.get_by_role('button', name='新建链接').click()
    page.get_by_label('标题', exact=True).fill('浏览器验证：文档')
    page.get_by_label('网址').fill('https://example.com/docs')
    page.get_by_role('button', name='保存', exact=True).click()
    expect(page.get_by_role('link', name='浏览器验证：文档')).to_have_attribute('href', 'https://example.com/docs')
    page.reload()
    expect(page.get_by_text('浏览器验证：会议笔记', exact=True)).to_be_visible()
    page.get_by_label('搜索内容').fill('准备周报')
    expect(page.locator('.entry')).to_have_count(1)
    page.get_by_label('搜索内容').fill('')
    page.screenshot(path='/tmp/info87-desktop.png', full_page=True)

    mobile = browser.new_context(viewport={'width':390, 'height':844}, is_mobile=True, has_touch=True)
    phone = mobile.new_page()
    phone.goto(base)
    phone.get_by_label('登录密码').fill(password)
    phone.get_by_role('button', name='进入工作台').click()
    expect(phone.get_by_text('浏览器验证：会议笔记', exact=True)).to_be_visible()
    assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    phone.get_by_role('button', name='新建待办').click()
    phone.get_by_label('标题', exact=True).fill('手机添加的事项')
    phone.get_by_role('button', name='保存', exact=True).click()
    expect(phone.get_by_text('手机添加的事项', exact=True)).to_be_visible()
    phone.screenshot(path='/tmp/info87-mobile.png', full_page=True)
    page.reload()
    expect(page.get_by_text('手机添加的事项', exact=True)).to_be_visible()
    page.get_by_role('button', name='退出登录').click()
    expect(page.get_by_label('登录密码')).to_be_visible()
    assert not errors, errors

    # Remove only records created by this check, through the authenticated API.
    cleanup(mobile)
    browser.close()
    print('PASS: desktop/mobile login, CRUD, persistence, shared data, search, text safety and logout')
