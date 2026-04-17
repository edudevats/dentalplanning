// ── DOM helpers ───────────────────────────────────────────────────────────────
function domEl(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text != null) el.textContent = text;
  return el;
}

function domIcon(name, cls) {
  const i = document.createElement('i');
  i.setAttribute('data-lucide', name);
  i.className = cls || 'h-4 w-4';
  return i;
}

// ── Escape HTML ───────────────────────────────────────────────────────────────
function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Mark a string as safe HTML (trusted, server-controlled data)
function safe(html) {
  return { __safe: true, html: String(html) };
}

function renderVal(v) {
  if (v && typeof v === 'object' && v.__safe) return v.html;
  return esc(v);
}

// ── Auth ──────────────────────────────────────────────────────────────────────
const Auth = {
  getToken: () => localStorage.getItem('token'),
  setToken: (t) => localStorage.setItem('token', t),
  removeToken: () => localStorage.removeItem('token'),

  check() {
    if (!this.getToken()) {
      window.location.href = '/login';
      return false;
    }
    return true;
  },

  logout() {
    this.removeToken();
    window.location.href = '/login';
  },

  redirectIfLoggedIn() {
    if (this.getToken()) {
      window.location.href = '/dashboard';
      return true;
    }
    return false;
  },
};

// ── API Client ────────────────────────────────────────────────────────────────
const API = {
  async request(url, options = {}) {
    const token = Auth.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    };

    const res = await fetch('/api/v1' + url, { ...options, headers });

    if (res.status === 401) {
      Auth.removeToken();
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (res.status === 204) return null;

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const err = new Error(data.message || data.error || 'Error en la solicitud');
      err.response = { data, status: res.status };
      throw err;
    }

    return data;
  },

  get: (url) => API.request(url),
  post: (url, body) => API.request(url, { method: 'POST', body: JSON.stringify(body) }),
  put: (url, body) => API.request(url, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (url) => API.request(url, { method: 'DELETE' }),
};

// ── Toast ─────────────────────────────────────────────────────────────────────
const Toast = {
  _container: null,
  _id: 0,

  _getContainer() {
    if (!this._container) {
      this._container = document.createElement('div');
      this._container.className =
        'fixed bottom-4 right-4 z-[100] flex flex-col-reverse gap-2 pointer-events-none';
      this._container.setAttribute('aria-live', 'polite');
      document.body.appendChild(this._container);
    }
    return this._container;
  },

  show(message, variant = 'info', duration = 4000) {
    const cfgs = {
      success: { border: 'border-green-500', text: 'text-green-800', ic: 'text-green-600', icon: '✓' },
      error:   { border: 'border-red-500',   text: 'text-red-800',   ic: 'text-red-600',   icon: '✕' },
      warning: { border: 'border-amber-500', text: 'text-amber-800', ic: 'text-amber-600', icon: '!' },
      info:    { border: 'border-blue-400',  text: 'text-blue-800',  ic: 'text-blue-500',  icon: 'i' },
    };
    const c = cfgs[variant] || cfgs.info;
    const id = `toast-${++this._id}`;

    const wrap = document.createElement('div');
    wrap.id = id;
    wrap.setAttribute('role', 'alert');
    wrap.className = `pointer-events-auto flex items-start gap-3 w-80 rounded-lg border-l-4 p-4 shadow-lg bg-white ${c.border} ${c.text} transition-all duration-200`;

    const icon = document.createElement('span');
    icon.className = `text-sm font-bold shrink-0 mt-0.5 ${c.ic}`;
    icon.textContent = c.icon;

    const msg = document.createElement('p');
    msg.className = 'flex-1 text-sm font-body leading-snug';
    msg.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'shrink-0 text-gray-400 hover:text-gray-700 cursor-pointer text-sm leading-none';
    closeBtn.textContent = '×';
    closeBtn.addEventListener('click', () => this._remove(id));

    wrap.appendChild(icon);
    wrap.appendChild(msg);
    wrap.appendChild(closeBtn);
    this._getContainer().appendChild(wrap);

    if (duration > 0) setTimeout(() => this._remove(id), duration);
  },

  _remove(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.opacity = '0';
    el.style.transform = 'translateX(1rem)';
    setTimeout(() => el.remove(), 200);
  },

  success: (msg, dur) => Toast.show(msg, 'success', dur),
  error:   (msg, dur) => Toast.show(msg, 'error', dur),
  warning: (msg, dur) => Toast.show(msg, 'warning', dur),
  info:    (msg, dur) => Toast.show(msg, 'info', dur),
};

