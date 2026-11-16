/* Stack House — kitchen ordering web app (no build step, plain JS). */
'use strict';

/* ============================== utilities ============================== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};

const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="17" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
  list: '<path d="M9 6h12M9 12h12M9 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01" stroke-width="3"/>',
  pot: '<path d="M4 11h16v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5v-5z"/><path d="M2 11h20"/><path d="M9 7.5c0-1.5 1-2 1-3.5M14 7.5c0-1.5 1-2 1-3.5"/>',
  sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.2a6.5 6.5 0 0 1 3.5 5.8"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="M5 12.5 10 17.5 19 7"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/>',
  print: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 14h12v7H6z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  logout: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  alert: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
  up: '<path d="m6 15 6-6 6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3v12H4z"/><circle cx="12" cy="13.5" r="3.5"/>',
  volume: '<path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
  mute: '<path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="m17 10 4 4M21 10l-4 4"/>',
};
const icon = (name, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;

/* dates: the server sends kitchen-local dates as YYYY-MM-DD and times as HH:MM */
function addDays(iso, n) {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
const fmtDay = (iso, opts = { weekday: 'short', day: 'numeric', month: 'short' }) =>
  new Date(iso + 'T12:00:00Z').toLocaleDateString(undefined, { ...opts, timeZone: 'UTC' });
const fullDay = (iso) => fmtDay(iso, { weekday: 'long', day: 'numeric', month: 'long' });
function dayLabel(iso) {
  if (iso === S.boot.today) return 'Today';
  if (iso === addDays(S.boot.today, 1)) return 'Tomorrow';
  if (iso === addDays(S.boot.today, -1)) return 'Yesterday';
  return fmtDay(iso, { weekday: 'long' });
}
function ago(ts) {
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(ts).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}
const clockTime = (ts) => new Date(ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

/* ============================== state & api ============================== */
const S = {
  boot: null, user: null, menu: null, dishById: new Map(), unread: 0, version: 0, lastNotifId: null,
  actions: {}, inputs: {}, forms: {}, view: null, seq: 0, pollTimer: null, actHouse: null,
  nowDraft: { items: [], notes: '', when: 'ASAP', time: '' }, knownUrgent: null,
};

async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (method !== 'GET') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body ?? {});
  }
  let res;
  try {
    res = await fetch('/api' + path, opts);
  } catch (e) {
    throw new Error('Cannot reach Stack House. Check your connection.');
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const err = new Error((data && data.error) || `Something went wrong (${res.status}).`);
    err.status = res.status;
    if (res.status === 401 && S.user && !path.startsWith('/login')) { S.user = null; boot(); }
    throw err;
  }
  return data;
}

async function loadMenu() {
  S.menu = await api('/menu');
  S.dishById = new Map(S.menu.dishes.map((d) => [d.id, d]));
}
const catByName = (name) => S.menu.categories.find((c) => c.name.toLowerCase() === String(name).toLowerCase());
const catById = (id) => S.menu.categories.find((c) => c.id === id);
const houseById = (id) => S.boot.houses.find((h) => h.id === id);
const myHouse = () => houseById(S.user.houseId);
const isKitchen = () => S.user.role === 'chef' || S.user.isAdmin;
const canOrder = () => S.user.role === 'member' && !!S.user.houseId;
const mealsOn = () => ['lunch', 'dinner'].filter((m) => S.boot.settings.meals[m].enabled);
const mealTime = (m) => S.boot.settings.meals[m].time;
const actHouse = () => houseById(S.actHouse) || myHouse();
const houseQuery = () => (S.actHouse && S.actHouse !== S.user.houseId ? `?houseId=${S.actHouse}` : '');

/* ============================== ui helpers ============================== */
let toastTimer;
function toast(msg, { error = false, onClick } = {}) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (error ? ' error' : '');
  t.hidden = false;
  t.onclick = () => { t.hidden = true; if (onClick) onClick(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, error ? 6000 : 4000);
}
const fail = (e) => toast(e.message || String(e), { error: true });

function openSheet({ title, body = '', foot = '', cls = '', actions = {}, onClose }) {
  const ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML = `<div class="sheet ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="sheet-head"><h2>${esc(title)}</h2>
        <button class="icon-btn" data-sact="close" aria-label="Close">${icon('x')}</button></div>
      <div class="sheet-body">${body}</div>
      <div class="sheet-foot" ${foot ? '' : 'hidden'}>${foot}</div></div>`;
  document.body.appendChild(ov);
  document.body.style.overflow = 'hidden';
  const onKey = (e) => { if (e.key === 'Escape' && ov === $$('.overlay').pop()) close(); };
  const sheet = {
    el: ov, actions,
    close,
    body: (html) => { $('.sheet-body', ov).innerHTML = html; },
    foot: (html) => { const f = $('.sheet-foot', ov); f.innerHTML = html; f.hidden = !html; },
  };
  function close() {
    ov.remove();
    if (!$('.overlay')) document.body.style.overflow = '';
    document.removeEventListener('keydown', onKey);
    if (onClose) onClose();
  }
  document.addEventListener('keydown', onKey);
  ov.addEventListener('click', (e) => {
    if (e.target === ov) return close();
    const el = e.target.closest('[data-sact]');
    if (!el || el.closest('.overlay') !== ov) return;
    if (el.dataset.sact === 'close') return close();
    const fn = sheet.actions[el.dataset.sact];
    if (fn) { e.preventDefault(); fn(el, e, sheet); }
  });
  return sheet;
}

function ask({ title, message = '', ok = 'OK', danger = false, input = null }) {
  return new Promise((resolve) => {
    let answered = false;
    const sheet = openSheet({
      title, cls: 'small',
      body: `${message ? `<p>${esc(message)}</p>` : ''}${input
        ? `<input class="input" id="ask-input" placeholder="${esc(input.placeholder || '')}" maxlength="${input.max || 300}">` : ''}`,
      foot: `<button class="btn secondary" data-sact="close">Cancel</button>
             <button class="btn ${danger ? 'danger' : ''}" data-sact="ok">${esc(ok)}</button>`,
      onClose: () => { if (!answered) resolve(null); },
      actions: {
        ok: (_el, _e, s) => {
          answered = true;
          const v = input ? $('#ask-input', s.el).value.trim() : true;
          s.close();
          resolve(v);
        },
      },
    });
    const inp = $('#ask-input', sheet.el);
    if (inp) setTimeout(() => inp.focus(), 60);
  });
}

function paint(seq, html, wide = false) {
  if (seq !== S.seq) return false;
  const v = $('#view');
  v.className = 'view' + (wide ? ' wide' : '');
  v.innerHTML = html;
  return true;
}

function centerActiveDay() {
  // scroll only the day strip sideways; never move the page
  const a = $('.day.active');
  if (!a) return;
  const strip = a.parentElement;
  const ar = a.getBoundingClientRect();
  const sr = strip.getBoundingClientRect();
  strip.scrollLeft += (ar.left - sr.left) - (sr.width - ar.width) / 2;
}

function dishThumb(dish, catName) {
  if (dish && dish.image) return `<img src="${esc(dish.image)}" alt="" loading="lazy">`;
  const cat = dish ? catById(dish.categoryId) : catByName(catName);
  return esc((cat && cat.icon) || '🍽️');
}

function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = label || 'Saving…'; }
  else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
}

/* ============================== shell, routing, events ============================== */
function navItems() {
  const items = [];
  if (canOrder()) items.push(['/', 'home', 'Home'], ['/plan', 'calendar', 'Plan'], ['/now', 'bolt', 'Order now'], ['/orders', 'list', 'Orders']);
  if (isKitchen()) items.push(['/kitchen', 'pot', 'Kitchen']);
  if (S.user.isAdmin) items.push(['/admin', 'sliders', 'Admin']);
  if (!canOrder()) items.push(['/me', 'user', 'Me']);
  return items;
}

function renderShell() {
  const h = myHouse();
  const sub = h ? `${h.name} family` : (S.user.role === 'chef' ? 'Kitchen' : '');
  $('#header').innerHTML = `
    <a class="brand" href="#/"><img src="/static/icons/icon-192.png" alt="">
      <div><div class="brand-name">Stack House</div><div class="brand-sub">${esc(sub)}</div></div></a>
    <div class="header-actions">
      <button class="icon-btn" data-act="notifs" aria-label="Notifications">${icon('bell')}<span class="badge" id="unread" hidden></span></button>
      <a class="icon-btn" href="#/me" aria-label="My profile"><span class="avatar" ${h ? `style="--c:${esc(h.color)}"` : ''}>${esc(initials(S.user.name))}</span></a>
    </div>`;
  $('#tabbar').innerHTML = navItems().map(([p, ic, label]) =>
    `<a class="tab" href="#${p}" data-path="${p}">${icon(ic)}<span>${label}</span></a>`).join('');
  $('#header').hidden = false;
  $('#tabbar').hidden = false;
  updateBadge();
}

function updateBadge() {
  const b = $('#unread');
  if (!b) return;
  b.hidden = !S.unread;
  b.textContent = S.unread > 99 ? '99+' : S.unread;
}

const ROUTES = [
  [/^\/$/, 'home'], [/^\/login$/, 'login'], [/^\/setup$/, 'setup'],
  [/^\/plan(?:\/(\d{4}-\d{2}-\d{2}))?$/, 'plan'], [/^\/now$/, 'now'], [/^\/orders$/, 'orders'],
  [/^\/kitchen(?:\/(\d{4}-\d{2}-\d{2}))?$/, 'kitchen'],
  [/^\/admin(?:\/(menu|families|people|settings))?$/, 'admin'], [/^\/me$/, 'me'],
];
let lastHash = location.hash;
let ignoreHash = false;

window.addEventListener('hashchange', () => {
  if (ignoreHash) { ignoreHash = false; return; }
  if (S.view && S.view.isDirty && S.view.isDirty() && !confirm('You have unsaved changes. Leave without saving?')) {
    ignoreHash = true;
    location.hash = lastHash;
    return;
  }
  route();
});
window.addEventListener('beforeunload', (e) => {
  if (S.view && S.view.isDirty && S.view.isDirty()) { e.preventDefault(); e.returnValue = ''; }
});

function go(path) { location.hash = '#' + path; }
function openUrl(url) {
  const u = new URL(url || '/', location.origin);
  if (u.origin === location.origin && u.pathname === '/') go((u.hash || '#/').slice(1));
  else location.href = u.href;
}

async function route() {
  lastHash = location.hash;
  let path = (location.hash.replace(/^#/, '') || '/').split('?')[0];
  if (!S.user) {
    const want = S.boot.setupNeeded ? '/setup' : '/login';
    if (path !== want) { ignoreHash = location.hash !== '#' + want; go(want); path = want; }
  } else if (path === '/login' || path === '/setup' || (path === '/' && !canOrder())) {
    path = canOrder() ? '/' : isKitchen() ? '/kitchen' : '/me';
    ignoreHash = true;
    go(path);
  }
  let name = 'home';
  let args = [];
  for (const [re, n] of ROUTES) {
    const m = path.match(re);
    if (m) { name = n; args = m.slice(1); break; }
  }
  S.actions = {}; S.inputs = {}; S.forms = {}; S.view = null;
  const seq = ++S.seq;
  $$('.tab').forEach((t) => {
    const p = t.dataset.path;
    t.classList.toggle('active', p === '/' ? path === '/' : path.startsWith(p));
  });
  window.scrollTo(0, 0);
  try {
    await VIEWS[name](seq, ...args);
  } catch (e) {
    if (seq === S.seq) {
      paint(seq, `<div class="empty"><div class="em">😕</div><p>${esc(e.message)}</p><p style="margin-top:12px">
        <button class="btn secondary" data-act="retry">Try again</button></p></div>`);
      S.actions.retry = () => route();
    }
  }
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || el.closest('.overlay')) return;
  const fn = S.actions[el.dataset.act] || GLOBAL_ACTIONS[el.dataset.act];
  if (fn) { e.preventDefault(); fn(el, e); }
});
for (const type of ['input', 'change']) {
  document.addEventListener(type, (e) => {
    const el = e.target.closest(type === 'input' ? '[data-in]' : '[data-ch]');
    if (!el || el.closest('.overlay')) return;
    const fn = S.inputs[type === 'input' ? el.dataset.in : el.dataset.ch];
    if (fn) fn(el, e);
  });
}
document.addEventListener('submit', (e) => {
  const f = e.target.closest('form[data-form]');
  if (!f || f.closest('.overlay')) return;
  e.preventDefault();
  const fn = S.forms[f.dataset.form];
  if (fn) fn(f, e);
});

