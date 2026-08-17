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

// ── Combobox (autocompletado) ─────────────────────────────────────────────────
// Convierte un <input type="text"> en un buscador con lista desplegable filtrada.
// Pensado para elegir de listas largas (ej. 200+ materiales) sin scrollear un
// <select> gigante. Soporta teclado (ArrowUp/Down, Enter, Escape) y click.
//
// opts:
//   input         : HTMLInputElement (requerido). Su contenedor debe poder
//                   posicionar el menu absoluto (se fuerza position:relative).
//   getItems      : () => Array<item>  (se evalua en cada render; permite datos
//                   que cambian, ej. ocultar ya-seleccionados)
//   getLabel      : (item) => string   (texto principal; default item.nombre)
//   getMeta       : (item) => string|null (texto secundario a la derecha, ej. costo)
//   isDisabled    : (item) => bool     (excluye el item de los resultados)
//   onSelect      : (item) => void     (callback al elegir)
//   clearOnSelect : bool  (default true) — limpia el input tras elegir
//   limit         : number (default 50) — maximo de resultados mostrados
//   emptyText     : string (default 'Sin resultados')
//   classes       : overrides de clases para adaptar el tema (menu/item/…)
//
// Devuelve { open, close, refresh }.
function Combobox(opts) {
  const input = opts.input;
  const getLabel = opts.getLabel || (m => m.nombre || '');
  const getMeta = opts.getMeta || (() => null);
  const isDisabled = opts.isDisabled || (() => false);
  const limit = opts.limit || 50;
  const clearOnSelect = opts.clearOnSelect !== false;
  const emptyText = opts.emptyText || 'Sin resultados';
  const cls = Object.assign({
    menu: 'absolute z-50 left-0 right-0 mt-1 max-h-64 overflow-y-auto rounded-lg border border-border bg-surface shadow-lg',
    item: 'px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-3',
    itemBase: 'text-text-primary hover:bg-surface-hover',
    itemActive: 'bg-primary-50 text-primary-700',
    meta: 'text-xs text-text-muted tabular-nums shrink-0',
    empty: 'px-3 py-2 text-sm text-text-muted',
  }, opts.classes || {});

  const parent = input.parentElement;
  if (parent && getComputedStyle(parent).position === 'static') {
    parent.style.position = 'relative';
  }

  const menu = domEl('ul', cls.menu);
  menu.style.display = 'none';
  parent.appendChild(menu);

  let filtered = [];
  let activeIdx = -1;
  let isOpen = false;

  function compute() {
    const all = (opts.getItems ? opts.getItems() : []) || [];
    const q = input.value.trim().toLowerCase();
    const usable = all.filter(m => !isDisabled(m));
    const matched = q ? usable.filter(m => getLabel(m).toLowerCase().includes(q)) : usable;
    return matched.slice(0, limit);
  }

  function highlight() {
    [...menu.children].forEach((li, i) => {
      if (li.dataset.idx === undefined) return;
      li.className = cls.item + ' ' + (i === activeIdx ? cls.itemActive : cls.itemBase);
    });
    if (activeIdx >= 0 && menu.children[activeIdx]) {
      menu.children[activeIdx].scrollIntoView({ block: 'nearest' });
    }
  }

  function render() {
    filtered = compute();
    activeIdx = filtered.length ? 0 : -1;
    menu.replaceChildren();
    if (!filtered.length) {
      menu.appendChild(domEl('li', cls.empty, emptyText));
    } else {
      filtered.forEach((m, i) => {
        const li = domEl('li', cls.item + ' ' + (i === activeIdx ? cls.itemActive : cls.itemBase));
        li.dataset.idx = String(i);
        li.appendChild(domEl('span', 'min-w-0 truncate', getLabel(m)));
        const meta = getMeta(m);
        if (meta != null) li.appendChild(domEl('span', cls.meta, meta));
        // mousedown (no click) para elegir antes de que el input pierda foco
        li.addEventListener('mousedown', (e) => { e.preventDefault(); choose(m); });
        li.addEventListener('mouseenter', () => { activeIdx = i; highlight(); });
        menu.appendChild(li);
      });
    }
    menu.style.display = '';
    isOpen = true;
  }

  function close() {
    menu.style.display = 'none';
    isOpen = false;
    activeIdx = -1;
  }

  function choose(m) {
    if (clearOnSelect) input.value = '';
    close();
    if (opts.onSelect) opts.onSelect(m);
  }

  input.setAttribute('autocomplete', 'off');
  input.addEventListener('input', render);
  input.addEventListener('focus', render);
  input.addEventListener('keydown', (e) => {
    if (!isOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { render(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (filtered.length) { activeIdx = (activeIdx + 1) % filtered.length; highlight(); }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (filtered.length) { activeIdx = (activeIdx - 1 + filtered.length) % filtered.length; highlight(); }
    } else if (e.key === 'Enter') {
      if (isOpen && activeIdx >= 0 && filtered[activeIdx]) { e.preventDefault(); choose(filtered[activeIdx]); }
    } else if (e.key === 'Escape') {
      close();
    }
  });
  document.addEventListener('click', (e) => {
    if (isOpen && !menu.contains(e.target) && e.target !== input) close();
  });

  return { open: render, close, refresh: () => { if (isOpen) render(); } };
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
// Modo mentoría: si la página se abrió con ?as_tenant=<id> (solo superadmin),
// cada GET propaga el parámetro para leer los datos de esa clínica.
const AS_TENANT = (() => {
  const v = new URLSearchParams(window.location.search).get('as_tenant');
  return v && /^\d+$/.test(v) ? v : null;
})();

const API = {
  async request(url, options = {}, _retry = true) {
    const token = Auth.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    };

    const method = (options.method || 'GET').toUpperCase();
    let finalUrl = url;
    if (AS_TENANT && method === 'GET') {
      finalUrl += (finalUrl.includes('?') ? '&' : '?') + 'as_tenant=' + AS_TENANT;
    }
    const res = await fetch('/api/v1' + finalUrl, { ...options, headers });

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
  delete: (url, body) => API.request(url, {
    method: 'DELETE',
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  }),
};

// ── Print Agent (impresión de tickets vía agente local) ──────────────────────
const PrintAgent = {
  _key: null, // cache en memoria por carga de página

  getUrl() {
    return (localStorage.getItem('print_agent_url') || 'http://localhost:9099')
      .replace(/\/+$/, '');
  },

  async _fetchKey() {
    if (this._key) return this._key;
    const r = await API.get('/facturacion/print-agent/key');
    if (!r.configured || !r.api_key) {
      const e = new Error('La impresión no está configurada. Pide al administrador que genere la clave en Ajustes → Impresión.');
      e.code = 'NOT_CONFIGURED';
      throw e;
    }
    this._key = r.api_key;
    return this._key;
  },

  async print(payload) {
    const key = await this._fetchKey();
    const res = await fetch(this.getUrl() + '/imprimir-ticket', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': key },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      if (res.status === 401) this._key = null; // la key cambió: limpiar cache
      const map = {
        401: 'La clave del agente no coincide. El administrador debe regenerarla en Ajustes → Impresión y volver a pegarla en el agente.',
        503: 'El agente de impresión no tiene clave configurada.',
        429: 'Demasiadas impresiones seguidas. Espera un momento.',
      };
      const e = new Error(map[res.status] || ('agente respondió ' + res.status));
      e.status = res.status;
      throw e;
    }
    return res;
  },
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

// ── Confirm (reemplazo accesible de window.confirm) ───────────────────────────
const Confirm = {
  show(opts = {}) {
    const {
      title = 'Confirmar',
      message = '',
      confirmText = 'Confirmar',
      cancelText = 'Cancelar',
      danger = false,
    } = opts;

    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'fixed inset-0 z-[90] flex items-center justify-center p-4';

      const backdrop = document.createElement('div');
      backdrop.className = 'fixed inset-0 bg-black/40';

      const box = document.createElement('div');
      box.className = 'relative bg-surface rounded-2xl shadow-xl w-full max-w-sm p-6';
      box.setAttribute('role', 'alertdialog');
      box.setAttribute('aria-modal', 'true');

      const h = document.createElement('h3');
      h.className = 'text-base font-semibold font-heading text-text-primary';
      h.textContent = title;

      const p = document.createElement('p');
      p.className = 'mt-2 text-sm font-body text-text-secondary leading-snug';
      p.textContent = message;

      const actions = document.createElement('div');
      actions.className = 'mt-5 flex justify-end gap-2';

      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className =
        'rounded-lg border border-border hover:bg-surface-hover px-4 py-2 text-sm font-medium cursor-pointer transition-colors duration-200';
      cancelBtn.textContent = cancelText;

      const okBtn = document.createElement('button');
      okBtn.type = 'button';
      okBtn.className = danger
        ? 'rounded-lg bg-red-600 hover:bg-red-700 text-white px-4 py-2 text-sm font-medium cursor-pointer transition-colors duration-200'
        : 'rounded-lg bg-primary-500 hover:bg-primary-600 text-white px-4 py-2 text-sm font-medium cursor-pointer transition-colors duration-200';
      okBtn.textContent = confirmText;

      let done = false;
      const finish = (val) => {
        if (done) return;
        done = true;
        document.removeEventListener('keydown', onKey);
        overlay.remove();
        resolve(val);
      };
      const onKey = (e) => {
        if (e.key === 'Escape') finish(false);
        else if (e.key === 'Enter') finish(true);
      };

      backdrop.addEventListener('click', () => finish(false));
      cancelBtn.addEventListener('click', () => finish(false));
      okBtn.addEventListener('click', () => finish(true));
      document.addEventListener('keydown', onKey);

      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      box.appendChild(h);
      box.appendChild(p);
      box.appendChild(actions);
      overlay.appendChild(backdrop);
      overlay.appendChild(box);
      document.body.appendChild(overlay);
      setTimeout(() => okBtn.focus(), 50);
    });
  },
};

// ── Prompt (reemplazo de window.prompt con campos configurables) ──────────────
// fields: [{ name, label, type='text', value='', placeholder='', required=false,
//            options=[[val,label],...] (select), rows=3 (textarea) }]
// Resuelve un objeto { name: value } o null si se cancela.
const Prompt = {
  show(opts = {}) {
    const {
      title = '',
      fields = [],
      confirmText = 'Guardar',
      cancelText = 'Cancelar',
    } = opts;

    const INPUT_CLS =
      'block w-full rounded-lg border border-border px-3 py-2 text-sm font-body bg-surface min-h-[40px]';

    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'fixed inset-0 z-[90] flex items-center justify-center p-4';

      const backdrop = document.createElement('div');
      backdrop.className = 'fixed inset-0 bg-black/40';

      const box = document.createElement('div');
      box.className = 'relative bg-surface rounded-2xl shadow-xl w-full max-w-sm p-6';
      box.setAttribute('role', 'dialog');
      box.setAttribute('aria-modal', 'true');

      const form = document.createElement('form');
      form.className = 'space-y-3';

      if (title) {
        const h = document.createElement('h3');
        h.className = 'text-base font-semibold font-heading text-text-primary';
        h.textContent = title;
        form.appendChild(h);
      }

      const controls = {};
      fields.forEach((f) => {
        const wrap = document.createElement('div');
        const label = document.createElement('label');
        label.className = 'block text-xs font-medium text-text-secondary mb-1 font-body';
        label.textContent = f.label + (f.required ? ' *' : '');
        wrap.appendChild(label);

        let ctrl;
        if (f.type === 'textarea') {
          ctrl = document.createElement('textarea');
          ctrl.rows = f.rows || 3;
          ctrl.className = 'block w-full rounded-lg border border-border px-3 py-2 text-sm font-body bg-surface';
        } else if (f.type === 'select') {
          ctrl = document.createElement('select');
          ctrl.className = INPUT_CLS;
          (f.options || []).forEach(([val, txt]) => {
            const o = document.createElement('option');
            o.value = val; o.textContent = txt;
            ctrl.appendChild(o);
          });
        } else {
          ctrl = document.createElement('input');
          ctrl.type = f.type || 'text';
          ctrl.className = INPUT_CLS;
          if (f.placeholder) ctrl.placeholder = f.placeholder;
        }
        if (f.value != null) ctrl.value = f.value;
        const id = `prompt-field-${f.name}`;
        ctrl.id = id;
        label.setAttribute('for', id);
        controls[f.name] = ctrl;
        wrap.appendChild(ctrl);
        form.appendChild(wrap);
      });

      const actions = document.createElement('div');
      actions.className = 'mt-2 flex justify-end gap-2';

      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className =
        'rounded-lg border border-border hover:bg-surface-hover px-4 py-2 text-sm font-medium cursor-pointer transition-colors duration-200';
      cancelBtn.textContent = cancelText;

      const okBtn = document.createElement('button');
      okBtn.type = 'submit';
      okBtn.className =
        'rounded-lg bg-primary-500 hover:bg-primary-600 text-white px-4 py-2 text-sm font-medium cursor-pointer transition-colors duration-200';
      okBtn.textContent = confirmText;

      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      form.appendChild(actions);
      box.appendChild(form);
      overlay.appendChild(backdrop);
      overlay.appendChild(box);
      document.body.appendChild(overlay);

      let done = false;
      const finish = (val) => {
        if (done) return;
        done = true;
        document.removeEventListener('keydown', onKey);
        overlay.remove();
        resolve(val);
      };
      const submit = () => {
        const out = {};
        for (const f of fields) {
          const v = (controls[f.name].value || '').trim();
          if (f.required && !v) {
            Toast.warning(`${f.label} es obligatorio`);
            controls[f.name].focus();
            return;
          }
          out[f.name] = v;
        }
        finish(out);
      };
      const onKey = (e) => { if (e.key === 'Escape') finish(null); };

      form.addEventListener('submit', (e) => { e.preventDefault(); submit(); });
      backdrop.addEventListener('click', () => finish(null));
      cancelBtn.addEventListener('click', () => finish(null));
      document.addEventListener('keydown', onKey);

      setTimeout(() => {
        const first = fields[0] && controls[fields[0].name];
        (first || okBtn).focus();
      }, 50);
    });
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
// options: { rowClass(row) → string } clases extra para el <tr> de esa fila.
//   Si rowClass devuelve algo, se omite el hover por defecto y lo aporta el
//   llamador: dos utilidades hover:bg-* con la misma especificidad se resuelven
//   por orden de aparicion en el CSS generado, y no queremos depender de eso.
function renderTable(containerId, columns, data, emptyMessage, loading, options = {}) {
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
      const extraCls = options.rowClass ? (options.rowClass(rowData) || '') : '';
      tr.className = extraCls
        ? 'border-b border-border transition-colors duration-100 ' + extraCls
        : 'border-b border-border hover:bg-surface-hover transition-colors duration-100';
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

    window.__userRole = user.role || null;
    applyRoleNav(user.role);

    SubscriptionPopup.check(data);
    return user;
  } catch (e) {
    // Contraseña temporal: require_auth responde 403 con must_change_password.
    // En vez de cerrar sesión, forzamos el cambio de contraseña.
    if (e?.response?.status === 403 && e?.response?.data?.must_change_password) {
      forceChangePassword();
      return;
    }
    Auth.logout();
  }
}

// ── Gating de navegación por rol ──────────────────────────────────────────────
function applyRoleNav(role) {
  if (role !== 'recepcionista') return;
  const allowed = ['/ingresos', '/facturas'];
  // Ocultar la opción "Cambiar de Sistema"
  document.querySelectorAll('aside a[href="/selector"]').forEach(a => {
    const wrap = a.closest('div');
    if (wrap) wrap.style.display = 'none';
  });
  // Ocultar cada ítem de nav que no esté permitido
  document.querySelectorAll('aside nav li').forEach(li => {
    const link = li.querySelector('[data-nav-path]');
    const path = link ? link.getAttribute('data-nav-path') : null;
    if (!path || !allowed.includes(path)) li.style.display = 'none';
  });
  // Ocultar encabezados de sección que quedaron sin ítems visibles
  document.querySelectorAll('aside nav > div').forEach(group => {
    const visible = Array.from(group.querySelectorAll('li'))
      .some(li => li.style.display !== 'none');
    if (!visible) group.style.display = 'none';
  });
  // Redirección suave si está en una página no permitida
  const here = window.location.pathname;
  if (!allowed.includes(here)) window.location.replace('/ingresos');
}

// ── Menú de usuario (top bar) + cambiar contraseña ────────────────────────────
let forcedPwChange = false;

function setCpForced(forced) {
  forcedPwChange = forced;
  const title = document.getElementById('modal-cp-title');
  if (title) title.textContent = forced ? 'Debes cambiar tu contraseña' : 'Cambiar contraseña';
  // En modo obligatorio se ocultan los botones de cerrar/cancelar.
  ['modal-cp-close', 'cp-cancel'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden', forced);
  });
}