// ── Modal ─────────────────────────────────────────────────────────────────────
const Modal = {
  open(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    setTimeout(() => {
      const f = el.querySelector('input:not([disabled]),select:not([disabled]),textarea,button');
      f?.focus();
    }, 50);
  },

  close(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('hidden');
    document.body.style.overflow = '';
  },
};

// ── Icons (SVG strings — internal use only, not user data) ────────────────────
const Icons = {
  eye:      `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>`,
  pencil:   `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>`,
  trash:    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>`,
  copy:     `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`,
  download: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>`,
  loader:   `<svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>`,
};

// ── Format helpers ────────────────────────────────────────────────────────────
function fmt(v) {
  return '$' + Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pct(v) {
  return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso);
  return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
}

function alignCls(a) {
  if (a === 'right') return 'text-right';
  if (a === 'center') return 'text-center';
  return 'text-left';
}

// ── Badge (returns safe HTML — values from API) ───────────────────────────────
function badge(text, variant = 'neutral') {
  const variants = {
    success: 'bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/20',
    warning: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20',
    danger:  'bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20',
    info:    'bg-cyan-50 text-cyan-700 ring-1 ring-inset ring-cyan-600/20',
    neutral: 'bg-gray-100 text-gray-700 ring-1 ring-inset ring-gray-500/20',
  };
  return safe(`<span class="inline-flex items-center rounded-full font-medium font-body whitespace-nowrap px-2.5 py-0.5 text-xs ${variants[variant] || variants.neutral}">${esc(text)}</span>`);
}

function badgeEl(text, variant = 'neutral') {
  const variants = {
    success: 'bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/20',
    warning: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20',
    danger:  'bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20',
    info:    'bg-cyan-50 text-cyan-700 ring-1 ring-inset ring-cyan-600/20',
    neutral: 'bg-gray-100 text-gray-700 ring-1 ring-inset ring-gray-500/20',
  };
  const span = document.createElement('span');
  span.className = 'inline-flex items-center rounded-full font-medium font-body whitespace-nowrap px-2.5 py-0.5 text-xs ' + (variants[variant] || variants.neutral);
  span.textContent = String(text);
  return span;
}