const GLOBAL_ACTIONS = {
  notifs: () => openNotifications(),
  reload: () => location.reload(),
};

/* ============================== polling & push ============================== */
function startPolling() {
  if (S.pollTimer) return;
  S.pollTimer = setInterval(poll, 15000);
  poll();
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && S.user) poll(); });

async function poll() {
  if (!S.user || document.hidden) return;
  try {
    const p = await api('/poll');
    S.boot.kitchen = p.kitchen;
    S.boot.today = p.today;
    if (p.latest) {
      if (S.lastNotifId !== null && p.latest.id > S.lastNotifId) {
        toast(p.latest.title, { onClick: () => openUrl(p.latest.url) });
      }
      S.lastNotifId = p.latest.id;
    } else if (S.lastNotifId === null) {
      S.lastNotifId = 0;
    }
    S.unread = p.unread;
    updateBadge();
    if (p.version !== S.version) {
      S.version = p.version;
      if (S.view && S.view.refresh && !(S.view.isDirty && S.view.isDirty())) S.view.refresh();
    }
  } catch (e) { /* offline: try again next tick */ }
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
  navigator.serviceWorker.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'open') openUrl(e.data.url);
    if (e.data && e.data.type === 'refresh') poll();
  });
}

function b64ToBytes(s) {
  const pad = '='.repeat((4 - (s.length % 4)) % 4);
  const raw = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent);
const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

async function pushState() {
  if (!window.isSecureContext) return 'insecure';
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg && await reg.pushManager.getSubscription();
    return sub ? 'on' : 'off';
  } catch (e) { return 'off'; }
}

async function enablePush() {
  const st = await pushState();
  if (st === 'insecure') throw new Error('Notifications need a secure (https) address for Stack House.');
  if (st === 'unsupported') {
    throw new Error(isIOS() && !isStandalone()
      ? 'On iPhone: tap Share → “Add to Home Screen”, open Stack House from there, then turn on notifications.'
      : 'This browser does not support notifications.');
  }
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') throw new Error('Notifications are blocked. Allow them in your browser settings.');
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(S.boot.vapidPublicKey) });
  await api('/push/subscribe', { method: 'POST', body: { subscription: sub.toJSON() } });
}

async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg && await reg.pushManager.getSubscription();
  if (sub) {
    await api('/push/unsubscribe', { method: 'POST', body: { endpoint: sub.endpoint } }).catch(() => {});
    await sub.unsubscribe();
  }
}

/* sound for the kitchen */
let audioCtx;
const soundOn = () => store.get('sh.sound') === '1';
function chime() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const t = audioCtx.currentTime;
    [880, 1175, 1568, 1175, 1568].forEach((f, i) => {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      const s = t + i * 0.17;
      o.type = 'sine';
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, s);
      g.gain.exponentialRampToValueAtTime(0.35, s + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, s + 0.45);
      o.connect(g).connect(audioCtx.destination);
      o.start(s);
      o.stop(s + 0.5);
    });
    if (navigator.vibrate) navigator.vibrate([300, 120, 300]);
  } catch (e) { /* audio not available */ }
}

/* ============================== notifications sheet ============================== */
async function openNotifications() {
  const sheet = openSheet({
    title: 'Notifications',
    body: '<div class="loading"><span class="spinner"></span></div>',
    actions: {
      open: (el, _e, s) => {
        api('/notifications/read', { method: 'POST', body: { ids: [Number(el.dataset.id)] } }).then(poll).catch(() => {});
        s.close();
        openUrl(el.dataset.url);
      },
      readall: async (_el, _e, s) => {
        await api('/notifications/read', { method: 'POST', body: { all: true } }).catch(fail);
        S.unread = 0;
        updateBadge();
        $$('.notif.unread', s.el).forEach((n) => n.classList.remove('unread'));
      },
    },
  });
  try {
    const { notifications } = await api('/notifications');
    if (!notifications.length) {
      sheet.body('<div class="empty"><div class="em">🔔</div><p>No notifications yet.</p></div>');
      return;
    }
    sheet.body(`<div class="list">${notifications.map((n) => `
      <a class="notif ${n.read ? '' : 'unread'}" data-sact="open" data-id="${n.id}" data-url="${esc(n.url)}" href="#">
        <div class="grow"><div class="nt">${esc(n.title)}</div>${n.body ? `<div class="nb">${esc(n.body)}</div>` : ''}
        <div class="tiny muted" style="margin-top:2px">${esc(ago(n.createdAt))}</div></div></a>`).join('')}</div>`);
    if (notifications.some((n) => !n.read)) sheet.foot('<button class="btn secondary" data-sact="readall">Mark all as read</button>');
  } catch (e) {
    sheet.body(`<p class="err">${esc(e.message)}</p>`);
  }
}

/* ============================== dish picking (shared) ============================== */
function itemInfo(it) {
  const dish = S.dishById.get(it.dishId);
  const catName = dish ? (catById(dish.categoryId) || {}).name : it.category;
  return { dish, name: dish ? dish.name : it.name, catName: catName || 'Other' };
}

