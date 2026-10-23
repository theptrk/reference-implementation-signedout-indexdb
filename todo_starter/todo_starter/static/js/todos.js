const root = document.querySelector('#todo-app');
const account = root.dataset.user;
const status = document.querySelector('#todo-status');
const list = document.querySelector('#todo-list');
const form = document.querySelector('#add-todo');
const retry = document.querySelector('#retry');
const DB = 'todo-starter-guest';
const LOCK = 'todo-starter-storage';
let todos = [];
let filter = 'all';
let ready = false;
const channel = 'BroadcastChannel' in window ? new BroadcastChannel(LOCK) : null;
channel?.addEventListener('message', () => window.location.reload());

function message(text, error = false) {
  status.textContent = text;
  status.hidden = !text;
  status.classList.toggle('error', error);
}
function controls(disabled) {
  root.querySelectorAll('input,button').forEach(el => { el.disabled = disabled; });
}
async function locked(fn) {
  if (!navigator.locks) throw new Error('This browser cannot safely save your list. Try an up-to-date version of Chrome, Firefox, or Safari. Your todos have not been changed.');
  return navigator.locks.request(LOCK, fn);
}
async function checkSession() {
  const response = await fetch('/app/session/', { cache: 'no-store' });
  if (!response.ok) throw new Error('Could not check your account. Please try again.');
  const current = await response.json();
  if ((current.user || '') !== account) {
    window.location.reload();
    throw new Error('Your account changed. Reloading your list…');
  }
}
async function api(url, method = 'GET', data) {
  const response = await fetch(url, {
    method, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value, 'X-Account-ID': account },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).error; } catch { /* Use safe fallback for HTML errors. */ }
    throw new Error(detail || 'Could not save your change. Check your connection and try again.');
  }
  return response.json();
}
function openDB(create = true) {
  return new Promise((resolve, reject) => {
    let missing = false;
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => {
      if (!create) { missing = true; request.transaction.abort(); }
      else request.result.createObjectStore('todos', { keyPath: 'id' });
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => db.close();
      resolve(db);
    };
    request.onerror = () => missing ? resolve(null) : reject(new Error('Data not saved. Browser storage is unavailable. Please allow site storage or try another browser.'));
    request.onblocked = () => reject(new Error('Close other tabs for this app, then try again.'));
  });
}
async function localOperation(mode, fn, create = true) {
  const db = await openDB(create);
  if (!db) return [];
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('todos', mode);
      const request = fn(tx.objectStore('todos'));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = tx.onabort = () => reject(new Error('Data not saved. Your browser could not save this change. Check available storage and try again.'));
    });
  } finally { db.close(); }
}
function deleteDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DB);
    request.onsuccess = resolve;
    request.onerror = () => reject(new Error('Your todos are saved to your account, but we couldn’t remove the separate copy in this browser. Try again to finish.'));
    request.onblocked = () => reject(new Error('Your todos are saved to your account. Close other tabs for this app, then try again to remove the separate copy in this browser.'));
  });
}
async function migrate() {
  const local = await localOperation('readonly', store => store.getAll(), false);
  if (local.length) {
    message(`Moving ${local.length} browser todo(s) to your account…`);
    for (let offset = 0; offset < local.length; offset += 1000) {
      const batch = local.slice(offset, offset + 1000);
      const result = await api('/app/api/todos/import/', 'POST', { todos: batch });
      const acknowledged = new Set(result.acknowledged);
      if (!batch.every(todo => acknowledged.has(todo.id))) throw new Error('We couldn’t confirm that your todos were saved to your account. They’re still saved in this browser. Try again.');
    }
  }
  // Deletes the database only after every batch is acknowledged. Receipts make retries safe.
  await deleteDB();
  if (local.length) channel?.postMessage('imported');
  return local.length;
}
function render() {
  list.replaceChildren();
  const visible = todos.filter(todo => filter === 'all' || (filter === 'done' ? todo.completed : !todo.completed));
  for (const todo of visible) {
    const row = document.createElement('li');
    row.className = `todo-row${todo.completed ? ' done' : ''}`;
    const label = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.checked = todo.completed;
    checkbox.addEventListener('change', () => mutate(async () => update(todo, { completed: checkbox.checked })));
    const title = document.createElement('span');
    title.className = 'todo-title'; title.textContent = todo.title;
    label.append(checkbox, title);
    const edit = document.createElement('button'); edit.textContent = 'Edit'; edit.setAttribute('aria-label', `Edit ${todo.title}`);
    edit.addEventListener('click', () => {
      const value = window.prompt('Edit your todo', todo.title);
      if (value === null) return;
      if (!value.trim() || value.trim().length > 300) { message('Enter a title of 1–300 characters.', true); return; }
      mutate(() => update(todo, { title: value.trim() }));
    });
    const remove = document.createElement('button'); remove.textContent = 'Delete'; remove.setAttribute('aria-label', `Delete ${todo.title}`);
    remove.addEventListener('click', () => mutate(async () => {
      if (account) await api(`/app/api/todos/${todo.id}/`, 'DELETE');
      else await localOperation('readwrite', store => store.delete(todo.id));
    }));
    row.append(label, edit, remove); list.append(row);
  }
  document.querySelector('#todo-empty').hidden = visible.length > 0;
  document.querySelector('#todo-count').textContent = `${todos.filter(todo => !todo.completed).length} left`;
}
async function update(todo, changes) {
  if (account) await api(`/app/api/todos/${todo.id}/`, 'PATCH', changes);
  else await localOperation('readwrite', store => store.put({ ...todo, ...changes }));
}
async function load() {
  todos = account ? (await api('/app/api/todos/')).todos : await localOperation('readonly', store => store.getAll());
  render();
}
async function mutate(fn) {
  if (!ready) return;
  controls(true);
  try {
    await locked(async () => { await checkSession(); await fn(); await load(); });
    message(account ? 'Saved to your account.' : 'Data saved in browser memory.');
    if (!account) channel?.postMessage('changed');
  } catch (error) { render(); message(error.message, true); }
  finally { controls(false); }
}
async function initialize() {
  ready = false; controls(true); retry.hidden = true;
  try {
    await locked(async () => {
      await checkSession();
      const imported = account ? await migrate() : 0;
      await load();
      message(imported ? 'Your existing todos are now saved to your account. You can access them on other devices by signing in. The separate copy in this browser has been removed.' : account ? 'Saved to your account. Sign in on another device to see this list.' : 'Data saved in browser memory.');
    });
    ready = true; controls(false);
  } catch (error) { message(error.message, true); retry.hidden = false; retry.disabled = false; }
}
form.addEventListener('submit', event => {
  event.preventDefault();
  const input = document.querySelector('#todo-title');
  const title = input.value.trim();
  if (!title) return;
  mutate(async () => {
    if (account) await api('/app/api/todos/', 'POST', { title });
    else await localOperation('readwrite', store => store.put({ id: crypto.randomUUID(), title, completed: false }));
    input.value = '';
  });
});
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  render();
}));
retry.addEventListener('click', initialize);
window.addEventListener('pageshow', event => { if (event.persisted) initialize(); });
initialize();
