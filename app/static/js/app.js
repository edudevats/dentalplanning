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

  getRefreshToken: () => localStorage.getItem('refresh_token'),
  setRefreshToken: (t) => localStorage.setItem('refresh_token', t),
  removeRefreshToken: () => localStorage.removeItem('refresh_token'),

  _refreshing: null,

  // Renueva el access token usando el refresh token. Single-flight: si ya hay
  // una renovación en curso, reusa la misma promesa para no llamar /refresh
  // varias veces cuando coinciden muchos 401. Devuelve el nuevo access token,
  // o null si no se pudo renovar.
  refreshAccessToken() {
    if (this._refreshing) return this._refreshing;
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return Promise.resolve(null);

    this._refreshing = (async () => {
      try {
        const res = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          headers: { Authorization: `Bearer ${refreshToken}` },
        });
        if (!res.ok) return null;
        const data = await res.json().catch(() => ({}));
        if (!data.access_token) return null;
        this.setToken(data.access_token);
        return data.access_token;
      } catch {
        return null;
      } finally {
        this._refreshing = null;
      }
    })();
    return this._refreshing;
  },

  check() {
    if (!this.getToken()) {
      window.location.href = '/login';
      return false;
    }
    return true;
  },

  logout() {
    this.removeToken();
    this.removeRefreshToken();
    window.location.href = '/login';
  },

  redirectIfLoggedIn() {
    if (this.getToken()) {
      window.location.href = '/selector';
      return true;
    }
    return false;
  },
};

// ── API Client ────────────────────────────────────────────────────────────────
const API = {
  async request(url, options = {}, _retry = true) {
    const token = Auth.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    };

    const res = await fetch('/api/v1' + url, { ...options, headers });

    // Un 401 de /auth/login o /auth/refresh es un error de credenciales que el
    // llamador debe manejar; no es una sesión expirada. El resto de los 401 sí
    // son token vencido: se renueva en silencio una vez y se reintenta; solo si
    // la renovación falla se cierra la sesión.
    const isCredentialCall =
      url.startsWith('/auth/login') || url.startsWith('/auth/refresh');
    if (res.status === 401 && !isCredentialCall) {
      if (_retry) {
        const newToken = await Auth.refreshAccessToken();
        if (newToken) return API.request(url, options, false);
      }
      Auth.logout();
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

    SubscriptionPopup.check(data);
    return user;
  } catch {
    Auth.logout();
  }
}

