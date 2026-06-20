// Helpers compartidos del Panel Super-Admin.
// Reutiliza globals: API, Auth, Toast, domEl, domIcon, esc (app.js)
// y window.csShared, window.invDom (inventario/cs_shared.js, inventario/dom.js).

(function () {
  const PREFIX = '/superadmin';

  const adminApi = {
    get:  (path)        => API.get(PREFIX + path),
    post: (path, body)  => API.post(PREFIX + path, body),
    put:  (path, body)  => API.put(PREFIX + path, body),
    del:  (path)        => API.delete(PREFIX + path),
  };

  // ── Status helpers ────────────────────────────────────────────────────────
  const STATUS_LABELS = {
    pending:   { label: 'Pendiente',   variant: 'warning' },
    active:    { label: 'Activa',      variant: 'primary' },
    suspended: { label: 'Suspendida',  variant: 'critical' },
    rejected:  { label: 'Rechazada',   variant: 'neutral' },
    activa:    { label: 'Activa',      variant: 'primary' },
    vencida:   { label: 'Vencida',     variant: 'critical' },
    cancelada: { label: 'Cancelada',   variant: 'neutral' },
  };

  function statusBadge(status) {
    const cfg = STATUS_LABELS[status] || { label: status || '—', variant: 'neutral' };
    const span = document.createElement('span');
    const classes = {
      primary:  'bg-cs-primary-container text-cs-on-primary-container',
      warning:  'bg-cs-surface-container-high text-cs-on-surface',
      critical: 'bg-cs-error-container/40 text-cs-on-error-container',
      neutral:  'bg-cs-surface-container text-cs-on-surface-var',
    }[cfg.variant];
    span.className = `inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold tracking-wide ${classes}`;
    span.textContent = cfg.label;
    return span;
  }

  // ── Formatters ────────────────────────────────────────────────────────────
  function currency(v) {
    if (window.csShared && window.csShared.currency) return window.csShared.currency(v);
    return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(v) || 0);
  }

  // Parsea a hora local. Las cadenas "solo fecha" (YYYY-MM-DD) las parsea JS
  // como UTC, lo que desfasa un día en zonas detrás de UTC (p. ej. México UTC-6);
  // por eso se construyen por componentes. Las cadenas con hora usan Date normal.
  function parseLocalDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(iso);
  }

  function formatDate(iso) {
    if (!iso) return '—';
    const d = parseLocalDate(iso);
    if (isNaN(d)) return '—';
    return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function formatMonth(iso) {
    if (!iso) return '—';
    const d = parseLocalDate(iso);
    if (isNaN(d)) return '—';
    return d.toLocaleDateString('es-MX', { month: 'short', year: '2-digit' });
  }

  // ── Confirm modal (vanilla, no native confirm) ────────────────────────────
  function confirmAction({ title, message, confirmLabel = 'Confirmar', cancelLabel = 'Cancelar', destructive = false } = {}) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'fixed inset-0 bg-black/40 z-[200] flex items-center justify-center p-4';

      const card = document.createElement('div');
      card.className = 'bg-cs-surface-bright rounded-lg shadow-xl max-w-md w-full p-6 space-y-4';

      const h = document.createElement('h3');
      h.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
      h.textContent = title || '¿Confirmar?';

      const p = document.createElement('p');
      p.className = 'text-sm text-cs-on-surface-var';
      p.textContent = message || '';

      const actions = document.createElement('div');
      actions.className = 'flex justify-end gap-2 pt-2';

      const cancelBtn = document.createElement('button');
      cancelBtn.className = 'px-4 py-2 rounded-lg bg-cs-surface-container text-cs-on-surface text-sm font-semibold hover:bg-cs-surface-container-high transition-colors cursor-pointer';
      cancelBtn.textContent = cancelLabel;

      const okBtn = document.createElement('button');
      const okClasses = destructive
        ? 'px-4 py-2 rounded-lg bg-cs-error text-white text-sm font-semibold hover:opacity-90 transition-opacity cursor-pointer'
        : 'px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold hover:opacity-95 transition-opacity cursor-pointer';
      okBtn.className = okClasses;
      okBtn.textContent = confirmLabel;

      const close = (val) => {
        overlay.remove();
        resolve(val);
      };
      cancelBtn.addEventListener('click', () => close(false));
      okBtn.addEventListener('click', () => close(true));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });

      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      card.appendChild(h);
      card.appendChild(p);
      card.appendChild(actions);
      overlay.appendChild(card);
      document.body.appendChild(overlay);
      okBtn.focus();
    });
  }

  // ── Generic modal builder (used by forms) ─────────────────────────────────
  function openModal({ title, content, primary, onClose }) {
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black/40 z-[200] flex items-center justify-center p-4';

    const card = document.createElement('div');
    card.className = 'bg-cs-surface-bright rounded-lg shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto';

    const header = document.createElement('div');
    header.className = 'px-6 pt-6 pb-2 flex items-start justify-between gap-4';
    const h = document.createElement('h3');
    h.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    h.textContent = title || '';
    const closeIcon = document.createElement('button');
    closeIcon.className = 'p-1 rounded-md text-cs-on-surface-var hover:bg-cs-surface-container transition-colors cursor-pointer';
    closeIcon.setAttribute('aria-label', 'Cerrar');
    closeIcon.textContent = '×';
    closeIcon.style.fontSize = '1.5rem';
    closeIcon.style.lineHeight = '1';
    header.appendChild(h);
    header.appendChild(closeIcon);

    const body = document.createElement('div');
    body.className = 'px-6 py-4';
    if (content instanceof Node) body.appendChild(content);

    const footer = document.createElement('div');
    footer.className = 'px-6 pb-6 pt-2 flex justify-end gap-2';

    const close = (val) => {
      overlay.remove();
      if (typeof onClose === 'function') onClose(val);
    };

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'px-4 py-2 rounded-lg bg-cs-surface-container text-cs-on-surface text-sm font-semibold hover:bg-cs-surface-container-high transition-colors cursor-pointer';
    cancelBtn.textContent = 'Cancelar';
    cancelBtn.addEventListener('click', () => close(false));
    footer.appendChild(cancelBtn);

    if (primary) {
      const okBtn = document.createElement('button');
      okBtn.className = 'px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold hover:opacity-95 transition-opacity cursor-pointer';
      okBtn.textContent = primary.label || 'Guardar';
      okBtn.addEventListener('click', async () => {
        try {
          okBtn.disabled = true;
          await primary.onClick();
          close(true);
        } catch (err) {
          okBtn.disabled = false;
          if (typeof Toast !== 'undefined') Toast.show(err.message || 'Error', 'error');
        }
      });
      footer.appendChild(okBtn);
    }

    closeIcon.addEventListener('click', () => close(false));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });

    card.appendChild(header);
    card.appendChild(body);
    card.appendChild(footer);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    return { overlay, card, body, close };
  }

  // ── Form builder ──────────────────────────────────────────────────────────
  function buildField(label, input) {
    const wrap = document.createElement('label');
    wrap.className = 'block space-y-1';
    const lbl = document.createElement('span');
    lbl.className = 'text-xs font-semibold text-cs-on-surface-var';
    lbl.textContent = label;
    wrap.appendChild(lbl);
    wrap.appendChild(input);
    return wrap;
  }

  function inputEl(type, name, value) {
    const i = document.createElement('input');
    i.type = type;
    i.name = name;
    if (value != null) i.value = value;
    i.className = 'w-full px-3 py-2 rounded-lg bg-cs-surface-container text-sm text-cs-on-surface focus:outline-none focus:ring-2 focus:ring-cs-primary/30';
    return i;
  }

  function selectEl(name, options, value) {
    const s = document.createElement('select');
    s.name = name;
    s.className = 'w-full px-3 py-2 rounded-lg bg-cs-surface-container text-sm text-cs-on-surface focus:outline-none focus:ring-2 focus:ring-cs-primary/30';
    options.forEach(opt => {
      const o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label;
      if (value != null && String(value) === String(opt.value)) o.selected = true;
      s.appendChild(o);
    });
    return s;
  }

  function textareaEl(name, value, rows = 3) {
    const t = document.createElement('textarea');
    t.name = name;
    t.rows = rows;
    if (value) t.value = value;
    t.className = 'w-full px-3 py-2 rounded-lg bg-cs-surface-container text-sm text-cs-on-surface focus:outline-none focus:ring-2 focus:ring-cs-primary/30 resize-y';
    return t;
  }

  // ── KPI card builder ──────────────────────────────────────────────────────
  function kpiCard({ label, value, icon = 'circle', hint = null }) {
    const card = document.createElement('div');
    card.className = 'rounded-lg bg-cs-surface-container-lowest p-5 flex flex-col gap-2';
    const top = document.createElement('div');
    top.className = 'flex items-center justify-between';
    const l = document.createElement('span');
    l.className = 'text-xs font-semibold tracking-wide uppercase text-cs-on-surface-var';
    l.textContent = label;
    const ic = document.createElement('span');
    ic.className = 'inline-flex items-center justify-center w-8 h-8 rounded-md bg-cs-primary-container text-cs-on-primary-container';
    const i = document.createElement('i');
    i.setAttribute('data-lucide', icon);
    i.className = 'h-4 w-4';
    ic.appendChild(i);
    top.appendChild(l);
    top.appendChild(ic);

    const v = document.createElement('p');
    v.className = 'font-cs-display text-3xl font-bold text-cs-on-surface tracking-tight';
    v.textContent = value;

    card.appendChild(top);
    card.appendChild(v);
    if (hint) {
      const h = document.createElement('p');
      h.className = 'text-xs text-cs-on-surface-var';
      h.textContent = hint;
      card.appendChild(h);
    }
    return card;
  }

  // ── Public API ────────────────────────────────────────────────────────────
  window.adminApi = adminApi;
  window.adminUI = {
    statusBadge, currency, formatDate, formatMonth,
    confirmAction, openModal,
    buildField, inputEl, selectEl, textareaEl, kpiCard,
  };
})();