function pickedHtml(items, key, readonly) {
  if (!items.length) return '';
  const order = S.menu.categories.map((c) => c.name);
  const groups = {};
  items.forEach((it) => {
    const info = itemInfo(it);
    (groups[info.catName] = groups[info.catName] || []).push({ it, info });
  });
  const cats = Object.keys(groups).sort((a, b) => {
    const ia = order.indexOf(a); const ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return `<div class="picked">${cats.map((c) => {
    const cat = catByName(c);
    return `<div class="pk-cat">${esc(cat ? cat.icon : '🍽️')} ${esc(c)}</div>${groups[c].map(({ it, info }) => `
      <div class="pk-row"><div class="thumb">${dishThumb(info.dish, info.catName)}</div>
        <div class="grow"><div class="pk-name">${esc(info.name)}</div></div>
        ${readonly
          ? `<span class="pill">${icon('people')} ${it.servings}</span>`
          : `<div class="stepper">
              <button data-act="dec" data-k="${key}" data-d="${it.dishId}" aria-label="Fewer people">${icon(it.servings <= 1 ? 'trash' : 'minus')}</button>
              <div class="val">${it.servings}<small>${it.servings === 1 ? 'person' : 'people'}</small></div>
              <button data-act="inc" data-k="${key}" data-d="${it.dishId}" aria-label="More people">${icon('plus')}</button>
            </div>`}
      </div>`).join('')}`;
  }).join('')}</div>`;
}

function stepItem(target, dishId, delta) {
  const i = target.items.findIndex((x) => x.dishId === dishId);
  if (i < 0) return;
  const next = target.items[i].servings + delta;
  if (next < 1) target.items.splice(i, 1);
  else target.items[i].servings = Math.min(99, next);
}

function openPicker(target, title, people, onChange) {
  let cat = 'all';
  let q = '';
  const sheet = openSheet({
    title,
    body: `<div class="search">${icon('search')}<input class="input" id="pk-q" type="search" placeholder="Search dishes" autocomplete="off"></div>
           <div class="chips" id="pk-cats"></div><div class="dish-grid" id="pk-grid"></div>`,
    foot: '<span class="muted small grow" id="pk-count"></span><button class="btn" data-sact="close">Done</button>',
    actions: {
      cat: (el) => { cat = el.dataset.c; draw(); },
      toggle: (el) => {
        const id = Number(el.dataset.d);
        const i = target.items.findIndex((x) => x.dishId === id);
        if (i >= 0) target.items.splice(i, 1);
        else target.items.push({ dishId: id, servings: people, note: '' });
        draw();
        onChange();
      },
    },
    onClose: onChange,
  });
  $('#pk-q', sheet.el).addEventListener('input', (e) => { q = e.target.value.trim().toLowerCase(); draw(); });

  function draw() {
    const cats = S.menu.categories.filter((c) => S.menu.dishes.some((d) => d.categoryId === c.id));
    $('#pk-cats', sheet.el).innerHTML = [`<button class="chip ${cat === 'all' ? 'active' : ''}" data-sact="cat" data-c="all">All</button>`]
      .concat(cats.map((c) => `<button class="chip ${String(c.id) === cat ? 'active' : ''}" data-sact="cat" data-c="${c.id}">${esc(c.icon)} ${esc(c.name)}</button>`)).join('');
    const picked = new Set(target.items.map((x) => x.dishId));
    const list = S.menu.dishes.filter((d) => (cat === 'all' || String(d.categoryId) === cat)
      && (!q || d.name.toLowerCase().includes(q) || d.description.toLowerCase().includes(q)));
    const order = new Map(S.menu.categories.map((c, i) => [c.id, i]));
    list.sort((a, b) => (order.get(a.categoryId) - order.get(b.categoryId)) || a.name.localeCompare(b.name));
    $('#pk-grid', sheet.el).innerHTML = list.length ? list.map((d) => `
      <button class="dish-card ${picked.has(d.id) ? 'on' : ''}" data-sact="toggle" data-d="${d.id}" aria-pressed="${picked.has(d.id)}">
        <div class="ph">${dishThumb(d)}</div><span class="tick">${icon(picked.has(d.id) ? 'check' : 'plus')}</span>
        <div class="dc-body"><div class="dc-name">${esc(d.name)}</div>${d.description ? `<div class="dc-desc">${esc(d.description)}</div>` : ''}</div>
      </button>`).join('')
      : `<div class="empty" style="grid-column:1/-1">${S.menu.dishes.length ? 'No dishes match.' : 'The menu is empty. An admin can add dishes.'}</div>`;
    $('#pk-count', sheet.el).textContent = target.items.length ? `${plural(target.items.length, 'dish', 'dishes')} selected` : 'Tap dishes to add them';
  }
  draw();
}

function houseSwitcher() {
  if (!S.user.isAdmin || S.boot.houses.length < 2) return '';
  return `<div class="chips" style="margin-bottom:10px"><span class="pill">Ordering for</span>${S.boot.houses.map((h) => `
    <button class="chip ${h.id === actHouse().id ? 'active' : ''}" data-act="house" data-h="${h.id}">
      <span class="dot" style="--c:${esc(h.color)}"></span>${esc(h.name)}</button>`).join('')}</div>`;
}

const URGENT_STATUS = {
  pending: ['warn', 'Waiting for the kitchen'],
  accepted: ['info', 'Being prepared'],
  ready: ['ok', 'Ready'],
  delivered: ['', 'Delivered'],
  declined: ['danger', 'Declined'],
  cancelled: ['', 'Cancelled'],
};
function urgentPill(o) {
  const [cls, label] = URGENT_STATUS[o.status] || ['', o.status];
  return `<span class="pill ${cls}">${esc(label)}${o.status === 'accepted' && o.eta ? ` · ~${esc(o.eta)}` : ''}</span>`;
}
function itemsList(items) {
  if (!items.length) return '';
  return `<ul class="order-items">${items.map((i) => `<li><span>${esc(i.name)}</span><span class="q">${icon('people')} ${i.servings}</span></li>`).join('')}</ul>`;
}
function urgentCardHtml(o, { mine = true } = {}) {
  return `<div class="card urgent-card" style="--c:${esc(o.houseColor)}">
    <div class="row between wrap"><div class="row">${urgentPill(o)}<span class="small muted">${esc(ago(o.createdAt))}</span></div>
      ${mine && o.status === 'pending' ? `<button class="btn sm danger-ghost" data-act="cancel-urgent" data-id="${o.id}">Cancel</button>` : ''}</div>
    ${itemsList(o.items)}
    ${o.notes ? `<div class="note">“${esc(o.notes)}”</div>` : ''}
    <div class="small muted" style="margin-top:8px">Needed: ${esc(o.neededBy || 'ASAP')} · by ${esc(o.createdBy || '—')}</div>
    ${o.chefNote ? `<div class="banner info" style="margin-top:8px">${icon('pot')}<div>Chef: ${esc(o.chefNote)}</div></div>` : ''}
  </div>`;
}

function mealSummary(order) {
  if (!order) return null;
  if (order.status === 'skipped') return 'Not needed';
  return order.items.map((i) => `${i.name} · ${i.servings}`).join(', ');
}

/* ============================== views ============================== */
const VIEWS = {};

/* ---------- login & setup ---------- */
VIEWS.login = async (seq) => {
  paint(seq, `<div class="auth"><div class="card auth-card stack-lg">
    <div class="center"><img class="auth-logo" src="/static/icons/icon-192.png" alt="">
      <h1>Stack House</h1><p class="muted">Central kitchen orders</p></div>
    <form class="form-grid" data-form="login" autocomplete="on">
      <div class="field"><label for="lu">Username</label>
        <input class="input" id="lu" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required></div>
      <div class="field"><label for="lp">Password</label>
        <input class="input" id="lp" name="password" type="password" autocomplete="current-password" required></div>
      <div class="err" id="login-err"></div>
      <button class="btn big block" type="submit">Log in</button>
    </form>
    <p class="muted small center">Forgot your password? Ask a Stack House admin to reset it.</p>
  </div></div>`);
  $('#lu').focus();
  S.forms.login = async (f) => {
    const btn = $('button[type=submit]', f);
    busy(btn, true, 'Logging in…');
    try {
      await api('/login', { method: 'POST', body: { username: f.username.value, password: f.password.value } });
      await boot();
    } catch (e) {
      $('#login-err').textContent = e.message;
      busy(btn, false);
    }
  };
};

VIEWS.setup = async (seq) => {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  paint(seq, `<div class="auth"><div class="card auth-card stack-lg" style="max-width:460px">
    <div class="center"><img class="auth-logo" src="/static/icons/icon-192.png" alt="">
      <h1>Welcome to Stack House</h1><p class="muted">Create the first admin account to get started.</p></div>
    <form class="form-grid" data-form="setup">
      <div class="field"><label for="sn">Your name</label><input class="input" id="sn" name="name" maxlength="60" required></div>
      <div class="field"><label for="sh">Your family</label><select class="input" id="sh" name="house">
        ${S.boot.houses.map((h) => `<option value="${h.id}">${esc(h.name)}</option>`).join('')}</select></div>
      <div class="field"><label for="su">Username</label>
        <input class="input" id="su" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required></div>
      <div class="field"><label for="sp">Password (at least 6 characters)</label>
        <input class="input" id="sp" name="password" type="password" autocomplete="new-password" minlength="6" required></div>
      <label class="switch"><input type="checkbox" name="sample" checked> Start with a sample menu (you can edit it later)</label>
      <p class="small muted">Kitchen timezone: <b>${esc(tz)}</b> (from this device — change it later in Admin → Settings).</p>
      <div class="err" id="setup-err"></div>
      <button class="btn big block" type="submit">Create account</button>
    </form></div></div>`);
  S.forms.setup = async (f) => {
    const btn = $('button[type=submit]', f);
    busy(btn, true, 'Setting up…');
    try {
      await api('/setup', { method: 'POST', body: {
        name: f.name.value, username: f.username.value, password: f.password.value,
        houseId: Number(f.house.value), sampleMenu: f.sample.checked, timezone: tz,
      } });
      await boot();
      go('/admin/people');
      toast('All set! Now add the other family members and the chef.');
    } catch (e) {
      $('#setup-err').textContent = e.message;
      busy(btn, false);
    }
  };
};

/* ---------- home ---------- */
VIEWS.home = async (seq) => {
  S.actHouse = S.user.houseId;
  const [{ days }, ords, push] = await Promise.all([api('/days'), api('/orders'), pushState()]);
  const today = S.boot.today;
  const tomorrow = addDays(today, 1);
  const td = days.find((d) => d.date === today);
  const tm = days.find((d) => d.date === tomorrow);
  const active = ords.urgent.filter((o) => ['pending', 'accepted', 'ready'].includes(o.status));
  const k = S.boot.kitchen;
  const hr = new Date().getHours();
  const hello = hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
  const kitchenPill = k.open
    ? `<span class="pill ok">${icon('pot')} Kitchen open until ${esc(k.until)}</span>`
    : `<span class="pill">${icon('clock')} Kitchen closed${k.nextOpen ? ` · opens ${esc(dayLabel(k.nextOpen.date).toLowerCase())} ${esc(k.nextOpen.time)}` : ''}</span>`;

  const mealLines = (day) => mealsOn().map((m) => {
    const o = day.meals[m];
    const what = o ? mealSummary(o) : null;
    return `<div class="meal-line"><div class="meal-ico ${m}">${icon(m === 'lunch' ? 'sun' : 'moon')}</div>
      <div class="grow"><div class="row between"><b>${cap(m)}</b><span class="small muted">${esc(mealTime(m))}</span></div>
      <div class="what">${what ? esc(what) : '<span style="color:var(--warn)">Not chosen yet</span>'}</div></div></div>`;
  }).join('');

  let tomorrowCard;
  if (!tm || !tm.open) {
    tomorrowCard = `<div class="card"><div class="card-head"><h2>Tomorrow · ${esc(fmtDay(tomorrow))}</h2></div>
      <p class="muted">The kitchen is closed tomorrow.</p></div>`;
  } else {
    const anySet = Object.values(tm.meals).some(Boolean);
    const pill = tm.isSet ? `<span class="pill ok">${icon('check')} Set</span>`
      : tm.locked ? '<span class="pill danger">Missed</span>'
        : `<span class="pill warn">${anySet ? 'Not finished' : 'Not set yet'}</span>`;
    tomorrowCard = `<div class="card"><div class="card-head"><h2>Tomorrow · ${esc(fmtDay(tomorrow))}</h2>${pill}</div>
      ${mealLines(tm)}
      <div class="card-foot"><span class="small muted">${tm.locked ? `${icon('lock')} Locked — use Order now for changes` : `Choose before <b>${esc(tm.lockAt)}</b>`}</span>
        <a class="btn ${tm.isSet ? 'secondary' : ''}" href="#/plan/${tomorrow}">${tm.locked ? 'View' : tm.isSet ? 'Edit' : 'Plan tomorrow'}</a></div></div>`;
  }
  const todayHas = td && td.open && Object.values(td.meals).some(Boolean);
  const todayCard = todayHas ? `<div class="card"><div class="card-head"><h2>Today</h2><a class="small" href="#/plan/${today}">Details</a></div>${mealLines(td)}</div>` : '';

  const strip = `<div class="days">${days.map((d) => {
    const cls = !d.open ? 'closed' : d.isSet ? 'set' : Object.values(d.meals).some(Boolean) ? 'partial' : '';
    return `<a class="day ${cls}" href="#/plan/${d.date}"><div class="dw">${esc(fmtDay(d.date, { weekday: 'short' }))}</div>
      <div class="dn">${Number(d.date.slice(8))}</div><div class="ds">${!d.open ? '–' : d.isSet ? icon('check') : cls === 'partial' ? '●' : ''}</div></a>`;
  }).join('')}</div>`;

  const pushCta = push === 'off' && store.get('sh.pushAsk') !== 'no' ? `
    <div class="card notify-cta"><div class="meal-ico">${icon('bell')}</div>
      <div class="grow"><b>Get reminders on this device</b><div class="small muted">We'll remind you to choose tomorrow's food and tell you when your order is ready.</div></div>
      <button class="btn sm" data-act="push-on">Turn on</button><button class="icon-btn" data-act="push-no" aria-label="Not now">${icon('x')}</button></div>` : '';

  const nowCard = `<div class="card now-card"><div class="big-ico">${icon('bolt')}</div>
    <div class="grow"><b>Need something now?</b><div class="small muted">For food outside the lunch and dinner plan.</div></div>
    <a class="btn" href="#/now" ${k.open || !S.boot.settings.urgentOnlyWhenOpen ? '' : 'aria-disabled="true"'}>Order now</a></div>`;

  if (!paint(seq, `
    <div class="hello"><div><div class="eyebrow">${esc(myHouse().name)} family</div><h1>${hello}, ${esc(S.user.name.split(' ')[0])}</h1></div>${kitchenPill}</div>
    <div class="stack">
      ${active.length ? `<div class="section-title" style="margin-top:0"><h2>Your order now requests</h2></div>${active.map((o) => urgentCardHtml(o)).join('')}` : ''}
      ${pushCta}${tomorrowCard}${todayCard}
      <div class="card"><div class="card-head"><h2>Plan ahead</h2><span class="small muted">Tap a day</span></div>${strip}</div>
      ${nowCard}
    </div>`)) return;
  S.actions['push-on'] = async () => { try { await enablePush(); toast('Notifications are on for this device ✓'); route(); } catch (e) { fail(e); } };
  S.actions['push-no'] = () => { store.set('sh.pushAsk', 'no'); route(); };
  S.actions['cancel-urgent'] = cancelUrgent;
  S.view = { refresh: () => VIEWS.home(S.seq) };
};

async function cancelUrgent(el) {
  if (!(await ask({ title: 'Cancel this order?', message: 'The kitchen will be told it is cancelled.', ok: 'Cancel order', danger: true }))) return;
  try {
    await api(`/urgent/${el.dataset.id}/cancel`, { method: 'POST', body: {} });
    toast('Order cancelled');
    if (S.view && S.view.refresh) S.view.refresh();
  } catch (e) { fail(e); }
}

/* ---------- plan meals ---------- */
VIEWS.plan = async (seq, date) => {
  if (!S.actHouse) S.actHouse = S.user.houseId;
  const { days } = await api('/days' + houseQuery());
  if (!date) {
    const tomorrow = addDays(S.boot.today, 1);
    const pick = days.find((d) => d.date >= tomorrow && d.open && !d.locked) || days.find((d) => d.open && !d.locked);
    date = pick ? pick.date : tomorrow;
    ignoreHash = true;
    location.replace(`#/plan/${date}`);
    lastHash = location.hash;
  }
  let plan = days.find((d) => d.date === date);
  if (!plan) plan = await api(`/plan/${date}` + houseQuery());
  if (seq !== S.seq) return;

  const P = { plan, meals: {}, snapshot: '' };
  const load = (p) => {
    P.plan = p;
    P.meals = {};
    mealsOn().forEach((m) => {
      const o = p.meals[m];
      P.meals[m] = {
        need: o ? o.status === 'ordered' : null,
        items: o && o.status === 'ordered' ? o.items.filter((i) => i.dishId).map((i) => ({ dishId: i.dishId, servings: i.servings, note: i.note, name: i.name, category: i.category })) : [],
        notes: o ? o.notes : '',
      };
    });
    P.snapshot = JSON.stringify(P.meals);
  };
  load(plan);
  const dirty = () => JSON.stringify(P.meals) !== P.snapshot;
  const inWindow = days.some((d) => d.date === date);
  const editable = () => inWindow && P.plan.open && (!P.plan.locked || S.user.isAdmin);
  const people = () => actHouse().people || 4;

  function saveBarHtml() {
    const msg = dirty() ? 'You have unsaved changes'
      : P.plan.isSet ? 'Saved — the chef can see your plan ✓' : 'Choose for each meal, then save';
    return `<div class="grow small">${msg}</div><button class="btn" data-act="save" ${dirty() ? '' : 'disabled'}>Save plan</button>`;
  }
  function mealCard(m) {
    const st = P.meals[m];
    const ed = editable();
    const o = P.plan.meals[m];
    const badge = o ? (o.status === 'ordered' ? '<span class="pill ok">Ordered</span>' : '<span class="pill">Not needed</span>')
      : '<span class="pill warn">Not set</span>';
    let body = '';
    if (ed) {
      body += `<div class="seg" role="group" aria-label="Do you need ${m}?">
        <button data-act="need" data-m="${m}" data-v="1" class="${st.need === true ? 'on yes' : ''}" aria-pressed="${st.need === true}">${icon('check')} Yes, ${m} please</button>
        <button data-act="need" data-m="${m}" data-v="0" class="${st.need === false ? 'on' : ''}" aria-pressed="${st.need === false}">No ${m}</button></div>`;
    }
    if (st.need === true) {
      body += pickedHtml(st.items, m, !ed);
      if (ed) body += `<button class="add-dishes" data-act="pick" data-m="${m}">${icon('plus')} ${st.items.length ? 'Add more dishes' : 'Choose dishes'}</button>`;
      else if (!st.items.length) body += '<p class="muted">No dishes.</p>';
    } else if (st.need === false) {
      body += `<p class="muted">No ${m} for the ${esc(actHouse().name)} family on this day.</p>`;
    } else if (!ed) {
      body += '<p class="muted">Not set.</p>';
    }
    if (ed && st.need !== null) {
      body += `<div class="field"><label for="notes-${m}">Notes for the chef (optional)</label>
        <textarea class="input" id="notes-${m}" data-in="notes" data-m="${m}" maxlength="500" rows="2" placeholder="e.g. less spicy, one plate without nuts">${esc(st.notes)}</textarea></div>`;
    } else if (st.notes) {
      body += `<div class="note">“${esc(st.notes)}”</div>`;
    }
    const by = o && o.updatedBy ? `<div class="tiny muted">Last changed by ${esc(o.updatedBy)} · ${esc(ago(o.updatedAt))}</div>` : '';
    return `<section class="card meal-card"><div class="mc-head"><div class="meal-ico ${m}">${icon(m === 'lunch' ? 'sun' : 'moon')}</div>
      <div class="grow"><h2>${cap(m)}</h2><div class="small muted">Served at ${esc(mealTime(m))}</div></div>${badge}</div>
      <div class="mc-body">${body}${by}</div></section>`;
  }
  function draw() {
    const p = P.plan;
    let banner = '';
    if (!p.open) banner = `<div class="banner">${icon('info')}<div>The kitchen is closed on this day.</div></div>`;
    else if (!inWindow) banner = `<div class="banner">${icon('lock')}<div>This day can't be changed anymore.</div></div>`;
    else if (p.locked && S.user.isAdmin) banner = `<div class="banner warn">${icon('lock')}<div>Orders for this day are locked. As an admin you can still change them — the chef will get a <b>late change</b> alert.</div></div>`;
    else if (p.locked) banner = `<div class="banner">${icon('lock')}<div>Orders for this day are locked. Need something extra? <a href="#/now">Order now</a>.</div></div>`;
    else banner = `<div class="banner info">${icon('clock')}<div>You can change this until <b>${esc(p.lockAt)}</b>.</div></div>`;

    const strip = `<div class="days">${days.map((d) => {
      const cls = [d.date === date ? 'active' : '', !d.open ? 'closed' : d.isSet ? 'set' : Object.values(d.meals).some(Boolean) ? 'partial' : ''].join(' ');
      return `<a class="day ${cls}" href="#/plan/${d.date}"><div class="dw">${esc(d.date === S.boot.today ? 'Today' : fmtDay(d.date, { weekday: 'short' }))}</div>
        <div class="dn">${Number(d.date.slice(8))}</div><div class="ds">${!d.open ? '–' : d.isSet ? icon('check') : cls.includes('partial') ? '●' : ''}</div></a>`;
    }).join('')}</div>`;

    paint(S.seq, `
      <div class="page-head"><div><div class="eyebrow">Plan meals · ${esc(actHouse().name)} family</div>
        <h1>${esc(dayLabel(date))}</h1><div class="muted">${esc(fullDay(date))}</div></div></div>
      ${houseSwitcher()}${strip}
      <div class="stack" style="margin-top:6px">${banner}${p.open ? mealsOn().map(mealCard).join('') : ''}</div>
      ${editable() ? `<div class="save-bar" id="save-bar">${saveBarHtml()}</div>` : ''}`);
    centerActiveDay();
  }
  const refreshBar = () => { const b = $('#save-bar'); if (b) b.innerHTML = saveBarHtml(); };

  draw();
  S.actions.need = (el) => {
    const st = P.meals[el.dataset.m];
    st.need = el.dataset.v === '1';
    draw();
    if (st.need && !st.items.length) S.actions.pick(el);
  };
  S.actions.pick = (el) => {
    const m = el.dataset.m;
    openPicker(P.meals[m], `${cap(m)} · ${fmtDay(date)}`, people(), () => draw());
  };
  S.actions.inc = (el) => { stepItem(P.meals[el.dataset.k], Number(el.dataset.d), 1); draw(); };
  S.actions.dec = (el) => { stepItem(P.meals[el.dataset.k], Number(el.dataset.d), -1); draw(); };
  S.actions.house = (el) => {
    if (dirty() && !confirm('Discard your unsaved changes?')) return;
    S.actHouse = Number(el.dataset.h);
    P.snapshot = JSON.stringify(P.meals);
    VIEWS.plan(S.seq, date);
  };
  S.inputs.notes = (el) => { P.meals[el.dataset.m].notes = el.value; refreshBar(); };
  S.actions.save = async (el) => {
    const payload = {};
    for (const m of mealsOn()) {
      const st = P.meals[m];
      if (st.need === null) continue;
      if (st.need && !st.items.length) { toast(`Pick at least one dish for ${m}, or choose “No ${m}”.`, { error: true }); return; }
      payload[m] = { need: st.need, notes: st.notes, items: st.need ? st.items.map(({ dishId, servings, note }) => ({ dishId, servings, note })) : [] };
    }
    busy(el, true);
    try {
      const body = { meals: payload };
      if (S.actHouse !== S.user.houseId) body.houseId = S.actHouse;
      const res = await api(`/plan/${date}`, { method: 'PUT', body });
      const i = days.findIndex((d) => d.date === date);
      if (i >= 0) days[i] = res;
      load(res);
      draw();
      toast(res.isSet ? 'Saved — the chef has been notified ✓' : 'Saved');
    } catch (e) {
      busy(el, false);
      fail(e);
    }
  };
  S.view = {
    isDirty: dirty,
    refresh: () => { if (!dirty()) VIEWS.plan(S.seq, date); },
  };
};

/* ---------- order now ---------- */
VIEWS.now = async (seq) => {
  if (!S.actHouse) S.actHouse = S.user.houseId;
  const ords = await api('/orders' + houseQuery());
  const U = S.nowDraft;
  const active = () => ords.urgent.filter((o) => ['pending', 'accepted', 'ready'].includes(o.status));
  const k = S.boot.kitchen;
  const closed = !k.open && S.boot.settings.urgentOnlyWhenOpen;

  function draw() {
    const whens = [['ASAP', 'As soon as possible'], ['in 30 min', 'In 30 min'], ['in 1 hour', 'In 1 hour'], ['time', 'At a time']];
    const form = closed
      ? `<div class="banner danger">${icon('clock')}<div>The kitchen is closed right now${k.nextOpen ? ` — it opens ${esc(dayLabel(k.nextOpen.date).toLowerCase())} at <b>${esc(k.nextOpen.time)}</b>` : ''}.</div></div>`
      : `<div class="card stack">
          <div class="row between"><h2>What do you need?</h2><span class="pill ok">${icon('pot')} Open until ${esc(k.until)}</span></div>
          ${pickedHtml(U.items, 'now', false)}
          <button class="add-dishes" data-act="pick">${icon('plus')} ${U.items.length ? 'Add more dishes' : 'Choose from the menu'}</button>
          <div class="field"><label for="now-notes">Anything else? (optional)</label>
            <textarea class="input" id="now-notes" data-in="notes" maxlength="500" rows="2" placeholder="e.g. tea for 6, sandwiches for the kids">${esc(U.notes)}</textarea></div>
          <div class="field"><span class="label">When do you need it?</span>
            <div class="chips">${whens.map(([v, l]) => `<button class="chip ${U.when === v ? 'active' : ''}" data-act="when" data-v="${v}">${l}</button>`).join('')}</div>
            ${U.when === 'time' ? `<input class="input time" type="time" data-in="time" value="${esc(U.time)}" aria-label="Time needed">` : ''}</div>
          <button class="btn big block" data-act="send">${icon('bolt')} Send to the kitchen</button>
        </div>`;
    const list = active();
    paint(S.seq, `
      <div class="page-head"><div><div class="eyebrow">Order now · ${esc(actHouse().name)} family</div><h1>Need food now?</h1>
        <div class="muted">Goes straight to the chef. For lunch and dinner, use <a href="#/plan">Plan</a>.</div></div></div>
      ${houseSwitcher()}
      <div class="stack">${form}
        ${list.length ? `<div class="section-title"><h2>In progress</h2><span class="count">${list.length}</span></div>${list.map((o) => urgentCardHtml(o)).join('')}` : ''}
      </div>`);
  }
  if (seq !== S.seq) return;
  draw();
  S.actions.pick = () => openPicker(U, 'Order now', actHouse().people || 4, draw);
  S.actions.inc = (el) => { stepItem(U, Number(el.dataset.d), 1); draw(); };
  S.actions.dec = (el) => { stepItem(U, Number(el.dataset.d), -1); draw(); };
  S.actions.when = (el) => { U.when = el.dataset.v; draw(); };
  S.actions.house = (el) => { S.actHouse = Number(el.dataset.h); VIEWS.now(S.seq); };
  S.actions['cancel-urgent'] = cancelUrgent;
  S.inputs.notes = (el) => { U.notes = el.value; };
  S.inputs.time = (el) => { U.time = el.value; };
  S.actions.send = async (el) => {
    if (!U.items.length && !U.notes.trim()) { toast('Pick a dish or write what you need.', { error: true }); return; }
    if (U.when === 'time' && !U.time) { toast('Choose the time you need it.', { error: true }); return; }
    busy(el, true, 'Sending…');
    try {
      const body = {
        items: U.items.map(({ dishId, servings, note }) => ({ dishId, servings, note })),
        notes: U.notes, neededBy: U.when === 'time' ? `at ${U.time}` : U.when,
      };
      if (S.actHouse !== S.user.houseId) body.houseId = S.actHouse;
      const order = await api('/urgent', { method: 'POST', body });
      ords.urgent.unshift(order);
      S.nowDraft = { items: [], notes: '', when: 'ASAP', time: '' };
      VIEWS.now(S.seq);
      toast('Sent! The chef has been notified 🚀');
    } catch (e) {
      busy(el, false);
      fail(e);
    }
  };
  S.view = { refresh: () => VIEWS.now(S.seq) };
};

/* ---------- orders ---------- */
VIEWS.orders = async (seq) => {
  if (!S.actHouse) S.actHouse = S.user.houseId;
  const o = await api('/orders' + houseQuery());
  const byDate = {};
  o.upcoming.forEach((x) => { (byDate[x.date] = byDate[x.date] || {})[x.meal] = x; });
  const upcoming = Object.keys(byDate).sort().map((d) => `
    <div class="card"><div class="card-head"><div><h2>${esc(dayLabel(d))}</h2><div class="small muted">${esc(fullDay(d))}</div></div>
      <a class="btn sm secondary" href="#/plan/${d}">Open</a></div>
      ${mealsOn().map((m) => {
        const x = byDate[d][m];
        return `<div class="meal-line"><div class="meal-ico ${m}">${icon(m === 'lunch' ? 'sun' : 'moon')}</div><div class="grow">
          <div class="row between"><b>${cap(m)}</b>${x ? (x.status === 'ordered' ? `<span class="pill ok">${plural(x.totalServings, 'serving')}</span>` : '<span class="pill">Not needed</span>') : '<span class="pill warn">Not set</span>'}</div>
          ${x && x.status === 'ordered' ? itemsList(x.items) : ''}${x && x.notes ? `<div class="note">“${esc(x.notes)}”</div>` : ''}</div></div>`;
      }).join('')}</div>`).join('');
  const past = o.past.length ? `<div class="card"><div class="list">${o.past.slice(0, 40).map((x) => `
    <div class="list-item"><div class="meal-ico ${x.meal}">${icon(x.meal === 'lunch' ? 'sun' : 'moon')}</div><div class="grow">
      <div class="row between"><b>${esc(fmtDay(x.date))} · ${cap(x.meal || '')}</b><span class="small muted">${x.status === 'ordered' ? plural(x.totalServings, 'serving') : 'Not needed'}</span></div>
      <div class="small muted">${esc(mealSummary(x))}</div></div></div>`).join('')}</div></div>` : '<p class="muted">Nothing in the last 30 days.</p>';

  if (!paint(seq, `
    <div class="page-head"><div><div class="eyebrow">${esc(actHouse().name)} family</div><h1>Orders</h1></div>
      <a class="btn secondary" href="#/plan">${icon('calendar')} Plan meals</a></div>
    ${houseSwitcher()}
    <div class="section-title" style="margin-top:4px"><h2>Order now requests</h2><span class="count">last 30 days</span></div>
    <div class="stack">${o.urgent.length ? o.urgent.slice(0, 20).map((x) => urgentCardHtml(x)).join('') : '<p class="muted">None yet.</p>'}</div>
    <div class="section-title"><h2>Coming up</h2></div>
    <div class="stack">${upcoming || `<div class="card empty"><div class="em">🗓️</div><p>Nothing planned yet.</p><p style="margin-top:10px"><a class="btn" href="#/plan">Plan meals</a></p></div>`}</div>
    <div class="section-title"><h2>Past meals</h2></div>${past}`)) return;
  S.actions['cancel-urgent'] = cancelUrgent;
  S.actions.house = (el) => { S.actHouse = Number(el.dataset.h); VIEWS.orders(S.seq); };
  S.view = { refresh: () => VIEWS.orders(S.seq) };
};

/* ---------- kitchen ---------- */
VIEWS.kitchen = async (seq, date) => {
  const data = await api('/kitchen' + (date ? `?date=${date}` : ''));
  if (seq !== S.seq) return;
  const day = data.day;
  date = day.date;

  // alert for new "order now" requests
  const pendingIds = data.urgent.filter((o) => o.status === 'pending').map((o) => o.id);
  if (S.knownUrgent && pendingIds.some((id) => !S.knownUrgent.has(id))) {
    if (soundOn()) chime();
  }
  S.knownUrgent = new Set(pendingIds);

  const urgentCard = (o) => {
    let actions = '';
    if (o.status === 'pending') {
      actions = `<select class="input" id="eta-${o.id}" aria-label="Ready in" style="width:auto;min-height:40px">
          ${['10 min', '15 min', '20 min', '30 min', '45 min', '1 hour'].map((v) => `<option ${v === '20 min' ? 'selected' : ''}>${v}</option>`).join('')}</select>
        <button class="btn sm ok" data-act="accept" data-id="${o.id}">${icon('check')} Accept</button>
        <button class="btn sm secondary" data-act="ready" data-id="${o.id}">Ready</button>
        <button class="btn sm danger-ghost" data-act="decline" data-id="${o.id}">Decline</button>`;
    } else if (o.status === 'accepted') {
      actions = `<button class="btn sm ok" data-act="ready" data-id="${o.id}">${icon('check')} Mark ready</button>
        <button class="btn sm secondary" data-act="delivered" data-id="${o.id}">Delivered</button>
        <button class="btn sm danger-ghost" data-act="decline" data-id="${o.id}">Decline</button>`;
    } else if (o.status === 'ready') {
      actions = `<button class="btn sm ok" data-act="delivered" data-id="${o.id}">${icon('check')} Delivered</button>`;
    }
    return `<div class="card urgent-card ${o.status}" style="--c:${esc(o.houseColor)}">
      <div class="row between wrap"><span class="house-tag"><span class="dot" style="--c:${esc(o.houseColor)}"></span>${esc(o.houseName)} family</span>${urgentPill(o)}</div>
      <div class="small muted" style="margin-top:2px">${esc(clockTime(o.createdAt))} (${esc(ago(o.createdAt))}) · by ${esc(o.createdBy || '—')} · needed <b>${esc(o.neededBy || 'ASAP')}</b></div>
      ${itemsList(o.items)}${o.notes ? `<div class="note">“${esc(o.notes)}”</div>` : ''}
      <div class="row wrap no-print" style="margin-top:12px">${actions}</div></div>`;
  };

  const houseChip = (h, m) => {
    const st = h.status || 'pending';
    const ic = st === 'ordered' ? icon('check') : st === 'skipped' ? icon('minus') : icon('clock');
    const label = st === 'ordered' ? `${h.order.totalServings}` : st === 'skipped' ? `No ${m}` : 'Not set';
    return `<div class="hs ${st}" title="${esc(h.name)}: ${esc(label)}"><span class="dot" style="--c:${esc(h.color)}"></span>${esc(h.name)}
      <span class="st small">${st === 'ordered' ? `${icon('people')}${label}` : `${ic}`}</span></div>`;
  };

  const mealBlock = (mb) => {
    const notSet = mb.houses.filter((h) => !h.status).length;
    const prep = mb.summary.length ? mb.summary.map((c) => {
      const cat = catByName(c.category);
      return `<div class="pk-cat">${esc(cat ? cat.icon : '🍽️')} ${esc(c.category)}</div>${c.dishes.map((d) => `
        <div class="prep-row"><div class="prep-total">${d.total}<small>${d.total === 1 ? 'person' : 'people'}</small></div>
          <div class="grow"><b>${esc(d.name)}</b><div class="by-house">${d.byHouse.map((b) => `<span><span class="dot" style="--c:${esc(b.color)}"></span>${esc(b.house)} ${b.servings}</span>`).join('')}</div>
          ${d.notes.map((n) => `<div class="small" style="color:var(--warn);margin-top:3px">✎ ${esc(n)}</div>`).join('')}</div></div>`).join('')}`;
    }).join('') : '<p class="muted">Nothing ordered for this meal yet.</p>';
    const notes = mb.houses.filter((h) => h.order && h.order.notes);
    const details = mb.houses.filter((h) => h.order).map((h) => `
      <div class="house-order" style="--c:${esc(h.color)}"><div class="row between"><b>${esc(h.name)}</b>
        <span class="small muted">${h.order.status === 'skipped' ? `No ${mb.meal}` : plural(h.order.totalServings, 'serving')}</span></div>
        ${h.order.status === 'ordered' ? itemsList(h.order.items) : ''}
        <div class="tiny muted" style="margin-top:4px">by ${esc(h.order.updatedBy || '—')} · ${esc(ago(h.order.updatedAt))}</div></div>`).join('');
    return `<section class="card">
      <div class="card-head"><div class="row"><div class="meal-ico ${mb.meal}">${icon(mb.meal === 'lunch' ? 'sun' : 'moon')}</div>
        <div><h2>${cap(mb.meal)}</h2><div class="small muted">Serve at ${esc(mb.time)}</div></div></div>
        <div class="meal-total"><span class="pill accent">${plural(mb.servings, 'serving')}</span>
          <span class="pill ${notSet ? 'warn' : 'ok'}">${mb.houses.length - notSet}/${mb.houses.length} families set</span></div></div>
      <div class="house-status">${mb.houses.map((h) => houseChip(h, mb.meal)).join('')}</div>
      ${notes.length ? `<div class="stack" style="margin-top:12px;gap:6px">${notes.map((h) => `<div class="note" style="margin:0"><b>${esc(h.name)}:</b> ${esc(h.order.notes)}</div>`).join('')}</div>` : ''}
      <h3 style="margin:18px 0 2px">Prep list</h3>${prep}
      ${details ? `<details class="orders-by-house" style="margin-top:12px"><summary>Orders by family</summary><div style="margin-top:8px">${details}</div></details>` : ''}
    </section>`;
  };

  const strip = `<div class="days">${data.days.map((d) => `
    <a class="day ${d.date === date ? 'active' : ''} ${d.open ? '' : 'closed'}" href="#/kitchen/${d.date}">
      <div class="dw">${esc(d.date === data.today ? 'Today' : fmtDay(d.date, { weekday: 'short' }))}</div>
      <div class="dn">${Number(d.date.slice(8))}</div><div class="ds">${d.open ? '' : '–'}</div></a>`).join('')}</div>`;

  const lockPill = !day.open ? '<span class="pill">Closed</span>'
    : day.locked ? `<span class="pill">${icon('lock')} Orders locked</span>`
      : `<span class="pill info">${icon('clock')} Families can change until ${esc(day.lockAt)}</span>`;

  if (!paint(seq, `
    <div class="page-head"><div><div class="eyebrow">Kitchen</div><h1>${esc(dayLabel(date))}</h1><div class="muted">${esc(fullDay(date))}</div></div>
      <div class="row no-print"><button class="btn secondary sm" data-act="sound">${icon(soundOn() ? 'volume' : 'mute')} Sound ${soundOn() ? 'on' : 'off'}</button>
        <button class="btn secondary sm" data-act="print">${icon('print')} Print</button></div></div>
    <div class="section-title" style="margin-top:4px"><h2>🚨 Order now requests</h2><span class="count">${data.urgent.length ? data.urgent.length + ' open' : ''}</span></div>
    <div class="k-grid cols">${data.urgent.length ? data.urgent.map(urgentCard).join('') : '<p class="muted">No open requests right now.</p>'}</div>
    ${data.urgentDone.length ? `<details style="margin-top:10px"><summary class="small muted" style="cursor:pointer">Finished today (${data.urgentDone.length})</summary>
      <div class="list" style="margin-top:6px">${data.urgentDone.map((o) => `<div class="list-item"><span class="dot" style="--c:${esc(o.houseColor)}"></span>
        <div class="grow"><b>${esc(o.houseName)}</b> <span class="small muted">${esc(o.items.map((i) => `${i.name} ×${i.servings}`).join(', ') || o.notes)}</span></div>${urgentPill(o)}</div>`).join('')}</div></details>` : ''}
    <div class="section-title"><h2>Meal plan</h2>${lockPill}</div>
    ${strip}
    <div class="k-grid cols" style="margin-top:8px">${day.open ? day.meals.map(mealBlock).join('') : '<div class="card empty"><div class="em">😴</div><p>The kitchen is closed on this day.</p></div>'}</div>`, true)) return;
  centerActiveDay();

  const setStatus = async (el, status, extra = {}) => {
    busy(el, true, '…');
    try {
      await api(`/urgent/${el.dataset.id}/status`, { method: 'POST', body: { status, ...extra } });
      VIEWS.kitchen(S.seq, date);
    } catch (e) { busy(el, false); fail(e); }
  };
  S.actions.accept = (el) => setStatus(el, 'accepted', { eta: $(`#eta-${el.dataset.id}`).value });
  S.actions.ready = (el) => setStatus(el, 'ready');
  S.actions.delivered = (el) => setStatus(el, 'delivered');
  S.actions.decline = async (el) => {
    const reason = await ask({ title: 'Decline this order?', message: 'Tell the family why (optional).', ok: 'Decline', danger: true, input: { placeholder: 'e.g. out of chicken, try in 1 hour' } });
    if (reason === null) return;
    setStatus(el, 'declined', { note: reason });
  };
  S.actions.sound = () => {
    store.set('sh.sound', soundOn() ? '0' : '1');
    if (soundOn()) chime();
    VIEWS.kitchen(S.seq, date);
  };
  S.actions.print = () => {
    $$('details.orders-by-house').forEach((d) => { d.open = true; });
    window.print();
  };
  S.view = { refresh: () => VIEWS.kitchen(S.seq, date) };
};

/* ---------- profile ---------- */
VIEWS.me = async (seq) => {
  const push = await pushState();
  const h = myHouse();
  const role = S.user.role === 'chef' ? 'Chef' : h ? `${h.name} family` : 'Member';
  const pushInfo = {
    on: [`<span class="pill ok">${icon('check')} On for this device</span>`, '<button class="btn sm secondary" data-act="push-test">Send a test</button><button class="btn sm ghost" data-act="push-off">Turn off</button>'],
    off: ['<span class="pill">Off on this device</span>', '<button class="btn sm" data-act="push-on">Turn on notifications</button>'],
    denied: ['<span class="pill danger">Blocked</span>', '<span class="small muted">Allow notifications for this site in your browser or phone settings, then reload.</span>'],
    unsupported: ['<span class="pill warn">Not available here</span>', `<span class="small muted">${isIOS() && !isStandalone()
      ? 'On iPhone/iPad: tap <b>Share</b> → <b>Add to Home Screen</b>, then open Stack House from your home screen and come back here.'
      : 'This browser does not support notifications. Try Chrome, Edge, Firefox or Safari.'}</span>`],
    insecure: ['<span class="pill warn">Needs https</span>', '<span class="small muted">Phone notifications only work when Stack House is opened over a secure https address. You will still see alerts here in the app.</span>'],
  }[push];

  if (!paint(seq, `
    <div class="page-head"><div><div class="eyebrow">My account</div><h1>${esc(S.user.name)}</h1>
      <div class="muted">@${esc(S.user.username)} · ${esc(role)}${S.user.isAdmin ? ' · Admin' : ''}</div></div></div>
    <div class="stack">
      <div class="card stack"><div class="row between wrap"><h2>${icon('bell')} Notifications</h2>${pushInfo[0]}</div>
        <p class="small muted">${S.user.role === 'chef' || S.user.kitchenAlerts
          ? 'You get an alert for every “Order now” request, when a family sets or changes its meals, and a summary when orders lock.'
          : 'You get a daily reminder to choose tomorrow\'s food, and updates on your “Order now” requests.'}</p>
        <div class="row wrap">${pushInfo[1]}</div></div>
      ${isKitchen() ? `<div class="card row between wrap"><div><h2>Kitchen sound</h2><p class="small muted">Play a chime on this device when an “Order now” request arrives while the Kitchen page is open.</p></div>
        <label class="switch"><input type="checkbox" data-ch="sound" ${soundOn() ? 'checked' : ''}> ${soundOn() ? 'On' : 'Off'}</label></div>` : ''}
      <form class="card form-grid" data-form="pw"><h2>Change password</h2>
        <div class="field"><label for="pw0">Current password</label><input class="input" id="pw0" name="current" type="password" autocomplete="current-password" required></div>
        <div class="form-grid two">
          <div class="field"><label for="pw1">New password</label><input class="input" id="pw1" name="new" type="password" autocomplete="new-password" minlength="6" required></div>
          <div class="field"><label for="pw2">Repeat new password</label><input class="input" id="pw2" name="again" type="password" autocomplete="new-password" minlength="6" required></div></div>
        <div class="err" id="pw-err"></div><div><button class="btn" type="submit">Update password</button></div></form>
      <button class="btn secondary block" data-act="logout">${icon('logout')} Log out</button>
    </div>`)) return;
  S.actions['push-on'] = async (el) => { busy(el, true, 'Turning on…'); try { await enablePush(); toast('Notifications are on ✓'); } catch (e) { fail(e); } VIEWS.me(S.seq); };
  S.actions['push-off'] = async () => { try { await disablePush(); toast('Notifications turned off for this device'); } catch (e) { fail(e); } VIEWS.me(S.seq); };
  S.actions['push-test'] = async () => { try { await api('/push/test', { method: 'POST', body: {} }); toast('Test sent — it should pop up in a moment'); } catch (e) { fail(e); } };
  S.actions.logout = logout;
  S.inputs.sound = (el) => { store.set('sh.sound', el.checked ? '1' : '0'); if (el.checked) chime(); VIEWS.me(S.seq); };
  S.forms.pw = async (f) => {
    if (f.new.value !== f.again.value) { $('#pw-err').textContent = 'The new passwords do not match.'; return; }
    try {
      await api('/me/password', { method: 'POST', body: { current: f.current.value, new: f.new.value } });
      f.reset();
      $('#pw-err').textContent = '';
      toast('Password updated ✓');
    } catch (e) { $('#pw-err').textContent = e.message; }
  };
};

async function logout() {
  try { await disablePush(); } catch (e) { /* ignore */ }
  try { await api('/logout', { method: 'POST', body: {} }); } catch (e) { /* ignore */ }
  clearInterval(S.pollTimer);
  S.pollTimer = null;
  S.user = null;
  S.lastNotifId = null;
  S.knownUrgent = null;
  S.actHouse = null;
  await boot();
}

/* ============================== admin ============================== */
VIEWS.admin = async (seq, tab = 'menu') => {
  const tabs = [['menu', 'Menu'], ['families', 'Families'], ['people', 'People'], ['settings', 'Settings']];
  const head = `<div class="page-head"><div><div class="eyebrow">Admin</div><h1>${esc(tabs.find((t) => t[0] === tab)[1])}</h1></div></div>
    <div class="chips admin-tabs">${tabs.map(([k, l]) => `<a class="chip ${k === tab ? 'active' : ''}" href="#/admin/${k}">${l}</a>`).join('')}</div>`;
  await ADMIN[tab](seq, head);
};
const ADMIN = {};

/* --- menu --- */
ADMIN.menu = async (seq, head) => {
  let data = await api('/menu?all=1');
  let filter = 'all';
  let q = '';
  const draw = () => {
    const order = new Map(data.categories.map((c, i) => [c.id, i]));
    const list = data.dishes.filter((d) => (filter === 'all' || String(d.categoryId) === filter) && (!q || d.name.toLowerCase().includes(q)))
      .sort((a, b) => (order.get(a.categoryId) - order.get(b.categoryId)) || a.name.localeCompare(b.name));
    const counts = {};
    data.dishes.forEach((d) => { counts[d.categoryId] = (counts[d.categoryId] || 0) + 1; });
    $('#menu-cats').innerHTML = [`<button class="chip ${filter === 'all' ? 'active' : ''}" data-act="filter" data-c="all">All <span class="n">${data.dishes.length}</span></button>`]
      .concat(data.categories.map((c) => `<button class="chip ${filter === String(c.id) ? 'active' : ''}" data-act="filter" data-c="${c.id}">${esc(c.icon)} ${esc(c.name)} <span class="n">${counts[c.id] || 0}</span></button>`)).join('');
    $('#menu-list').innerHTML = list.length ? list.map((d) => {
      const c = data.categories.find((x) => x.id === d.categoryId);
      return `<div class="dish-row ${d.active ? '' : 'off'}"><div class="thumb">${d.image ? `<img src="${esc(d.image)}" alt="">` : esc(c ? c.icon : '🍽️')}</div>
        <div class="grow"><div class="pk-name">${esc(d.name)}</div><div class="small muted">${esc(c ? c.name : '')}${d.description ? ' · ' + esc(d.description) : ''}</div></div>
        <label class="switch" title="Available to order"><input type="checkbox" data-ch="avail" data-id="${d.id}" ${d.active ? 'checked' : ''} aria-label="Available"></label>
        <button class="icon-btn" data-act="edit" data-id="${d.id}" aria-label="Edit ${esc(d.name)}">${icon('edit')}</button></div>`;
    }).join('') : '<div class="empty"><div class="em">🍽️</div><p>No dishes here yet.</p></div>';
  };
  if (!paint(seq, `${head}
    <div class="row wrap" style="margin-bottom:12px"><div class="search grow" style="flex-basis:240px">${icon('search')}<input class="input" type="search" data-in="q" placeholder="Search dishes"></div>
      <button class="btn secondary" data-act="cats">${icon('list')} Categories</button>
      <button class="btn" data-act="add">${icon('plus')} Add dish</button></div>
    <div class="chips" id="menu-cats"></div>
    <div class="card" style="margin-top:8px"><div id="menu-list"></div></div>
    <p class="small muted" style="margin-top:10px">Turn a dish off to hide it from the menu without deleting it.</p>`)) return;
  draw();
  const reload = async () => { data = await api('/menu?all=1'); await loadMenu(); draw(); };
  S.actions.filter = (el) => { filter = el.dataset.c; draw(); };
  S.inputs.q = (el) => { q = el.value.trim().toLowerCase(); draw(); };
  S.inputs.avail = async (el) => {
    try { await api(`/dishes/${el.dataset.id}`, { method: 'PUT', body: { active: el.checked } }); await reload(); }
    catch (e) { fail(e); el.checked = !el.checked; }
  };
  S.actions.add = () => dishEditor(null, data.categories, filter !== 'all' ? Number(filter) : null, reload);
  S.actions.edit = (el) => dishEditor(data.dishes.find((d) => d.id === Number(el.dataset.id)), data.categories, null, reload);
  S.actions.cats = () => categoryEditor(data.categories, reload);
};

function resizeImage(file, max = 1000) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale);
      c.height = Math.round(img.height * scale);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', 0.84));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('That file is not a picture we can read.')); };
    img.src = url;
  });
}

