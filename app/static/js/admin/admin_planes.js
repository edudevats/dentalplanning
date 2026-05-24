// Panel super-admin / Planes
(function () {
  const { currency, openModal, buildField, inputEl, textareaEl } = window.adminUI;

  const MODULOS = [
    { slug: 'contable', label: 'Sistema Contable', desc: 'Tratamientos, precios, dashboard, reportes' },
    { slug: 'inventario', label: 'Inventario', desc: 'Materiales, lotes, operatorios' },
    { slug: 'finanzas_personales', label: 'Finanzas Personales', desc: 'Ingresos y gastos personales del dueño' },
  ];
  const MOD_LABELS = { contable: 'Contable', inventario: 'Inventario', finanzas_personales: 'Finanzas' };

  let plans = [];
  let subsCountByPlan = {};

  async function loadAll() {
    const [plansResp, subsResp] = await Promise.all([
      adminApi.get('/plans'),
      adminApi.get('/subscriptions'),
    ]);
    plans = plansResp.plans || [];
    subsCountByPlan = {};
    (subsResp.subscriptions || []).forEach(s => {
      subsCountByPlan[s.plan_id] = (subsCountByPlan[s.plan_id] || 0) + 1;
    });
    render();
  }

  function render() {
    const tbody = document.getElementById('planes-rows');
    invDom.clearChildren(tbody);
    document.getElementById('empty-state').classList.toggle('hidden', plans.length > 0);

    plans.forEach(p => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors duration-200';

      // Nombre
      const tdName = document.createElement('td');
      tdName.className = 'px-4 py-3.5 font-semibold text-cs-on-surface';
      tdName.textContent = p.nombre;

      // Precio
      const tdPrice = document.createElement('td');
      tdPrice.className = 'px-4 py-3.5 text-right font-cs-display font-semibold text-cs-on-surface';
      tdPrice.textContent = currency(p.precio_mensual);

      // Módulos
      const tdMods = document.createElement('td');
      tdMods.className = 'px-4 py-3.5';
      const mods = p.modulos || [];
      if (mods.length === 0) {
        tdMods.textContent = '—';
        tdMods.classList.add('text-cs-on-surface-var');
      } else {
        const wrap = document.createElement('div');
        wrap.className = 'flex flex-wrap gap-1';
        mods.forEach(m => {
          const badge = document.createElement('span');
          badge.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold bg-cs-primary-container text-cs-on-primary-container';
          badge.textContent = MOD_LABELS[m] || m;
          wrap.appendChild(badge);
        });
        tdMods.appendChild(wrap);
      }

      // Descripción
      const tdDesc = document.createElement('td');
      tdDesc.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdDesc.textContent = p.descripcion || '—';

      // Tipo (temporal / permanente)
      const tdTipo = document.createElement('td');
      tdTipo.className = 'px-4 py-3.5 text-center';
      const tipoBadge = document.createElement('span');
      if (p.es_temporal) {
        tipoBadge.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold bg-yellow-500/15 text-yellow-600';
        tipoBadge.textContent = p.dias_expiracion ? p.dias_expiracion + ' días' : 'Temporal';
      } else {
        tipoBadge.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold bg-cs-primary-container text-cs-on-primary-container';
        tipoBadge.textContent = 'Permanente';
      }
      tdTipo.appendChild(tipoBadge);

      // Visibilidad (público / oculto) — toggle
      const tdVis = document.createElement('td');
      tdVis.className = 'px-4 py-3.5 text-center';
      tdVis.appendChild(buildVisToggle(p));

      // Suscripciones
      const tdSubs = document.createElement('td');
      tdSubs.className = 'px-4 py-3.5 text-center text-cs-on-surface';
      tdSubs.textContent = subsCountByPlan[p.id] || 0;

      // Promo (cupo/fecha/codigo)
      const tdPromo = document.createElement('td');
      tdPromo.className = 'px-4 py-3.5 text-center';
      tdPromo.appendChild(buildPromoBadge(p));

      // Estado (toggle)
      const tdStatus = document.createElement('td');
      tdStatus.className = 'px-4 py-3.5 text-center';
      tdStatus.appendChild(buildStatusToggle(p));

      // Clip sync status
      const tdClip = document.createElement('td');
      tdClip.className = 'px-4 py-3.5 text-center';
      tdClip.appendChild(buildClipBadge(p));

      // Acciones
      const tdAct = document.createElement('td');
      tdAct.className = 'px-4 py-3.5 text-right';
      const editBtn = document.createElement('button');
      editBtn.className = 'inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-cs-surface-container text-cs-on-surface hover:bg-cs-surface-container-high transition-colors cursor-pointer';
      const ic = document.createElement('i'); ic.setAttribute('data-lucide', 'pencil'); ic.className = 'h-3 w-3';
      editBtn.appendChild(ic);
      editBtn.appendChild(document.createTextNode('Editar'));
      editBtn.addEventListener('click', () => openPlanModal(p));
      tdAct.appendChild(editBtn);

      tr.appendChild(tdName);
      tr.appendChild(tdPrice);
      tr.appendChild(tdMods);
      tr.appendChild(tdDesc);
      tr.appendChild(tdTipo);
      tr.appendChild(tdVis);
      tr.appendChild(tdSubs);
      tr.appendChild(tdPromo);
      tr.appendChild(tdStatus);
      tr.appendChild(tdClip);
      tr.appendChild(tdAct);
      tbody.appendChild(tr);
    });

    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  function buildStatusToggle(plan) {
    const wrap = document.createElement('button');
    wrap.className = `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${plan.activo ? 'bg-cs-primary-container text-cs-on-primary-container' : 'bg-cs-surface-container text-cs-on-surface-var'}`;
    const dot = document.createElement('span');
    dot.className = `w-2 h-2 rounded-full ${plan.activo ? 'bg-cs-primary' : 'bg-cs-outline'}`;
    wrap.appendChild(dot);
    wrap.appendChild(document.createTextNode(plan.activo ? 'Activo' : 'Inactivo'));
    wrap.addEventListener('click', async () => {
      try {
        await adminApi.put(`/plans/${plan.id}`, {
          nombre: plan.nombre,
          precio_mensual: plan.precio_mensual,
          descripcion: plan.descripcion,
          activo: !plan.activo,
          modulos: plan.modulos || [],
          publico: plan.publico,
          es_temporal: plan.es_temporal,
          dias_expiracion: plan.dias_expiracion,
          cupo_maximo: plan.cupo_maximo,
          fecha_inicio_promo: plan.fecha_inicio_promo,
          fecha_fin_promo: plan.fecha_fin_promo,
          codigo_invitacion: plan.codigo_invitacion,
        });
        Toast.show(plan.activo ? 'Plan desactivado' : 'Plan activado', 'success');
        await loadAll();
      } catch (err) { Toast.show(err.message, 'error'); }
    });
    return wrap;
  }

  function buildPromoBadge(plan) {
    const wrap = document.createElement('div');
    wrap.className = 'inline-flex flex-col items-center gap-0.5';

    if (!plan.es_promocional) {
      const dash = document.createElement('span');
      dash.className = 'text-cs-on-surface-var text-xs';
      dash.textContent = '—';
      wrap.appendChild(dash);
      return wrap;
    }

    if (plan.cupo_maximo != null) {
      const isFull = plan.cupo_disponible <= 0;
      const cupoSpan = document.createElement('span');
      cupoSpan.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold ' +
        (isFull ? 'bg-red-500/15 text-red-700' : 'bg-purple-500/15 text-purple-700');
      cupoSpan.textContent = `${plan.cupo_usados}/${plan.cupo_maximo}` + (isFull ? ' agotado' : '');
      wrap.appendChild(cupoSpan);
    }

    if (plan.fecha_fin_promo) {
      const fechaSpan = document.createElement('span');
      fechaSpan.className = 'text-[10px] text-cs-on-surface-var';
      fechaSpan.textContent = 'Hasta ' + plan.fecha_fin_promo;
      wrap.appendChild(fechaSpan);
    }

    if (plan.codigo_invitacion) {
      const codeSpan = document.createElement('span');
      codeSpan.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold bg-cyan-500/15 text-cyan-700';
      codeSpan.textContent = 'cód: ' + plan.codigo_invitacion;
      wrap.appendChild(codeSpan);
    }

    return wrap;
  }

  function buildClipBadge(plan) {
    const wrap = document.createElement('div');
    wrap.className = 'inline-flex flex-col items-center gap-1';

    if (plan.es_temporal || plan.precio_mensual <= 0) {
      const span = document.createElement('span');
      span.className = 'inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold bg-cs-surface-container text-cs-on-surface-var';
      span.textContent = 'No aplica';
      wrap.appendChild(span);
      return wrap;
    }

    if (plan.clip_synced) {
      const row = document.createElement('div');
      row.className = 'flex items-center gap-1';
      const dot = document.createElement('span');
      dot.className = 'w-1.5 h-1.5 rounded-full bg-green-500';
      const txt = document.createElement('span');
      txt.className = 'text-[10px] font-semibold text-green-700';
      txt.textContent = 'Sincronizado';
      row.appendChild(dot);
      row.appendChild(txt);
      wrap.appendChild(row);

      if (plan.clip_subscription_link) {
        const a = document.createElement('a');
        a.href = plan.clip_subscription_link;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.className = 'text-[10px] text-cs-primary hover:underline cursor-pointer';
        a.textContent = 'Ver link';
        wrap.appendChild(a);
      }
    } else {
      const btn = document.createElement('button');
      btn.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/15 text-amber-700 hover:bg-amber-500/25 cursor-pointer';
      const ic = document.createElement('i');
      ic.setAttribute('data-lucide', 'alert-circle');
      ic.className = 'h-3 w-3';
      btn.appendChild(ic);
      btn.appendChild(document.createTextNode('Sin sincronizar'));
      btn.addEventListener('click', () => syncSinglePlan(plan));
      wrap.appendChild(btn);
    }
    return wrap;
  }

  async function syncSinglePlan(plan) {
    try {
      await adminApi.post(`/plans/${plan.id}/sync-clip`, {});
      Toast.show(`"${plan.nombre}" sincronizado con Clip`, 'success');
      await loadAll();
    } catch (err) {
      Toast.show(err.message || 'Error al sincronizar', 'error');
    }
  }

  function setSyncBtnContent(btn, iconName, label, spin) {
    while (btn.firstChild) btn.removeChild(btn.firstChild);
    const ic = document.createElement('i');
    ic.setAttribute('data-lucide', iconName);
    ic.className = 'h-4 w-4' + (spin ? ' animate-spin' : '');
    btn.appendChild(ic);
    btn.appendChild(document.createTextNode(' ' + label));
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  async function syncAllPlans() {
    const btn = document.getElementById('btn-sync-clip');
    btn.disabled = true;
    setSyncBtnContent(btn, 'loader-2', 'Sincronizando...', true);
    try {
      const r = await adminApi.post('/plans/sync-clip', {});
      const s = (r.synced || []).length;
      const sk = (r.skipped || []).length;
      const e = (r.errors || []).length;
      let msg = `Sincronizados: ${s}`;
      if (sk) msg += ` · Ya estaban: ${sk}`;
      if (e) msg += ` · Errores: ${e}`;
      Toast.show(msg, s > 0 ? 'success' : 'info');
      if (e) console.warn('Sync errors:', r.errors);
      await loadAll();
    } catch (err) {
      Toast.show(err.message || 'Error al sincronizar', 'error');
    } finally {
      btn.disabled = false;
      setSyncBtnContent(btn, 'refresh-cw', 'Sincronizar con Clip', false);
    }
  }

  function buildVisToggle(plan) {
    const wrap = document.createElement('button');
    wrap.className = `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${plan.publico ? 'bg-green-500/15 text-green-700' : 'bg-cs-surface-container text-cs-on-surface-var'}`;
    const dot = document.createElement('span');
    dot.className = `w-2 h-2 rounded-full ${plan.publico ? 'bg-green-500' : 'bg-cs-outline'}`;
    wrap.appendChild(dot);
    wrap.appendChild(document.createTextNode(plan.publico ? 'Público' : 'Oculto'));
    wrap.addEventListener('click', async () => {
      try {
        await adminApi.put(`/plans/${plan.id}`, {
          nombre: plan.nombre,
          precio_mensual: plan.precio_mensual,
          descripcion: plan.descripcion,
          activo: plan.activo,
          modulos: plan.modulos || [],
          publico: !plan.publico,
          es_temporal: plan.es_temporal,
          dias_expiracion: plan.dias_expiracion,
          cupo_maximo: plan.cupo_maximo,
          fecha_inicio_promo: plan.fecha_inicio_promo,
          fecha_fin_promo: plan.fecha_fin_promo,
          codigo_invitacion: plan.codigo_invitacion,
        });
        Toast.show(plan.publico ? 'Plan oculto' : 'Plan público', 'success');
        await loadAll();
      } catch (err) { Toast.show(err.message, 'error'); }
    });
    return wrap;
  }

  function openPlanModal(plan = null) {
    const isEdit = !!plan;
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const nameInput = inputEl('text', 'nombre', plan ? plan.nombre : '');
    nameInput.placeholder = 'Ej. Pro';
    const priceInput = inputEl('number', 'precio_mensual', plan ? plan.precio_mensual : '');
    priceInput.step = '0.01'; priceInput.min = '0';
    priceInput.placeholder = '999.00';
    const descInput = textareaEl('descripcion', plan ? plan.descripcion || '' : '', 3);
    descInput.placeholder = 'Qué incluye este plan…';

    wrap.appendChild(buildField('Nombre', nameInput));
    wrap.appendChild(buildField('Precio mensual (MXN)', priceInput));
    wrap.appendChild(buildField('Descripción', descInput));

    // Público checkbox
    const publicoLabel = document.createElement('label');
    publicoLabel.className = 'flex items-center gap-2.5 p-2.5 rounded-lg bg-cs-surface-container cursor-pointer hover:bg-cs-surface-container-high transition-colors';
    const publicoChk = document.createElement('input');
    publicoChk.type = 'checkbox';
    publicoChk.checked = plan ? plan.publico !== false : true;
    const publicoTxt = document.createElement('div');
    const publicoN = document.createElement('span');
    publicoN.className = 'text-sm font-semibold text-cs-on-surface block';
    publicoN.textContent = 'Plan público';
    const publicoD = document.createElement('span');
    publicoD.className = 'text-xs text-cs-on-surface-var block';
    publicoD.textContent = 'Visible en la página de registro para nuevos usuarios';
    publicoTxt.appendChild(publicoN);
    publicoTxt.appendChild(publicoD);
    publicoLabel.appendChild(publicoChk);
    publicoLabel.appendChild(publicoTxt);
    wrap.appendChild(buildField('Visibilidad', publicoLabel));

    // Temporal checkbox + días
    const temporalWrap = document.createElement('div');
    temporalWrap.className = 'space-y-3';
    const temporalLabel = document.createElement('label');
    temporalLabel.className = 'flex items-center gap-2.5 p-2.5 rounded-lg bg-cs-surface-container cursor-pointer hover:bg-cs-surface-container-high transition-colors';
    const temporalChk = document.createElement('input');
    temporalChk.type = 'checkbox';
    temporalChk.checked = plan ? !!plan.es_temporal : false;
    const temporalTxt = document.createElement('div');
    const temporalN = document.createElement('span');
    temporalN.className = 'text-sm font-semibold text-cs-on-surface block';
    temporalN.textContent = 'Plan temporal (prueba)';
    const temporalD = document.createElement('span');
    temporalD.className = 'text-xs text-cs-on-surface-var block';
    temporalD.textContent = 'Expira después de un número de días. Al vencer se pide cambio a plan pagado.';
    temporalTxt.appendChild(temporalN);
    temporalTxt.appendChild(temporalD);
    temporalLabel.appendChild(temporalChk);
    temporalLabel.appendChild(temporalTxt);
    temporalWrap.appendChild(temporalLabel);

    const diasRow = document.createElement('div');
    diasRow.className = temporalChk.checked ? '' : 'hidden';
    const diasInput = inputEl('number', 'dias_expiracion', plan && plan.dias_expiracion ? plan.dias_expiracion : '8');
    diasInput.min = '1';
    diasInput.placeholder = '8';
    diasRow.appendChild(buildField('Días de prueba', diasInput));
    temporalWrap.appendChild(diasRow);

    temporalChk.addEventListener('change', () => {
      diasRow.classList.toggle('hidden', !temporalChk.checked);
    });
    wrap.appendChild(buildField('Tipo de plan', temporalWrap));

    // Module checkboxes
    const currentMods = plan ? (plan.modulos || []) : [];
    const modsWrap = document.createElement('div');
    modsWrap.className = 'space-y-2';
    const checkboxes = [];
    MODULOS.forEach(m => {
      const label = document.createElement('label');
      label.className = 'flex items-start gap-2.5 p-2.5 rounded-lg bg-cs-surface-container cursor-pointer hover:bg-cs-surface-container-high transition-colors';
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.className = 'mt-0.5';
      chk.checked = currentMods.includes(m.slug);
      chk.dataset.slug = m.slug;
      const txt = document.createElement('div');
      const n = document.createElement('span');
      n.className = 'text-sm font-semibold text-cs-on-surface block';
      n.textContent = m.label;
      const d = document.createElement('span');
      d.className = 'text-xs text-cs-on-surface-var block';
      d.textContent = m.desc;
      txt.appendChild(n);
      txt.appendChild(d);
      label.appendChild(chk);
      label.appendChild(txt);
      modsWrap.appendChild(label);
      checkboxes.push(chk);
    });
    wrap.appendChild(buildField('Módulos incluidos', modsWrap));

    // Promotional limits
    const promoWrap = document.createElement('div');
    promoWrap.className = 'space-y-3';
    const promoLabel = document.createElement('label');
    promoLabel.className = 'flex items-center gap-2.5 p-2.5 rounded-lg bg-cs-surface-container cursor-pointer hover:bg-cs-surface-container-high transition-colors';
    const promoChk = document.createElement('input');
    promoChk.type = 'checkbox';
    promoChk.checked = !!(plan && (plan.cupo_maximo || plan.fecha_fin_promo || plan.codigo_invitacion));
    const promoTxt = document.createElement('div');
    const promoN = document.createElement('span');
    promoN.className = 'text-sm font-semibold text-cs-on-surface block';
    promoN.textContent = 'Plan promocional con límites';
    const promoD = document.createElement('span');
    promoD.className = 'text-xs text-cs-on-surface-var block';
    promoD.textContent = 'Define cupo máximo, vigencia o código de invitación. Desaparece de /register al llenarse o vencerse.';
    promoTxt.appendChild(promoN);
    promoTxt.appendChild(promoD);
    promoLabel.appendChild(promoChk);
    promoLabel.appendChild(promoTxt);
    promoWrap.appendChild(promoLabel);

    const promoFields = document.createElement('div');
    promoFields.className = (promoChk.checked ? '' : 'hidden ') + 'grid grid-cols-1 md:grid-cols-2 gap-3 pt-2';

    const cupoInput = inputEl('number', 'cupo_maximo', plan && plan.cupo_maximo ? plan.cupo_maximo : '');
    cupoInput.min = '1';
    cupoInput.placeholder = '100';
    promoFields.appendChild(buildField('Cupo máximo (opcional)', cupoInput));

    const fechaInicio = inputEl('date', 'fecha_inicio_promo', plan && plan.fecha_inicio_promo || '');
    promoFields.appendChild(buildField('Vigente desde (opcional)', fechaInicio));

    const fechaFin = inputEl('date', 'fecha_fin_promo', plan && plan.fecha_fin_promo || '');
    promoFields.appendChild(buildField('Vigente hasta (opcional)', fechaFin));

    const codigoInput = inputEl('text', 'codigo_invitacion', plan && plan.codigo_invitacion || '');
    codigoInput.placeholder = 'BLACKFRIDAY';
    codigoInput.maxLength = 50;
    promoFields.appendChild(buildField('Código de invitación (opcional)', codigoInput));

    promoWrap.appendChild(promoFields);
    promoChk.addEventListener('change', () => {
      promoFields.classList.toggle('hidden', !promoChk.checked);
    });
    wrap.appendChild(buildField('Configuración promocional', promoWrap));

    if (isEdit) {
      const activoLabel = document.createElement('label');
      activoLabel.className = 'inline-flex items-center gap-2 text-sm text-cs-on-surface';
      const activoChk = document.createElement('input');
      activoChk.type = 'checkbox';
      activoChk.checked = !!plan.activo;
      activoLabel.appendChild(activoChk);
      activoLabel.appendChild(document.createTextNode('Plan activo (visible para asignación)'));
      wrap.appendChild(activoLabel);
      wrap._activoChk = activoChk;
    }

    openModal({
      title: isEdit ? `Editar plan · ${plan.nombre}` : 'Nuevo plan',
      content: wrap,
      primary: { label: isEdit ? 'Guardar' : 'Crear plan', onClick: async () => {
        const nombre = nameInput.value.trim();
        const precio = parseFloat(priceInput.value);
        if (!nombre || nombre.length < 2) throw new Error('El nombre es obligatorio (mínimo 2 caracteres).');
        if (isNaN(precio) || precio < 0) throw new Error('Precio inválido.');
        const modulos = checkboxes.filter(c => c.checked).map(c => c.dataset.slug);
        const promoOn = promoChk.checked;
        const body = {
          nombre,
          precio_mensual: precio,
          descripcion: descInput.value.trim() || null,
          activo: isEdit ? wrap._activoChk.checked : true,
          modulos,
          publico: publicoChk.checked,
          es_temporal: temporalChk.checked,
          dias_expiracion: temporalChk.checked ? parseInt(diasInput.value, 10) || null : null,
          cupo_maximo: promoOn && cupoInput.value ? parseInt(cupoInput.value, 10) : null,
          fecha_inicio_promo: promoOn && fechaInicio.value ? fechaInicio.value : null,
          fecha_fin_promo: promoOn && fechaFin.value ? fechaFin.value : null,
          codigo_invitacion: promoOn && codigoInput.value.trim() ? codigoInput.value.trim() : null,
        };
        if (isEdit) {
          await adminApi.put(`/plans/${plan.id}`, body);
          Toast.show('Plan actualizado', 'success');
        } else {
          await adminApi.post('/plans', body);
          Toast.show('Plan creado', 'success');
        }
        await loadAll();
      } },
    });
  }

  async function init() {
    document.getElementById('btn-nuevo-plan').addEventListener('click', () => openPlanModal());
    document.getElementById('btn-sync-clip').addEventListener('click', syncAllPlans);
    try {
      await loadAll();
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al cargar planes', 'error');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
