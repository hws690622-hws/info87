'use strict';
const $ = (id) => document.getElementById(id);
const labels = {task:'待办', note:'笔记', link:'链接'};
let entries = [], filter = 'all', editing = null, editKind = 'task', toastTimer;

function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6000);
}
async function api(path, method = 'GET', body, headers = {}) {
  const options = {method, headers:{'X-Workbench':'1', ...headers}, credentials:'same-origin'};
  if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || '操作未完成，请稍后重试。'); error.status = response.status; throw error;
  }
  return data;
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function connection(ok) {
  $('connection-dot').classList.toggle('online', ok);
  $('connection-text').textContent = ok ? '已同步 · ' + new Date().toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'}) : '连接中断，请刷新重试';
}
function showWorkspace(active) {
  $('login-screen').hidden = active; $('workspace').hidden = !active;
  if (!active) { entries = []; render(); $('password').value = ''; }
}
async function refresh() {
  try { entries = await api('/api/entries'); render(); connection(true); }
  catch (error) { connection(false); if (error.status === 401) toast('登录已过期，请保留未保存的文字，退出后重新登录。'); else toast('暂时无法连接。当前页面已保留，请检查网络后刷新。'); }
}
function localDay() {
  const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
function render() {
  ['all','task','note','link'].forEach(kind => { $('count-'+kind).textContent = String(entries.filter(item => kind === 'all' || item.kind === kind).length); });
  $('stat-tasks').textContent = String(entries.filter(item => item.kind === 'task' && !item.completed).length);
  $('stat-notes').textContent = String(entries.filter(item => item.kind === 'note').length);
  $('stat-links').textContent = String(entries.filter(item => item.kind === 'link').length);
  const term = $('search').value.toLocaleLowerCase().trim();
  const shown = entries.filter(item => (filter === 'all' || item.kind === filter) && [item.title,item.content,item.url].some(text => text.toLocaleLowerCase().includes(term)));
  $('result-count').textContent = `${shown.length} 条内容`;
  $('entries').replaceChildren(...shown.map(card));
  $('empty').hidden = shown.length !== 0;
  $('empty-title').textContent = term ? '还没有找到相关内容' : '从一件小事开始';
  $('empty-text').textContent = term ? '换个关键词试试，或者清空搜索看看全部内容。' : '写下一个待办、记一段想法，或收藏一个常用网站。';
}
function card(item) {
  const article = element('article', 'entry' + (item.completed ? ' done' : ''));
  const head = element('div', 'entry-head');
  head.append(element('span', 'type-label type-'+item.kind, labels[item.kind]));
  const actions = element('div', 'entry-actions');
  const edit = element('button', 'icon-button', '✎'); edit.setAttribute('aria-label', `编辑${item.title}`); edit.title = '编辑'; edit.onclick = () => openEditor(item.kind, item);
  const remove = element('button', 'icon-button', '×'); remove.setAttribute('aria-label', `删除${item.title}`); remove.title = '删除';
  remove.onclick = async () => {
    if (!confirm(`确定删除「${item.title}」吗？此操作无法撤销。`)) return;
    remove.disabled = true;
    try { await api('/api/entries/'+item.id, 'DELETE', {}, {'If-Match':String(item.version)}); await refresh(); toast('已删除'); }
    catch (error) { toast(error.message); remove.disabled = false; }
  };
  actions.append(edit,remove); head.append(actions); article.append(head);
  const body = element('div','entry-body');
  if (item.kind === 'task') {
    const check = element('input'); check.type = 'checkbox'; check.checked = item.completed; check.setAttribute('aria-label', `完成${item.title}`);
    check.onchange = async () => {
      check.disabled = true;
      try { await api('/api/entries/'+item.id, 'PATCH', {version:item.version,completed:check.checked}); await refresh(); }
      catch (error) { check.checked = item.completed; check.disabled = false; toast(error.message); }
    };
    body.append(check);
  }
  const text = element('div'); const title = element('h3');
  if (item.kind === 'link') {
    const anchor = element('a', '', item.title); anchor.href = item.url; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; title.append(anchor);
    text.append(title, element('span','entry-url',item.url));
  } else { title.textContent = item.title; text.append(title); }
  if (item.content) text.append(element('p','entry-content',item.content));
  body.append(text); article.append(body);
  const footer = element('div','entry-footer');
  const due = element('span', 'due'+(item.due_date && item.due_date < localDay() && !item.completed ? ' overdue' : ''), item.kind === 'task' ? (item.completed ? '✓ 已完成' : item.due_date ? '截止 '+item.due_date : '未设置截止日期') : '随时回来看看');
  footer.append(due, element('span','',new Date(item.updated_at).toLocaleDateString('zh-CN',{month:'short',day:'numeric'})+' 更新'));
  article.append(footer); return article;
}
function openEditor(kind, item = null) {
  editing = item; editKind = kind;
  $('editor-title').textContent = (item ? '编辑' : '新建') + labels[kind];
  $('entry-title').value = item?.title || ''; $('entry-content').value = item?.content || '';
  $('entry-url').value = item?.url || ''; $('entry-date').value = item?.due_date || '';
  $('content-field').hidden = kind === 'link'; $('url-field').hidden = kind !== 'link'; $('date-field').hidden = kind !== 'task';
  $('entry-url').required = kind === 'link'; $('editor-error').textContent = '';
  $('editor').showModal(); $('entry-title').focus();
}
function closeEditor() {
  const changed = $('entry-title').value !== (editing?.title || '') || $('entry-content').value !== (editing?.content || '') || $('entry-url').value !== (editing?.url || '') || $('entry-date').value !== (editing?.due_date || '');
  if (!changed || confirm('内容尚未保存，确定关闭吗？')) $('editor').close();
}
$('editor').addEventListener('cancel', event => { event.preventDefault(); closeEditor(); });
$('close-editor').onclick = closeEditor; $('cancel-editor').onclick = closeEditor;
$('entry-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; $('editor-error').textContent = '';
  const body = {kind:editKind,title:$('entry-title').value,content:$('entry-content').value,url:$('entry-url').value,due_date:$('entry-date').value};
  if (editing) body.version = editing.version;
  try { await api(editing ? '/api/entries/'+editing.id : '/api/entries', editing ? 'PATCH':'POST', body); $('editor').close(); await refresh(); toast('已保存到工作台'); }
  catch (error) { $('editor-error').textContent = error.message; }
  finally { button.disabled = false; }
};
$('login-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; $('login-error').textContent = '';
  try { await api('/api/login','POST',{password:$('password').value}); $('password').value = ''; showWorkspace(true); await refresh(); }
  catch (error) { $('login-error').textContent = error.message; }
  finally { button.disabled = false; }
};
$('logout').onclick = async () => {
  try { await api('/api/logout','POST',{}); showWorkspace(false); }
  catch (error) { toast(error.message); }
};
document.querySelectorAll('[data-create]').forEach(button => { button.onclick = () => openEditor(button.dataset.create); });
document.querySelectorAll('[data-filter]').forEach(button => { button.onclick = () => {
  filter = button.dataset.filter; $('section-heading').textContent = {all:'我的内容',task:'待办事项',note:'工作笔记',link:'常用链接'}[filter];
  document.querySelectorAll('[data-filter]').forEach(other => { const active = other === button; other.classList.toggle('active',active); other.setAttribute('aria-pressed',String(active)); }); render();
}; });
$('search').oninput = render; $('refresh').onclick = refresh;
$('today').textContent = new Date().toLocaleDateString('zh-CN', {year:'numeric',month:'long',day:'numeric',weekday:'long'});
document.addEventListener('visibilitychange', () => { if (!document.hidden && !$('workspace').hidden) refresh(); });
setInterval(() => { if (!document.hidden && !$('workspace').hidden) refresh(); }, 30000);
(async () => {
  try { const state = await api('/api/session'); showWorkspace(state.authenticated); if (state.authenticated) await refresh(); }
  catch { $('login-error').textContent = '暂时无法连接服务，请稍后刷新重试。'; }
})();