function dishEditor(dish, cats, defaultCat, onSaved) {
  let image; // undefined = unchanged, null = remove, string = new data URL
  const current = () => (image === undefined ? dish && dish.image : image);
  const catOf = (id) => cats.find((c) => c.id === id);
  const sheet = openSheet({
    title: dish ? 'Edit dish' : 'Add a dish',
    body: `<div class="photo-pick"><div class="thumb" id="de-thumb"></div><div class="stack" style="gap:6px">
        <label class="btn sm secondary">${icon('camera')} Choose photo<input type="file" accept="image/*" id="de-file" hidden></label>
        <button class="btn sm ghost" data-sact="rmimg" id="de-rm">Remove photo</button></div></div>
      <div class="field"><label for="de-name">Name</label><input class="input" id="de-name" maxlength="80" value="${esc(dish ? dish.name : '')}"></div>
      <div class="field"><label for="de-cat">Category</label><select class="input" id="de-cat">${cats.map((c) => `<option value="${c.id}" ${(dish ? dish.categoryId : defaultCat) === c.id ? 'selected' : ''}>${esc(c.icon)} ${esc(c.name)}</option>`).join('')}</select></div>
      <div class="field"><label for="de-desc">Description (optional)</label><textarea class="input" id="de-desc" maxlength="300" rows="2">${esc(dish ? dish.description : '')}</textarea></div>
      <label class="switch"><input type="checkbox" id="de-active" ${!dish || dish.active ? 'checked' : ''}> Available to order</label>
      <div class="err" id="de-err"></div>`,
    foot: `${dish ? `<button class="btn danger-ghost" data-sact="del" style="margin-right:auto">${icon('trash')} Delete</button>` : ''}
      <button class="btn secondary" data-sact="close">Cancel</button><button class="btn" data-sact="save">Save</button>`,
    actions: {
      rmimg: () => { image = null; drawThumb(); },
      save: async (el, _e, s) => {
        const body = { name: $('#de-name', s.el).value, categoryId: Number($('#de-cat', s.el).value),
          description: $('#de-desc', s.el).value, active: $('#de-active', s.el).checked };
        if (image !== undefined) body.image = image;
        busy(el, true);
        try {
          await api(dish ? `/dishes/${dish.id}` : '/dishes', { method: dish ? 'PUT' : 'POST', body });
          s.close();
          toast(dish ? 'Dish updated' : 'Dish added');
          onSaved();
        } catch (e) { busy(el, false); $('#de-err', s.el).textContent = e.message; }
      },
      del: async (_el, _e, s) => {
        if (!(await ask({ title: `Delete ${dish.name}?`, message: 'It will be removed from the menu. Past orders keep its name. To hide it for a while, turn off “Available” instead.', ok: 'Delete', danger: true }))) return;
        try { await api(`/dishes/${dish.id}`, { method: 'DELETE', body: {} }); s.close(); toast('Dish deleted'); onSaved(); }
        catch (e) { fail(e); }
      },
    },
  });
  function drawThumb() {
    const src = current();
    const cat = catOf(Number($('#de-cat', sheet.el).value));
    $('#de-thumb', sheet.el).innerHTML = src ? `<img src="${esc(src)}" alt="">` : esc(cat ? cat.icon : '🍽️');
    $('#de-rm', sheet.el).hidden = !src;
  }
  $('#de-cat', sheet.el).addEventListener('change', drawThumb);
  $('#de-file', sheet.el).addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try { image = await resizeImage(f); drawThumb(); } catch (err) { fail(err); }
  });
  drawThumb();
  setTimeout(() => { if (!dish) $('#de-name', sheet.el).focus(); }, 60);
}

