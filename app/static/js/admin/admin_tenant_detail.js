// Panel super-admin / Detalle de clínica
(function () {
  const { statusBadge, currency, formatDate, confirmAction, openModal,
          buildField, inputEl, selectEl, textareaEl, kpiCard } = window.adminUI;

  const root = document.querySelector('[data-tenant-id]');
  const tenantId = parseInt(root.dataset.tenantId, 10);
  let tenant = null;
  let plansCache = null;
  let billingSnapshot = null;

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

    actions.appendChild(headerBtn('Ver reportes', 'bar-chart-3', 'neutral', () => {
      window.location.href = `/admin/tenants/${tenantId}/reportes?as_tenant=${tenantId}`;
    }));

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

    // Sobre-cupo: más usuarios de un rol que asientos pagados. Lo calcula el
    // backend en _serialize_tenant, porque la capacidad depende de los asientos
    // activos y esta vista no los tiene cargados.
    const ETIQUETA_ROL_CUPO = {
      recepcionista: 'recepcionistas',
      asistente: 'asistentes dentales',
    };
    (tenant.sobre_cupo || []).forEach(rol => {
      const alerta = document.createElement('p');
      alerta.className = 'text-xs font-semibold text-cs-error';
      alerta.textContent =
        `Sobre-cupo: esta clínica tiene más ${ETIQUETA_ROL_CUPO[rol] || rol} `
        + 'activos que asientos pagados.';
      card.appendChild(alerta);
    });

    const nameInput = inputEl('text', 'name', tenant.name);
    const emailInput = inputEl('email', 'contact_email', tenant.contact_email || '');

    const grid = document.createElement('div');
    grid.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';
    grid.appendChild(buildField('Nombre', nameInput));
    grid.appendChild(buildField('Email de contacto', emailInput));

    const planDisplay = document.createElement('div');
    planDisplay.className = 'px-3 py-2 rounded-lg bg-cs-surface-container text-sm text-cs-on-surface';
    if (tenant.subscription && tenant.subscription.plan_nombre) {
      planDisplay.textContent = tenant.subscription.plan_nombre;
    } else {
      planDisplay.textContent = tenant.plan || 'Sin plan asignado';
      planDisplay.classList.add('text-cs-on-surface-var');
    }
    grid.appendChild(buildField('Plan actual', planDisplay));
    card.appendChild(grid);

    const saveBtn = document.createElement('button');
    saveBtn.className = 'px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold hover:opacity-95 transition-opacity cursor-pointer';
    saveBtn.textContent = 'Guardar cambios';
    saveBtn.addEventListener('click', async () => {
      try {
        const body = {
          name: nameInput.value.trim(),
          contact_email: emailInput.value.trim() || null,
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
      { label: 'Último acceso' }, { label: '' },
    ]));
    const tbody = document.createElement('tbody');
    (data.users || []).forEach(u => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors';
      if (!u.is_active) tr.classList.add('opacity-50');

      // Nombre (+ badge deshabilitado)
      const tdName = document.createElement('td');
      tdName.className = 'px-4 py-3 text-cs-on-surface';
      tdName.appendChild(document.createTextNode(u.name || '—'));
      if (!u.is_active) {
        const b = document.createElement('span');
        b.className = 'inline-flex items-center ml-2 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-cs-error-container/40 text-cs-on-error-container';
        b.textContent = 'Deshabilitado';
        tdName.appendChild(b);
      }
      tr.appendChild(tdName);

      // Email (+ badge contraseña temporal)
      const tdEmail = document.createElement('td');
      tdEmail.className = 'px-4 py-3 text-cs-on-surface';
      tdEmail.appendChild(document.createTextNode(u.email || '—'));
      if (u.must_change_password) {
        const badge = document.createElement('span');
        badge.className = 'inline-flex items-center ml-2 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-cs-surface-container-high text-cs-on-surface';
        badge.textContent = 'Contraseña temporal';
        tdEmail.appendChild(badge);
      }
      // Permisos del asistente, en solo lectura: el super-admin diagnostica,
      // no reparte permisos internos del tenant.
      if (u.role === 'asistente') {
        const permisos = u.permisos || {};
        const resumen = Object.keys(permisos).length
          ? Object.entries(permisos).map(([r, n]) => `${r}: ${n}`).join(' · ')
          : 'sin permisos';
        const chip = document.createElement('span');
        chip.className = 'block mt-1 text-[10px] text-cs-on-surface-var';
        chip.textContent = resumen;
        chip.title = 'Permisos otorgados por el administrador de la clínica';
        tdEmail.appendChild(chip);
      }
      tr.appendChild(tdEmail);

      // Rol
      const tdRole = document.createElement('td');
      tdRole.className = 'px-4 py-3';
      if (u.is_superuser) {
        tdRole.textContent = 'super-admin';
        tdRole.classList.add('text-cs-on-surface-var');
      } else {
        const sel = selectEl('role', [
          { value: 'admin', label: 'Admin' },
          { value: 'recepcionista', label: 'Recepcionista' },
          { value: 'asistente', label: 'Asistente dental' },
        ], u.role);
        sel.classList.add('text-xs', 'py-1');
        sel.disabled = !u.is_active;
        sel.addEventListener('change', async () => {
          const prev = u.role;
          try {
            const res = await adminApi.put(`/users/${u.id}/role`, { role: sel.value });
            u.role = sel.value;
            u.permisos = res.permisos || {};
            if (res.sobre_cupo) {
              Toast.show(
                `Rol actualizado, pero la clínica quedó sobre-cupo en ${res.sobre_cupo_rol}: `
                + 'tiene más usuarios de ese tipo que asientos pagados.',
                'warning'
              );
            } else {
              Toast.show('Rol actualizado', 'success');
            }
            renderUsers();
          } catch (err) {
            sel.value = prev;
            Toast.show(err.message || 'No se pudo cambiar el rol', 'error');
          }
        });
        tdRole.appendChild(sel);
      }
      tr.appendChild(tdRole);

      // Último acceso
      const tdLast = document.createElement('td');
      tdLast.className = 'px-4 py-3 text-cs-on-surface-var';
      tdLast.textContent = u.last_login ? formatDate(u.last_login) : 'Nunca';
      tr.appendChild(tdLast);

      // Acciones
      const tdAct = document.createElement('td');
      tdAct.className = 'px-4 py-3 text-right space-x-1';
      if (!u.is_superuser) {
        const toggleBtn = document.createElement('button');
        toggleBtn.className = u.is_active
          ? 'px-2.5 py-1 rounded-md text-xs font-semibold bg-cs-error/90 text-white hover:bg-cs-error transition-colors cursor-pointer'
          : 'px-2.5 py-1 rounded-md text-xs font-semibold bg-cs-primary text-cs-on-primary hover:opacity-90 transition-opacity cursor-pointer';
        toggleBtn.textContent = u.is_active ? 'Deshabilitar' : 'Habilitar';
        toggleBtn.addEventListener('click', async () => {
          try {
            await adminApi.put(`/users/${u.id}/active`, { is_active: !u.is_active });
            Toast.show(u.is_active ? 'Usuario deshabilitado' : 'Usuario habilitado', 'success');
            await renderUsers();
          } catch (err) {
            Toast.show(err.message || 'No se pudo cambiar el estado', 'error');
          }
        });
        tdAct.appendChild(toggleBtn);
      }
      const btn = document.createElement('button');
      btn.className = 'px-2.5 py-1 rounded-md text-xs font-semibold bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high transition-colors cursor-pointer';
      btn.textContent = 'Reset password';
      btn.disabled = !u.is_active;
      if (!u.is_active) btn.classList.add('opacity-40', 'cursor-not-allowed');
      else btn.addEventListener('click', () => onResetPassword(u));
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
  function buildMonthlyChargeCard(charge) {
    const paid = charge.clip_status === 'PAID';
    const estimated = Boolean(charge.is_estimate);
    const card = document.createElement('div');
    card.className = paid
      ? 'rounded-lg border border-green-500/25 bg-green-500/5 p-6 space-y-4'
      : 'rounded-lg border border-cs-primary/25 bg-cs-primary/5 p-6 space-y-4';

    const head = document.createElement('div');
    head.className = 'flex flex-wrap items-start justify-between gap-3';
    const titleWrap = document.createElement('div');
    const eyebrow = document.createElement('p');
    eyebrow.className = 'text-[10px] font-semibold uppercase tracking-wider text-cs-on-surface-var';
    eyebrow.textContent = estimated ? 'Próximo corte' : 'Corte mensual';
    const title = document.createElement('h2');
    title.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    title.textContent = estimated ? 'Total estimado del mes' : 'Total del mes';
    titleWrap.appendChild(eyebrow);
    titleWrap.appendChild(title);
    head.appendChild(titleWrap);

    const status = document.createElement('span');
    status.className = paid
      ? 'inline-flex px-2.5 py-1 rounded-full text-[10px] font-semibold bg-green-500/15 text-green-700'
      : estimated
        ? 'inline-flex px-2.5 py-1 rounded-full text-[10px] font-semibold bg-cs-surface-container-high text-cs-on-surface-var'
        : 'inline-flex px-2.5 py-1 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-700';
    status.textContent = paid ? 'Pagado' : estimated ? 'Estimado' : 'Pendiente';
    head.appendChild(status);
    card.appendChild(head);

    const total = document.createElement('p');
    total.className = 'font-cs-display text-3xl font-bold text-cs-on-surface';
    total.textContent = currency(charge.monto);
    card.appendChild(total);

    const breakdown = document.createElement('div');
    breakdown.className = 'grid grid-cols-2 lg:grid-cols-4 gap-3';
    const rows = [
      ['Plan', currency(charge.plan_amount)],
      ['Uso de facturas', currency(charge.invoice_base_fee)],
      [`Timbres (${charge.stamp_count || 0} × ${currency(charge.stamp_unit_price)})`, currency(charge.stamp_amount)],
      ['Total', currency(charge.monto)],
    ];
    rows.forEach(([label, value], index) => {
      const cell = document.createElement('div');
      cell.className = index === rows.length - 1
        ? 'rounded-md bg-cs-primary/10 px-3 py-2'
        : 'rounded-md bg-cs-surface-container-lowest px-3 py-2';
      const lbl = document.createElement('p');
      lbl.className = 'text-[10px] font-semibold uppercase tracking-wide text-cs-on-surface-var';
      lbl.textContent = label;
      const val = document.createElement('p');
      val.className = 'mt-1 text-sm font-semibold text-cs-on-surface';
      val.textContent = value;
      cell.appendChild(lbl);
      cell.appendChild(val);
      breakdown.appendChild(cell);
    });
    card.appendChild(breakdown);

    const meta = document.createElement('p');
    meta.className = 'text-xs text-cs-on-surface-var';
    meta.textContent = `Corte: ${formatDate(charge.billing_cycle_date)} · Fecha límite: ${formatDate(charge.due_date)}`;
    card.appendChild(meta);

    if (charge.can_mark_paid) {
      const payBtn = document.createElement('button');
      payBtn.className = 'inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cs-primary text-cs-on-primary text-sm font-semibold hover:opacity-90 transition-opacity cursor-pointer';
      const icon = document.createElement('i');
      icon.setAttribute('data-lucide', 'badge-check');
      icon.className = 'h-4 w-4';
      payBtn.appendChild(icon);
      payBtn.appendChild(document.createTextNode('Registrar este pago'));
      payBtn.addEventListener('click', () => openNewPayment(charge));
      card.appendChild(payBtn);
    } else if (estimated) {
      const note = document.createElement('p');
      note.className = 'text-xs text-cs-on-surface-var';
      note.textContent = 'El total se actualizará con los timbres acumulados y podrá marcarse como pagado al llegar la fecha de corte.';
      card.appendChild(note);
    }
    return card;
  }

  async function renderBilling() {
    const panel = document.querySelector('[data-panel="billing"]');
    invDom.clearChildren(panel);
    const pays = await adminApi.get(`/payments?tenant_id=${tenantId}`);
    billingSnapshot = pays;

    const subCard = document.createElement('div');
    subCard.className = 'rounded-lg bg-cs-surface-container-lowest p-6 space-y-3';
    const sH = document.createElement('h2');
    sH.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    sH.textContent = 'Suscripción';
    subCard.appendChild(sH);

    if (tenant.subscription) {
      const sub = tenant.subscription;
      const estadoColors = {
        activa: 'text-green-400',
        gracia: 'text-yellow-400',
        vencida: 'text-red-400',
        cancelada: 'text-cs-on-surface-var',
      };

      const grid = document.createElement('div');
      grid.className = 'grid grid-cols-2 md:grid-cols-4 gap-3 text-sm';

      const fields = [
        ['Plan', sub.plan_nombre || '—'],
        ['Estado', sub.estado || '—'],
        ['Inicio', formatDate(sub.inicio)],
        ['Próximo cobro', formatDate(sub.proximo_cobro)],
      ];
      if (sub.estado === 'gracia' && sub.grace_expires_at) {
        fields.push(['Gracia expira', formatDate(sub.grace_expires_at)]);
      }

      fields.forEach(([k, v]) => {
        const cell = document.createElement('div');
        cell.className = 'rounded-md bg-cs-surface-container px-3 py-2';
        const lbl = document.createElement('p');
        lbl.className = 'text-[10px] font-semibold uppercase tracking-wide text-cs-on-surface-var';
        lbl.textContent = k;
        const val = document.createElement('p');
        val.className = `text-sm ${k === 'Estado' ? (estadoColors[v] || 'text-cs-on-surface') : 'text-cs-on-surface'} font-semibold`;
        val.textContent = v;
        cell.appendChild(lbl); cell.appendChild(val);
        grid.appendChild(cell);
      });
      subCard.appendChild(grid);

      if (sub.estado === 'vencida') {
        const warn = document.createElement('div');
        warn.className = 'flex items-center gap-2 p-3 rounded-md bg-red-500/10 text-red-400 text-xs font-semibold';
        const wIc = document.createElement('i'); wIc.setAttribute('data-lucide', 'alert-circle'); wIc.className = 'h-4 w-4 shrink-0';
        warn.appendChild(wIc);
        warn.appendChild(document.createTextNode('Cuenta inactiva — registra un pago para habilitarla.'));
        subCard.appendChild(warn);
      }

      // Cambio de plan programado (downgrade pendiente)
      if (sub.plan_programado_nombre) {
        const prog = document.createElement('div');
        prog.className = 'flex flex-wrap items-center gap-2 p-3 rounded-md bg-cs-primary/10 text-cs-on-surface text-xs';
        const pIc = document.createElement('i'); pIc.setAttribute('data-lucide', 'calendar-clock'); pIc.className = 'h-4 w-4 shrink-0 text-cs-primary';
        prog.appendChild(pIc);
        const pTxt = document.createElement('span');
        pTxt.appendChild(document.createTextNode('Cambio programado a '));
        const strong = document.createElement('strong');
        strong.textContent = sub.plan_programado_nombre;
        pTxt.appendChild(strong);
        pTxt.appendChild(document.createTextNode(
          sub.plan_programado_desde ? ` el ${formatDate(sub.plan_programado_desde)}` : ''
        ));
        prog.appendChild(pTxt);
        const cancelProg = document.createElement('button');
        cancelProg.className = 'ml-auto px-2 py-1 rounded-md bg-cs-surface-container text-cs-on-surface font-semibold hover:bg-cs-surface-container-high transition-colors cursor-pointer';
        cancelProg.textContent = 'Cancelar cambio';
        cancelProg.addEventListener('click', async () => {
          const ok = await confirmAction({
            title: 'Cancelar cambio de plan',
            message: `Se cancelará el cambio programado a ${sub.plan_programado_nombre}.`,
            confirmLabel: 'Cancelar cambio', destructive: true,
          });
          if (!ok) return;
          await adminApi.del(`/tenants/${tenantId}/plan-programado`);
          Toast.show('Cambio de plan cancelado', 'success');
          await refreshAll();
        });
        prog.appendChild(cancelProg);
        subCard.appendChild(prog);
      }

      // Module badges
      const mods = sub.plan_modulos || [];
      if (mods.length > 0) {
        const modRow = document.createElement('div');
        modRow.className = 'flex items-center gap-2 pt-1';
        const modLabel = document.createElement('span');
        modLabel.className = 'text-[10px] font-semibold uppercase tracking-wide text-cs-on-surface-var';
        modLabel.textContent = 'Módulos:';
        modRow.appendChild(modLabel);
        const MOD_LABELS = { contable: 'Contable', inventario: 'Inventario', finanzas_personales: 'Finanzas', crm: 'CRM' };
        mods.forEach(m => {
          const badge = document.createElement('span');
          badge.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold bg-cs-primary-container text-cs-on-primary-container';
          badge.textContent = MOD_LABELS[m] || m;
          modRow.appendChild(badge);
        });
        subCard.appendChild(modRow);
      }

      // Acciones de suscripción
      const subActions = document.createElement('div');
      subActions.className = 'flex flex-wrap gap-2 mt-1';

      const changePlanBtn = document.createElement('button');
      changePlanBtn.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-cs-surface-container text-cs-on-surface text-xs font-semibold hover:bg-cs-surface-container-high transition-colors cursor-pointer';
      const cpIc = document.createElement('i'); cpIc.setAttribute('data-lucide', 'repeat'); cpIc.className = 'h-3 w-3';
      changePlanBtn.appendChild(cpIc);
      changePlanBtn.appendChild(document.createTextNode('Cambiar plan'));
      changePlanBtn.addEventListener('click', () => openAssignPlan(sub));
      subActions.appendChild(changePlanBtn);

      const editDateBtn = document.createElement('button');
      editDateBtn.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-cs-surface-container text-cs-on-surface text-xs font-semibold hover:bg-cs-surface-container-high transition-colors cursor-pointer';
      const edIc = document.createElement('i'); edIc.setAttribute('data-lucide', 'calendar-clock'); edIc.className = 'h-3 w-3';
      editDateBtn.appendChild(edIc);
      editDateBtn.appendChild(document.createTextNode('Editar fecha de cobro'));
      editDateBtn.addEventListener('click', () => openEditFechaCobro(sub));
      subActions.appendChild(editDateBtn);

      const upgradeBtn = document.createElement('button');
      upgradeBtn.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-cs-primary text-cs-on-primary text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer';
      const upIc = document.createElement('i'); upIc.setAttribute('data-lucide', 'trending-up'); upIc.className = 'h-3 w-3';
      upgradeBtn.appendChild(upIc);
      upgradeBtn.appendChild(document.createTextNode('Upgrade / Downgrade'));
      upgradeBtn.addEventListener('click', () => openCambioPlan(sub));
      subActions.appendChild(upgradeBtn);

      subCard.appendChild(subActions);
    } else {
      const empty = document.createElement('p');
      empty.className = 'text-sm text-cs-on-surface-var';
      empty.textContent = 'Sin suscripción asignada. Asigna un plan para habilitar la cuenta mediante pago.';
      subCard.appendChild(empty);

      const assignBtn = document.createElement('button');
      assignBtn.className = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-cs-primary text-cs-on-primary text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer mt-2';
      const aIc = document.createElement('i'); aIc.setAttribute('data-lucide', 'tag'); aIc.className = 'h-3 w-3';
      assignBtn.appendChild(aIc);
      assignBtn.appendChild(document.createTextNode('Asignar plan'));
      assignBtn.addEventListener('click', () => openAssignPlan(null));
      subCard.appendChild(assignBtn);
    }
    panel.appendChild(subCard);

    if (pays.monthly_charge) {
      panel.appendChild(buildMonthlyChargeCard(pays.monthly_charge));
    }

    const payCard = document.createElement('div');
    payCard.className = 'rounded-lg bg-cs-surface-container-lowest p-6 space-y-3';
    const pH = document.createElement('div');
    pH.className = 'flex flex-wrap items-center justify-between gap-2';
    const pTitle = document.createElement('h2');
    pTitle.className = 'font-cs-display text-lg font-semibold text-cs-on-surface';
    pTitle.textContent = 'Historial de pagos';
    pH.appendChild(pTitle);
    const newBtn = document.createElement('button');
    newBtn.className = 'inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-cs-primary text-cs-on-primary text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer';
    const ic = document.createElement('i'); ic.setAttribute('data-lucide', 'plus'); ic.className = 'h-3 w-3';
    newBtn.appendChild(ic);
    newBtn.appendChild(document.createTextNode('Registrar pago'));
    newBtn.addEventListener('click', () => {
      const charge = billingSnapshot && billingSnapshot.monthly_charge;
      openNewPayment(charge && charge.can_mark_paid ? charge : null);
    });
    pH.appendChild(newBtn);

    if (tenant.subscription) {
      const clipBtn = document.createElement('button');
      clipBtn.className = 'inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-cs-surface-container-high text-cs-on-surface text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer';
      const clipIc = document.createElement('i'); clipIc.setAttribute('data-lucide', 'credit-card'); clipIc.className = 'h-3 w-3';
      clipBtn.appendChild(clipIc);
      clipBtn.appendChild(document.createTextNode('Cobrar con Clip'));
      clipBtn.addEventListener('click', onChargeClip);
      pH.appendChild(clipBtn);
    }

    payCard.appendChild(pH);

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
        { label: 'Estado' }, { label: 'Periodo' }, { label: 'Comentarios' }, { label: '' },
      ]));
      const tb = document.createElement('tbody');
      pays.payments.forEach(p => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-cs-surface-container transition-colors';
        const periodo = (p.periodo_inicio && p.periodo_fin)
          ? `${formatDate(p.periodo_inicio)} – ${formatDate(p.periodo_fin)}` : '—';
        const cells = [
          { v: formatDate(p.fecha) },
          { v: currency(p.monto) },
          { v: p.metodo },
          { v: p.clip_status || '—', isClip: Boolean(p.clip_status) },
          { v: periodo },
          { v: p.comentarios || '—' },
        ];
        cells.forEach(({ v, isClip }) => {
          const td = document.createElement('td');
          td.className = 'px-3 py-2 text-cs-on-surface';
          if (isClip) {
            const badge = document.createElement('span');
            const color = v === 'PAID' ? 'bg-green-100 text-green-800'
              : v === 'PENDING' ? 'bg-yellow-100 text-yellow-800'
              : 'bg-red-100 text-red-800';
            badge.className = `inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold ${color}`;
            badge.textContent = v;
            td.appendChild(badge);
          } else {
            td.textContent = v;
          }
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

  async function openNewPayment(monthlyCharge = null) {
    const isMonthlyCharge = Boolean(monthlyCharge && monthlyCharge.can_mark_paid);
    const plans = isMonthlyCharge ? [] : (await loadPlans()).filter(p => p.activo);
    const plansById = {};
    plans.forEach(p => { plansById[p.id] = p; });

    const wrap = document.createElement('div');
    wrap.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';
    const today = new Date().toISOString().slice(0, 10);

    const planSel = selectEl('plan_id', plans.map(p => ({ value: p.id, label: `${p.nombre} — ${currency(p.precio_mensual)}/mes` })));
    const currentPlanId = tenant.subscription && tenant.subscription.plan_id;
    if (currentPlanId && plansById[currentPlanId]) planSel.value = String(currentPlanId);

    const fecha = inputEl('date', 'fecha', today);
    const monto = inputEl('number', 'monto', isMonthlyCharge ? monthlyCharge.monto : '');
    monto.step = '0.01'; monto.min = '0';
    if (isMonthlyCharge) {
      monto.readOnly = true;
      monto.classList.add('opacity-75', 'cursor-not-allowed');
    }
    const methodOptions = [
      { value: 'transferencia', label: 'Transferencia' },
      { value: 'efectivo', label: 'Efectivo' },
      { value: 'tarjeta', label: 'Tarjeta' },
      { value: 'otro', label: 'Otro' },
    ];
    if (!isMonthlyCharge) methodOptions.splice(3, 0, { value: 'clip', label: 'Clip' });
    const metodo = selectEl('metodo', methodOptions);
    const pIni = inputEl(
      'date', 'periodo_inicio',
      isMonthlyCharge ? monthlyCharge.periodo_inicio : today,
    );
    const pFin = inputEl(
      'date', 'periodo_fin',
      isMonthlyCharge ? monthlyCharge.periodo_fin : '',
    );
    const comen = textareaEl(
      'comentarios',
      isMonthlyCharge ? `Pago manual del corte ${monthlyCharge.billing_cycle_date}` : '',
      2,
    );
    if (isMonthlyCharge) {
      pIni.readOnly = true;
      pFin.readOnly = true;
      pIni.classList.add('opacity-75', 'cursor-not-allowed');
      pFin.classList.add('opacity-75', 'cursor-not-allowed');
    }

    // Al elegir un plan se autollenan monto y periodo (editables).
    let montoTouched = isMonthlyCharge;
    let finTouched = isMonthlyCharge;
    function selectedPlan() { return plansById[parseInt(planSel.value, 10)]; }
    function refreshFromPlan() {
      const plan = selectedPlan();
      if (!plan) return;
      if (!montoTouched) monto.value = plan.precio_mensual != null ? plan.precio_mensual : '';
      if (!finTouched) pFin.value = computeProximo(plan, pIni.value);
    }
    planSel.addEventListener('change', () => { montoTouched = false; finTouched = false; refreshFromPlan(); });
    pIni.addEventListener('change', () => { if (!finTouched) pFin.value = computeProximo(selectedPlan(), pIni.value); });
    monto.addEventListener('input', () => { montoTouched = true; });
    pFin.addEventListener('input', () => { finTouched = true; });

    if (isMonthlyCharge) {
      const summary = document.createElement('div');
      summary.className = 'md:col-span-2 rounded-lg border border-cs-primary/25 bg-cs-primary/5 p-4 space-y-2';
      const summaryTitle = document.createElement('p');
      summaryTitle.className = 'text-sm font-semibold text-cs-on-surface';
      summaryTitle.textContent = `Total del mes: ${currency(monthlyCharge.monto)}`;
      const summaryBody = document.createElement('p');
      summaryBody.className = 'text-xs text-cs-on-surface-var';
      summaryBody.textContent = `Plan ${currency(monthlyCharge.plan_amount)} + facturación ${currency(monthlyCharge.invoice_base_fee)} + ${monthlyCharge.stamp_count || 0} timbres (${currency(monthlyCharge.stamp_amount)}).`;
      summary.appendChild(summaryTitle);
      summary.appendChild(summaryBody);
      wrap.appendChild(summary);
    } else if (plans.length > 0) {
      const planCol = document.createElement('div');
      planCol.className = 'md:col-span-2';
      planCol.appendChild(buildField('Plan', planSel));
      wrap.appendChild(planCol);
    }
    wrap.appendChild(buildField('Fecha del pago', fecha));
    wrap.appendChild(buildField('Monto (MXN)', monto));
    wrap.appendChild(buildField('Método', metodo));
    wrap.appendChild(buildField('Periodo desde', pIni));
    wrap.appendChild(buildField('Periodo hasta', pFin));
    const fullCol = document.createElement('div');
    fullCol.className = 'md:col-span-2';
    fullCol.appendChild(buildField('Comentarios', comen));
    wrap.appendChild(fullCol);

    if (!isMonthlyCharge && plans.length > 0) refreshFromPlan();

    const note = document.createElement('div');
    note.className = 'md:col-span-2 flex items-start gap-2 p-3 rounded-md bg-cs-primary/10 text-cs-on-surface text-xs';
    const noteIc = document.createElement('i'); noteIc.setAttribute('data-lucide', 'info'); noteIc.className = 'h-4 w-4 shrink-0 text-cs-primary mt-0.5';
    note.appendChild(noteIc);
    note.appendChild(document.createTextNode(
      isMonthlyCharge
        ? 'Se liquidará el corte mensual existente sin crear un pago duplicado. La clínica quedará activa y el próximo cobro avanzará un mes.'
        : 'Al registrar un pago con "Periodo hasta" la suscripción se activará y la cuenta quedará habilitada hasta esa fecha.'
    ));
    wrap.appendChild(note);

    openModal({
      title: isMonthlyCharge ? 'Marcar corte como pagado' : 'Registrar pago', content: wrap,
      primary: { label: isMonthlyCharge ? 'Marcar como pagado' : 'Registrar', onClick: async () => {
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
          pending_payment_id: isMonthlyCharge && monthlyCharge.id
            ? monthlyCharge.id : undefined,
          billing_cycle_date: isMonthlyCharge && !monthlyCharge.id
            ? monthlyCharge.billing_cycle_date : undefined,
        });
        Toast.show(
          isMonthlyCharge ? 'Corte mensual marcado como pagado' : 'Pago registrado',
          'success',
        );
        await refreshAll();
      } },
    });
  }

  async function onChargeClip() {
    if (!tenant.subscription) {
      Toast.show('La clínica necesita una suscripción activa para cobrar.', 'warning');
      return;
    }
    const planName = tenant.subscription.plan_nombre || tenant.plan || '';
    const ok = await confirmAction({
      title: `Cobrar con Clip — ${tenant.name}`,
      message: `Se cerrará el periodo de ${planName} y se generará un link por el plan, la cuota de facturación y los timbres acumulados. Solo puede hacerse al llegar la fecha de corte.`,
      confirmLabel: 'Generar cobro variable',
    });
    if (!ok) return;

    try {
      const result = await adminApi.post(`/tenants/${tenantId}/charge`, {});
      const url = result.clip_url;
      if (url) {
        window.open(url, '_blank');
        Toast.show('Link de pago generado. Se abrió en nueva pestaña.', 'success');
      } else {
        Toast.show('Link generado pero sin URL de redirección.', 'warning');
      }
      await loadTenant();
      await renderBilling();
    } catch (err) {
      Toast.show(err.message || 'Error al generar cobro Clip', 'error');
    }
  }

  // ── Date helpers (espejo de _compute_proximo_cobro del backend) ─────────
  function addDays(dateStr, days) {
    const [y, m, d] = dateStr.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    dt.setDate(dt.getDate() + days);
    const pad = n => String(n).padStart(2, '0');
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
  }

  function addOneMonth(dateStr) {
    const [y, m, d] = dateStr.split('-').map(Number);
    let ny = y, nm = m + 1;
    if (nm > 12) { nm = 1; ny += 1; }
    const lastDay = new Date(ny, nm, 0).getDate(); // último día del mes destino
    const pad = n => String(n).padStart(2, '0');
    return `${ny}-${pad(nm)}-${pad(Math.min(d, lastDay))}`;
  }

  function computeProximo(plan, inicioStr) {
    if (!inicioStr) return '';
    if (plan && plan.dias_expiracion && plan.dias_expiracion > 0) {
      return addDays(inicioStr, plan.dias_expiracion);
    }
    return addOneMonth(inicioStr);
  }

  async function openAssignPlan(sub) {
    const plans = (await loadPlans()).filter(p => p.activo);
    if (plans.length === 0) { Toast.show('No hay planes activos', 'warning'); return; }
    const isNew = !sub;
    const plansById = {};
    plans.forEach(p => { plansById[p.id] = p; });

    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const info = document.createElement('p');
    info.className = 'text-sm text-cs-on-surface-var';
    info.textContent = isNew
      ? 'Asigna un plan. La cuenta quedará inactiva hasta que registres un pago (salvo planes free/temporales).'
      : `Plan actual: ${sub.plan_nombre || '—'}. Selecciona el nuevo plan:`;
    wrap.appendChild(info);

    const planSel = selectEl('plan_id', plans.map(p => ({ value: p.id, label: `${p.nombre} — ${currency(p.precio_mensual)}/mes` })));
    if (!isNew) planSel.value = String(sub.plan_id);
    wrap.appendChild(buildField(isNew ? 'Plan' : 'Nuevo plan', planSel));

    // La fecha de inicio toma la fecha en la que se hace el cambio (hoy).
    const today = new Date().toISOString().slice(0, 10);
    const inicio = inputEl('date', 'inicio', today);
    wrap.appendChild(buildField('Fecha de inicio', inicio));

    const proximo = inputEl('date', 'proximo_cobro', '');
    const proximoField = buildField('Próximo cobro', proximo);
    const proximoLabel = proximoField.querySelector('span');
    wrap.appendChild(proximoField);

    const upgradeNote = document.createElement('p');
    upgradeNote.className = 'text-xs text-cs-primary hidden';
    upgradeNote.textContent = 'Se conserva la fecha de cobro actual (upgrade entre planes de pago).';
    wrap.appendChild(upgradeNote);

    // Un upgrade entre planes de pago conserva el aniversario de cobro (espejo
    // de la regla autoritativa del backend en assign_plan).
    const currentPlan = isNew ? null : plansById[sub.plan_id];
    const isPaidPlan = p => !!(p && p.precio_mensual > 0 && !p.es_temporal);
    function isUpgrade() { return !isNew && isPaidPlan(currentPlan) && isPaidPlan(selectedPlan()); }
    function setReadonly(el, ro) {
      el.readOnly = ro;
      el.classList.toggle('opacity-75', ro);
      el.classList.toggle('cursor-not-allowed', ro);
    }

    let proximoTouched = false;
    function selectedPlan() { return plansById[parseInt(planSel.value, 10)]; }
    function refreshProximo() {
      const plan = selectedPlan();
      if (isUpgrade()) {
        inicio.value = sub.inicio || inicio.value;
        proximo.value = sub.proximo_cobro || '';
        proximoLabel.textContent = 'Próximo cobro (se conserva)';
        upgradeNote.classList.remove('hidden');
        setReadonly(inicio, true);
        setReadonly(proximo, true);
        return;
      }
      upgradeNote.classList.add('hidden');
      setReadonly(inicio, false);
      setReadonly(proximo, false);
      const hasVigencia = !!(plan && plan.dias_expiracion && plan.dias_expiracion > 0);
      proximoLabel.textContent = hasVigencia ? 'Fin de vigencia' : 'Próximo cobro';
      if (!proximoTouched) proximo.value = computeProximo(plan, inicio.value);
    }
    // Cambiar plan o fecha de inicio reactiva el autocálculo.
    planSel.addEventListener('change', () => { proximoTouched = false; refreshProximo(); });
    inicio.addEventListener('change', () => { proximoTouched = false; refreshProximo(); });
    proximo.addEventListener('input', () => { proximoTouched = true; });
    refreshProximo();

    openModal({
      title: isNew ? `Asignar plan — ${tenant.name}` : `Cambiar plan — ${tenant.name}`,
      content: wrap,
      primary: {
        label: isNew ? 'Asignar plan' : 'Cambiar plan',
        onClick: async () => {
          const newPlanId = parseInt(planSel.value, 10);
          if (!isNew && newPlanId === sub.plan_id && inicio.value === sub.inicio && proximo.value === sub.proximo_cobro) {
            throw new Error('Selecciona un plan diferente o cambia las fechas.');
          }
          await adminApi.post(`/tenants/${tenantId}/assign-plan`, {
            plan_id: newPlanId,
            inicio: inicio.value || undefined,
            proximo_cobro: proximo.value || undefined,
          });
          Toast.show(isNew ? 'Plan asignado. Registra un pago para activar la cuenta.' : 'Plan actualizado', 'success');
          await refreshAll();
        },
      },
    });
  }

  async function openCambioPlan(sub) {
    // cobro_variable = plan principal de pago (excluye addons, free y temporales).
    const plans = (await loadPlans()).filter(
      p => p.activo && p.cobro_variable && p.id !== sub.plan_id
    );
    const actual = (await loadPlans()).find(p => p.id === sub.plan_id);
    if (!actual || actual.precio_mensual <= 0 || actual.es_temporal) {
      Toast.show('El plan actual no es de pago. Usa "Cambiar plan".', 'warning');
      return;
    }
    if (plans.length === 0) { Toast.show('No hay otros planes de pago activos', 'warning'); return; }

    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const info = document.createElement('p');
    info.className = 'text-sm text-cs-on-surface-var';
    info.textContent = `Plan actual: ${actual.nombre} (${currency(actual.precio_mensual)}/mes). `
      + 'Un plan más caro se aplica ya y cobra la diferencia; uno más barato se '
      + 'programa para el próximo cobro, sin cargo.';
    wrap.appendChild(info);

    const planSel = selectEl('plan_id', plans.map(p => ({
      value: p.id,
      label: `${p.nombre} — ${currency(p.precio_mensual)}/mes`,
    })));
    wrap.appendChild(buildField('Nuevo plan', planSel));

    const metodo = selectEl('metodo', [
      { value: 'transferencia', label: 'Transferencia' },
      { value: 'efectivo', label: 'Efectivo' },
      { value: 'tarjeta', label: 'Tarjeta' },
      { value: 'otro', label: 'Otro' },
    ]);
    const metodoField = buildField('Método de cobro de la diferencia', metodo);
    wrap.appendChild(metodoField);

    const resumen = document.createElement('div');
    resumen.className = 'p-3 rounded-md text-xs font-semibold';
    wrap.appendChild(resumen);

    function selected() { return plans.find(p => p.id === parseInt(planSel.value, 10)); }
    function refresh() {
      const p = selected();
      if (!p) return;
      const diff = Math.round((p.precio_mensual - actual.precio_mensual) * 100) / 100;
      const esUpgrade = diff > 0;
      metodoField.classList.toggle('hidden', !esUpgrade);
      resumen.className = 'p-3 rounded-md text-xs font-semibold '
        + (esUpgrade ? 'bg-cs-primary/10 text-cs-on-surface' : 'bg-cs-surface-container text-cs-on-surface-var');
      resumen.textContent = esUpgrade
        ? `Upgrade: se cobra la diferencia de ${currency(diff)} y el plan entra de inmediato. La fecha de cobro no cambia.`
        : `Downgrade: sin cobro. El cambio se aplicará el ${formatDate(sub.proximo_cobro)}.`;
    }
    planSel.addEventListener('change', refresh);
    refresh();

    openModal({
      title: `Cambio de plan — ${tenant.name}`,
      content: wrap,
      primary: {
        label: 'Aplicar cambio',
        onClick: async () => {
          const p = selected();
          if (!p) throw new Error('Selecciona un plan.');
          await adminApi.post(`/tenants/${tenantId}/cambio-plan`, {
            plan_id: p.id,
            metodo: metodo.value,
          });
          const diff = p.precio_mensual - actual.precio_mensual;
          Toast.show(diff > 0 ? 'Upgrade aplicado y diferencia registrada'
                              : 'Downgrade programado', 'success');
          await refreshAll();
        },
      },
    });
  }

  async function openEditFechaCobro(sub) {
    const today = new Date().toISOString().slice(0, 10);
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const info = document.createElement('p');
    info.className = 'text-sm text-cs-on-surface-var';
    info.textContent = 'Corrige la fecha del próximo cobro sin cambiar el plan. '
      + 'Si la fecha es futura, la cuenta se reactiva.';
    wrap.appendChild(info);

    const fecha = inputEl('date', 'proximo_cobro', sub.proximo_cobro || today);
    wrap.appendChild(buildField('Próximo cobro', fecha));

    openModal({
      title: `Editar fecha de cobro — ${tenant.name}`,
      content: wrap,
      primary: {
        label: 'Guardar',
        onClick: async () => {
          if (!fecha.value) throw new Error('Selecciona una fecha.');
          await adminApi.put(`/tenants/${tenantId}/subscription/fecha-cobro`, {
            proximo_cobro: fecha.value,
          });
          Toast.show('Fecha de cobro actualizada', 'success');
          await refreshAll();
        },
      },
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

  // ── Asientos de recepcionista ──────────────────────────────────────────
  async function loadAsientos() {
    const cont = document.getElementById('asientos-list');
    if (!cont) return;
    let data;
    try { data = await adminApi.get(`/tenants/${tenantId}/asientos`); }
    catch { cont.textContent = 'Error al cargar asientos'; return; }
    invDom.clearChildren(cont);
    const asientos = (data.asientos || []).filter(a => a.estado !== 'cancelada' && a.estado !== 'rechazada');
    if (!asientos.length) { cont.textContent = 'Sin asientos.'; return; }
    asientos.forEach(a => cont.appendChild(
      window.adminAsientos.renderRow(a, { onChange: loadAsientos })
    ));
  }

  // ── Tab: Audit ─────────────────────────────────────────────────────────
  async function renderAudit() {
    const panel = document.querySelector('[data-panel="audit"]');
    invDom.clearChildren(panel);
    const data = await adminApi.get(`/audit?tenant_id=${tenantId}`);
    const events = data.events || [];

    const card = document.createElement('div');
    card.className = 'rounded-lg bg-cs-surface-container-lowest p-2 overflow-x-auto';
    if (events.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'text-sm text-cs-on-surface-var p-4';
      empty.textContent = 'Sin eventos registrados para esta clínica.';
      card.appendChild(empty);
      panel.appendChild(card);
      return;
    }
    const table = document.createElement('table');
    table.className = 'w-full text-sm';
    table.appendChild(buildHead([
      { label: 'Fecha' }, { label: 'Actor' }, { label: 'Acción' }, { label: 'Detalle' },
    ]));
    const tbody = document.createElement('tbody');
    events.forEach(e => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors';
      const cells = [formatDate(e.created_at), e.actor_name || '—', e.action, e.summary || '—'];
      cells.forEach(v => {
        const td = document.createElement('td');
        td.className = 'px-4 py-2.5 text-cs-on-surface';
        td.textContent = v;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    card.appendChild(table);
    panel.appendChild(card);
  }

  // ── Tab orchestration ─────────────────────────────────────────────────
  const renderers = {
    general: renderGeneral,
    users: renderUsers,
    billing: renderBilling,
    notes: renderNotes,
    metrics: renderMetrics,
    audit: renderAudit,
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
      loadAsientos();
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