// ── Subscription / Trial popups ───────────────────────────────────────────────
const SubscriptionPopup = {
  _CONTAINER_ID: 'subscription-popup-container',

  check(data) {
    if (!data) return;
    this._remove();

    const trial = data.trial;
    if (trial && trial.expirado) {
      this._showTrialExpired(trial);
      return;
    }

    const nag = data.billing_nag;
    if (!nag) return;

    if (nag.no_suscrito) {
      this._showNotSubscribed(nag);
    } else if (nag.en_gracia || nag.dias_hasta_cobro < 0) {
      this._showSubscriptionExpired(nag);
    } else if (nag.dias_hasta_cobro <= 1) {
      if (this._isDismissed(nag.proximo_cobro)) return;
      this._showRenewalReminder(nag);
    }
  },

  _container() {
    let c = document.getElementById(this._CONTAINER_ID);
    if (!c) {
      c = document.createElement('div');
      c.id = this._CONTAINER_ID;
      document.body.appendChild(c);
    }
    return c;
  },

  _remove() {
    const c = document.getElementById(this._CONTAINER_ID);
    if (c) c.remove();
  },

  _isDismissed(proximoCobro) {
    if (!proximoCobro) return false;
    const key = `dp_dismiss_billing_${proximoCobro}`;
    const today = new Date().toISOString().slice(0, 10);
    return localStorage.getItem(key) === today;
  },

  _dismiss(proximoCobro) {
    const key = `dp_dismiss_billing_${proximoCobro}`;
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem(key, today);
    this._remove();
  },

  _buildOverlay(blocking) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm';
    if (!blocking) overlay.classList.add('pointer-events-auto');
    return overlay;
  },

  _buildCard(accent) {
    const accentMap = {
      red:    { ring: 'ring-red-500/30',    bar: 'bg-red-500',    icon: 'text-red-600' },
      amber:  { ring: 'ring-amber-500/30',  bar: 'bg-amber-500',  icon: 'text-amber-600' },
      blue:   { ring: 'ring-blue-500/30',   bar: 'bg-blue-500',   icon: 'text-blue-600' },
    };
    const a = accentMap[accent] || accentMap.blue;
    const card = document.createElement('div');
    card.className = `relative w-full max-w-md rounded-2xl bg-white shadow-2xl ring-1 ${a.ring} overflow-hidden`;
    const bar = document.createElement('div');
    bar.className = `h-1.5 w-full ${a.bar}`;
    card.appendChild(bar);
    card._iconClass = a.icon;
    return card;
  },

  _addBody(card, title, lines) {
    const body = document.createElement('div');
    body.className = 'p-6 space-y-4 font-body';

    const h = document.createElement('h2');
    h.className = 'font-cs-display text-2xl font-bold text-gray-900';
    h.textContent = title;
    body.appendChild(h);

    lines.forEach(line => {
      const p = document.createElement('p');
      p.className = line.bold ? 'text-sm text-gray-900 font-semibold' : 'text-sm text-gray-600 leading-relaxed';
      p.textContent = line.text || line;
      body.appendChild(p);
    });

    card.appendChild(body);
    return body;
  },

  _addInfoBox(body, items) {
    const box = document.createElement('div');
    box.className = 'rounded-lg bg-gray-50 ring-1 ring-gray-200 p-4 space-y-1.5';
    items.forEach(([label, value]) => {
      const row = document.createElement('div');
      row.className = 'flex justify-between text-sm';
      const l = document.createElement('span');
      l.className = 'text-gray-500';
      l.textContent = label;
      const v = document.createElement('span');
      v.className = 'font-semibold text-gray-900';
      v.textContent = value;
      row.appendChild(l);
      row.appendChild(v);
      box.appendChild(row);
    });
    body.appendChild(box);
  },

  _addActions(card, buttons) {
    const actions = document.createElement('div');
    actions.className = 'px-6 pb-6 pt-2 flex flex-col-reverse sm:flex-row sm:justify-end gap-2';
    buttons.forEach(btn => {
      const el = document.createElement(btn.href ? 'a' : 'button');
      if (btn.href) {
        el.href = btn.href;
        el.target = '_blank';
        el.rel = 'noopener noreferrer';
      }
      el.className = btn.primary
        ? 'inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 text-white text-sm font-semibold shadow hover:opacity-95 transition-opacity cursor-pointer'
        : 'inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-gray-100 text-gray-700 text-sm font-semibold hover:bg-gray-200 transition-colors cursor-pointer';
      el.textContent = btn.label;
      if (btn.onClick) el.addEventListener('click', btn.onClick);
      actions.appendChild(el);
    });
    card.appendChild(actions);
  },

  _fmtMoney(v) {
    return '$' + Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' MXN';
  },

  _fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso);
    return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'long', year: 'numeric' });
  },

  // ── Popup 1: Trial expired (BLOCKING) ───────────────────────────────────────
  _showTrialExpired(trial) {
    const overlay = this._buildOverlay(true);
    const card = this._buildCard('amber');

    this._addBody(card, 'Tu periodo de prueba terminó', [
      'Esperamos que hayas disfrutado probando Dental Planning. Para seguir usando el sistema y conservar tus datos, suscríbete a un plan de pago.',
    ]);

    this._addInfoBox(card.lastChild, [
      ['Plan de prueba', `${trial.dias_expiracion || 0} días`],
      ['Expiró', this._fmtDate(trial.expira)],
    ]);

    this._addActions(card, [
      {
        label: 'Cerrar sesión',
        primary: false,
        onClick: () => Auth.logout(),
      },
      {
        label: 'Ver planes y suscribirme',
        primary: true,
        onClick: () => { window.location.href = '/registro?upgrade=1'; },
      },
    ]);

    overlay.appendChild(card);
    this._container().appendChild(overlay);
  },

  // ── Popup 2a: Not subscribed yet (BLOCKING) — registered but never paid ─────
  _showNotSubscribed(nag) {
    const overlay = this._buildOverlay(true);
    const card = this._buildCard('amber');

    this._addBody(card, 'Activa tu suscripción', [
      'Tu cuenta está creada pero aún no has completado la suscripción. Da click abajo para registrar tu tarjeta y activar tu acceso. El cobro se hará automáticamente cada mes.',
    ]);

    this._addInfoBox(card.lastChild, [
      ['Plan', nag.plan_nombre || '—'],
      ['Monto mensual', this._fmtMoney(nag.monto)],
    ]);

    const buttons = [
      { label: 'Cerrar sesión', primary: false, onClick: () => Auth.logout() },
    ];
    if (nag.subscription_link) {
      buttons.push({ label: 'Suscribirme ahora', primary: true, href: nag.subscription_link });
    }
    this._addActions(card, buttons);

    overlay.appendChild(card);
    this._container().appendChild(overlay);
  },

  // ── Popup 2: Subscription expired / in grace (BLOCKING) ─────────────────────
  _showSubscriptionExpired(nag) {
    const overlay = this._buildOverlay(true);
    const card = this._buildCard('red');

    const title = nag.en_gracia ? 'Tu suscripción está en periodo de gracia' : 'Tu suscripción venció';
    const intro = nag.en_gracia
      ? `Tu pago no se ha completado. Tienes hasta el ${this._fmtDate(nag.gracia_expira)} para regularizar tu cuenta. Después de esa fecha el acceso quedará bloqueado.`
      : 'Tu suscripción venció. Paga ahora para recuperar el acceso completo al sistema.';

    this._addBody(card, title, [intro]);

    this._addInfoBox(card.lastChild, [
      ['Plan', nag.plan_nombre || '—'],
      ['Monto', this._fmtMoney(nag.monto)],
      ['Vencimiento', this._fmtDate(nag.proximo_cobro)],
    ]);

    const buttons = [
      { label: 'Cerrar sesión', primary: false, onClick: () => Auth.logout() },
    ];
    if (nag.subscription_link) {
      buttons.push({
        label: 'Re-suscribirme',
        primary: true,
        href: nag.subscription_link,
      });
    } else {
      buttons.push({
        label: 'Contactar soporte',
        primary: true,
        href: 'mailto:soporte@dentalplanning.mx?subject=Renovacion de suscripcion',
      });
    }

    this._addActions(card, buttons);

    overlay.appendChild(card);
    this._container().appendChild(overlay);
  },

  // ── Popup 3: Renewal reminder T-1 (DISMISSIBLE) ─────────────────────────────
  _showRenewalReminder(nag) {
    const overlay = this._buildOverlay(false);
    const card = this._buildCard('blue');

    const daysText = nag.dias_hasta_cobro === 0
      ? 'Tu suscripción se renueva HOY.'
      : 'Tu suscripción se renueva mañana.';

    this._addBody(card, 'Recordatorio de cobro', [
      daysText + ' Se cobrará automáticamente a la tarjeta que registraste con Clip.',
    ]);

    this._addInfoBox(card.lastChild, [
      ['Plan', nag.plan_nombre || '—'],
      ['Monto', this._fmtMoney(nag.monto)],
      ['Fecha de cobro', this._fmtDate(nag.proximo_cobro)],
    ]);

    const buttons = [
      {
        label: 'Entendido',
        primary: true,
        onClick: () => this._dismiss(nag.proximo_cobro),
      },
    ];
    this._addActions(card, buttons);

    overlay.appendChild(card);
    this._container().appendChild(overlay);
  },
};

// ── Active nav ────────────────────────────────────────────────────────────────
function setActiveNav() {
  const path = window.location.pathname;
  const tab = new URLSearchParams(window.location.search).get('tab');
  document.querySelectorAll('[data-nav-path]').forEach(el => {
    const navPath = el.getAttribute('data-nav-path');
    const navTab = el.getAttribute('data-nav-tab');
    const isActive = navTab !== null
      ? (path === navPath && tab === navTab)
      : (path === navPath || (navPath !== '/dashboard' && path.startsWith(navPath + '/')));
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