function categoryEditor(cats, onChanged) {
  let list = cats;
  const sheet = openSheet({
    title: 'Categories',
    cls: 'small',
    body: '',
    actions: {
      up: (el) => move(el, 'up'),
      down: (el) => move(el, 'down'),
      del: async (el) => {
        const c = list.find((x) => x.id === Number(el.dataset.id));
        if (!(await ask({ title: `Delete ${c.name}?`, ok: 'Delete', danger: true }))) return;
        try { list = (await api(`/categories/${c.id}`, { method: 'DELETE', body: {} })).categories; draw(); onChanged(); } catch (e) { fail(e); }
      },
      add: async () => {
        const name = $('#cat-new', sheet.el).value.trim();
        const ic = $('#cat-new-icon', sheet.el).value.trim();
        if (!name) return;
        try { list = (await api('/categories', { method: 'POST', body: { name, icon: ic } })).categories; draw(); onChanged(); } catch (e) { fail(e); }
      },
    },
  });
  async function move(el, dir) {
    try { list = (await api(`/categories/${el.dataset.id}`, { method: 'PUT', body: { move: dir } })).categories; draw(); onChanged(); } catch (e) { fail(e); }
  }
  function draw() {
    sheet.body(`<p class="small muted">Rename a category or change its emoji, then click outside the box to save.</p>
      <div class="list">${list.map((c, i) => `<div class="list-item">
        <input class="input" style="width:58px;text-align:center" maxlength="8" value="${esc(c.icon)}" data-cid="${c.id}" data-f="icon" aria-label="Emoji">
        <input class="input grow" maxlength="40" value="${esc(c.name)}" data-cid="${c.id}" data-f="name" aria-label="Name">
        <button class="icon-btn" data-sact="up" data-id="${c.id}" ${i === 0 ? 'disabled' : ''} aria-label="Move up">${icon('up')}</button>
        <button class="icon-btn" data-sact="down" data-id="${c.id}" ${i === list.length - 1 ? 'disabled' : ''} aria-label="Move down">${icon('down')}</button>
        <button class="icon-btn" data-sact="del" data-id="${c.id}" aria-label="Delete">${icon('trash')}</button></div>`).join('')}</div>
      <div class="row"><input class="input" id="cat-new-icon" style="width:58px;text-align:center" maxlength="8" placeholder="🍽️" aria-label="Emoji">
        <input class="input grow" id="cat-new" maxlength="40" placeholder="New category, e.g. Breakfast">
        <button class="btn" data-sact="add">Add</button></div>`);
  }
  sheet.el.addEventListener('change', async (e) => {
    const inp = e.target.closest('[data-cid]');
    if (!inp) return;
    try {
      list = (await api(`/categories/${inp.dataset.cid}`, { method: 'PUT', body: { [inp.dataset.f]: inp.value } })).categories;
      toast('Saved');
      onChanged();
    } catch (err) { fail(err); draw(); }
  });
  draw();
}

