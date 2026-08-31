// Panel super-admin / Planes → pestaña "Usuarios adicionales".
//
// Vive aparte de admin_planes.js a propósito: un asiento no se edita como un
// plan de clínica (no lleva módulos, visibilidad ni promociones), y mezclar las
// dos tablas en un archivo fue justo lo que hizo confusa la pantalla anterior.
(function () {
  const { currency, openModal, buildField, inputEl, textareaEl, kpiCard } = window.adminUI;

  let tipos = [];

  // ── Carga y render ────────────────────────────────────────────────────────
  async function loadTipos() {
    const data = await adminApi.get('/tipos-usuario');
    tipos = data.tipos || [];
    render();
  }

  function render() {
    renderKpis();
    renderRows();
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  function renderKpis() {
    const wrap = document.getElementById('tipos-kpis');
    invDom.clearChildren(wrap);
    const activos = tipos.reduce((a, t) => a + (t.asientos_activos || 0), 0);
    const pendientes = tipos.reduce((a, t) => a + (t.asientos_pendientes || 0), 0);
    const ingreso = tipos.reduce((a, t) => a + (t.ingreso_mensual || 0), 0);
    wrap.appendChild(kpiCard({
      label: 'Asientos activos', value: activos, icon: 'user-check',
      hint: 'Usuarios extra pagados en todas las clínicas',
    }));
    wrap.appendChild(kpiCard({
      label: 'Solicitudes pendientes', value: pendientes, icon: 'clock',
      hint: pendientes ? 'Se aprueban en Solicitudes' : 'Nada por aprobar',
      href: pendientes ? '/admin/solicitudes' : null,
    }));
    wrap.appendChild(kpiCard({
      label: 'Ingreso mensual', value: currency(ingreso), icon: 'banknote',
      hint: 'Suma de los asientos activos a su precio actual',
    }));
  }

  function renderRows() {
    const tbody = document.getElementById('tipos-rows');
    invDom.clearChildren(tbody);
    tipos.forEach(t => tbody.appendChild(buildRow(t)));
  }

  function buildRow(t) {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-cs-surface-container transition-colors duration-200';

    // Tipo de usuario
    const tdName = document.createElement('td');
    tdName.className = 'px-3 py-3.5 whitespace-nowrap';
    const name = document.createElement('div');
    name.className = 'font-semibold text-cs-on-surface';
    name.textContent = t.etiqueta;
    tdName.appendChild(name);
    if (t.nombre) {
      const sub = document.createElement('div');
      sub.className = 'text-xs text-cs-on-surface-var';
      sub.textContent = t.nombre;
      tdName.appendChild(sub);
    }

    // Precio
    const tdPrice = document.createElement('td');
    tdPrice.className = 'px-3 py-3.5 text-right font-cs-display font-semibold text-cs-on-surface whitespace-nowrap';
    tdPrice.textContent = t.precio_mensual == null ? '—' : currency(t.precio_mensual);

    // Qué puede hacer
    const tdScope = document.createElement('td');
    tdScope.className = 'px-3 py-3.5 text-xs text-cs-on-surface-var leading-relaxed min-w-[22rem]';
    tdScope.textContent = t.descripcion_rol;

    // Activos / Pendientes
    const tdActivos = document.createElement('td');
    tdActivos.className = 'px-3 py-3.5 text-center font-semibold text-cs-on-surface';
    tdActivos.textContent = t.asientos_activos;

    const tdPend = document.createElement('td');
    tdPend.className = 'px-3 py-3.5 text-center whitespace-nowrap';
    tdPend.appendChild(pendientesCell(t.asientos_pendientes));

    // Ingreso mensual
    const tdMrr = document.createElement('td');
    tdMrr.className = 'px-3 py-3.5 text-right font-cs-display text-cs-on-surface whitespace-nowrap';
    tdMrr.textContent = currency(t.ingreso_mensual);

    // Estado
    const tdEstado = document.createElement('td');
    tdEstado.className = 'px-3 py-3.5 text-center whitespace-nowrap';
    tdEstado.appendChild(estadoCell(t));

    // Clip
    const tdClip = document.createElement('td');
    tdClip.className = 'px-3 py-3.5 text-center whitespace-nowrap';
    tdClip.appendChild(clipCell(t));

    // Acciones
    const tdActions = document.createElement('td');
    tdActions.className = 'px-3 py-3.5 text-right';
    tdActions.appendChild(editButton(t));

    [tdName, tdPrice, tdScope, tdActivos, tdPend, tdMrr, tdEstado, tdClip, tdActions]
      .forEach(td => tr.appendChild(td));
    return tr;
  }

  function pill(text, classes) {
    const span = document.createElement('span');
    span.className = `inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold tracking-wide ${classes}`;
    span.textContent = text;
    return span;
  }

  function pendientesCell(n) {
    if (!n) {
      const dash = document.createElement('span');
      dash.className = 'text-cs-on-surface-var';
      dash.textContent = '—';
      return dash;
    }
    const a = document.createElement('a');
    a.href = '/admin/solicitudes';
    a.className = 'inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-amber-500/15 text-amber-700 hover:bg-amber-500/25';
    a.textContent = `${n} por aprobar`;
    return a;
  }

  function estadoCell(t) {
    if (!t.plan_id) return pill('Sin configurar', 'bg-cs-error-container/40 text-cs-on-error-container');
    return t.activo
      ? pill('Activo', 'bg-cs-primary-container text-cs-on-primary-container')
      : pill('Inactivo', 'bg-cs-surface-container text-cs-on-surface-var');
  }

  function clipCell(t) {
    if (!t.plan_id) {
      const dash = document.createElement('span');
      dash.className = 'text-cs-on-surface-var text-xs';
      dash.textContent = '—';
      return dash;
    }
    if (t.clip_synced) {
      return pill('Sincronizado', 'bg-cs-primary-container text-cs-on-primary-container');
    }
    const btn = document.createElement('button');
    btn.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/15 text-amber-700 hover:bg-amber-500/25 cursor-pointer';
    const ic = document.createElement('i');
    ic.setAttribute('data-lucide', 'alert-circle');
    ic.className = 'h-3 w-3';
    btn.appendChild(ic);
    btn.appendChild(document.createTextNode('Sin sincronizar'));
    btn.addEventListener('click', () => syncTipo(t));
    return btn;
  }

  function editButton(t) {
    const btn = document.createElement('button');
    btn.className = 'px-3 py-1.5 rounded-lg bg-cs-surface-container text-cs-on-surface text-xs font-semibold hover:bg-cs-surface-container-high transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed';
    btn.textContent = 'Editar';
    if (!t.plan_id) {
      btn.disabled = true;
      btn.title = 'Este tipo aún no tiene plan de cobro. Córrelo con `flask billing seed-addon`.';
    } else {
      btn.addEventListener('click', () => openTipoModal(t));
    }
    return btn;
  }

  // ── Acciones ──────────────────────────────────────────────────────────────
  async function syncTipo(t) {
    try {
      await adminApi.post(`/plans/${t.plan_id}/sync-clip`, {});
      Toast.show(`"${t.etiqueta}" sincronizado con Clip`, 'success');
      await loadTipos();
    } catch (err) {
      Toast.show(err.message || 'Error al sincronizar', 'error');
    }
  }

  function openTipoModal(t) {
    const wrap = document.createElement('div');
    wrap.className = 'space-y-4';

    const nameInput = inputEl('text', 'nombre', t.nombre || '');
    wrap.appendChild(buildField('Nombre en el cobro', nameInput));

    const priceInput = inputEl('number', 'precio_mensual', t.precio_mensual ?? 0);
    priceInput.step = '0.01';
    priceInput.min = '0';
    wrap.appendChild(buildField('Precio mensual por asiento (MXN)', priceInput));

    const descInput = textareaEl('descripcion', t.descripcion || '', 2);
    wrap.appendChild(buildField('Descripción', descInput));

    const activoLabel = document.createElement('label');
    activoLabel.className = 'inline-flex items-center gap-2 text-sm text-cs-on-surface';
    const activoChk = document.createElement('input');
    activoChk.type = 'checkbox';
    activoChk.checked = !!t.activo;
    activoLabel.appendChild(activoChk);
    activoLabel.appendChild(document.createTextNode('Se puede vender (las clínicas pueden pedir este asiento)'));
    wrap.appendChild(activoLabel);

    if (t.asientos_activos > 0) {
      const aviso = document.createElement('p');
      aviso.className = 'text-xs text-cs-on-surface-var';
      aviso.textContent = `Cambiar el precio no toca los ${t.asientos_activos} asiento(s) ya cobrados: aplica de la siguiente aprobación en adelante.`;
      wrap.appendChild(aviso);
    }

    openModal({
      title: `Editar · ${t.etiqueta}`,
      content: wrap,
      primary: { label: 'Guardar', onClick: async () => {
        const nombre = nameInput.value.trim();
        const precio = parseFloat(priceInput.value);
        if (nombre.length < 4) throw new Error('El nombre debe tener al menos 4 caracteres (requerido por Clip).');
        if (isNaN(precio) || precio < 0) throw new Error('Precio inválido.');
        await adminApi.put(`/plans/${t.plan_id}`, {
          nombre,
          precio_mensual: precio,
          descripcion: descInput.value.trim() || null,
          activo: activoChk.checked,
        });
        Toast.show('Tipo de usuario actualizado', 'success');
        await loadTipos();
      } },
    });
  }

  // ── Pestañas ──────────────────────────────────────────────────────────────
  // La pestaña de usuarios carga bajo demanda: entrar a /admin/planes no debe
  // pagar el conteo de asientos si el super-admin sólo viene a ver los planes.
  let cargada = false;

  function activateTab(name) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== name));
    if (name === 'usuarios' && !cargada) {
      cargada = true;
      loadTipos().catch(err => {
        cargada = false;
        console.error(err);
        Toast.show(err.message || 'Error al cargar los tipos de usuario', 'error');
      });
    }
  }

  function init() {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.addEventListener('click', () => activateTab(b.dataset.tab));
    });
    if (location.hash === '#usuarios') activateTab('usuarios');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
