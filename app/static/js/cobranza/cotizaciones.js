/* Pantalla de cotizaciones y cobranza. Requiere app.js y cotizacion_form.js. */
const Cobranza = (() => {
  const state = {
    rows: [],
    current: null,
    user: null,
    methods: [],
    branches: [],
    paymentKey: null,
  };
  const $ = id => document.getElementById(id);
  const writableRoles = ['admin', 'editor', 'recepcionista'];

  // Pide la contraseña del admin para una operación sensible.
  // Devuelve la contraseña, o null si el usuario cancela (botón, X o backdrop).
  const AdminGate = {
    ask(mensaje) {
      return new Promise((resolve) => {
        const input = $('admin-gate-input');
        const msg = $('admin-gate-msg');
        const form = $('admin-gate-form');
        input.value = '';
        msg.textContent = mensaje || 'Escribe tu contraseña de administrador para continuar.';
        const onSubmit = (e) => {
          e.preventDefault();
          cleanup();
          Modal.close('modal-admin-gate');
          resolve(input.value);
        };
        const onCancel = () => { cleanup(); Modal.close('modal-admin-gate'); resolve(null); };
        function cleanup() {
          form.removeEventListener('submit', onSubmit);
          $('admin-gate-cancel').removeEventListener('click', onCancel);
          $('admin-gate-x').removeEventListener('click', onCancel);
          $('admin-gate-backdrop').removeEventListener('click', onCancel);
        }
        form.addEventListener('submit', onSubmit);
        $('admin-gate-cancel').addEventListener('click', onCancel);
        $('admin-gate-x').addEventListener('click', onCancel);
        $('admin-gate-backdrop').addEventListener('click', onCancel);
        Modal.open('modal-admin-gate');
        setTimeout(() => input.focus(), 50);
      });
    },
  };

  function localISO() {
    const date = new Date();
    return [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0'),
    ].join('-');
  }

  function role() {
    return state.user && state.user.role;
  }

  function statusMeta(status) {
    const values = {
      borrador: ['Borrador', 'bg-slate-100 text-slate-700'],
      enviada: ['Enviada', 'bg-sky-100 text-sky-700'],
      vencida: ['Vencida', 'bg-amber-100 text-amber-800'],
      aprobada: ['En cobranza', 'bg-violet-100 text-violet-700'],
      liquidada: ['Liquidada', 'bg-emerald-100 text-emerald-700'],
      rechazada: ['Rechazada', 'bg-red-100 text-red-700'],
      cancelada: ['Cancelada', 'bg-slate-200 text-slate-600'],
    };
    return values[status] || [status, 'bg-slate-100 text-slate-700'];
  }

  function badge(status) {
    const [label, classes] = statusMeta(status);
    return `<span class="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${classes}">${label}</span>`;
  }

  // Etiquetas legibles para app.cobranza.models.FACTURACION_ESTADOS. El
  // estado sólo avanza de "no_requerida"/"pendiente" al liquidar el plan,
  // así que mientras siga abierto no tiene caso mostrar el identificador
  // crudo junto a "Factura: Sí".
  const FACTURACION_LABELS = {
    no_requerida: 'No requerida',
    pendiente: 'Pendiente',
    ticket_creado: 'Ticket creado',
    completada: 'Completada',
    error_ticket: 'Error al generar el ticket',
    error_correo: 'Error al enviar el correo',
    sin_ingresos: 'Sin ingresos registrados',
    parcial_historicos: 'Cobro parcial (el resto son pagos históricos)',
  };

  // Un plan cancelado tambien puede facturarse: los abonos que el paciente ya
  // pago son dinero real. Solo un plan todavia abierto esta "pendiente de
  // liquidar"; en los demas mostramos el estado real de facturacion.
  function facturacionTexto(quote, baseStatus) {
    if (!quote.requiere_factura) return null;
    if (!['liquidada', 'cancelada'].includes(baseStatus)) return 'Pendiente de liquidar';
    const estado = quote.facturacion_estado || 'pendiente';
    return FACTURACION_LABELS[estado] || estado;
  }

  function refreshPatients(patients) {
    const select = $('filtro-paciente');
    const selected = select.value;
    select.innerHTML = '<option value="">Todos los pacientes</option>' +
      patients.map(patient =>
        `<option value="${patient.id}">${esc(patient.nombre)}</option>`
      ).join('');
    select.value = selected;
  }

  function query() {
    const params = new URLSearchParams();
    const fields = {
      'filtro-estatus': 'estatus',
      'filtro-paciente': 'paciente_id',
      'filtro-desde': 'fecha_desde',
      'filtro-hasta': 'fecha_hasta',
    };
    Object.entries(fields).forEach(([id, name]) => {
      if ($(id).value) params.set(name, $(id).value);
    });
    return params.toString();
  }

  async function reload() {
    try {
      const [rows, summary] = await Promise.all([
        API.get('/cobranza/cotizaciones?' + query()),
        API.get('/cobranza/resumen'),
      ]);
      state.rows = rows || [];
      renderList();
      $('stat-por-cobrar').textContent = fmt(summary.por_cobrar || 0);
      $('stat-sin-pagos').textContent = String(summary.sin_pagos_recientes || 0);
      $('stat-cobrado').textContent = fmt(summary.cobrado_mes || 0);
      $('stat-activos').textContent = String(summary.planes_activos || 0);
    } catch (error) {
      Toast.error(error.message || 'No se pudieron cargar las cotizaciones');
    }
  }

  function renderList() {
    const search = (($('cs-global-search') || {}).value || '').trim().toLowerCase();
    const rows = state.rows.filter(row => !search
      || row.folio.toLowerCase().includes(search)
      || (row.paciente_nombre || '').toLowerCase().includes(search));
    $('cotizaciones-empty').classList.toggle('hidden', rows.length > 0);
    $('cotizaciones-body').innerHTML = rows.map(row => `
      <tr data-id="${row.id}" class="border-t border-border hover:bg-surface-hover cursor-pointer">
        <td class="px-4 py-3">
          <p class="font-semibold text-text-primary">${esc(row.folio)}</p>
          <p class="text-xs text-text-muted">${esc(row.paciente_nombre || '')}</p>
        </td>
        <td class="px-4 py-3 text-right tabular-nums">${fmt(row.total)}</td>
        <td class="px-4 py-3 text-right tabular-nums text-emerald-700">${fmt(row.pagado)}</td>
        <td class="px-4 py-3 text-right tabular-nums font-semibold">${fmt(row.saldo)}</td>
        <td class="px-4 py-3 text-center">
          <span class="text-xs">${row.parcialidades_pagadas} de ${row.num_parcialidades}</span>
          ${row.sin_pagos_recientes ? '<p class="text-[11px] text-amber-700">+45 días sin pago</p>' : ''}
        </td>
        <td class="px-4 py-3 text-center">${badge(row.estatus)}</td>
      </tr>`).join('');
    $('cotizaciones-body').querySelectorAll('tr').forEach(row => {
      row.addEventListener('click', () => openDetail(Number(row.dataset.id)));
    });
  }

  function scheduleTable(quote) {
    if (!quote.programados || !quote.programados.length) {
      return '<p class="text-sm text-text-muted">El calendario se generará al aprobar.</p>';
    }
    return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="text-xs text-text-muted"><tr>
        <th class="py-2 text-left">Pago</th><th class="py-2 text-left">Fecha</th>
        <th class="py-2 text-right">Programado</th><th class="py-2 text-right">Cubierto</th>
        <th class="py-2 text-right"></th></tr></thead>
      <tbody>${quote.programados.map(item => {
        const pending = Math.max(item.monto_programado - item.monto_pagado, 0);
        return `<tr class="border-t border-border">
          <td class="py-2">${item.numero === 0 ? 'Anticipo' : `Pago ${item.numero}`}</td>
          <td class="py-2">${formatDate(item.fecha_vencimiento)}</td>
          <td class="py-2 text-right tabular-nums">${fmt(item.monto_programado)}</td>
          <td class="py-2 text-right tabular-nums">${fmt(item.monto_pagado)}</td>
          <td class="py-2 text-right">${quote.estatus === 'aprobada' && pending > 0
            ? `<button type="button" data-pay="${pending}" class="schedule-pay text-xs font-semibold text-primary-600 cursor-pointer">Abonar</button>`
            : `<span class="text-xs text-text-muted">${esc(item.estatus)}</span>`}</td>
        </tr>`;
      }).join('')}</tbody></table></div>`;
  }

  function paymentsTable(quote) {
    if (!quote.pagos || !quote.pagos.length) {
      return '<p class="text-sm text-text-muted">Aún no hay abonos registrados.</p>';
    }
    return `<div class="overflow-x-auto"><table class="w-full text-sm">
      <thead class="text-xs text-text-muted"><tr>
        <th class="py-2 text-left">Fecha</th><th class="py-2 text-left">Método</th>
        <th class="py-2 text-right">Monto</th><th class="py-2 text-center">Origen</th>
      </tr></thead>
      <tbody>${quote.pagos.map(payment => `<tr class="border-t border-border">
        <td class="py-2">${formatDate(payment.fecha)}</td>
        <td class="py-2">${esc(payment.metodo_pago_nombre || 'Sin método')}</td>
        <td class="py-2 text-right tabular-nums">${fmt(payment.monto)}</td>
        <td class="py-2 text-center text-xs">${payment.historico ? 'Histórico' : 'Ingreso #' + payment.ingreso_id}</td>
      </tr>`).join('')}</tbody></table></div>`;
  }

  function renderDetail(quote) {
    const baseStatus = quote.estatus_base || quote.estatus;
    const facturacionInfo = facturacionTexto(quote, baseStatus);
    $('detalle-folio').textContent = quote.folio;
    $('detalle-paciente').textContent = quote.paciente_nombre || '';
    $('detalle-contenido').innerHTML = `
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div><p class="text-xs text-text-muted">Estado</p><div class="mt-1">${badge(quote.estatus)}</div></div>
        <div><p class="text-xs text-text-muted">Total</p><p class="text-lg font-bold tabular-nums">${fmt(quote.total)}</p></div>
        <div><p class="text-xs text-text-muted">Pagado</p><p class="text-lg font-bold text-emerald-700 tabular-nums">${fmt(quote.pagado)}</p></div>
        <div><p class="text-xs text-text-muted">Saldo</p><p class="text-lg font-bold tabular-nums">${fmt(quote.saldo)}</p></div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section><h3 class="font-semibold mb-2">Conceptos</h3>
          <div class="space-y-2">${(quote.conceptos || []).map(item => `
            <div class="flex justify-between gap-4 rounded-lg bg-surface-alt px-3 py-2 text-sm">
              <span>${esc(item.descripcion)} × ${item.cantidad}</span><strong>${fmt(item.importe)}</strong>
            </div>`).join('')}</div>
          ${quote.descuento_tipo ? `<p class="text-xs text-text-muted mt-2">Descuento: ${esc(quote.descuento_tipo)} ${quote.descuento_valor}</p>` : ''}
        </section>
        <section><h3 class="font-semibold mb-2">Datos del plan</h3>
          <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt class="text-text-muted">Doctor</dt><dd>${esc(quote.especialista_nombre || 'Sin asignar')}</dd>
            <dt class="text-text-muted">Frecuencia</dt><dd>${esc(quote.frecuencia)}</dd>
            <dt class="text-text-muted">Anticipo</dt><dd>${fmt(quote.anticipo)}</dd>
            <dt class="text-text-muted">Vigencia</dt><dd>${formatDate(quote.valida_hasta)}</dd>
            <dt class="text-text-muted">Factura</dt><dd>${quote.requiere_factura ? 'Sí' : 'No'}</dd>
            ${facturacionInfo ? `<dt class="text-text-muted">Facturación</dt><dd>${esc(facturacionInfo)}</dd>` : ''}
          </dl>
          ${(baseStatus === 'borrador' || baseStatus === 'enviada') && role() === 'admin'
            ? `<label class="block text-sm mt-3">Sucursal al aprobar
                <select id="detalle-sucursal" class="mt-1 w-full rounded-lg border border-border px-3 py-2">
                  <option value="">Primera sucursal activa</option>
                  ${state.branches.map(branch => `<option value="${branch.id}" ${String(branch.id) === String(quote.sucursal_id || '') ? 'selected' : ''}>${esc(branch.nombre)}</option>`).join('')}
                </select></label>` : ''}
        </section>
      </div>
      <section class="mt-6"><h3 class="font-semibold mb-2">Calendario</h3>${scheduleTable(quote)}</section>
      <section class="mt-6"><h3 class="font-semibold mb-2">Historial de abonos</h3>${paymentsTable(quote)}</section>
      ${quote.devoluciones && quote.devoluciones.length ? `
      <section class="mt-6"><h3 class="font-semibold mb-2">Devoluciones</h3>
        <div class="space-y-2">${quote.devoluciones.map(d => `
          <div class="rounded-lg bg-surface-alt px-3 py-2 text-sm">
            <div class="flex justify-between gap-4">
              <span>${formatDate(d.fecha)} · ${esc(d.metodo_pago_nombre || 'Sin método')}</span>
              <strong>${fmt(d.monto)}</strong>
            </div>
            ${d.motivo ? `<p class="text-xs text-text-muted mt-1">${esc(d.motivo)}</p>` : ''}
          </div>`).join('')}</div>
        <p class="text-sm font-semibold mt-2">Total devuelto: ${fmt(quote.devuelto)}</p>
      </section>` : ''}
      ${quote.notas ? `<section class="mt-6"><h3 class="font-semibold mb-1">Notas</h3><p class="text-sm whitespace-pre-wrap">${esc(quote.notas)}</p></section>` : ''}`;

    const alert = $('detalle-alerta');
    const invoiceError = ['error_ticket', 'error_correo', 'sin_ingresos'].includes(quote.facturacion_estado);
    alert.className = 'hidden mx-6 mt-5 rounded-lg px-4 py-3 text-sm';
    if (quote.vencida) {
      alert.textContent = 'La vigencia ya terminó. El administrador todavía puede aprobarla si desea reactivarla.';
      alert.classList.remove('hidden');
      alert.classList.add('bg-amber-50', 'text-amber-800');
    } else if (invoiceError) {
      alert.textContent = `El cobro quedó guardado, pero la facturación necesita atención: ${quote.facturacion_error || quote.facturacion_estado}`;
      alert.classList.remove('hidden');
      alert.classList.add('bg-red-50', 'text-red-700');
    }

    $('detalle-contenido').querySelectorAll('.schedule-pay').forEach(button => {
      button.addEventListener('click', () => openPayment(Number(button.dataset.pay)));
    });
    renderActions(quote, baseStatus, invoiceError);
    if (window.lucide) lucide.createIcons();
  }

  function action(label, classes, handler, icon) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold cursor-pointer ${classes}`;
    if (icon) button.appendChild(domIcon(icon, 'h-4 w-4'));
    button.appendChild(document.createTextNode(label));
    button.addEventListener('click', handler);
    $('detalle-acciones').appendChild(button);
  }

  function renderActions(quote, baseStatus, invoiceError) {
    $('detalle-acciones').replaceChildren();
    action('Cotización PDF', 'border border-border hover:bg-surface-hover', () => download('pdf'), 'file-down');
    if (['aprobada', 'liquidada', 'cancelada'].includes(baseStatus)) {
      action('Copiar estado', 'border border-border hover:bg-surface-hover', copyStatement, 'copy');
      action('Estado de cuenta PDF', 'border border-border hover:bg-surface-hover', () => download('estado-cuenta.pdf'), 'file-text');
      if (writableRoles.includes(role())) {
        action('Enviar estado por correo', 'border border-primary-200 text-primary-700 hover:bg-primary-50', sendStatement, 'mail');
      }
    }
    if (['borrador', 'enviada'].includes(baseStatus) && writableRoles.includes(role())) {
      action('Editar', 'border border-border hover:bg-surface-hover', () => CobranzaForm.open(quote), 'pencil');
      action('Enviar', 'border border-primary-200 text-primary-700 hover:bg-primary-50', sendQuote, 'mail');
    }
    if (['borrador', 'enviada'].includes(baseStatus) && role() === 'admin') {
      action('Rechazar', 'border border-danger-100 text-danger-700', () => transition('rechazar'), 'x-circle');
      action('Aprobar', 'bg-primary-500 text-white hover:bg-primary-600', approve, 'check-circle');
    }
    if (baseStatus === 'aprobada' && writableRoles.includes(role())) {
      action('Registrar abono', 'bg-primary-500 text-white hover:bg-primary-600', () => openPayment(), 'circle-dollar-sign');
    }
    if (baseStatus === 'cancelada' && role() === 'admin') {
      action('Registrar devolución', 'border border-danger-100 text-danger-700', openRefund, 'undo-2');
    }
    if (baseStatus === 'aprobada' && role() === 'admin') {
      action('Cancelar plan', 'border border-danger-100 text-danger-700', () => transition('cancelar'), 'ban');
      action('Editar mensualidades', 'border border-border hover:bg-surface-hover', openEditCalendar, 'calendar-cog');
      action('Agregar concepto', 'border border-border hover:bg-surface-hover', openAddConcept, 'plus-circle');
    }
    // La facturacion se ofrece en planes liquidados y tambien en cancelados:
    // en un plan cancelado los abonos cobrados son dinero real y el paciente
    // tiene derecho a su factura. Si aun no hay ticket es la primera emision;
    // si el intento anterior fallo, es un reintento.
    const facturable = ['liquidada', 'cancelada'].includes(baseStatus)
      && quote.requiere_factura
      && quote.facturacion_estado !== 'completada';
    if (facturable && role() === 'admin') {
      const label = invoiceError ? 'Reintentar facturación' : 'Facturar abonos cobrados';
      action(label, 'bg-amber-500 text-white hover:bg-amber-600', retryInvoice, 'refresh-cw');
    }
    // Eliminar disponible en cualquier estatus (antes sólo borrador).
    if (role() === 'admin') {
      action('Eliminar', 'border border-danger-100 text-danger-700', removeQuote, 'trash-2');
    }
  }

  async function openDetail(id) {
    try {
      state.current = await API.get(`/cobranza/cotizaciones/${id}`);
      renderDetail(state.current);
      Modal.open('modal-cotizacion-detalle');
    } catch (error) {
      Toast.error(error.message || 'No se pudo abrir la cotización');
    }
  }

  async function refreshDetail() {
    if (state.current) await openDetail(state.current.id);
  }

  async function transition(name) {
    if (!window.confirm(`¿Confirmas ${name} esta cotización?`)) return;
    try {
      await API.post(`/cobranza/cotizaciones/${state.current.id}/${name}`, {});
      Toast.success('Cotización actualizada');
      await reload();
      await refreshDetail();
    } catch (error) { Toast.error(error.message); }
  }

  async function approve() {
    const select = $('detalle-sucursal');
    try {
      await API.post(`/cobranza/cotizaciones/${state.current.id}/aprobar`, {
        sucursal_id: select && select.value ? Number(select.value) : null,
      });
      Toast.success('Plan aprobado');
      await reload();
      await refreshDetail();
    } catch (error) { Toast.error(error.message); }
  }

  async function removeQuote() {
    if (!window.confirm('¿Eliminar definitivamente esta cotización y todos sus pagos e ingresos?')) return;
    const password = await AdminGate.ask('Eliminar la cotización borra sus pagos e ingresos. Confirma con tu contraseña.');
    if (password === null) return;
    try {
      await API.delete(`/cobranza/cotizaciones/${state.current.id}`, { admin_password: password });
      Modal.close('modal-cotizacion-detalle');
      Toast.success('Cotización eliminada');
      await reload();
    } catch (error) { Toast.error(error.message); }
  }

  // Monto máximo devolvible: lo cobrado en abonos no históricos, menos lo ya
  // devuelto. Replica devolvible() del backend (services.py) para el hint de
  // UI; el backend es quien valida de verdad al guardar.
  function montoDevolvible(quote) {
    const cobrado = (quote.pagos || [])
      .filter(p => !p.historico)
      .reduce((sum, p) => sum + Number(p.monto || 0), 0);
    return Math.max(cobrado - Number(quote.devuelto || 0), 0);
  }

  async function openRefund() {
    const password = await AdminGate.ask('Registrar una devolución. Confirma con tu contraseña.');
    if (password === null) return;

    const disponible = montoDevolvible(state.current);
    $('form-devolucion').reset();
    $('devolucion-fecha').value = localISO();
    $('devolucion-monto').value = disponible ? disponible.toFixed(2) : '';
    $('devolucion-disponible').textContent = `Disponible: ${fmt(disponible)}`;
    $('devolucion-metodo').innerHTML = '<option value="">Sin método</option>' +
      state.methods.map(method => `<option value="${method.id}">${esc(method.nombre)}</option>`).join('');

    $('form-devolucion').onsubmit = async (event) => {
      event.preventDefault();
      const button = $('btn-guardar-devolucion');
      button.disabled = true;
      try {
        const result = await API.post(`/cobranza/cotizaciones/${state.current.id}/devoluciones`, {
          fecha: $('devolucion-fecha').value,
          monto: Number($('devolucion-monto').value),
          metodo_pago_id: Number($('devolucion-metodo').value) || null,
          motivo: $('devolucion-motivo').value.trim() || null,
          admin_password: password,
        });
        Modal.close('modal-devolucion');
        Toast.success('Devolución registrada');
        if (result.aviso_nota_credito) Toast.warning(result.aviso_nota_credito, 8000);
        await reload();
        await refreshDetail();
      } catch (error) {
        Toast.error(error.message || 'No se pudo registrar la devolución');
      } finally {
        button.disabled = false;
      }
    };
    Modal.open('modal-devolucion');
  }

  async function openEditCalendar() {
    const password = await AdminGate.ask('Editar las mensualidades del plan. Confirma con tu contraseña.');
    if (password === null) return;

    const body = $('editar-calendario-body');
    body.replaceChildren();
    const rows = [];

    function updateSum() {
      const suma = rows.reduce((sum, r) => sum + (Number(r.inputMonto.value) || 0), 0);
      $('editar-calendario-suma').textContent = `${fmt(suma)} / ${fmt(state.current.total)}`;
    }

    (state.current.programados || []).forEach(item => {
      const pagado = item.monto_pagado > 0.01;
      const tr = document.createElement('tr');
      tr.className = 'border-t border-border';

      tr.appendChild(domEl('td', 'py-2', item.numero === 0 ? 'Anticipo' : `Pago ${item.numero}`));

      const tdFecha = document.createElement('td');
      tdFecha.className = 'py-2';
      const inputFecha = document.createElement('input');
      inputFecha.type = 'date';
      inputFecha.value = item.fecha_vencimiento;
      inputFecha.disabled = pagado;
      inputFecha.className = 'w-full rounded-lg border border-border px-2 py-1 text-sm disabled:bg-surface-alt disabled:text-text-muted';
      tdFecha.appendChild(inputFecha);
      tr.appendChild(tdFecha);

      const tdMonto = document.createElement('td');
      tdMonto.className = 'py-2 text-right';
      const inputMonto = document.createElement('input');
      inputMonto.type = 'number';
      inputMonto.min = '0.01';
      inputMonto.step = '0.01';
      inputMonto.value = item.monto_programado;
      inputMonto.disabled = pagado;
      inputMonto.className = 'w-28 rounded-lg border border-border px-2 py-1 text-sm text-right disabled:bg-surface-alt disabled:text-text-muted';
      inputMonto.addEventListener('input', updateSum);
      tdMonto.appendChild(inputMonto);
      tr.appendChild(tdMonto);

      const tdEstatus = document.createElement('td');
      tdEstatus.className = 'py-2 text-center';
      if (pagado) tdEstatus.appendChild(badgeEl('pagada', 'success'));
      tr.appendChild(tdEstatus);

      body.appendChild(tr);
      rows.push({ numero: item.numero, inputFecha, inputMonto });
    });
    updateSum();

    $('form-editar-calendario').onsubmit = async (event) => {
      event.preventDefault();
      const calendario = rows.map(r => ({
        numero: r.numero,
        fecha_vencimiento: r.inputFecha.value,
        monto_programado: Number(r.inputMonto.value),
      }));
      const button = $('btn-guardar-calendario');
      button.disabled = true;
      try {
        await API.put(`/cobranza/cotizaciones/${state.current.id}/calendario`, {
          calendario,
          admin_password: password,
        });
        Modal.close('modal-editar-calendario');
        Toast.success('Mensualidades actualizadas');
        await reload();
        await refreshDetail();
      } catch (error) {
        Toast.error(error.message || 'No se pudieron guardar las mensualidades');
      } finally {
        button.disabled = false;
      }
    };
    Modal.open('modal-editar-calendario');
  }

  function updateConceptPreview() {
    const cantidad = Number($('concepto-cantidad').value) || 0;
    const precio = Number($('concepto-precio').value) || 0;
    const incremento = cantidad * precio;
    const nuevoTotal = Number(state.current.total || 0) + incremento;
    const pendientes = (state.current.programados || [])
      .filter(p => p.numero >= 1 && p.monto_pagado <= 0.01);
    let mensaje = `Nuevo total: ${fmt(nuevoTotal)}`;
    if (pendientes.length) {
      const porPendiente = incremento / pendientes.length;
      const ejemplo = Number(pendientes[0].monto_programado || 0) + porPendiente;
      mensaje += ` · las mensualidades pendientes pasan a ${fmt(ejemplo)}`;
    }
    $('concepto-preview').textContent = mensaje;
  }

  async function openAddConcept() {
    const password = await AdminGate.ask('Agregar un concepto al plan. Confirma con tu contraseña.');
    if (password === null) return;

    $('form-agregar-concepto').reset();
    $('concepto-cantidad').value = '1';
    $('concepto-precio').value = '';
    updateConceptPreview();
    $('concepto-cantidad').oninput = updateConceptPreview;
    $('concepto-precio').oninput = updateConceptPreview;

    $('form-agregar-concepto').onsubmit = async (event) => {
      event.preventDefault();
      const button = $('btn-guardar-concepto');
      button.disabled = true;
      try {
        await API.post(`/cobranza/cotizaciones/${state.current.id}/conceptos`, {
          descripcion: $('concepto-descripcion').value.trim(),
          cantidad: Number($('concepto-cantidad').value) || 1,
          precio_unitario: Number($('concepto-precio').value) || 0,
          admin_password: password,
        });
        Modal.close('modal-agregar-concepto');
        Toast.success('Concepto agregado');
        await reload();
        await refreshDetail();
      } catch (error) {
        Toast.error(error.message || 'No se pudo agregar el concepto');
      } finally {
        button.disabled = false;
      }
    };
    Modal.open('modal-agregar-concepto');
  }

  async function sendQuote() {
    try {
      await API.post(`/cobranza/cotizaciones/${state.current.id}/enviar`, {});
      Toast.success('Cotización enviada');
      await reload();
      await refreshDetail();
    } catch (error) { Toast.error(error.message); }
  }

  async function sendStatement() {
    try {
      const result = await API.post(
        `/cobranza/cotizaciones/${state.current.id}/estado-cuenta/enviar`, {},
      );
      Toast.success(result.message || 'Estado de cuenta enviado por correo');
    } catch (error) {
      Toast.error(error.message || 'No se pudo enviar el estado de cuenta');
    }
  }

  async function copyStatement() {
    try {
      const data = await API.get(`/cobranza/cotizaciones/${state.current.id}/estado-cuenta`);
      await navigator.clipboard.writeText(data.texto);
      Toast.success('Estado de cuenta copiado');
    } catch (error) { Toast.error(error.message || 'No se pudo copiar'); }
  }

  async function download(suffix) {
    try {
      const url = `/api/v1/cobranza/cotizaciones/${state.current.id}/${suffix}`;
      let response = await fetch(url, { headers: { Authorization: `Bearer ${Auth.getToken()}` } });
      if (response.status === 401 && await Auth.refreshAccessToken()) {
        response = await fetch(url, { headers: { Authorization: `Bearer ${Auth.getToken()}` } });
      }
      if (!response.ok) throw new Error('No se pudo generar el PDF');
      const blob = await response.blob();
      const anchor = document.createElement('a');
      anchor.href = URL.createObjectURL(blob);
      anchor.download = `${state.current.folio}-${suffix.replace('.pdf', '')}.pdf`;
      anchor.click();
      URL.revokeObjectURL(anchor.href);
    } catch (error) { Toast.error(error.message); }
  }

  function openPayment(suggested) {
    state.paymentKey = null;
    $('form-pago').reset();
    $('pago-fecha').value = localISO();
    $('pago-monto').value = suggested ? Math.min(suggested, state.current.saldo) : state.current.saldo;
    $('pago-saldo').textContent = `Saldo actual: ${fmt(state.current.saldo)}`;
    $('pago-historico-wrap').classList.toggle('hidden', role() !== 'admin');
    $('pago-metodo').innerHTML = '<option value="">Sin método</option>' +
      state.methods.map(method => `<option value="${method.id}">${esc(method.nombre)}</option>`).join('');
    Modal.open('modal-pago');
  }

  async function savePayment(event) {
    event.preventDefault();
    state.paymentKey = state.paymentKey || (
      window.crypto && crypto.randomUUID ? crypto.randomUUID()
        : `pay-${Date.now()}-${Math.random().toString(16).slice(2)}`
    );
    const button = $('btn-guardar-pago');
    button.disabled = true;
    try {
      const result = await API.request(
        `/cobranza/cotizaciones/${state.current.id}/pagos`,
        {
          method: 'POST',
          headers: { 'Idempotency-Key': state.paymentKey },
          body: JSON.stringify({
            fecha: $('pago-fecha').value,
            monto: Number($('pago-monto').value),
            metodo_pago_id: Number($('pago-metodo').value) || null,
            historico: $('pago-historico').checked,
            notas: $('pago-notas').value.trim() || null,
          }),
        },
      );
      state.paymentKey = null;
      Modal.close('modal-pago');
      Toast.success(result.idempotent_replay ? 'El abono ya estaba registrado' : 'Abono registrado');
      if (result.facturacion && result.facturacion.error) {
        Toast.warning('El pago quedó guardado; revisa el estado de facturación');
      }
      await reload();
      await refreshDetail();
    } catch (error) {
      Toast.error(error.message || 'No se pudo registrar el abono');
    } finally {
      button.disabled = false;
    }
  }

  async function retryInvoice() {
    try {
      const result = await API.post(
        `/cobranza/cotizaciones/${state.current.id}/facturacion/reintentar`, {},
      );
      Toast[result.error ? 'warning' : 'success'](
        result.error ? 'El reintento sigue pendiente' : 'Facturación procesada',
      );
      await refreshDetail();
    } catch (error) { Toast.error(error.message); }
  }

  async function openAuditLog() {
    try {
      const filas = await API.get('/cobranza/auditoria');
      const cont = $('auditoria-lista');
      cont.replaceChildren();
      if (!filas.length) {
        const vacio = document.createElement('p');
        vacio.className = 'text-sm text-text-muted';
        vacio.textContent = 'Sin operaciones registradas.';
        cont.appendChild(vacio);
      } else {
        // textContent en todos los campos: `paciente` y `usuario` vienen de
        // datos capturados por el usuario y no deben interpretarse como HTML.
        filas.forEach((f) => {
          const row = document.createElement('div');
          row.className = 'flex justify-between border-b border-border py-2 text-sm';
          const fecha = f.created_at ? new Date(f.created_at).toLocaleDateString() : '';
          const monto = f.monto != null ? `$${Number(f.monto).toLocaleString()}` : '';
          const izq = document.createElement('span');
          izq.textContent = `${fecha} · ${f.accion} · ${f.cotizacion_folio}`
            + (f.paciente ? ` · ${f.paciente}` : '');
          const der = document.createElement('span');
          der.textContent = `${monto}${f.usuario ? ' · ' + f.usuario : ''}`;
          row.append(izq, der);
          cont.appendChild(row);
        });
      }
      Modal.open('modal-auditoria');
    } catch (error) { Toast.error(error.message || 'No se pudo cargar la bitácora'); }
  }

  function clearFilters() {
    ['filtro-estatus', 'filtro-paciente', 'filtro-desde', 'filtro-hasta']
      .forEach(id => { $(id).value = ''; });
    reload();
  }

  async function init() {
    CobranzaForm.init();
    try {
      const [me, methods, branches] = await Promise.all([
        API.get('/auth/me'),
        API.get('/ajustes/metodos-pago'),
        API.get('/facturacion/sucursales'),
        CobranzaForm.loadCatalogs(),
      ]);
      state.user = me.user || me;
      state.methods = Array.isArray(methods) ? methods : [];
      state.branches = (Array.isArray(branches) ? branches : []).filter(branch => branch.activa !== false);
      refreshPatients(CobranzaForm.patients());
      $('btn-nueva-cotizacion').classList.toggle('hidden', !writableRoles.includes(role()));
      $('btn-bitacora').classList.toggle('hidden', role() !== 'admin');
    } catch (error) {
      Toast.error(error.message || 'No se pudieron cargar los catálogos');
    }
    $('btn-nueva-cotizacion').addEventListener('click', () => CobranzaForm.open());
    $('btn-bitacora').addEventListener('click', openAuditLog);
    $('form-pago').addEventListener('submit', savePayment);
    $('btn-limpiar-filtros').addEventListener('click', clearFilters);
    ['filtro-estatus', 'filtro-paciente', 'filtro-desde', 'filtro-hasta']
      .forEach(id => $(id).addEventListener('change', reload));
    const search = $('cs-global-search');
    if (search) search.addEventListener('input', renderList);
    document.querySelectorAll('[data-close-modal]').forEach(element => {
      element.addEventListener('click', () => Modal.close(element.dataset.closeModal));
    });
    await reload();
  }

  return { init, reload, openDetail, refreshPatients };
})();

document.addEventListener('DOMContentLoaded', Cobranza.init);