/* --- families --- */
ADMIN.families = async (seq, head) => {
  const { houses } = await api('/admin/houses');
  if (!paint(seq, `${head}
    <p class="muted" style="margin-bottom:12px">“People” is the usual number of people in the family — it's the starting number when they add a dish.</p>
    <div class="stack">${houses.map((h) => `
      <div class="card"><div class="row wrap">
        <input type="color" class="color-input" value="${esc(h.color)}" data-h="${h.id}" data-f="color" aria-label="Color">
        <div class="field grow"><label>Family name</label><input class="input" maxlength="40" value="${esc(h.name)}" data-h="${h.id}" data-f="name"></div>
        <div class="field" style="width:110px"><label>People</label><input class="input" type="number" min="1" max="99" value="${h.people}" data-h="${h.id}" data-f="people"></div></div>
        <div class="card-foot"><span class="small muted">${plural(h.members, 'member')}</span>
          <div class="row">${h.members ? '' : `<button class="btn sm danger-ghost" data-act="del" data-id="${h.id}">${icon('trash')} Delete</button>`}
          <button class="btn sm" data-act="save" data-id="${h.id}">Save</button></div></div></div>`).join('')}
      <div class="card row wrap"><div class="field grow"><label for="nh">Add a family</label><input class="input" id="nh" maxlength="40" placeholder="Family name"></div>
        <button class="btn" data-act="add" style="align-self:flex-end">${icon('plus')} Add</button></div>
    </div>`)) return;
  const after = async (msg) => { const b = await api('/bootstrap'); S.boot.houses = b.houses; renderShell(); toast(msg); VIEWS.admin(S.seq, 'families'); };
  S.actions.save = async (el) => {
    const id = el.dataset.id;
    const val = (f) => $(`[data-h="${id}"][data-f="${f}"]`).value;
    try { await api(`/admin/houses/${id}`, { method: 'PUT', body: { name: val('name'), color: val('color'), people: Number(val('people')) } }); after('Family saved'); }
    catch (e) { fail(e); }
  };
  S.actions.del = async (el) => {
    if (!(await ask({ title: 'Delete this family?', ok: 'Delete', danger: true }))) return;
    try { await api(`/admin/houses/${el.dataset.id}`, { method: 'DELETE', body: {} }); after('Family deleted'); } catch (e) { fail(e); }
  };
  S.actions.add = async () => {
    const name = $('#nh').value.trim();
    if (!name) return;
    try { await api('/admin/houses', { method: 'POST', body: { name } }); after('Family added'); } catch (e) { fail(e); }
  };
};

