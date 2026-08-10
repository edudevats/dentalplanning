// Panel super-admin / Clínicas
(function () {
  const { statusBadge, currency, formatDate, confirmAction, openModal,
          buildField, inputEl, selectEl, textareaEl } = window.adminUI;

  const VALID_STATUS = ['', 'pending', 'active', 'suspended', 'rejected'];
  const VALID_SUB = ['', 'activa', 'mora', 'gracia', 'vencida'];
  const VALID_SORT = ['reciente', 'proximo_cobro', '-proximo_cobro', 'plan'];
  const VALID_NUEVAS = ['', 'mes'];

  let currentSearch = '';
  let currentStatus = '';
  let currentSubEstado = '';
  let currentSort = 'reciente';
  let currentNuevas = '';
  let plansCache = null;
  let currentMode = 'tenants';

  // Siembra el estado desde la query string. Valores desconocidos se descartan
  // para no mandar basura al backend ni dejar chips en un estado imposible.
  function readFiltersFromUrl() {
    const p = new URL(window.location.href).searchParams;
    const status = p.get('status') || '';
    const sub = p.get('sub_estado') || '';
    const sort = p.get('sort') || 'reciente';
    const nuevas = p.get('nuevas') || '';
    currentStatus = VALID_STATUS.includes(status) ? status : '';
    currentSubEstado = VALID_SUB.includes(sub) ? sub : '';
    currentSort = VALID_SORT.includes(sort) ? sort : 'reciente';
    currentSearch = p.get('search') || '';
    currentNuevas = VALID_NUEVAS.includes(nuevas) ? nuevas : '';
  }

  // Única fuente de los query params: la usan refresh(), syncUrl() y el export.
  function buildParams() {
    const params = new URLSearchParams();
    if (currentSearch) params.set('search', currentSearch);
    if (currentStatus) params.set('status', currentStatus);
    if (currentSubEstado) params.set('sub_estado', currentSubEstado);
    if (currentNuevas) params.set('nuevas', currentNuevas);
    if (currentSort && currentSort !== 'reciente') params.set('sort', currentSort);
    return params;
  }

  // replaceState y no pushState: filtrar no debe llenar el historial.
  // En modo Personas los filtros de clínicas no describen lo que se ve en
  // pantalla, así que no se escriben en la URL.
  function syncUrl() {
    if (currentMode === 'users') return;
    const qs = buildParams().toString();
    window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }

  async function loadPlans() {
    if (plansCache) return plansCache;
    const data = await adminApi.get('/plans');
    plansCache = (data.plans || []).filter(p => p.activo);
    return plansCache;
  }

  async function refresh() {
    const qs = buildParams().toString();
    const data = await adminApi.get(`/tenants${qs ? `?${qs}` : ''}`);
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
          const MOD_LABELS = { contable: 'Cont', inventario: 'Inv', finanzas_personales: 'Fin', crm: 'CRM' };
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

      // Estado suscripción
      const tdSubEstado = document.createElement('td');
      tdSubEstado.className = 'px-4 py-3.5';
      if (t.subscription && t.subscription.estado) {
        tdSubEstado.appendChild(statusBadge(t.subscription.estado));
      } else {
        tdSubEstado.textContent = '—';
        tdSubEstado.classList.add('text-cs-on-surface-var');
      }

      // Próximo cobro
      const tdProximo = document.createElement('td');
      tdProximo.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdProximo.textContent = (t.subscription && t.subscription.proximo_cobro)
        ? formatDate(t.subscription.proximo_cobro) : '—';

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

      // Última actividad
      const tdActividad = document.createElement('td');
      tdActividad.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdActividad.textContent = t.ultima_actividad ? formatDate(t.ultima_actividad) : 'Nunca';

      // Acciones
      const tdActions = document.createElement('td');
      tdActions.className = 'px-4 py-3.5 text-right space-x-1';
      buildActions(tdActions, t);

      tr.appendChild(tdName);
      tr.appendChild(tdContact);
      tr.appendChild(tdStatus);
      tr.appendChild(tdPlan);
      tr.appendChild(tdSubEstado);
      tr.appendChild(tdProximo);
      tr.appendChild(tdUsers);
      tr.appendChild(tdPago);
      tr.appendChild(tdActividad);
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

  // ── Modo Personas ──────────────────────────────────────────────────────
  async function refreshUsers() {
    const q = currentSearch.trim();
    const tbody = document.getElementById('users-rows');
    invDom.clearChildren(tbody);
    if (q.length < 2) return;
    const data = await adminApi.get(`/users/search?q=${encodeURIComponent(q)}`);
    (data.users || []).forEach(u => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors duration-200 cursor-pointer';
      tr.addEventListener('click', () => { window.location.href = `/admin/tenants/${u.tenant_id}`; });

      const tdName = document.createElement('td');
      tdName.className = 'px-4 py-3.5 font-semibold text-cs-on-surface';
      tdName.textContent = u.name || '—';

      const tdEmail = document.createElement('td');
      tdEmail.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdEmail.appendChild(document.createTextNode(u.email || '—'));
      if (u.must_change_password) {
        const badge = document.createElement('span');
        badge.className = 'inline-flex ml-2 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-cs-surface-container-high text-cs-on-surface';
        badge.textContent = 'Contraseña temporal';
        tdEmail.appendChild(badge);
      }

      const tdRole = document.createElement('td');
      tdRole.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdRole.textContent = u.is_superuser ? 'super-admin' : (u.role || '—');

      const tdClinic = document.createElement('td');
      tdClinic.className = 'px-4 py-3.5 text-cs-on-surface';
      tdClinic.textContent = u.tenant_name || '—';

      const tdGo = document.createElement('td');
      tdGo.className = 'px-4 py-3.5 text-right';
      const a = document.createElement('a');
      a.href = `/admin/tenants/${u.tenant_id}`;
      a.className = 'inline-flex items-center gap-1 text-cs-primary text-xs font-semibold hover:underline';
      a.textContent = 'Ver clínica';
      tdGo.appendChild(a);

      tr.appendChild(tdName);
      tr.appendChild(tdEmail);
      tr.appendChild(tdRole);
      tr.appendChild(tdClinic);
      tr.appendChild(tdGo);
      tbody.appendChild(tr);
    });
  }

  function applyMode() {
    const isUsers = currentMode === 'users';
    document.getElementById('users-table-wrap').classList.toggle('hidden', !isUsers);
    document.querySelector('#tenants-rows').closest('div').classList.toggle('hidden', isUsers);
    document.getElementById('status-chips').classList.toggle('hidden', isUsers);
    document.getElementById('sub-filters').classList.toggle('hidden', isUsers);
    document.getElementById('empty-state').classList.add('hidden');
    const search = document.getElementById('filter-search');
    search.placeholder = isUsers ? 'Buscar persona por nombre o email…' : 'Buscar por nombre, slug o email…';
    if (isUsers) refreshUsers().catch(err => Toast.show(err.message, 'error'));
    else refresh().catch(err => Toast.show(err.message, 'error'));
    syncUrl();
  }

  function wireModeToggle() {
    document.querySelectorAll('.mode-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.mode-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentMode = chip.dataset.mode;
        applyMode();
      });
    });
  }

  // ── Filtros wiring ─────────────────────────────────────────────────────
  function wireFilters() {
    const searchInput = document.getElementById('filter-search');
    searchInput.value = currentSearch;
    let timer;
    searchInput.addEventListener('input', (e) => {
      currentSearch = e.target.value;
      clearTimeout(timer);
      timer = setTimeout(() => {
        syncUrl();
        if (currentMode === 'users') refreshUsers().catch(err => Toast.show(err.message, 'error'));
        else refresh().catch(err => Toast.show(err.message, 'error'));
      }, 250);
    });

    document.querySelectorAll('.status-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.status === currentStatus);
      chip.addEventListener('click', () => {
        document.querySelectorAll('.status-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentStatus = chip.dataset.status;
        syncUrl();
        refresh().catch(err => Toast.show(err.message, 'error'));
      });
    });

    document.querySelectorAll('.sub-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.sub === currentSubEstado);
      chip.addEventListener('click', () => {
        document.querySelectorAll('.sub-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentSubEstado = chip.dataset.sub;
        syncUrl();
        refresh().catch(err => Toast.show(err.message, 'error'));
      });
    });

    // Toggle suelto: prende y apaga, no pertenece a un grupo excluyente.
    document.querySelectorAll('.nuevas-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.nuevas === currentNuevas);
      chip.addEventListener('click', () => {
        currentNuevas = currentNuevas === chip.dataset.nuevas ? '' : chip.dataset.nuevas;
        document.querySelectorAll('.nuevas-chip').forEach(c =>
          c.classList.toggle('active', c.dataset.nuevas === currentNuevas));
        syncUrl();
        refresh().catch(err => Toast.show(err.message, 'error'));
      });
    });

    const sortSel = document.getElementById('sort-select');
    sortSel.value = currentSort;
    sortSel.addEventListener('change', () => {
      currentSort = sortSel.value;
      syncUrl();
      refresh().catch(err => Toast.show(err.message, 'error'));
    });
  }

  async function init() {
    readFiltersFromUrl();
    wireFilters();
    wireModeToggle();
    document.getElementById('btn-export-csv').addEventListener('click', () => {
      const qs = buildParams().toString();
      adminApi.download(`/tenants/export.csv${qs ? `?${qs}` : ''}`, 'clinicas.csv');
    });
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