// ── Table renderer ────────────────────────────────────────────────────────────
// columns: [{ key, label, align, render(val, row) → string | safe() }]
function renderTable(containerId, columns, data, emptyMessage, loading) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Build header
  const thead = document.createElement('thead');
  const hrow = document.createElement('tr');
  hrow.className = 'bg-surface-alt';
  columns.forEach(col => {
    const th = document.createElement('th');
    th.className = `px-4 py-3 text-xs font-semibold uppercase tracking-wider text-text-secondary ${alignCls(col.align)}`;
    th.textContent = typeof col.label === 'string' ? col.label : '';
    hrow.appendChild(th);
  });
  thead.appendChild(hrow);

  const table = document.createElement('table');
  table.className = 'w-full min-w-[600px] text-sm font-body';
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  tbody.className = 'bg-surface';

  if (loading) {
    for (let i = 0; i < 5; i++) {
      const row = document.createElement('tr');
      row.className = 'border-b border-border';
      columns.forEach(() => {
        const td = document.createElement('td');
        td.className = 'px-4 py-3';
        const skel = document.createElement('div');
        skel.className = 'h-4 bg-surface-alt rounded animate-pulse w-3/4';
        td.appendChild(skel);
        row.appendChild(td);
      });
      tbody.appendChild(row);
    }
  } else if (!data || !data.length) {
    const row = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = columns.length;
    td.className = 'px-4 py-12 text-center text-sm text-text-muted';
    td.textContent = emptyMessage || 'No se encontraron registros';
    row.appendChild(td);
    tbody.appendChild(row);
  } else {
    data.forEach(rowData => {
      const tr = document.createElement('tr');
      tr.className = 'border-b border-border hover:bg-surface-hover transition-colors duration-100';
      columns.forEach(col => {
        const td = document.createElement('td');
        td.className = `px-4 py-3 text-text-primary ${alignCls(col.align)}`;
        const val = rowData[col.key];
        if (col.render) {
          const result = col.render(val, rowData);
          if (result instanceof Node) {
            td.appendChild(result);
          } else if (result && typeof result === 'object' && result.__safe) {
            // Trusted HTML from our own rendering functions
            td.innerHTML = result.html;
          } else {
            td.textContent = result == null ? '' : String(result);
          }
        } else {
          td.textContent = val == null ? '' : String(val);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  table.appendChild(tbody);

  const wrap = document.createElement('div');
  wrap.className = 'w-full overflow-x-auto rounded-lg border border-border';
  wrap.appendChild(table);

  container.replaceChildren(wrap);
}

// ── Stat card update ──────────────────────────────────────────────────────────
function updateStat(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

// ── User info ─────────────────────────────────────────────────────────────────
async function loadUserInfo() {
  try {
    const data = await API.get('/auth/me');
    const user = data.user || data;
    const name = user.name || 'Usuario';
    const role = user.role || 'Administrador';
    const initials = name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '??';

    document.querySelectorAll('[data-user-name]').forEach(el => { el.textContent = name; });
    document.querySelectorAll('[data-user-role]').forEach(el => { el.textContent = role; });
    document.querySelectorAll('[data-user-initials]').forEach(el => { el.textContent = initials; });
    return user;
  } catch {
    Auth.logout();
  }
}

// ── Active nav ────────────────────────────────────────────────────────────────
function setActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll('[data-nav-path]').forEach(el => {
    const navPath = el.getAttribute('data-nav-path');
    const isActive = path === navPath || (navPath !== '/dashboard' && path.startsWith(navPath + '/'));
    if (isActive) {
      el.classList.add('bg-primary-50', 'text-primary-700', 'border-r-2', 'border-primary-500');
      el.classList.remove('text-text-secondary');
    } else {
      el.classList.remove('bg-primary-50', 'text-primary-700', 'border-r-2', 'border-primary-500');
      el.classList.add('text-text-secondary');
    }
  });
}

// ── Mobile sidebar ────────────────────────────────────────────────────────────
function initMobileSidebar() {
  const btn = document.getElementById('sidebar-toggle');
  const overlay = document.getElementById('sidebar-overlay');
  const sidebar = document.getElementById('mobile-sidebar');
  const closeBtn = document.getElementById('sidebar-close');

  function openSidebar() {
    sidebar?.classList.remove('-translate-x-full');
    overlay?.classList.remove('hidden');
  }
  function closeSidebar() {
    sidebar?.classList.add('-translate-x-full');
    overlay?.classList.add('hidden');
  }

  btn?.addEventListener('click', openSidebar);
  overlay?.addEventListener('click', closeSidebar);
  closeBtn?.addEventListener('click', closeSidebar);
}

// ── Month/Year option builders ────────────────────────────────────────────────
function buildMonthOptions(sel) {
  const months = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  return months.map((m, i) => {
    const opt = document.createElement('option');
    opt.value = String(i + 1);
    opt.textContent = m;
    if (String(i + 1) === String(sel)) opt.selected = true;
    return opt;
  });
}

function buildYearOptions(sel, range = 4) {
  const cur = new Date().getFullYear();
  const opts = [];
  for (let y = cur + 1; y >= cur - range; y--) {
    const opt = document.createElement('option');
    opt.value = String(y);
    opt.textContent = String(y);
    if (String(y) === String(sel)) opt.selected = true;
    opts.push(opt);
  }
  return opts;
}

function populateSelect(el, options, selectedVal, placeholder) {
  el.replaceChildren();
  if (placeholder) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = placeholder;
    opt.disabled = true;
    if (!selectedVal) opt.selected = true;
    el.appendChild(opt);
  }
  options.forEach(({ value, label }) => {
    const opt = document.createElement('option');
    opt.value = String(value);
    opt.textContent = label;
    if (String(value) === String(selectedVal)) opt.selected = true;
    el.appendChild(opt);
  });
}