/* --- people --- */
ADMIN.people = async (seq, head) => {
  const { users } = await api('/admin/users');
  const groups = S.boot.houses.map((h) => [h, users.filter((u) => u.role === 'member' && u.houseId === h.id)]);
  const chefs = users.filter((u) => u.role === 'chef');
  const row = (u) => {
    const h = houseById(u.houseId);
    return `<div class="list-item"><span class="avatar" ${h ? `style="--c:${esc(h.color)}"` : ''}>${esc(initials(u.name))}</span>
      <div class="grow"><div class="pk-name">${esc(u.name)} <span class="small muted">@${esc(u.username)}</span></div>
        <div class="row wrap" style="gap:6px;margin-top:3px">${u.isAdmin ? '<span class="pill accent">Admin</span>' : ''}${u.role === 'chef' ? '<span class="pill info">Chef</span>' : ''}
          ${u.kitchenAlerts && u.role !== 'chef' ? '<span class="pill">Kitchen alerts</span>' : ''}${u.active ? '' : '<span class="pill danger">Inactive</span>'}
          ${u.lastLoginAt ? `<span class="tiny muted">last login ${esc(ago(u.lastLoginAt))}</span>` : '<span class="tiny muted">never logged in</span>'}</div></div>
      <button class="icon-btn" data-act="edit" data-id="${u.id}" aria-label="Edit ${esc(u.name)}">${icon('edit')}</button></div>`;
  };
  if (!paint(seq, `${head}
    <div class="row between wrap" style="margin-bottom:12px"><p class="muted">Everyone logs in with their own username and password.</p>
      <button class="btn" data-act="add">${icon('plus')} Add person</button></div>
    <div class="stack">
      ${groups.map(([h, us]) => `<div class="card"><div class="card-head"><span class="house-tag"><span class="dot" style="--c:${esc(h.color)}"></span>${esc(h.name)} family</span>
        <span class="small muted">${plural(us.length, 'person', 'people')}</span></div>
        ${us.length ? `<div class="list">${us.map(row).join('')}</div>` : '<p class="small muted">No one yet.</p>'}</div>`).join('')}
      <div class="card"><div class="card-head"><span class="house-tag">👨‍🍳 Kitchen</span></div>
        ${chefs.length ? `<div class="list">${chefs.map(row).join('')}</div>` : '<p class="small muted">Add the chef so they get “Order now” alerts and the daily kitchen summary.</p>'}</div>
    </div>`)) return;
  const reload = () => VIEWS.admin(S.seq, 'people');
  S.actions.add = () => userEditor(null, reload);
  S.actions.edit = (el) => userEditor(users.find((u) => u.id === Number(el.dataset.id)), reload);
};