// Abre el modal en modo OBLIGATORIO (no se puede cerrar): para la contraseña temporal.
function forceChangePassword() {
  ['cp-current', 'cp-new', 'cp-confirm'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  setCpForced(true);
  document.documentElement.style.visibility = 'visible';
  Modal.open('modal-change-password');
}

function initUserMenu() {
  const btn = document.getElementById('user-menu-btn');
  const menu = document.getElementById('user-menu');
  if (!btn || !menu) return;

  const closeMenu = () => { menu.classList.add('hidden'); btn.setAttribute('aria-expanded', 'false'); };
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = menu.classList.toggle('hidden');
    btn.setAttribute('aria-expanded', open ? 'false' : 'true');
  });
  document.addEventListener('click', (e) => {
    if (!menu.contains(e.target) && !btn.contains(e.target)) closeMenu();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenu(); });

  document.getElementById('btn-logout-menu')?.addEventListener('click', () => Auth.logout());

  const cpBtn = document.getElementById('btn-change-password');
  cpBtn?.addEventListener('click', () => {
    closeMenu();
    ['cp-current', 'cp-new', 'cp-confirm'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    setCpForced(false);
    Modal.open('modal-change-password');
  });

  const closeCp = () => { if (forcedPwChange) return; Modal.close('modal-change-password'); };
  document.getElementById('modal-cp-close')?.addEventListener('click', closeCp);
  document.getElementById('modal-cp-backdrop')?.addEventListener('click', closeCp);
  document.getElementById('cp-cancel')?.addEventListener('click', closeCp);
  document.getElementById('cp-save')?.addEventListener('click', changePassword);
}

