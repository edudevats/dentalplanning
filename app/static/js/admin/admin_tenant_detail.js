// Panel super-admin / Detalle de clínica
(function () {
  const { statusBadge, currency, formatDate, confirmAction, openModal,
          buildField, inputEl, selectEl, textareaEl, kpiCard } = window.adminUI;

  const root = document.querySelector('[data-tenant-id]');
  const tenantId = parseInt(root.dataset.tenantId, 10);
  let tenant = null;
  let plansCache = null;

  function buildHead(cols) {
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    tr.className = 'text-left text-cs-on-surface-var';
    cols.forEach(c => {
      const th = document.createElement('th');
      th.className = c.right ? 'px-4 py-3 font-semibold text-right' : 'px-4 py-3 font-semibold';
      th.textContent = c.label || '';
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    return thead;
  }

  // ── Loader ────────────────────────────────────────────────────────────
  async function loadTenant() {
    tenant = await adminApi.get(`/tenants/${tenantId}`);
    renderHeader();
  }

  async function loadPlans() {
    if (!plansCache) {
      const data = await adminApi.get('/plans');
      plansCache = data.plans || [];
    }
    return plansCache;
  }

  // ── Header ─────────────────────────────────────────────────────────────
  function renderHeader() {
    document.getElementById('tenant-name').textContent = tenant.name;
    document.getElementById('tenant-slug').textContent = tenant.slug;
    document.getElementById('tenant-contact').textContent = tenant.contact_email || '—';
    document.getElementById('tenant-approved').textContent = formatDate(tenant.approved_at);
    document.getElementById('tenant-next-payment').textContent = tenant.subscription && tenant.subscription.proximo_cobro
      ? formatDate(tenant.subscription.proximo_cobro) : '—';
    document.getElementById('tenant-notes-count').textContent = tenant.notes_count || 0;

    const statusSlot = document.getElementById('tenant-status-slot');
    invDom.clearChildren(statusSlot);
    statusSlot.appendChild(statusBadge(tenant.status));

    document.getElementById('tenant-plan-slot').textContent = tenant.plan ? `Plan: ${tenant.plan}` : 'Sin plan';

    const actions = document.getElementById('tenant-actions');
    invDom.clearChildren(actions);
    if (tenant.status === 'pending') {
      actions.appendChild(headerBtn('Aprobar', 'check', 'primary', openApprove));
      actions.appendChild(headerBtn('Rechazar', 'x', 'critical', openReject));
    } else if (tenant.status === 'active') {
      actions.appendChild(headerBtn('Suspender', 'pause', 'critical', onSuspend));
    } else {
      actions.appendChild(headerBtn('Reactivar', 'play', 'primary', onActivate));
    }

    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  function headerBtn(label, icon, variant, onClick) {
    const styles = {
      primary:  'bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary hover:opacity-95',
      critical: 'bg-cs-error text-white hover:opacity-90',
      neutral:  'bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high',
    }[variant];
    const btn = document.createElement('button');
    btn.className = `inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-opacity cursor-pointer ${styles}`;
    const i = document.createElement('i');
    i.setAttribute('data-lucide', icon);
    i.className = 'h-4 w-4';
    btn.appendChild(i);
    btn.appendChild(document.createTextNode(label));
    btn.addEventListener('click', onClick);
    return btn;
  }

  async function openApprove() {
    const plans = (await loadPlans()).filter(p => p.activo);
    if (plans.length === 0) { Toast.show('Crea un plan activo primero', 'warning'); return; }
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';
    const planSel = selectEl('plan_id', plans.map(p => ({ value: p.id, label: `${p.nombre} — ${currency(p.precio_mensual)}/mes` })));
    wrap.appendChild(buildField('Plan inicial', planSel));
    const today = new Date().toISOString().slice(0, 10);
    const inicio = inputEl('date', 'inicio', today);
    wrap.appendChild(buildField('Fecha de inicio', inicio));
    openModal({
      title: `Aprobar ${tenant.name}`, content: wrap,
      primary: { label: 'Aprobar', onClick: async () => {
        await adminApi.post(`/tenants/${tenantId}/approve`, {
          plan_id: parseInt(planSel.value, 10), inicio: inicio.value || undefined,
        });
        Toast.show('Clínica aprobada', 'success');
        await refreshAll();
      } },
    });
  }

  function openReject() {
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';
    const ta = textareaEl('razon', '', 4);
    ta.placeholder = 'Motivo del rechazo…';
    wrap.appendChild(buildField('Razón', ta));
    openModal({
      title: `Rechazar ${tenant.name}`, content: wrap,
      primary: { label: 'Rechazar', onClick: async () => {
        if (!ta.value.trim() || ta.value.trim().length < 3) throw new Error('Mínimo 3 caracteres.');
        await adminApi.post(`/tenants/${tenantId}/reject`, { razon: ta.value.trim() });
        Toast.show('Rechazada', 'success');
        await refreshAll();
      } },
    });
  }

  async function onSuspend() {
    const ok = await confirmAction({
      title: `Suspender ${tenant.name}`,
      message: 'Los usuarios perderán acceso. Se puede reactivar luego.',
      confirmLabel: 'Suspender', destructive: true,
    });
    if (!ok) return;
    await adminApi.post(`/tenants/${tenantId}/suspend`, {});
    Toast.show('Suspendida', 'success');
    await refreshAll();
  }

  async function onActivate() {
    await adminApi.post(`/tenants/${tenantId}/activate`, {});
    Toast.show('Reactivada', 'success');
    await refreshAll();
  }

  // ── Tab: General ───────────────────────────────────────────────────────
  function renderGeneral() {
    const panel = document.querySelector('[data-panel="general"]');
    invDom.clearChildren(panel);

    const card = document.createElement('div');
    card.className = 'rounded-lg bg-cs-surface-container-lowest p-6 space-y-4';

    const h = document.createElement('h2');
    h.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    h.textContent = 'Datos generales';
    card.appendChild(h);

    const nameInput = inputEl('text', 'name', tenant.name);
    const emailInput = inputEl('email', 'contact_email', tenant.contact_email || '');
    const planInput = inputEl('text', 'plan', tenant.plan || '');

    const grid = document.createElement('div');
    grid.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';
    grid.appendChild(buildField('Nombre', nameInput));
    grid.appendChild(buildField('Email de contacto', emailInput));
    grid.appendChild(buildField('Plan (etiqueta)', planInput));
    card.appendChild(grid);

    const saveBtn = document.createElement('button');
    saveBtn.className = 'px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold hover:opacity-95 transition-opacity cursor-pointer';
    saveBtn.textContent = 'Guardar cambios';
    saveBtn.addEventListener('click', async () => {
      try {
        const body = {
          name: nameInput.value.trim(),
          contact_email: emailInput.value.trim() || null,
          plan: planInput.value.trim() || undefined,
        };
        await adminApi.put(`/tenants/${tenantId}`, body);
        Toast.show('Cambios guardados', 'success');
        await loadTenant();
      } catch (err) { Toast.show(err.message, 'error'); }
    });
    card.appendChild(saveBtn);

    if (tenant.rejected_reason) {
      const warn = document.createElement('div');
      warn.className = 'mt-4 p-3 rounded-md bg-cs-error-container/30 text-cs-on-error-container text-sm';
      warn.textContent = `Rechazo previo: ${tenant.rejected_reason}`;
      card.appendChild(warn);
    }

    panel.appendChild(card);
  }

  // ── Tab: Users ─────────────────────────────────────────────────────────
  async function renderUsers() {
    const panel = document.querySelector('[data-panel="users"]');
    invDom.clearChildren(panel);
    const data = await adminApi.get(`/tenants/${tenantId}/users`);

    const card = document.createElement('div');
    card.className = 'rounded-lg bg-cs-surface-container-lowest p-2 overflow-x-auto';
    const table = document.createElement('table');
    table.className = 'w-full text-sm';
    table.appendChild(buildHead([
      { label: 'Nombre' }, { label: 'Email' }, { label: 'Rol' },
      { label: 'Alta' }, { label: '' },
    ]));
    const tbody = document.createElement('tbody');
    (data.users || []).forEach(u => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors';
      const cells = [u.name, u.email, u.role, formatDate(u.created_at)];
      cells.forEach(v => {
        const td = document.createElement('td');
        td.className = 'px-4 py-3 text-cs-on-surface';
        td.textContent = v != null ? v : '—';
        tr.appendChild(td);
      });
      const tdAct = document.createElement('td');
      tdAct.className = 'px-4 py-3 text-right';
      const btn = document.createElement('button');
      btn.className = 'px-2.5 py-1 rounded-md text-xs font-semibold bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high transition-colors cursor-pointer';
      btn.textContent = 'Reset password';
      btn.addEventListener('click', () => onResetPassword(u));
      tdAct.appendChild(btn);
      tr.appendChild(tdAct);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    card.appendChild(table);
    panel.appendChild(card);
  }

  async function onResetPassword(user) {
    const ok = await confirmAction({
      title: `Resetear password de ${user.email}`,
      message: 'Se generará una password temporal que deberás compartir de forma segura. La actual quedará invalidada.',
      confirmLabel: 'Resetear', destructive: true,
    });
    if (!ok) return;
    try {
      const res = await adminApi.post(`/users/${user.id}/reset-password`, {});
      const wrap = document.createElement('div');
      wrap.className = 'space-y-3';
      const p = document.createElement('p');
      p.className = 'text-sm text-cs-on-surface-var';
      p.textContent = res.message || 'Password temporal generada.';
      wrap.appendChild(p);
      const code = document.createElement('div');
      code.className = 'p-3 rounded-md bg-cs-surface-container font-mono text-sm text-cs-on-surface select-all';
      code.textContent = res.temp_password;
      wrap.appendChild(code);
      openModal({ title: 'Password temporal', content: wrap });
    } catch (err) { Toast.show(err.message, 'error'); }
  }

  // ── Tab: Billing ───────────────────────────────────────────────────────
  async function renderBilling() {
    const panel = document.querySelector('[data-panel="billing"]');
    invDom.clearChildren(panel);

    const subCard = document.createElement('div');
    subCard.className = 'rounded-lg bg-cs-surface-container-lowest p-6 space-y-3';
    const sH = document.createElement('h2');
    sH.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    sH.textContent = 'Suscripción';
    subCard.appendChild(sH);

    if (tenant.subscription) {
      const grid = document.createElement('div');
      grid.className = 'grid grid-cols-2 md:grid-cols-4 gap-3 text-sm';
      [
        ['Plan', tenant.subscription.plan_nombre || '—'],
        ['Estado', tenant.subscription.estado || '—'],
        ['Inicio', formatDate(tenant.subscription.inicio)],
        ['Próximo cobro', formatDate(tenant.subscription.proximo_cobro)],
      ].forEach(([k, v]) => {
        const cell = document.createElement('div');
        cell.className = 'rounded-md bg-cs-surface-container px-3 py-2';
        const lbl = document.createElement('p');
        lbl.className = 'text-[10px] font-semibold uppercase tracking-wide text-cs-on-surface-var';
        lbl.textContent = k;
        const val = document.createElement('p');
        val.className = 'text-sm text-cs-on-surface';
        val.textContent = v;
        cell.appendChild(lbl); cell.appendChild(val);
        grid.appendChild(cell);
      });
      subCard.appendChild(grid);
    } else {
      const empty = document.createElement('p');
      empty.className = 'text-sm text-cs-on-surface-var';
      empty.textContent = 'Esta clínica aún no tiene suscripción. Aprueba la solicitud para asignar un plan.';
      subCard.appendChild(empty);
    }
    panel.appendChild(subCard);

    const payCard = document.createElement('div');
    payCard.className = 'rounded-lg bg-cs-surface-container-lowest p-6 space-y-3';
    const pH = document.createElement('div');
    pH.className = 'flex items-center justify-between';
    const pTitle = document.createElement('h2');
    pTitle.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    pTitle.textContent = 'Historial de pagos';
    pH.appendChild(pTitle);
    const newBtn = document.createElement('button');
    newBtn.className = 'inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-cs-primary text-cs-on-primary text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer';
    const ic = document.createElement('i'); ic.setAttribute('data-lucide', 'plus'); ic.className = 'h-3 w-3';
    newBtn.appendChild(ic);
    newBtn.appendChild(document.createTextNode('Registrar pago'));
    newBtn.addEventListener('click', openNewPayment);
    pH.appendChild(newBtn);
    payCard.appendChild(pH);

    const pays = await adminApi.get(`/payments?tenant_id=${tenantId}`);
    if (!pays.payments || pays.payments.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'text-sm text-cs-on-surface-var';
      empty.textContent = 'Sin pagos registrados.';
      payCard.appendChild(empty);
    } else {
      const wrap = document.createElement('div');
      wrap.className = 'overflow-x-auto';
      const t = document.createElement('table');
      t.className = 'w-full text-sm';
      t.appendChild(buildHead([
        { label: 'Fecha' }, { label: 'Monto' }, { label: 'Método' },
        { label: 'Periodo' }, { label: 'Comentarios' }, { label: '' },
      ]));
      const tb = document.createElement('tbody');
      pays.payments.forEach(p => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-cs-surface-container transition-colors';
        const periodo = (p.periodo_inicio && p.periodo_fin)
          ? `${formatDate(p.periodo_inicio)} – ${formatDate(p.periodo_fin)}` : '—';
        const cells = [
          formatDate(p.fecha),
          currency(p.monto),
          p.metodo,
          periodo,
          p.comentarios || '—',
        ];
        cells.forEach(v => {
          const td = document.createElement('td');
          td.className = 'px-3 py-2 text-cs-on-surface';
          td.textContent = v;
          tr.appendChild(td);
        });
        const tdDel = document.createElement('td');
        tdDel.className = 'px-3 py-2 text-right';
        const del = document.createElement('button');
        del.className = 'text-cs-error text-xs font-semibold hover:underline cursor-pointer';
        del.textContent = 'Eliminar';
        del.addEventListener('click', async () => {
          const ok = await confirmAction({
            title: 'Eliminar pago',
            message: `¿Eliminar el pago del ${formatDate(p.fecha)}?`,
            confirmLabel: 'Eliminar', destructive: true,
          });
          if (!ok) return;
          await adminApi.del(`/payments/${p.id}`);
          Toast.show('Pago eliminado', 'success');
          await renderBilling();
        });
        tdDel.appendChild(del);
        tr.appendChild(tdDel);
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      wrap.appendChild(t);
      payCard.appendChild(wrap);
    }

    panel.appendChild(payCard);
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  function openNewPayment() {
    const wrap = document.createElement('div');
    wrap.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';
    const today = new Date().toISOString().slice(0, 10);
    const fecha = inputEl('date', 'fecha', today);
    const monto = inputEl('number', 'monto', '');
    monto.step = '0.01'; monto.min = '0';
    const metodo = selectEl('metodo', [
      { value: 'transferencia', label: 'Transferencia' },
      { value: 'efectivo', label: 'Efectivo' },
      { value: 'tarjeta', label: 'Tarjeta' },
      { value: 'otro', label: 'Otro' },
    ]);
    const pIni = inputEl('date', 'periodo_inicio', '');
    const pFin = inputEl('date', 'periodo_fin', '');
    const comen = textareaEl('comentarios', '', 2);

    wrap.appendChild(buildField('Fecha del pago', fecha));
    wrap.appendChild(buildField('Monto (MXN)', monto));
    wrap.appendChild(buildField('Método', metodo));
    wrap.appendChild(buildField('Periodo desde', pIni));
    wrap.appendChild(buildField('Periodo hasta', pFin));
    const fullCol = document.createElement('div');
    fullCol.className = 'md:col-span-2';
    fullCol.appendChild(buildField('Comentarios', comen));
    wrap.appendChild(fullCol);

    openModal({
      title: 'Registrar pago', content: wrap,
      primary: { label: 'Registrar', onClick: async () => {
        if (!fecha.value || !monto.value || parseFloat(monto.value) <= 0) {
          throw new Error('Fecha y monto son obligatorios.');
        }
        await adminApi.post('/payments', {
          tenant_id: tenantId,
          fecha: fecha.value,
          monto: parseFloat(monto.value),
          metodo: metodo.value,
          periodo_inicio: pIni.value || undefined,
          periodo_fin: pFin.value || undefined,
          comentarios: comen.value || undefined,
        });
        Toast.show('Pago registrado', 'success');
        await loadTenant();
        await renderBilling();
      } },
    });
  }

  // ── Tab: Notes ─────────────────────────────────────────────────────────
  async function renderNotes() {
    const panel = document.querySelector('[data-panel="notes"]');
    invDom.clearChildren(panel);

    const composer = document.createElement('div');
    composer.className = 'rounded-lg bg-cs-surface-container-lowest p-4 space-y-3';
    const ta = textareaEl('texto', '', 3);
    ta.placeholder = 'Nota interna sobre esta clínica…';
    composer.appendChild(ta);
    const addBtn = document.createElement('button');
    addBtn.className = 'px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold hover:opacity-95 transition-opacity cursor-pointer';
    addBtn.textContent = 'Agregar nota';
    addBtn.addEventListener('click', async () => {
      const txt = ta.value.trim();
      if (!txt) return;
      await adminApi.post(`/tenants/${tenantId}/notes`, { texto: txt });
      ta.value = '';
      Toast.show('Nota agregada', 'success');
      await renderNotes();
      await loadTenant();
    });
    composer.appendChild(addBtn);
    panel.appendChild(composer);

    const list = document.createElement('div');
    list.className = 'space-y-2';

    const data = await adminApi.get(`/tenants/${tenantId}/notes`);
    if (!data.notes || data.notes.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'text-sm text-cs-on-surface-var';
      empty.textContent = 'Sin notas todavía.';
      list.appendChild(empty);
    } else {
      data.notes.forEach(n => {
        const card = document.createElement('div');
        card.className = 'rounded-lg bg-cs-surface-container-lowest p-4 space-y-2';
        const meta = document.createElement('div');
        meta.className = 'flex items-center justify-between text-xs text-cs-on-surface-var';
        const left = document.createElement('span');
        left.textContent = `${n.autor_name || 'Sistema'} · ${formatDate(n.created_at)}`;
        const del = document.createElement('button');
        del.className = 'text-cs-error font-semibold hover:underline cursor-pointer';
        del.textContent = 'Eliminar';
        del.addEventListener('click', async () => {
          const ok = await confirmAction({
            title: 'Eliminar nota',
            message: 'Esta acción no se puede deshacer.',
            confirmLabel: 'Eliminar', destructive: true,
          });
          if (!ok) return;
          await adminApi.del(`/notes/${n.id}`);
          Toast.show('Nota eliminada', 'success');
          await renderNotes();
          await loadTenant();
        });
        meta.appendChild(left);
        meta.appendChild(del);

        const body = document.createElement('p');
        body.className = 'text-sm text-cs-on-surface whitespace-pre-wrap';
        body.textContent = n.texto;

        card.appendChild(meta);
        card.appendChild(body);
        list.appendChild(card);
      });
    }
    panel.appendChild(list);
  }

  // ── Tab: Metrics ───────────────────────────────────────────────────────
  async function renderMetrics() {
    const panel = document.querySelector('[data-panel="metrics"]');
    invDom.clearChildren(panel);
    const [mats, txs] = await Promise.all([
      adminApi.get(`/tenants/${tenantId}/materiales`),
      adminApi.get(`/tenants/${tenantId}/tratamientos`),
    ]);
    const grid = document.createElement('div');
    grid.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';
    grid.appendChild(kpiCard({
      label: 'Tratamientos en catálogo', value: (txs.tratamientos || []).length, icon: 'list',
    }));
    grid.appendChild(kpiCard({
      label: 'Materiales registrados', value: (mats.materiales || []).length, icon: 'package',
    }));
    panel.appendChild(grid);

    if ((mats.materiales || []).length > 0) {
      const card = document.createElement('div');
      card.className = 'rounded-lg bg-cs-surface-container-lowest p-2 overflow-x-auto';
      const t = document.createElement('table');
      t.className = 'w-full text-sm';
      t.appendChild(buildHead([
        { label: 'Material' },
        { label: 'Costo unitario', right: true },
        { label: 'Unidades / paquete', right: true },
      ]));
      const tb = document.createElement('tbody');
      mats.materiales.slice(0, 25).forEach(m => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-cs-surface-container transition-colors';
        const c1 = document.createElement('td'); c1.className = 'px-4 py-2.5 text-cs-on-surface'; c1.textContent = m.nombre;
        const c2 = document.createElement('td'); c2.className = 'px-4 py-2.5 text-right text-cs-on-surface'; c2.textContent = currency(m.costo_unitario || 0);
        const c3 = document.createElement('td'); c3.className = 'px-4 py-2.5 text-right text-cs-on-surface'; c3.textContent = m.unidades_paquete || '—';
        tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3);
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      card.appendChild(t);
      panel.appendChild(card);
    }
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  // ── Tab orchestration ─────────────────────────────────────────────────
  const renderers = {
    general: renderGeneral,
    users: renderUsers,
    billing: renderBilling,
    notes: renderNotes,
    metrics: renderMetrics,
  };

  function activateTab(name) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== name));
    const fn = renderers[name];
    if (fn) Promise.resolve(fn()).catch(err => Toast.show(err.message || 'Error', 'error'));
  }

  function wireTabs() {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.addEventListener('click', () => activateTab(b.dataset.tab));
    });
  }

  async function refreshAll() {
    await loadTenant();
    const active = document.querySelector('.tab-btn.active');
    activateTab(active ? active.dataset.tab : 'general');
  }

  async function init() {
    wireTabs();
    try {
      await loadTenant();
      activateTab('general');
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al cargar la clínica', 'error');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