function userEditor(u, onSaved) {
  const st = { role: u ? u.role : 'member' };
  const self = u && u.id === S.user.id;
  const sheet = openSheet({
    title: u ? `Edit ${u.name}` : 'Add a person',
    body: '',
    foot: `${u && !self ? `<button class="btn danger-ghost" data-sact="del" style="margin-right:auto">${icon('trash')} Delete</button>` : ''}
      <button class="btn secondary" data-sact="close">Cancel</button><button class="btn" data-sact="save">Save</button>`,
    actions: {
      role: (el) => { keep(); st.role = el.dataset.v; draw(); },
      save: async (el, _e, s) => {
        keep();
        const body = { name: st.name, username: st.username, role: st.role, houseId: st.role === 'member' ? Number(st.houseId) : null,
          isAdmin: st.isAdmin, kitchenAlerts: st.kitchenAlerts };
        if (u) body.active = st.active;
        if (st.password) body.password = st.password;
        busy(el, true);
        try {
          await api(u ? `/admin/users/${u.id}` : '/admin/users', { method: u ? 'PUT' : 'POST', body });
          s.close();
          toast(u ? 'Saved' : `${st.name} can now log in as “${st.username.toLowerCase()}”`);
          if (self) { const b = await api('/bootstrap'); S.user = b.user; renderShell(); }
          onSaved();
        } catch (e) { busy(el, false); $('#ue-err', s.el).textContent = e.message; }
      },
      del: async (_el, _e, s) => {
        if (!(await ask({ title: `Delete ${u.name}?`, message: 'They will no longer be able to log in. Their past orders stay. You can also just turn off “Active”.', ok: 'Delete', danger: true }))) return;
        try { await api(`/admin/users/${u.id}`, { method: 'DELETE', body: {} }); s.close(); toast('Deleted'); onSaved(); } catch (e) { fail(e); }
      },
    },
  });
  Object.assign(st, {
    name: u ? u.name : '', username: u ? u.username : '', password: '',
    houseId: u && u.houseId ? u.houseId : S.boot.houses[0] && S.boot.houses[0].id,
    isAdmin: u ? u.isAdmin : false, kitchenAlerts: u ? u.kitchenAlerts : false, active: u ? u.active : true,
  });
  function keep() {
    const v = (id) => $(id, sheet.el);
    if (!v('#ue-name')) return;
    st.name = v('#ue-name').value.trim();
    st.username = v('#ue-user').value.trim();
    st.password = v('#ue-pass').value;
    if (v('#ue-house')) st.houseId = v('#ue-house').value;
    st.isAdmin = v('#ue-admin').checked;
    st.kitchenAlerts = st.role === 'chef' ? true : v('#ue-alerts').checked;
    if (v('#ue-active')) st.active = v('#ue-active').checked;
  }
  function draw() {
    sheet.body(`
      <div class="form-grid two">
        <div class="field"><label for="ue-name">Name</label><input class="input" id="ue-name" maxlength="60" value="${esc(st.name)}"></div>
        <div class="field"><label for="ue-user">Username</label><input class="input" id="ue-user" maxlength="32" autocapitalize="none" spellcheck="false" value="${esc(st.username)}"></div></div>
      <div class="field"><label for="ue-pass">${u ? 'New password (leave empty to keep the current one)' : 'Password (at least 6 characters)'}</label>
        <input class="input" id="ue-pass" type="text" autocomplete="off" value="${esc(st.password)}"></div>
      <div class="field"><span class="label">Role</span><div class="seg">
        <button data-sact="role" data-v="member" class="${st.role === 'member' ? 'on' : ''}">${icon('people')} Family member</button>
        <button data-sact="role" data-v="chef" class="${st.role === 'chef' ? 'on' : ''}">${icon('pot')} Chef</button></div></div>
      ${st.role === 'member' ? `<div class="field"><label for="ue-house">Family</label><select class="input" id="ue-house">
        ${S.boot.houses.map((h) => `<option value="${h.id}" ${String(h.id) === String(st.houseId) ? 'selected' : ''}>${esc(h.name)}</option>`).join('')}</select></div>` : ''}
      <label class="switch"><input type="checkbox" id="ue-admin" ${st.isAdmin ? 'checked' : ''} ${self ? 'disabled' : ''}> Admin — can edit the menu, people and settings</label>
      ${st.role === 'member' ? `<label class="switch"><input type="checkbox" id="ue-alerts" ${st.kitchenAlerts ? 'checked' : ''}> Kitchen alerts — also receive the chef's notifications</label>` : '<input type="checkbox" id="ue-alerts" checked hidden>'}
      ${u ? `<label class="switch"><input type="checkbox" id="ue-active" ${st.active ? 'checked' : ''} ${self ? 'disabled' : ''}> Active — can log in</label>` : ''}
      <div class="err" id="ue-err"></div>`);
  }
  draw();
}

/* --- settings --- */
ADMIN.settings = async (seq, head) => {
  const tzs = (await api('/admin/timezones')).timezones;
  const C = JSON.parse(JSON.stringify(S.boot.settings));
  let snapshot = JSON.stringify(C);
  const dirty = () => JSON.stringify(C) !== snapshot;
  const DAYN = { sun: 'Sunday', mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday', thu: 'Thursday', fri: 'Friday', sat: 'Saturday' };
  const deviceTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  const draw = () => {
    paint(S.seq, `${head}<div class="stack">
      <div class="card stack"><h2>${icon('clock')} Kitchen timezone</h2>
        <p class="small muted">All times below are in this timezone.</p>
        <div class="row wrap"><select class="input grow" data-ch="cfg" data-p="timezone">${tzs.map((t) => `<option ${t === C.timezone ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>
        ${deviceTz && deviceTz !== C.timezone && tzs.includes(deviceTz) ? `<button class="btn sm secondary" data-act="tz">Use ${esc(deviceTz)}</button>` : ''}</div></div>

      <div class="card stack"><h2>Meals</h2><p class="small muted">Turn a meal off if the kitchen doesn't serve it. Families can always say “No lunch” or “No dinner” for a day.</p>
        ${['lunch', 'dinner'].map((m) => `<div class="row wrap"><label class="switch grow"><input type="checkbox" data-ch="cfg" data-p="meals.${m}.enabled" ${C.meals[m].enabled ? 'checked' : ''}> <b>${cap(m)}</b></label>
          <span class="small muted">served at</span><input class="input time" type="time" data-ch="cfg" data-p="meals.${m}.time" value="${esc(C.meals[m].time)}" aria-label="${cap(m)} time"></div>`).join('')}</div>

      <div class="card"><h2>Working hours</h2><p class="small muted" style="margin:4px 0 8px">“Order now” requests are only possible during these hours. On closed days there is no lunch or dinner.</p>
        ${Object.keys(DAYN).map((d) => { const w = C.workingHours[d]; return `<div class="wh-row ${w.open ? '' : 'off'}"><b>${DAYN[d].slice(0, 3)}</b>
          <label class="switch"><input type="checkbox" data-ch="cfg" data-p="workingHours.${d}.open" ${w.open ? 'checked' : ''} aria-label="${DAYN[d]} open"></label>
          <div class="wh-times">${w.open ? '' : '<span class="small muted">Closed</span>'}<input class="input time" type="time" data-ch="cfg" data-p="workingHours.${d}.start" value="${esc(w.start)}" aria-label="${DAYN[d]} opens">
            <span class="muted">–</span><input class="input time" type="time" data-ch="cfg" data-p="workingHours.${d}.end" value="${esc(w.end === '24:00' ? '23:59' : w.end)}" aria-label="${DAYN[d]} closes"></div></div>`; }).join('')}</div>

      <div class="card stack"><h2>Ordering</h2>
        <div class="row wrap"><span>Plans for a day lock at</span><input class="input time" type="time" data-ch="cfg" data-p="cutoff.time" value="${esc(C.cutoff.time)}" aria-label="Lock time">
          <select class="input" style="width:auto" data-ch="cfg" data-p="cutoff.dayOffset" data-num="1">
            ${[[1, 'the day before'], [0, 'on the same day'], [2, 'two days before']].map(([v, l]) => `<option value="${v}" ${C.cutoff.dayOffset === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div class="row wrap"><span>Families can plan</span><input class="input" style="width:90px" type="number" min="1" max="30" data-ch="cfg" data-p="daysAhead" data-num="1" value="${C.daysAhead}" aria-label="Days ahead"><span>days ahead</span></div>
        <label class="switch"><input type="checkbox" data-ch="cfg" data-p="urgentOnlyWhenOpen" ${C.urgentOnlyWhenOpen ? 'checked' : ''}> Only allow “Order now” during working hours</label></div>

      <div class="card stack"><h2>${icon('bell')} Daily reminders</h2>
        <p class="small muted">Every day at these times, families that haven't chosen tomorrow's food get a reminder. The chef gets a summary when orders lock, and a morning brief when the kitchen opens.</p>
        <div class="tag-list">${C.reminderTimes.map((t, i) => `<span class="pill accent">${esc(t)}<button data-act="rm-rem" data-i="${i}" aria-label="Remove ${esc(t)}">${icon('x')}</button></span>`).join('') || '<span class="small muted">No reminders.</span>'}</div>
        <div class="row"><input class="input time" type="time" id="new-rem" aria-label="New reminder time"><button class="btn sm secondary" data-act="add-rem">${icon('plus')} Add time</button></div></div>

      <div class="card stack"><h2>Closed days</h2><p class="small muted">Holidays or days off — no meals and no reminders.</p>
        <div class="tag-list">${C.closedDates.map((d, i) => `<span class="pill">${esc(fmtDay(d, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }))}<button data-act="rm-closed" data-i="${i}" aria-label="Remove">${icon('x')}</button></span>`).join('') || '<span class="small muted">None.</span>'}</div>
        <div class="row"><input class="input" style="width:auto" type="date" id="new-closed" aria-label="Closed date"><button class="btn sm secondary" data-act="add-closed">${icon('plus')} Add day</button></div></div>

      <div class="card row between wrap"><div class="grow"><h2>Backup</h2><p class="small muted">Download everything — people, menu, orders, settings and dish photos — as one zip file. Keep a copy somewhere safe now and then.</p></div>
        <a class="btn secondary" href="/api/admin/backup" download>Download backup</a></div>
    </div>
    <div class="save-bar" id="save-bar"></div>`);
    bar();
  };
  const bar = () => {
    $('#save-bar').innerHTML = `<div class="grow small">${dirty() ? 'You have unsaved changes' : 'All changes saved'}</div>
      <button class="btn" data-act="save" ${dirty() ? '' : 'disabled'}>Save settings</button>`;
  };
  const setPath = (path, value) => {
    const keys = path.split('.');
    let o = C;
    keys.slice(0, -1).forEach((k) => { o = o[k]; });
    o[keys[keys.length - 1]] = value;
  };
  if (seq !== S.seq) return;
  draw();
  S.inputs.cfg = (el) => {
    const v = el.type === 'checkbox' ? el.checked : el.dataset.num ? Number(el.value) : el.value;
    setPath(el.dataset.p, v);
    if (el.type === 'checkbox') draw(); else bar();
  };
  S.actions.tz = () => { C.timezone = deviceTz; draw(); };
  S.actions['add-rem'] = () => { const v = $('#new-rem').value; if (v && !C.reminderTimes.includes(v)) { C.reminderTimes.push(v); C.reminderTimes.sort(); } draw(); };
  S.actions['rm-rem'] = (el) => { C.reminderTimes.splice(Number(el.dataset.i), 1); draw(); };
  S.actions['add-closed'] = () => { const v = $('#new-closed').value; if (v && !C.closedDates.includes(v)) { C.closedDates.push(v); C.closedDates.sort(); } draw(); };
  S.actions['rm-closed'] = (el) => { C.closedDates.splice(Number(el.dataset.i), 1); draw(); };
  S.actions.save = async (el) => {
    busy(el, true);
    try {
      const res = await api('/admin/settings', { method: 'PUT', body: C });
      S.boot.settings = res.settings;
      S.boot.kitchen = res.kitchen;
      Object.assign(C, JSON.parse(JSON.stringify(res.settings)));
      snapshot = JSON.stringify(C);
      draw();
      toast('Settings saved ✓');
    } catch (e) { busy(el, false); fail(e); }
  };
  S.view = { isDirty: dirty };
};

/* ============================== boot ============================== */
async function boot() {
  try {
    S.boot = await api('/bootstrap');
  } catch (e) {
    $('#view').innerHTML = `<div class="empty"><div class="em">📡</div><p>${esc(e.message)}</p>
      <p style="margin-top:12px"><button class="btn secondary" data-act="reload">Try again</button></p></div>`;
    return;
  }
  S.user = S.boot.user;
  if (S.user) {
    S.version = S.boot.version;
    S.actHouse = S.user.houseId;
    await loadMenu();
    renderShell();
    startPolling();
  } else {
    $('#header').hidden = true;
    $('#tabbar').hidden = true;
  }
  await route();
}

boot();
