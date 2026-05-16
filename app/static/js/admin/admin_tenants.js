// Panel super-admin / Clínicas
(function () {
  const { statusBadge, currency, formatDate, confirmAction, openModal,
          buildField, inputEl, selectEl, textareaEl } = window.adminUI;

  let currentSearch = '';
  let currentStatus = new URL(window.location.href).searchParams.get('status') || '';
  let plansCache = null;

  async function loadPlans() {
    if (plansCache) return plansCache;
    const data = await adminApi.get('/plans');
    plansCache = (data.plans || []).filter(p => p.activo);
    return plansCache;
  }

  async function refresh() {
    const params = new URLSearchParams();
    if (currentSearch) params.set('search', currentSearch);
    if (currentStatus) params.set('status', currentStatus);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const data = await adminApi.get(`/tenants${qs}`);
    renderRows(data.tenants || []);
  }

  function renderRows(tenants) {
    const tbody = document.getElementById('tenants-rows');
    invDom.clearChildren(tbody);
    document.getElementById('empty-state').classList.toggle('hidden', tenants.length > 0);

    tenants.forEach(t => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors duration-200 cursor-pointer';
      tr.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        window.location.href = `/admin/tenants/${t.id}`;
      });

      // Clínica
      const tdName = document.createElement('td');
      tdName.className = 'px-4 py-3.5';
      const nameEl = document.createElement('p');
      nameEl.className = 'font-semibold text-cs-on-surface';
      nameEl.textContent = t.name;
      const slugEl = document.createElement('p');
      slugEl.className = 'text-xs text-cs-on-surface-var font-mono';
      slugEl.textContent = t.slug;
      tdName.appendChild(nameEl);
      tdName.appendChild(slugEl);

      // Contacto
      const tdContact = document.createElement('td');
      tdContact.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdContact.textContent = t.contact_email || '—';

      // Status
      const tdStatus = document.createElement('td');
      tdStatus.className = 'px-4 py-3.5';
      tdStatus.appendChild(statusBadge(t.status));
      if (t.subscription && t.subscription.estado && t.subscription.estado !== 'activa') {
        const subBadge = document.createElement('span');
        const subColors = {
          gracia: 'bg-yellow-500/15 text-yellow-400',
          vencida: 'bg-red-500/15 text-red-400',
          cancelada: 'bg-cs-surface-container text-cs-on-surface-var',
        };
        subBadge.className = `inline-flex ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${subColors[t.subscription.estado] || ''}`;
        subBadge.textContent = t.subscription.estado;
        tdStatus.appendChild(subBadge);
      }

      // Plan + modules
      const tdPlan = document.createElement('td');
      tdPlan.className = 'px-4 py-3.5';
      if (t.subscription && t.subscription.plan_nombre) {
        const planName = document.createElement('p');
        planName.className = 'font-semibold text-cs-on-surface text-xs';
        planName.textContent = t.subscription.plan_nombre;
        tdPlan.appendChild(planName);
        const mods = t.subscription.plan_modulos || [];
        if (mods.length > 0) {
          const modWrap = document.createElement('div');
          modWrap.className = 'flex flex-wrap gap-0.5 mt-0.5';
          const MOD_LABELS = { contable: 'Cont', inventario: 'Inv', finanzas_personales: 'Fin' };
          mods.forEach(m => {
            const badge = document.createElement('span');
            badge.className = 'inline-flex px-1.5 py-0 rounded text-[9px] font-semibold bg-cs-primary-container text-cs-on-primary-container';
            badge.textContent = MOD_LABELS[m] || m;
            modWrap.appendChild(badge);
          });
          tdPlan.appendChild(modWrap);
        }
      } else {
        tdPlan.textContent = t.plan || '—';
        tdPlan.classList.add('text-cs-on-surface-var');
      }

      // Users
      const tdUsers = document.createElement('td');
      tdUsers.className = 'px-4 py-3.5 text-right font-cs-display font-semibold text-cs-on-surface';
      tdUsers.textContent = t.users_count != null ? t.users_count : '—';

      // Último pago
      const tdPago = document.createElement('td');
      tdPago.className = 'px-4 py-3.5 text-cs-on-surface-var';
      if (t.ultimo_pago) {
        tdPago.textContent = `${formatDate(t.ultimo_pago.fecha)} · ${currency(t.ultimo_pago.monto)}`;
      } else {
        tdPago.textContent = '—';
      }

      // Acciones
      const tdActions = document.createElement('td');
      tdActions.className = 'px-4 py-3.5 text-right space-x-1';
      buildActions(tdActions, t);

      tr.appendChild(tdName);
      tr.appendChild(tdContact);
      tr.appendChild(tdStatus);
      tr.appendChild(tdPlan);
      tr.appendChild(tdUsers);
      tr.appendChild(tdPago);
      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });

    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  function buildActions(td, t) {
    if (t.status === 'pending') {
      td.appendChild(actionButton('Aprobar', 'check', 'primary', () => openApproveModal(t)));
      td.appendChild(actionButton('Rechazar', 'x', 'critical', () => openRejectModal(t)));
    } else if (t.status === 'active') {
      td.appendChild(actionButton('Suspender', 'pause', 'critical', () => onSuspend(t)));
    } else if (t.status === 'suspended' || t.status === 'rejected') {
      td.appendChild(actionButton('Reactivar', 'play', 'primary', () => onActivate(t)));
    }
  }

  function actionButton(label, icon, variant, onClick) {
    const btn = document.createElement('button');
    const styles = {
      primary:  'bg-cs-primary text-cs-on-primary hover:opacity-90',
      critical: 'bg-cs-error/90 text-white hover:bg-cs-error',
      neutral:  'bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high',
    }[variant] || 'bg-cs-surface-container text-cs-on-surface';
    btn.className = `inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-colors cursor-pointer ${styles}`;
    const i = document.createElement('i');
    i.setAttribute('data-lucide', icon);
    i.className = 'h-3 w-3';
    btn.appendChild(i);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      onClick();
    });
    return btn;
  }

  // ── Approve flow ───────────────────────────────────────────────────────
  async function openApproveModal(t) {
    const plans = await loadPlans();
    if (plans.length === 0) {
      Toast.show('Primero crea al menos un plan activo en /admin/planes', 'warning');
      return;
    }
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const intro = document.createElement('p');
    intro.className = 'text-sm text-cs-on-surface-var';
    intro.textContent = `Vas a aprobar la clínica "${t.name}" y asignarle un plan inicial.`;
    wrap.appendChild(intro);

    const planSel = selectEl('plan_id',
      plans.map(p => ({ value: p.id, label: `${p.nombre} — ${currency(p.precio_mensual)}/mes` })));
    wrap.appendChild(buildField('Plan inicial', planSel));

    const today = new Date().toISOString().slice(0, 10);
    const inicioInput = inputEl('date', 'inicio', today);
    wrap.appendChild(buildField('Fecha de inicio', inicioInput));

    openModal({
      title: `Aprobar ${t.name}`,
      content: wrap,
      primary: {
        label: 'Aprobar y asignar plan',
        onClick: async () => {
          await adminApi.post(`/tenants/${t.id}/approve`, {
            plan_id: parseInt(planSel.value, 10),
            inicio: inicioInput.value || undefined,
          });
          Toast.show('Clínica aprobada', 'success');
          refresh();
        },
      },
    });
  }

  // ── Reject flow ────────────────────────────────────────────────────────
  function openRejectModal(t) {
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const ta = textareaEl('razon', '', 4);
    ta.placeholder = 'Explica brevemente por qué se rechaza esta solicitud…';
    wrap.appendChild(buildField('Razón del rechazo', ta));

    openModal({
      title: `Rechazar ${t.name}`,
      content: wrap,
      primary: {
        label: 'Rechazar',
        onClick: async () => {
          if (!ta.value.trim() || ta.value.trim().length < 3) {
            throw new Error('Escribe una razón de al menos 3 caracteres.');
          }
          await adminApi.post(`/tenants/${t.id}/reject`, { razon: ta.value.trim() });
          Toast.show('Clínica rechazada', 'success');
          refresh();
        },
      },
    });
  }

  async function onSuspend(t) {
    const ok = await confirmAction({
      title: `Suspender ${t.name}`,
      message: 'Los usuarios de esta clínica perderán acceso inmediatamente. Podés reactivarla en cualquier momento.',
      confirmLabel: 'Suspender',
      destructive: true,
    });
    if (!ok) return;
    await adminApi.post(`/tenants/${t.id}/suspend`, {});
    Toast.show('Clínica suspendida', 'success');
    refresh();
  }

  async function onActivate(t) {
    await adminApi.post(`/tenants/${t.id}/activate`, {});
    Toast.show('Clínica reactivada', 'success');
    refresh();
  }

  // ── Filtros wiring ─────────────────────────────────────────────────────
  function wireFilters() {
    const searchInput = document.getElementById('filter-search');
    let timer;
    searchInput.addEventListener('input', (e) => {
      currentSearch = e.target.value;
      clearTimeout(timer);
      timer = setTimeout(refresh, 250);
    });

    document.querySelectorAll('.status-chip').forEach(chip => {
      if (chip.dataset.status === currentStatus) {
        document.querySelectorAll('.status-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
      }
      chip.addEventListener('click', () => {
        document.querySelectorAll('.status-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentStatus = chip.dataset.status;
        refresh();
      });
    });
  }

  async function init() {
    wireFilters();
    try {
      await refresh();
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al cargar clínicas', 'error');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