async function changePassword() {
  const current = document.getElementById('cp-current').value;
  const nueva = document.getElementById('cp-new').value;
  const confirmar = document.getElementById('cp-confirm').value;
  if (!current || !nueva || !confirmar) { Toast.warning('Completa todos los campos'); return; }
  if (nueva !== confirmar) { Toast.error('La nueva contraseña no coincide'); return; }
  const btn = document.getElementById('cp-save');
  btn.disabled = true;
  try {
    await API.put('/auth/password', { current_password: current, new_password: nueva });
    Toast.success('Contraseña actualizada');
    if (forcedPwChange) { window.location.reload(); return; }
    Modal.close('modal-change-password');
  } catch (e) {
    const data = e?.response?.data;
    let msg = data?.error || e?.message || 'No se pudo cambiar la contraseña';
    // Si es un error de validación de Marshmallow, mostrar la regla específica.
    if (data?.details) {
      const first = Object.values(data.details)[0];
      if (Array.isArray(first) && first.length) msg = first[0];
      else if (typeof first === 'string') msg = first;
    }
    Toast.error(msg);
  } finally {
    btn.disabled = false;
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

    if (nag.tipo === 'cobro_variable') {
      if (!nag.vencido && this._isDismissed(`charge_${nag.cobro_id}`)) return;
      this._showVariableCharge(nag);
      return;
    }

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
  _showVariableCharge(nag) {
    const blocking = Boolean(nag.vencido);
    const overlay = this._buildOverlay(blocking);
    const card = this._buildCard(blocking ? 'red' : 'blue');
    const days = Number(nag.dias_restantes || 0);
    const intro = nag.vencido
      ? 'El plazo de pago terminó. Realiza el pago para regularizar el acceso de tu clínica.'
      : `Tu mensualidad ya fue calculada. Tienes ${days} ${days === 1 ? 'día' : 'días'} para pagarla.`;

    this._addBody(card, nag.vencido ? 'Pago mensual vencido' : 'Tu mensualidad está lista', [intro]);

    const info = [
      ['Plan ' + (nag.plan_nombre || ''), this._fmtMoney(nag.plan_monto)],
    ];
    if (Number(nag.facturacion_monto || 0) > 0) {
      info.push(['Uso de facturas', this._fmtMoney(nag.facturacion_monto)]);
    }
    if (Number(nag.timbres_cantidad || 0) > 0) {
      info.push([
        `${nag.timbres_cantidad} timbre${Number(nag.timbres_cantidad) === 1 ? '' : 's'} × ${this._fmtMoney(nag.timbre_precio)}`,
        this._fmtMoney(nag.timbres_monto),
      ]);
    }
    info.push(['Total a pagar', this._fmtMoney(nag.monto)]);
    info.push(['Fecha límite', this._fmtDate(nag.fecha_limite)]);
    this._addInfoBox(card.lastChild, info);

    const buttons = blocking
      ? [{ label: 'Cerrar sesión', primary: false, onClick: () => Auth.logout() }]
      : [{
          label: 'Pagar después',
          primary: false,
          onClick: () => this._dismiss(`charge_${nag.cobro_id}`),
        }];
    if (nag.payment_url) {
      buttons.push({ label: 'Pagar ahora', primary: true, href: nag.payment_url });
    } else {
      buttons.push({
        label: 'Contactar soporte',
        primary: true,
        href: 'mailto:soporte@dentalplanning.mx?subject=Cobro mensual',
      });
    }
    this._addActions(card, buttons);

    overlay.appendChild(card);
    this._container().appendChild(overlay);
  },

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

// ── Modo mentoría (superadmin viendo reportes de una clínica) ────────────────
(function () {
  if (!AS_TENANT) return;
  document.addEventListener('DOMContentLoaded', async () => {
    // Los links de reportes del sidebar conservan el contexto as_tenant
    document.querySelectorAll('a[data-nav-path^="/reportes/"]').forEach(a => {
      const href = a.getAttribute('href');
      a.href = href + (href.includes('?') ? '&' : '?') + 'as_tenant=' + AS_TENANT;
    });

    if (!window.location.pathname.startsWith('/reportes/')) return;

    let nombre = 'clínica #' + AS_TENANT;
    try {
      const t = await API.get('/superadmin/tenants/' + AS_TENANT);
      if (t && t.name) nombre = t.name;
    } catch (e) {
      // Sin permiso o tenant inexistente: se deja el id como etiqueta
    }
    const bar = document.createElement('div');
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:100;' +
      'background:#b45309;color:#fff;text-align:center;font-size:13px;' +
      'font-weight:600;padding:6px 12px;';
    bar.textContent = 'Modo mentoría — viendo reportes de ' + nombre + ' (solo lectura)';
    document.body.prepend(bar);
    document.body.style.paddingTop = '32px';
  });
})();
