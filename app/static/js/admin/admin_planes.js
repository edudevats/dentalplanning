// Panel super-admin / Planes
(function () {
  const { currency, openModal, buildField, inputEl, textareaEl } = window.adminUI;

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

      // Descripción
      const tdDesc = document.createElement('td');
      tdDesc.className = 'px-4 py-3.5 text-cs-on-surface-var';
      tdDesc.textContent = p.descripcion || '—';

      // Suscripciones
      const tdSubs = document.createElement('td');
      tdSubs.className = 'px-4 py-3.5 text-center text-cs-on-surface';
      tdSubs.textContent = subsCountByPlan[p.id] || 0;

      // Estado (toggle)
      const tdStatus = document.createElement('td');
      tdStatus.className = 'px-4 py-3.5 text-center';
      tdStatus.appendChild(buildStatusToggle(p));

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
      tr.appendChild(tdDesc);
      tr.appendChild(tdSubs);
      tr.appendChild(tdStatus);
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
        });
        Toast.show(plan.activo ? 'Plan desactivado' : 'Plan activado', 'success');
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

    if (isEdit) {
      const activoLabel = document.createElement('label');
      activoLabel.className = 'inline-flex items-center gap-2 text-sm text-cs-on-surface';
      const activoChk = document.createElement('input');
      activoChk.type = 'checkbox';
      activoChk.checked = !!plan.activo;
      activoLabel.appendChild(activoChk);
      activoLabel.appendChild(document.createTextNode('Plan activo (visible para asignación)'));
      wrap.appendChild(activoLabel);
      wrap.dataset.activoChkId = 'inline';
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
        const body = {
          nombre,
          precio_mensual: precio,
          descripcion: descInput.value.trim() || null,
          activo: isEdit ? wrap._activoChk.checked : true,
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
