/* Página /corte-caja: pega el DOM con la API de caja (/api/v1/caja) usando
   las reglas de CorteUX (app/static/js/caja/corte_ux.js) para decidir cuándo
   se puede cerrar. Sin build step: se carga como <script> plano después de
   corte_ux.js y de app.js (API, Toast, Modal, renderTable, populateSelect,
   fmt, formatDate, domEl, domIcon ya existen en el scope global). */

// Fecha de hoy en hora local, sin toISOString: a partir de las 18:00 en México
// toISOString devuelve el día siguiente y el corte se abriría en la fecha
// equivocada. Mismo helper que ya usa la página de ingresos.
function todayLocalISO() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return d.getFullYear() + '-' + mm + '-' + dd;
}

let resumen = null;
let userRole = null;
let sucursales = [];
let sucursalSel = null;
let empresaNombre = ''; // nombre de la clínica, para el ticket impreso (de /auth/me)

document.getElementById('fecha-hoy').textContent = formatDate(todayLocalISO());

async function cargarResumen() {
  const params = new URLSearchParams({ fecha: todayLocalISO() });
  if (sucursalSel) params.set('sucursal_id', sucursalSel);
  try {
    resumen = await API.get('/caja/corte?' + params.toString());
  } catch (e) {
    // Sin esto, la pantalla se queda con las tarjetas en el $0.00 de la
    // plantilla sin avisar nada: en una conciliación de efectivo, un dato
    // silenciosamente equivocado es peor que un error visible.
    Toast.error('No se pudo cargar el corte de caja');
    // El `resumen` en memoria se queda con el de la sucursal anterior (no se
    // toca en este catch), pero `sucursalSel` ya cambió. Sin apagar el aviso
    // aquí, el botón se queda rojo hablando de una caja que ya no es la que se
    // está mirando, y ese rojo es justo el que abre abrirCorregirDia().
    TurnoCaja.marcarCajaAjena({ abierta: false });
    return;
  }
  render();
  // Después de render() y en la misma función a propósito: el estado del botón
  // depende de la sucursal seleccionada, así que tiene que refrescarse en el
  // mismo sitio donde se refresca el resumen —incluido el cambio de sucursal,
  // que pasa por aquí—. Si no, el botón se quedaría hablando de la sucursal
  // anterior.
  TurnoCaja.marcarCajaAjena({
    abierta: !!resumen.caja_abierta,
    por: resumen.caja_abierta_por,
  });
}

function render() {
  document.getElementById('stat-efectivo').textContent = fmt(resumen.totales.efectivo);
  document.getElementById('stat-tarjeta').textContent = fmt(resumen.totales.tarjeta);
  document.getElementById('stat-tarjeta-neto').textContent =
    'Neto al banco: ' + fmt(resumen.neto_tarjeta);
  document.getElementById('stat-transferencia').textContent =
    fmt(resumen.totales.transferencia);
  document.getElementById('stat-total-dia').textContent = fmt(resumen.total_dia);

  // Desglose: la misma resta que services.resumen_dia, de arriba abajo.
  document.getElementById('desglose-efectivo').textContent = fmt(resumen.totales.efectivo);
  document.getElementById('stat-salidas').textContent = fmt(resumen.salidas_efectivo);
  document.getElementById('stat-pagos-doctores').textContent =
    fmt(resumen.pagos_doctores_efectivo);
  document.getElementById('stat-esperado').textContent = fmt(resumen.esperado_efectivo);
  // `a_entregar` y NO `esperado_efectivo`: el fondo se queda en el cajón.
  document.getElementById('stat-entregar').textContent = fmt(resumen.a_entregar);

  // El fondo solo se menciona cuando existe, salvo para quien puede
  // corregirlo: un fondo en cero es justo el caso que vino a arreglar.
  const muestraFondo = CorteUX.muestraLeyendaFondo(resumen);
  document.getElementById('leyenda-fondo').style.display = muestraFondo ? '' : 'none';
  document.getElementById('leyenda-entregar').style.display = muestraFondo ? '' : 'none';
  document.getElementById('stat-fondo').textContent = fmt(resumen.fondo_inicial);
  // Quién puede corregir lo decide el servidor (`puede_corregir_dia`).
  document.getElementById('btn-corregir-dia').style.display =
    resumen.puede_corregir_dia ? 'inline-flex' : 'none';

  const otro = Number(resumen.totales.otro || 0);
  document.getElementById('stat-otro').textContent = fmt(otro);
  document.getElementById('aviso-otro').classList.toggle('hidden', otro === 0);

  renderSinClasificar();
  renderSalidas();
  renderPagosDoctores();
  renderIngresos();
  renderEstadoCierre();
  renderCierre();
  lucide.createIcons();
}

// Botón de solo icono para las filas: 40×40 de área táctil, etiqueta
// accesible y foco visible. Sus clases están en el safelist de la plantilla.
function botonIcono(icono, etiqueta, alClic, peligro) {
  const btn = domEl('button',
    'inline-flex items-center justify-center h-10 w-10 rounded-lg text-text-muted transition-colors cursor-pointer ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 ' +
    (peligro ? 'hover:bg-danger-50 hover:text-danger-600'
             : 'hover:bg-surface-hover hover:text-text-primary'));
  btn.type = 'button';
  btn.title = etiqueta;
  btn.setAttribute('aria-label', etiqueta);
  btn.appendChild(domIcon(icono));
  btn.addEventListener('click', alClic);
  return btn;
}

// Lista de ingresos sin método de pago: son efectivo que nadie está contando
// y CorteUX.puedeCerrar bloquea el cierre mientras existan.
function renderSinClasificar() {
  const items = resumen.sin_clasificar || [];
  document.getElementById('aviso-sin-clasificar').classList.toggle('hidden', items.length === 0);
  const lista = document.getElementById('lista-sin-clasificar');
  lista.replaceChildren();
  items.forEach(it => {
    lista.appendChild(domEl(
      'li', '',
      (it.paciente || 'Sin paciente') + ' — ' + (it.concepto || 'Sin concepto') + ' — ' + fmt(it.monto),
    ));
  });
}

// Salidas del día. `propia` (calculado por el backend) decide si esta sesión
// puede borrarla: la recepcionista solo ve el concepto real de las suyas.
function renderSalidas() {
  const cols = [
    { key: 'concepto', label: 'Concepto' },
    { key: 'monto', label: 'Monto', align: 'right', render: v => domEl('span', 'tabular-nums font-medium', fmt(v)) },
    { key: 'id', label: '', align: 'right', render: (id, row) => {
      if (!row.propia || resumen.estado === 'cerrado') return '';
      return botonIcono('trash-2', 'Eliminar salida', () => abrirEliminarSalida(id), true);
    } },
  ];
  renderTable('tabla-salidas', cols, resumen.salidas || [], 'Sin salidas registradas hoy', false);
}

// Borrar una salida es irreversible: se confirma con un modal, igual que
// "Eliminar Ingreso" en edr/ingresos.html y "Eliminar Gasto" en edr/gastos.html.
let salidaAEliminarId = null;

function abrirEliminarSalida(id) {
  salidaAEliminarId = id;
  Modal.open('modal-eliminar-salida');
}

async function confirmarEliminarSalida() {
  const btn = document.getElementById('btn-confirmar-eliminar-salida');
  const txt = document.getElementById('texto-confirmar-eliminar-salida');
  btn.disabled = true;
  txt.textContent = 'Eliminando...';
  try {
    await API.delete('/caja/salidas/' + salidaAEliminarId);
    Toast.success('Salida eliminada');
    Modal.close('modal-eliminar-salida');
    await cargarResumen();
  } catch (e) {
    Toast.warning(e.message || 'No se pudo eliminar la salida');
  } finally {
    btn.disabled = false;
    txt.textContent = 'Eliminar';
  }
}

// ── Pagos a doctores: lista del día ─────────────────────────────────────────
// Lista propia y no renderTable: un pago de comisiones se despliega para ver
// qué pacientes cubrió, y renderTable no tiene filas expandibles.
function tipoPagoBadge(p) {
  const esSalario = p.tipo === 'salario';
  const texto = (p.comisiones && p.comisiones.length)
    ? 'Comisiones' : (esSalario ? 'Salario' : 'Comisión');
  return domEl('span',
    'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ' +
    (esSalario ? 'bg-accent-50 text-accent-700' : 'bg-primary-50 text-primary-700'),
    texto);
}

function renderPagosDoctores() {
  const cont = document.getElementById('tabla-pagos-doctores');
  cont.replaceChildren();
  const pagos = resumen.pagos_doctores || [];
  if (!pagos.length) {
    cont.appendChild(domEl('p', 'text-sm text-text-muted font-body py-6 text-center',
      'Sin pagos a doctores hoy'));
    return;
  }
  const ul = domEl('ul', 'divide-y divide-border');
  pagos.forEach(p => {
    const li = domEl('li', 'py-3 first:pt-0');
    const fila = domEl('div', 'flex items-start gap-3');

    const info = domEl('div', 'flex-1 min-w-0');
    const titulo = domEl('div', 'flex items-center gap-2 flex-wrap');
    titulo.appendChild(domEl('span', 'text-sm font-medium text-text-primary font-body',
      p.especialista_nombre));
    titulo.appendChild(tipoPagoBadge(p));
    info.appendChild(titulo);
    if (p.concepto) {
      info.appendChild(domEl('p', 'text-xs text-text-secondary font-body truncate', p.concepto));
    }
    if (p.comisiones && p.comisiones.length) {
      const det = domEl('details', 'mt-1');
      const n = p.comisiones.length;
      det.appendChild(domEl('summary',
        'text-xs text-primary-600 hover:text-primary-700 cursor-pointer font-body',
        'Ver ' + n + (n === 1 ? ' paciente' : ' pacientes')));
      const lista = domEl('ul', 'mt-1 space-y-0.5 text-xs text-text-secondary font-body');
      p.comisiones.forEach(c => {
        const item = domEl('li', 'flex justify-between gap-3');
        item.appendChild(domEl('span', 'truncate', c.paciente + ' · ' + c.nombre_tratamiento));
        item.appendChild(domEl('span', 'tabular-nums shrink-0', fmt(c.monto)));
        lista.appendChild(item);
      });
      if (p.descuento_saldo) {
        lista.appendChild(domEl('li', 'text-warning-700',
          'Saldo aplicado: −' + fmt(p.descuento_saldo)));
      }
      det.appendChild(lista);
      info.appendChild(det);
    }
    fila.appendChild(info);

    fila.appendChild(domEl('span',
      'text-sm font-semibold tabular-nums text-text-primary font-body shrink-0 pt-2',
      fmt(p.monto)));

    const acciones = domEl('div', 'flex items-center shrink-0');
    acciones.appendChild(botonIcono('printer', 'Reimprimir comprobante',
      () => imprimirComprobantePago(p.id)));
    // `propia` ya es true para el admin (el servidor no le enmascara nada).
    if (p.propia && resumen.estado !== 'cerrado') {
      acciones.appendChild(botonIcono('trash-2', 'Eliminar pago',
        () => abrirEliminarPago(p.id), true));
    }
    fila.appendChild(acciones);
    li.appendChild(fila);
    ul.appendChild(li);
  });
  cont.appendChild(ul);
}

async function imprimirComprobantePago(id) {
  // Separado en dos try: un 404/403 del servidor (pago ajeno, no encontrado)
  // no es lo mismo que el agente de impresión apagado, y mezclarlos en un
  // solo catch le echaba la culpa al agente por errores del servidor.
  let payload;
  try {
    payload = await API.get('/caja/pagos-doctores/' + id + '/comprobante');
  } catch (e) {
    Toast.warning(e.message || 'No se pudo obtener el comprobante');
    return;
  }
  try {
    await PrintAgent.print(payload);
  } catch (e) {
    Toast.warning('No se pudo imprimir (¿agente de impresión encendido?)');
  }
}

let pagoAEliminarId = null;

function abrirEliminarPago(id) {
  pagoAEliminarId = id;
  Modal.open('modal-eliminar-pago');
}

async function confirmarEliminarPago() {
  const btn = document.getElementById('btn-confirmar-eliminar-pago');
  const txt = document.getElementById('texto-confirmar-eliminar-pago');
  if (btn.disabled || pagoAEliminarId === null) return;
  btn.disabled = true;
  txt.textContent = 'Eliminando…';
  try {
    await API.delete('/caja/pagos-doctores/' + pagoAEliminarId);
    Toast.success('Pago eliminado');
    Modal.close('modal-eliminar-pago');
    pagoAEliminarId = null;
    await cargarResumen();
  } catch (e) {
    Toast.warning(e.message || 'No se pudo eliminar el pago');
  } finally {
    btn.disabled = false;
    txt.textContent = 'Eliminar';
  }
}

// ── Pagos a doctores: modal "Pagar a doctor" ────────────────────────────────
let doctores = null;              // [{id, nombre}] de /caja/doctores; una vez por carga
let pagoModo = 'comisiones';      // 'comisiones' | 'libre'
let pendientes = null;            // respuesta de /caja/comisiones-pendientes
let seleccionComisiones = new Set();
let pagoEnviando = false;
let pagoRegistradoId = null;

async function abrirPagoDoctor() {
  if (!resumen || resumen.estado === 'cerrado') return;
  if (doctores === null) {
    try {
      doctores = (await API.get('/caja/doctores')).doctores || [];
    } catch (e) {
      Toast.error('No se pudo cargar la lista de doctores');
      return;
    }
  }
  pagoRegistradoId = null;
  pendientes = null;
  seleccionComisiones = new Set();
  document.getElementById('f-pago-concepto').value = '';
  document.getElementById('f-pago-monto').value = '';
  document.getElementById('f-pago-tipo').value = 'salario';
  document.getElementById('error-pago-doctor').style.display = 'none';
  document.getElementById('error-pago-monto').style.display = 'none';
  populateSelect(document.getElementById('f-pago-doctor'),
    doctores.map(d => ({ value: String(d.id), label: d.nombre })), '', 'Elige un doctor');
  mostrarPasoPago('captura');
  cambiarModoPago('comisiones');
  Modal.open('modal-pago-doctor');
  setTimeout(() => document.getElementById('f-pago-doctor').focus(), 50);
}

function mostrarPasoPago(paso) {
  const exito = paso === 'exito';
  document.getElementById('pago-captura').style.display = exito ? 'none' : '';
  document.getElementById('pago-footer-captura').style.display = exito ? 'none' : '';
  document.getElementById('pago-exito').style.display = exito ? '' : 'none';
  document.getElementById('pago-footer-exito').style.display = exito ? '' : 'none';
  lucide.createIcons();
}

function cambiarModoPago(modo) {
  pagoModo = modo;
  document.querySelectorAll('.modo-pago').forEach(b => {
    const activo = b.dataset.modo === modo;
    b.classList.toggle('active', activo);
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
  });
  document.getElementById('panel-comisiones').style.display = modo === 'comisiones' ? '' : 'none';
  document.getElementById('panel-libre').style.display = modo === 'libre' ? '' : 'none';
  document.getElementById('error-pago-doctor').style.display = 'none';
  if (modo === 'comisiones') {
    cargarPendientes();
  } else {
    actualizarPago();
  }
}

async function cargarPendientes() {
  const selDoctor = document.getElementById('f-pago-doctor');
  const estado = document.getElementById('comisiones-estado');
  const pedido = selDoctor.value;
  pendientes = null;
  seleccionComisiones = new Set();
  document.getElementById('comisiones-lista-wrap').style.display = 'none';
  if (!pedido) {
    estado.textContent = 'Elige un doctor para ver sus comisiones pendientes.';
    actualizarPago();
    return;
  }
  estado.textContent = 'Cargando comisiones…';
  actualizarPago();
  let data;
  try {
    data = await API.get('/caja/comisiones-pendientes?especialista_id=' + encodeURIComponent(pedido));
  } catch (e) {
    if (selDoctor.value !== pedido || pagoModo !== 'comisiones') return;
    estado.replaceChildren(domEl('span', '', 'No se pudieron cargar las comisiones. '));
    const reintentar = domEl('button', 'text-primary-600 hover:text-primary-700 font-medium cursor-pointer', 'Reintentar');
    reintentar.type = 'button';
    reintentar.addEventListener('click', cargarPendientes);
    estado.appendChild(reintentar);
    return;
  }
  // Si mientras cargaba se eligió otro doctor o se cambió de modo, esta
  // respuesta ya no describe lo que está en pantalla.
  if (selDoctor.value !== pedido || pagoModo !== 'comisiones') return;
  pendientes = data;
  seleccionComisiones = new Set((data.comisiones || []).map(c => String(c.ingreso_id)));
  renderComisionesPendientes();
  actualizarPago();
}

function renderComisionesPendientes() {
  const estado = document.getElementById('comisiones-estado');
  const wrap = document.getElementById('comisiones-lista-wrap');
  const lista = document.getElementById('comisiones-lista');
  lista.replaceChildren();
  const coms = (pendientes && pendientes.comisiones) || [];
  if (!coms.length) {
    wrap.style.display = 'none';
    estado.replaceChildren(domEl('span', '', 'No tiene comisiones pendientes. '));
    const atajo = domEl('button', 'text-primary-600 hover:text-primary-700 font-medium cursor-pointer', 'Registrar un pago libre');
    atajo.type = 'button';
    atajo.addEventListener('click', () => cambiarModoPago('libre'));
    estado.appendChild(atajo);
    return;
  }
  estado.textContent = '';
  wrap.style.display = '';
  coms.forEach(c => {
    const id = String(c.ingreso_id);
    const li = domEl('li');
    const label = domEl('label', 'flex items-center gap-3 px-4 py-2.5 text-sm font-body cursor-pointer hover:bg-surface-hover min-h-[44px]');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'h-4 w-4 accent-primary-600 shrink-0';
    cb.checked = seleccionComisiones.has(id);
    cb.addEventListener('change', () => {
      if (cb.checked) seleccionComisiones.add(id); else seleccionComisiones.delete(id);
      actualizarPago();
    });
    label.appendChild(cb);
    const texto = domEl('span', 'flex-1 min-w-0');
    texto.appendChild(domEl('span', 'block truncate text-text-primary', c.paciente));
    texto.appendChild(domEl('span', 'block truncate text-xs text-text-secondary',
      formatDate(c.fecha) + ' · ' + c.nombre_tratamiento));
    label.appendChild(texto);
    label.appendChild(domEl('span', 'tabular-nums font-medium text-text-primary shrink-0', fmt(c.comision_doctor)));
    li.appendChild(label);
    lista.appendChild(li);
  });
}

// Única función que decide el estado del pie del modal: resumen, texto y
// habilitado del botón, y aviso de efectivo.
function actualizarPago() {
  const btn = document.getElementById('btn-confirmar-pago');
  const texto = document.getElementById('texto-confirmar-pago');
  const resumenCom = document.getElementById('comisiones-resumen');
  let ok = !!document.getElementById('f-pago-doctor').value && !pagoEnviando;
  let neto = null;

  if (pagoModo === 'comisiones') {
    const r = pendientes
      ? CorteUX.resumenPagoComisiones(pendientes.comisiones, Array.from(seleccionComisiones), pendientes.saldo_negativo)
      : null;
    resumenCom.style.display = r && r.cantidad ? '' : 'none';
    if (r) {
      document.getElementById('resumen-cantidad').textContent = r.cantidad;
      document.getElementById('resumen-suma').textContent = fmt(r.suma);
      document.getElementById('fila-descuento').style.display = r.descuento > 0 ? '' : 'none';
      document.getElementById('resumen-descuento').textContent = '−' + fmt(r.descuento);
      document.getElementById('resumen-neto').textContent = fmt(r.neto);
      const total = (pendientes.comisiones || []).length;
      const todas = document.getElementById('f-comisiones-todas');
      todas.checked = total > 0 && r.cantidad === total;
      todas.indeterminate = r.cantidad > 0 && r.cantidad < total;
      if (r.cantidad) neto = r.neto;
    }
    ok = ok && !!r && r.cantidad > 0;
  } else {
    resumenCom.style.display = 'none';
    const monto = CorteUX.normalizarMonto(document.getElementById('f-pago-monto').value);
    const concepto = document.getElementById('f-pago-concepto').value.trim();
    ok = ok && monto !== null && monto > 0 && !!concepto;
    if (monto !== null && monto > 0) neto = monto;
  }

  if (!pagoEnviando) texto.textContent = CorteUX.textoBotonPago(neto);
  btn.disabled = !ok;

  const aviso = document.getElementById('aviso-pago-efectivo');
  if (neto !== null && resumen && CorteUX.excedeEfectivo(resumen, neto)) {
    aviso.textContent = 'En el cajón debería haber ' + fmt(resumen.esperado_efectivo) +
      '. Verifica que alcance antes de entregar el dinero.';
    aviso.style.display = '';
  } else {
    aviso.style.display = 'none';
  }
}

// Error bajo el campo al salir de él, no mientras escribe.
function validarMontoPago() {
  const valor = document.getElementById('f-pago-monto').value;
  const monto = CorteUX.normalizarMonto(valor);
  document.getElementById('error-pago-monto').style.display =
    valor.trim() && (monto === null || monto === 0) ? '' : 'none';
}

async function confirmarPagoDoctor(ev) {
  if (ev) ev.preventDefault();
  const btn = document.getElementById('btn-confirmar-pago');
  if (pagoEnviando || btn.disabled) return;
  const err = document.getElementById('error-pago-doctor');
  err.style.display = 'none';

  const base = {
    fecha: todayLocalISO(),
    sucursal_id: sucursalSel || null,
    especialista_id: Number(document.getElementById('f-pago-doctor').value),
  };
  pagoEnviando = true;
  btn.disabled = true;
  document.getElementById('texto-confirmar-pago').textContent = 'Registrando…';
  try {
    let pago;
    if (pagoModo === 'comisiones') {
      pago = await API.post('/caja/pagos-doctores/comisiones', Object.assign({}, base, {
        ingreso_ids: Array.from(seleccionComisiones).map(Number),
      }));
    } else {
      pago = await API.post('/caja/pagos-doctores', Object.assign({}, base, {
        tipo: document.getElementById('f-pago-tipo').value,
        concepto: document.getElementById('f-pago-concepto').value.trim(),
        monto: CorteUX.normalizarMonto(document.getElementById('f-pago-monto').value),
      }));
    }
    pagoRegistradoId = pago.id;
    document.getElementById('pago-exito-detalle').textContent =
      fmt(pago.monto) + ' a ' + (pago.especialista_nombre || 'el doctor');
    mostrarPasoPago('exito');
    await cargarResumen();
  } catch (e) {
    err.textContent = e.message || 'No se pudo registrar el pago';
    err.style.display = '';
    // La comisión pudo haberla pagado alguien más mientras el modal estaba
    // abierto: se recargan para que la lista diga la verdad.
    if (pagoModo === 'comisiones') await cargarPendientes();
  } finally {
    pagoEnviando = false;
    actualizarPago();
  }
}

function engancharPagoDoctor() {
  document.getElementById('btn-pagar-doctor').addEventListener('click', abrirPagoDoctor);
  document.getElementById('f-pago-doctor').addEventListener('change', () => {
    if (pagoModo === 'comisiones') cargarPendientes(); else actualizarPago();
  });
  document.querySelectorAll('.modo-pago').forEach(b =>
    b.addEventListener('click', () => cambiarModoPago(b.dataset.modo)));
  document.getElementById('f-comisiones-todas').addEventListener('change', e => {
    if (!pendientes) return;
    seleccionComisiones = e.target.checked
      ? new Set((pendientes.comisiones || []).map(c => String(c.ingreso_id)))
      : new Set();
    renderComisionesPendientes();
    actualizarPago();
  });
  ['f-pago-concepto', 'f-pago-monto', 'f-pago-tipo'].forEach(id =>
    document.getElementById(id).addEventListener('input', actualizarPago));
  document.getElementById('f-pago-monto').addEventListener('blur', validarMontoPago);
  document.getElementById('form-pago-doctor').addEventListener('submit', confirmarPagoDoctor);
  document.querySelectorAll('[data-cerrar-pago]').forEach(el =>
    el.addEventListener('click', () => Modal.close('modal-pago-doctor')));
  document.getElementById('btn-imprimir-pago').addEventListener('click', () => {
    if (pagoRegistradoId) imprimirComprobantePago(pagoRegistradoId);
  });
}

// Se decide abierto/plegado una sola vez: si ella lo abre o lo cierra, un
// recálculo (p. ej. al registrar una salida) no se lo cambia.
let ingresosPlegadoDecidido = false;

// Ingresos del día: solo lectura aquí, se editan desde /ingresos.
function renderIngresos() {
  const filas = resumen.ingresos || [];
  const cols = [
    { key: 'paciente', label: 'Paciente', render: v => v || '—' },
    { key: 'concepto', label: 'Concepto', render: v => v || '—' },
    { key: 'metodo', label: 'Método', render: v => v || domEl('span', 'text-warning-600', 'Sin método') },
    { key: 'monto', label: 'Monto', align: 'right', render: v => domEl('span', 'tabular-nums font-medium', fmt(v)) },
  ];
  renderTable('tabla-ingresos', cols, filas, 'Sin ingresos registrados hoy', false);

  const total = filas.reduce((s, f) => s + Number(f.monto || 0), 0);
  document.getElementById('ingresos-resumen').textContent =
    filas.length + (filas.length === 1 ? ' ingreso' : ' ingresos') + ' · ' + fmt(total);
  if (!ingresosPlegadoDecidido) {
    document.getElementById('bloque-ingresos').open =
      CorteUX.ingresosAbiertosPorDefecto(filas.length);
    ingresosPlegadoDecidido = true;
  }
}

// El botón se habilita SOLO según CorteUX: una sola regla, probada aparte.
function renderEstadoCierre() {
  const contado = document.getElementById('f-contado').value;
  const comentario = document.getElementById('f-comentario').value;
  const veredicto = CorteUX.puedeCerrar(resumen, contado, comentario);

  // El comentario aparece en cuanto la diferencia se sale de la tolerancia.
  document.getElementById('f-comentario').parentElement.classList.toggle(
    'hidden', !CorteUX.excedeTolerancia(resumen, contado));

  const btn = document.getElementById('btn-cerrar');
  btn.disabled = !veredicto.ok;
  btn.classList.toggle('opacity-50', !veredicto.ok);
  btn.classList.toggle('cursor-not-allowed', !veredicto.ok);
  document.getElementById('motivo-bloqueo').textContent = veredicto.motivo || '';

  const dif = CorteUX.diferencia(resumen, contado);
  const et = document.getElementById('etiqueta-diferencia');
  if (dif === null) { et.textContent = ''; return; }
  const info = CorteUX.etiquetaDiferencia(dif);
  et.textContent = info.texto;
  et.className = 'mt-1 text-sm font-medium font-body ' + info.clase;
}

['f-contado', 'f-comentario'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderEstadoCierre));

// Cuando el día ya está cerrado, el bloque de captura se sustituye por el
// sello de solo lectura y ya no se puede registrar una salida nueva.
function renderCierre() {
  const cerrado = resumen.estado === 'cerrado';
  document.getElementById('bloque-cierre').classList.toggle('hidden', cerrado);
  document.getElementById('sello-cerrado').classList.toggle('hidden', !cerrado);

  // Igual que el botón de eliminar en renderSalidas(): con la caja cerrada,
  // el control de alta no solo se deshabilita, se quita del flujo. Se usa
  // `style.display` y no `classList.toggle('hidden', ...)`: en este botón la
  // clase `hidden` compite con `inline-flex` (ya presente en el markup) y,
  // verificado con getComputedStyle en el navegador, `inline-flex` gana la
  // cascada del CDN de Tailwind — la clase `hidden` queda puesta pero el
  // elemento se sigue viendo y sigue siendo clicable. El estilo inline no
  // compite con ninguna clase y siempre gana.
  const btnSalida = document.getElementById('btn-nueva-salida');
  btnSalida.style.display = cerrado ? 'none' : '';
  btnSalida.disabled = cerrado;
  btnSalida.classList.toggle('opacity-50', cerrado);
  btnSalida.classList.toggle('cursor-not-allowed', cerrado);

  // Mismo trato que "Nueva salida": con la caja cerrada no se paga a nadie.
  const btnPago = document.getElementById('btn-pagar-doctor');
  btnPago.style.display = cerrado ? 'none' : '';
  btnPago.disabled = cerrado;

  if (cerrado && resumen.corte) {
    const c = resumen.corte;
    const dl = document.getElementById('sello-detalle');
    dl.replaceChildren();
    const datos = [
      ['Cerró', c.cerrado_por || '—'],
      ['Fecha', c.cerrado_at ? formatDate(c.cerrado_at) : '—'],
      ['Diferencia', fmt(c.diferencia)],
    ];
    if (c.comentario) datos.push(['Comentario', c.comentario]);
    datos.forEach(([etiqueta, valor]) => {
      const div = domEl('div', 'min-w-0');
      div.appendChild(domEl('dt', 'text-xs text-accent-700 font-body', etiqueta));
      div.appendChild(domEl('dd', 'text-sm font-medium text-text-primary font-body break-words', valor));
      dl.appendChild(div);
    });
  }
}

function abrirNuevaSalida() {
  document.getElementById('f-salida-concepto').value = '';
  document.getElementById('f-salida-monto').value = '';
  Modal.open('modal-salida');
  setTimeout(() => document.getElementById('f-salida-concepto').focus(), 50);
}

let salidaEnviando = false;

async function guardarSalida(ev) {
  if (ev) ev.preventDefault();
  if (salidaEnviando) return;
  const concepto = document.getElementById('f-salida-concepto').value.trim();
  const monto = CorteUX.normalizarMonto(document.getElementById('f-salida-monto').value);
  if (!concepto) { Toast.warning('Escribe de qué fue la salida'); return; }
  if (monto === null || monto === 0) { Toast.warning('El monto debe ser mayor a cero'); return; }
  // Sin este candado, un doble clic (o Enter dos veces) sobre una respuesta
  // lenta registraba la misma salida dos veces.
  const btn = document.getElementById('btn-guardar-salida');
  const txt = document.getElementById('texto-guardar-salida');
  salidaEnviando = true;
  btn.disabled = true;
  txt.textContent = 'Guardando…';
  try {
    await API.post('/caja/salidas', {
      fecha: todayLocalISO(), concepto_nombre: concepto, monto: monto,
      sucursal_id: sucursalSel || null,
    });
    Modal.close('modal-salida');
    await cargarResumen();
  } catch (e) {
    Toast.warning(e.message || 'No se pudo registrar la salida');
  } finally {
    salidaEnviando = false;
    btn.disabled = false;
    txt.textContent = 'Guardar';
  }
}

function abrirCorregirDia() {
  // Mismo candado que render() ya aplica a btn-corregir-dia, dicho aquí porque
  // la cara roja del botón de la cabecera llega a este mismo modal sin pasar
  // por render(): este botón abre una operación que mueve dinero (fondo,
  // sucursal, turnos, re-foliado de tickets), así que no puede fiarse de un
  // `resumen` que quedó viejo — p. ej. tras un cambio de sucursal tan rápido
  // que cargarResumen() todavía no volvió, tendríamos `sucursalSel` apuntando
  // a una sucursal y `resumen` describiendo otra.
  if (!resumen || !resumen.puede_corregir_dia) return;

  // Arranca con el fondo vigente, no en blanco: casi siempre se corrige a
  // partir de lo que ya se declaró, no desde cero.
  document.getElementById('f-corregir-fondo').value =
    Number(resumen.fondo_inicial || 0) !== 0 ? String(resumen.fondo_inicial) : '';

  // El campo de sucursal solo aparece con dos o más: con una no hay a dónde
  // mover, y ofrecerlo sería otro hueco por el que equivocarse.
  const wrap = document.getElementById('wrap-corregir-sucursal');
  wrap.style.display = resumen.puede_mover_sucursal ? '' : 'none';
  if (resumen.puede_mover_sucursal) {
    populateSelect(document.getElementById('f-corregir-sucursal'),
      sucursales.map(s => ({ value: String(s.id), label: s.nombre })),
      resumen.sucursal_id ? String(resumen.sucursal_id) : '',
      // El placeholder que crea populateSelect nace `disabled`, así que "Sin
      // sucursal" se puede LEER (es lo que aparece cuando el día en curso es el
      // cubo de los huérfanos) pero no se puede ELEGIR: mover una caja hacia
      // ningún lado es exactamente el estado que este trabajo vino a cerrar.
      // El camino sí existe al revés — desde "Sin sucursal" hacia una real —, y
      // es cómo el admin rescata los movimientos viejos que quedaron sueltos.
      'Sin sucursal');
  }

  document.getElementById('error-corregir-dia').style.display = 'none';
  Modal.open('modal-corregir-dia');
}

async function guardarCorreccionDia() {
  const err = document.getElementById('error-corregir-dia');
  const monto = CorteUX.normalizarMonto(
    document.getElementById('f-corregir-fondo').value);
  if (monto === null || monto < 0) {
    err.textContent = 'El fondo inicial no es un monto válido';
    err.style.display = '';
    return;
  }

  const destino = resumen.puede_mover_sucursal
    ? (Number(document.getElementById('f-corregir-sucursal').value) || null)
    : null;

  const btn = document.getElementById('btn-confirmar-corregir');
  const texto = document.getElementById('texto-confirmar-corregir');
  btn.disabled = true; texto.textContent = 'Guardando...';
  try {
    await API.patch('/caja/dia', {
      fondo_inicial: monto,
      sucursal_id: sucursalSel || null,
      sucursal_destino_id: destino,
    });
    Modal.close('modal-corregir-dia');
    Toast.success('Caja corregida');
    // Si la caja se mudó, la pantalla tiene que seguirla: quedarse en la
    // sucursal vieja mostraría el día que acaba de vaciarse.
    if (destino !== null && String(destino) !== String(sucursalSel || '')) {
      sucursalSel = String(destino);
      const sel = document.getElementById('sel-sucursal');
      if (sel) sel.value = sucursalSel;
    }
    // Recargar y no parchear el objeto en memoria: el fondo mueve el esperado
    // y la mudanza mueve los totales enteros.
    await cargarResumen();
    if (userRole === 'admin') cargarHistorico();
  } catch (e) {
    err.textContent = e.message || 'No se pudo corregir la caja';
    err.style.display = '';
  } finally {
    btn.disabled = false; texto.textContent = 'Guardar';
  }
}

// El botón "Cerrar caja" no cierra directo: abre el modal de confirmación
// con la foto de esperado/contado/diferencia, y ese modal es el que llama
// a confirmarCierre().
function abrirConfirmarCierre() {
  const contadoTexto = document.getElementById('f-contado').value;
  const contado = CorteUX.normalizarMonto(contadoTexto);
  const dif = CorteUX.diferencia(resumen, contadoTexto);
  document.getElementById('confirmar-salidas').textContent = fmt(resumen.salidas_efectivo);
  document.getElementById('confirmar-pagos-doctores').textContent = fmt(resumen.pagos_doctores_efectivo);
  document.getElementById('confirmar-esperado').textContent = fmt(resumen.esperado_efectivo);
  document.getElementById('confirmar-contado').textContent = fmt(contado);
  const el = document.getElementById('confirmar-diferencia');
  if (dif === null) {
    el.textContent = '';
    el.className = 'font-medium tabular-nums';
  } else {
    const info = CorteUX.etiquetaDiferencia(dif);
    el.textContent = info.texto;
    el.className = 'font-medium tabular-nums ' + info.clase;
  }
  Modal.open('modal-confirmar-cierre');
}

async function confirmarCierre() {
  const contado = CorteUX.normalizarMonto(document.getElementById('f-contado').value);
  const comentario = document.getElementById('f-comentario').value.trim();
  // Se deshabilita mientras corre, igual que confirmarEliminarSalida(): con
  // `sucursal_id` nulo —el default de casi todo tenant— el índice UNIQUE no
  // ataja el duplicado, así que un doble clic sobre una respuesta lenta dejaría
  // dos cortes firmados del mismo día y el histórico perdería uno.
  const btn = document.getElementById('btn-confirmar-cierre');
  const txt = document.getElementById('texto-confirmar-cierre');
  btn.disabled = true;
  txt.textContent = 'Cerrando...';
  try {
    await API.post('/caja/corte', {
      fecha: todayLocalISO(), sucursal_id: sucursalSel || null,
      efectivo_contado: contado, comentario: comentario || null,
    });
    Modal.close('modal-confirmar-cierre');
    Toast.success('Caja cerrada');
    await cargarResumen();
  } catch (e) {
    // El servidor es la fuente de verdad: si rechaza, se muestra su motivo.
    Toast.warning(e.message || 'No se pudo cerrar la caja');
  } finally {
    btn.disabled = false;
    txt.textContent = 'Confirmar cierre';
  }
}

async function imprimirComprobante() {
  try {
    await PrintAgent.print(construirTicketCorte(resumen));
  } catch (e) {
    Toast.warning('No se pudo imprimir (¿agente de impresión encendido?)');
  }
}

// Mismo contrato que GET /facturacion/ingresos/<id>/ticket-simple
// (app/facturacion/routes.py:450-462), que el agente de impresión ya sabe
// renderizar: {facturable, empresa, sucursal, fecha, conceptos:[{nombre,monto}], total}.
// No existe un endpoint de "ticket de corte" en el backend, así que el
// payload se arma aquí con las líneas del corte. Se omite la línea "Cerró:
// <nombre>" porque el formato del agente solo sabe pintar filas nombre→monto
// y un concepto en $0.00 se leería como un bug; ese dato ya está en el sello
// de la pantalla.
function construirTicketCorte(resumen) {
  const corte = resumen.corte || {};
  const suc = sucursales.find(s => String(s.id) === String(sucursalSel));
  // "Otro" solo si hubo: mismo criterio que #aviso-otro en la pantalla. Una
  // línea en $0.00 en un ticket de papel se lee como un bug.
  const otro = Number(resumen.totales.otro || 0);
  return {
    facturable: false,
    empresa: empresaNombre || '',
    sucursal: suc ? suc.nombre : null,
    fecha: resumen.fecha,
    conceptos: [
      { nombre: 'Efectivo', monto: resumen.totales.efectivo },
      { nombre: 'Tarjeta', monto: resumen.totales.tarjeta },
      { nombre: 'Transferencia', monto: resumen.totales.transferencia },
      ...(otro ? [{ nombre: 'Otro', monto: otro }] : []),
      { nombre: 'Salidas', monto: resumen.salidas_efectivo },
      // Solo si hubo: una línea en $0.00 en papel se lee como un bug.
      ...(Number(resumen.pagos_doctores_efectivo || 0)
        ? [{ nombre: 'Pagos a doctores', monto: resumen.pagos_doctores_efectivo }] : []),
      // Sin esta línea el papel firmado deja de cuadrar consigo mismo por
      // exactamente el monto del fondo: "Esperado" ya lo incluye. Va antes de
      // "Esperado" para que el ticket se pueda sumar de arriba abajo.
      ...(Number(resumen.fondo_inicial || 0)
        ? [{ nombre: 'Fondo inicial', monto: resumen.fondo_inicial }] : []),
      { nombre: 'Esperado', monto: resumen.esperado_efectivo },
      { nombre: 'Contado', monto: corte.efectivo_contado != null ? corte.efectivo_contado : 0 },
      { nombre: 'Diferencia', monto: corte.diferencia != null ? corte.diferencia : 0 },
    ],
    total: resumen.esperado_efectivo,
  };
}

// ── Vista de administración: histórico, detalle y reapertura ────────────────
// Etiquetas legibles de app/caja/models.py (EVENTO_CIERRE / RECIERRE / REAPERTURA).
const ETIQUETAS_EVENTO = {
  cierre: 'Cierre', recierre: 'Recierre', reapertura: 'Reapertura',
};

async function cargarHistorico() {
  const params = new URLSearchParams({
    desde: document.getElementById('f-desde').value,
    hasta: document.getElementById('f-hasta').value,
  });
  if (sucursalSel) params.set('sucursal_id', sucursalSel);
  let data;
  try {
    data = await API.get('/caja/cortes?' + params.toString());
  } catch (e) {
    // Mismo criterio que cargarResumen(): un histórico que no carga tiene que
    // decirlo, no quedarse en blanco en silencio — y sobre todo, un 403 (rol
    // sin permiso) o un 500 aquí no debe tumbar init() y con él la vista de
    // recepción, que sí le toca ver a este usuario.
    Toast.error('No se pudo cargar el histórico de cortes');
    return;
  }
  renderHistorico(data.cortes);
}

function nombreSucursal(id) {
  if (!id) return 'Sin sucursal';
  const s = sucursales.find(x => String(x.id) === String(id));
  return s ? s.nombre : 'Sin sucursal';
}

function renderHistorico(filas) {
  const cols = [
    // renderTable NO tiene onRowClick: el detalle se abre con un botón propio,
    // igual que el botón de comentario en app/templates/edr/ingresos.html.
    { key: 'corte_id', label: '', render: (v, row) => {
        const acciones = domEl('div', 'flex items-center gap-1');

        const btn = domEl('button', 'shrink-0 rounded p-1.5 text-primary-600 hover:text-primary-700 transition-colors cursor-pointer');
        btn.type = 'button';
        btn.setAttribute('aria-label', 'Ver detalle del corte');
        btn.appendChild(domIcon('eye', 'h-4 w-4'));
        btn.addEventListener('click', () => abrirDetalle(row));
        acciones.appendChild(btn);

        // Un día que quedó abierto no se puede cerrar desde ningún otro lado:
        // la cara de recepción solo habla de hoy. Sin este botón, los días
        // pasados se quedan abiertos para siempre.
        if (row.estado === 'sin_cerrar') {
          const cerrar = domEl('button', 'shrink-0 rounded p-1.5 text-warning-600 hover:text-warning-500 transition-colors cursor-pointer');
          cerrar.type = 'button';
          cerrar.setAttribute('aria-label', 'Cerrar la caja de este día');
          cerrar.title = 'Cerrar la caja de este día';
          cerrar.appendChild(domIcon('lock', 'h-4 w-4'));
          cerrar.addEventListener('click', () => abrirCierreDia(row));
          acciones.appendChild(cerrar);
        }
        return acciones;
      } },
    { key: 'fecha', label: 'Fecha', render: v => formatDate(v) },
    { key: 'sucursal_id', label: 'Sucursal', render: v => nombreSucursal(v) },
    { key: 'total_efectivo', label: 'Efectivo', align: 'right', render: v => fmt(v) },
    { key: 'total_tarjeta', label: 'Tarjeta', align: 'right', render: v => fmt(v) },
    { key: 'total_transferencia', label: 'Transfer.', align: 'right', render: v => fmt(v) },
    { key: 'total_dia', label: 'Total', align: 'right', render: v => fmt(v) },
    // Ingresos del día sin método de pago. Es el único lugar donde el admin
    // los ve: bloquean el cierre, y si entran DESPUÉS de cerrar no mueven
    // ninguno de los seis totales congelados, así que ni siquiera disparan la
    // marca de "movimientos posteriores". Va como columna y no dentro del
    // texto de Estado porque es un importe y se escanea con los demás.
    { key: 'sin_clasificar_monto', label: 'Sin método', align: 'right',
      render: v => v
        ? domEl('span', 'tabular-nums font-medium text-danger-600', fmt(v))
        : domEl('span', 'text-text-muted', '—') },
    { key: 'salidas_efectivo', label: 'Gastos', align: 'right', render: v => fmt(v) },
    { key: 'pagos_doctores_efectivo', label: 'Pagos dr.', align: 'right', render: v => fmt(v) },
    { key: 'esperado_efectivo', label: 'Esperado', align: 'right', render: v => fmt(v) },
    { key: 'efectivo_contado', label: 'Contado', align: 'right',
      render: v => v === null ? '—' : fmt(v) },
    { key: 'diferencia', label: 'Diferencia', align: 'right', render: v => {
        if (v === null) return domEl('span', 'text-text-muted', '—');
        const info = CorteUX.etiquetaDiferencia(v);
        return domEl('span', 'tabular-nums font-medium ' + info.clase, fmt(v));
      } },
    { key: 'estado', label: 'Estado', render: (v, row) => {
        if (v === 'sin_cerrar') return domEl('span', 'text-warning-600', 'Sin cerrar');
        if (row.movimientos_posteriores) {
          // La foto firmada ya no coincide con lo capturado: hay que decirlo.
          return domEl('span', 'text-warning-600',
                       'Cerrado · movimientos posteriores');
        }
        return domEl('span', 'text-accent-700', 'Cerrado');
      } },
    { key: 'cerrado_por', label: 'Cerró', render: v => v || '—' },
  ];

  // Firma real (app/static/js/app.js:693):
  //   renderTable(containerId, columns, data, emptyMessage, loading, options)
  // Argumentos POSICIONALES, containerId es un string, y las columnas van
  // ANTES que los datos. No recibe un elemento ni un objeto de opciones al final.
  renderTable('tabla-historico', cols, filas, 'No hay movimientos en este rango',
    false, {
      // Un día que nadie cerró es la señal más útil del reporte: se ve de lejos.
      rowClass: row => {
        if (row.estado === 'sin_cerrar') return 'bg-warning-50';
        if (row.diferencia !== null && row.diferencia < 0) return 'bg-danger-50';
        if (row.diferencia) return 'bg-warning-50';
        return '';
      },
    });
  lucide.createIcons();
}

let detalleActual = null;

async function abrirDetalle(row) {
  if (!row.corte_id) {
    // Día sin cerrar: no hay corte que detallar todavía.
    Toast.warning('Ese día todavía no tiene corte cerrado');
    return;
  }
  detalleActual = await API.get('/caja/cortes/' + row.corte_id);
  renderDetalle(detalleActual);
  Modal.open('modal-detalle');
}

// Llena #detalle-cuerpo con la foto firmada del corte, lo que hay hoy
// (ingresos/salidas recalculados) y la bitácora de eventos.
function renderDetalle(data) {
  const c = data.corte;

  // Aviso de movimientos posteriores: la foto firmada ya no coincide con lo
  // capturado después del cierre (alguien registró algo sobre el día cerrado).
  const aviso = document.getElementById('detalle-aviso');
  aviso.classList.toggle('hidden', !data.movimientos_posteriores);
  if (data.movimientos_posteriores) {
    aviso.textContent = 'Hay movimientos posteriores al cierre: el efectivo '
      + 'esperado hoy difiere de la foto firmada por ' + fmt(data.delta_efectivo) + '.';
  }

  // Totales de la foto firmada al cerrar (no se recalculan aquí).
  const filas = [
    ['Efectivo', c.total_efectivo], ['Tarjeta', c.total_tarjeta],
    ['Transferencia', c.total_transferencia], ['Otro', c.total_otro],
    ['Comisión bancaria', c.comision_tarjeta], ['Neto al banco', c.neto_tarjeta],
    ['Total del día', c.total_dia], ['Salidas', c.salidas_efectivo],
    ['Pagos a doctores', c.pagos_doctores_efectivo],
    ['Esperado', c.esperado_efectivo], ['Contado', c.efectivo_contado],
    ['Diferencia', c.diferencia],
  ];
  const totalesEl = document.getElementById('detalle-totales');
  totalesEl.replaceChildren();
  filas.forEach(([label, valor]) => {
    const row = domEl('div', 'flex items-center justify-between px-4 py-2.5');
    row.appendChild(domEl('span', 'text-text-secondary', label));
    row.appendChild(domEl('span', 'font-medium tabular-nums', valor == null ? '—' : fmt(valor)));
    totalesEl.appendChild(row);
  });
  if (c.comentario) {
    const row = domEl('div', 'px-4 py-2.5 text-text-secondary');
    const strong = domEl('span', 'font-medium', 'Comentario: ');
    row.appendChild(strong);
    row.appendChild(document.createTextNode(c.comentario));
    totalesEl.appendChild(row);
  }

  // Ingresos y salidas recalculados de hoy (no la foto): así se ve lo mismo
  // que compara `movimientos_posteriores`.
  renderTable('detalle-ingresos', [
    { key: 'paciente', label: 'Paciente', render: v => v || '—' },
    { key: 'concepto', label: 'Concepto', render: v => v || '—' },
    { key: 'metodo', label: 'Método', render: v => v || domEl('span', 'text-warning-600', 'Sin método') },
    { key: 'monto', label: 'Monto', align: 'right', render: v => fmt(v) },
  ], data.ingresos || [], 'Sin ingresos ese día', false);

  renderTable('detalle-salidas', [
    { key: 'concepto', label: 'Concepto' },
    { key: 'monto', label: 'Monto', align: 'right', render: v => fmt(v) },
  ], data.salidas || [], 'Sin salidas ese día', false);

  renderTable('detalle-pagos-doctores', [
    { key: 'especialista_nombre', label: 'Doctor' },
    { key: 'concepto', label: 'Concepto', render: v => v || '—' },
    { key: 'monto', label: 'Monto', align: 'right', render: v => fmt(v) },
  ], data.pagos_doctores || [], 'Sin pagos a doctores ese día', false);

  // Bitácora: más reciente primero.
  const eventosEl = document.getElementById('detalle-eventos');
  eventosEl.replaceChildren();
  const eventos = data.eventos || [];
  if (!eventos.length) {
    eventosEl.appendChild(domEl('li', 'text-text-muted', 'Sin eventos registrados'));
  } else {
    eventos.slice().reverse().forEach(ev => {
      let linea = (ETIQUETAS_EVENTO[ev.evento] || ev.evento) + ' — ' + (ev.usuario || '—');
      if (ev.created_at) linea += ' · ' + formatDate(ev.created_at);
      if (ev.motivo) linea += ' · ' + ev.motivo;
      eventosEl.appendChild(domEl('li', '', linea));
    });
  }

  // `hidden` compite con `inline-flex` (ya en el markup de #btn-reabrir) y
  // pierde la cascada del JIT de Tailwind si `hidden` no estaba en el marcado
  // que el compilador escaneó al cargar — mismo problema que btn-nueva-salida
  // en renderCierre(), documentado ahí. Se usa `style.display` por la misma
  // razón: no compite con ninguna clase, así que siempre gana.
  const btnReabrir = document.getElementById('btn-reabrir');
  btnReabrir.style.display = c.cerrado ? '' : 'none';

  lucide.createIcons();
}

function abrirReabrir() {
  document.getElementById('f-motivo').value = '';
  Modal.open('modal-reabrir');
}

async function confirmarReapertura() {
  const motivo = document.getElementById('f-motivo').value.trim();
  if (!motivo) { Toast.warning('Escribe el motivo de la reapertura'); return; }
  try {
    await API.post('/caja/reabrir/' + detalleActual.corte.id, { motivo });
    Modal.close('modal-reabrir');
    Modal.close('modal-detalle');
    Toast.success('Corte reabierto');
    await cargarHistorico();
  } catch (e) {
    Toast.warning(e.message || 'No se pudo reabrir el corte');
  }
}

// ── Cerrar un día pasado desde el histórico ──────────────────────────────────
// El resumen NO se arma con los datos de la fila: se pide el mismo
// GET /caja/corte que usa la cara de recepción. La fila del histórico no trae
// `tolerancia` y su `sin_clasificar` es un importe, no la lista que espera
// CorteUX; y sobre todo, así las dos pantallas cierran con las mismas reglas y
// no pueden separarse con el tiempo.
let cierreDia = null;   // { fecha, sucursal_id, resumen }

async function abrirCierreDia(row) {
  try {
    const params = new URLSearchParams({ fecha: row.fecha });
    if (row.sucursal_id) params.set('sucursal_id', row.sucursal_id);
    const resumenDia = await API.get('/caja/corte?' + params.toString());
    cierreDia = { fecha: row.fecha, sucursal_id: row.sucursal_id, resumen: resumenDia };
  } catch (e) {
    Toast.error('No se pudo cargar el día que quieres cerrar');
    return;
  }

  document.getElementById('cerrar-dia-titulo').textContent =
    formatDate(cierreDia.fecha) + ' · ' + nombreSucursal(cierreDia.sucursal_id);
  document.getElementById('cerrar-dia-esperado').textContent =
    fmt(cierreDia.resumen.esperado_efectivo);
  document.getElementById('f-contado-dia').value = '';
  document.getElementById('f-comentario-dia').value = '';
  renderEstadoCierreDia();
  Modal.open('modal-cerrar-dia');
}

function renderEstadoCierreDia() {
  if (!cierreDia) return;
  const contado = document.getElementById('f-contado-dia').value;
  const comentario = document.getElementById('f-comentario-dia').value;
  const veredicto = CorteUX.puedeCerrar(cierreDia.resumen, contado, comentario);

  document.getElementById('wrap-comentario-dia').classList.toggle(
    'hidden', !CorteUX.excedeTolerancia(cierreDia.resumen, contado));

  const btn = document.getElementById('btn-confirmar-cierre-dia');
  btn.disabled = !veredicto.ok;
  document.getElementById('cerrar-dia-motivo').textContent = veredicto.motivo || '';

  const dif = CorteUX.diferencia(cierreDia.resumen, contado);
  const et = document.getElementById('cerrar-dia-etiqueta');
  if (dif === null) { et.textContent = ''; et.className = 'mt-1 text-sm font-medium font-body'; return; }
  const info = CorteUX.etiquetaDiferencia(dif);
  et.textContent = info.texto;
  et.className = 'mt-1 text-sm font-medium font-body ' + info.clase;
}

['f-contado-dia', 'f-comentario-dia'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderEstadoCierreDia));

async function confirmarCierreDia() {
  if (!cierreDia) return;
  const btn = document.getElementById('btn-confirmar-cierre-dia');
  const texto = document.getElementById('texto-confirmar-cierre-dia');
  btn.disabled = true;
  texto.textContent = 'Cerrando...';
  try {
    await API.post('/caja/corte', {
      fecha: cierreDia.fecha,
      sucursal_id: cierreDia.sucursal_id || null,
      efectivo_contado: CorteUX.normalizarMonto(document.getElementById('f-contado-dia').value),
      comentario: document.getElementById('f-comentario-dia').value.trim() || null,
    });
    Modal.close('modal-cerrar-dia');
    Toast.success('Caja del ' + formatDate(cierreDia.fecha) + ' cerrada');
    await cargarHistorico();
    // Si resultó ser el día de hoy, la cara de recepción también cambió.
    if (cierreDia.fecha === todayLocalISO()) await cargarResumen();
  } catch (e) {
    Toast.warning(e.message || 'No se pudo cerrar la caja de ese día');
  } finally {
    btn.disabled = false;
    texto.textContent = 'Cerrar caja';
  }
}

// ── Pestañas (solo admin) ────────────────────────────────────────────────────
// Mismo patrón que app/static/js/admin/admin_tenant_detail.js. Los dos paneles
// declaran `hidden` en el marcado inicial, así que `classList.toggle('hidden')`
// sí gana la cascada del JIT de Tailwind (una clase agregada por JS pierde
// contra una utilidad de display que ya estaba; aquí no hay ninguna).
function activarPestana(nombre) {
  document.querySelectorAll('.tab-caja').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === nombre));
  document.querySelectorAll('[data-panel]').forEach(p =>
    p.classList.toggle('hidden', p.dataset.panel !== nombre));
}

async function init() {
  // Red de última instancia: cargarResumen() y cargarHistorico() ya son
  // defensivas (try/catch propio, nunca rechazan), así que hoy nada dentro de
  // este cuerpo debería llegar aquí. Se deja de todos modos para que un
  // `await` futuro que alguien agregue sin copiar ese patrón no vuelva a dejar
  // la página a medio revelar en silencio, como pasó antes de este arreglo.
  try {
    const [me, sucs] = await Promise.allSettled([
      API.get('/auth/me'), API.get('/facturacion/sucursales'),
    ]);
    const user = (me.status === 'fulfilled' ? (me.value.user || me.value) : {}) || {};
    userRole = user.role || null;
    empresaNombre = (user.tenant && user.tenant.name) || '';
    sucursales = sucs.status === 'fulfilled' ? (sucs.value || []) : [];

    // Con una sola sucursal (o ninguna) el selector estorba: no se muestra.
    if (sucursales.length >= 2) {
      document.getElementById('wrap-sucursal').classList.remove('hidden');
      // Preseleccionar la primera sucursal y NO el placeholder "Sin sucursal":
      // desde el candado de sucursal obligatoria (2026-08-26) ya no nace ningún
      // turno con sucursal_id NULL, así que arrancar en ese cubo le mostraba al
      // admin $0.00 en todas las tarjetas y el aviso de caja abierta no podía
      // encenderse nunca — cargarResumen() pedía el corte de un cubo donde ya
      // no vive nadie. Se fija ANTES de la primera cargarResumen() (al final de
      // init()) para que esa primera carga no repita el mismo hueco.
      sucursalSel = String(sucursales[0].id);
      populateSelect(document.getElementById('sel-sucursal'),
        sucursales.map(s => ({ value: String(s.id), label: s.nombre })),
        sucursalSel, 'Sin sucursal');
      document.getElementById('sel-sucursal').addEventListener('change', e => {
        sucursalSel = e.target.value || null;
        cargarResumen();
        // El histórico de /caja/cortes es admin-only en el backend (403 para
        // cualquier otro rol, incluido asistente); solo se pide aquí para admin.
        if (userRole === 'admin') cargarHistorico();
      });
    }

    // Fail-closed: las dos vistas parten ocultas y se revela la que toca.
    document.getElementById('vista-recepcion').classList.remove('hidden');

    document.getElementById('form-salida').addEventListener('submit', guardarSalida);
    document.getElementById('btn-confirmar-eliminar-pago')
      .addEventListener('click', confirmarEliminarPago);
    engancharPagoDoctor();

    // Corrección de la caja del día. Los listeners se enganchan siempre; quien
    // no puede corregir nunca ve el botón (`puede_corregir_dia`, en render()).
    document.getElementById('btn-corregir-dia').addEventListener('click', abrirCorregirDia);
    document.getElementById('btn-confirmar-corregir').addEventListener('click', guardarCorreccionDia);
    ['btn-cancelar-corregir', 'btn-cerrar-corregir', 'backdrop-corregir'].forEach(id =>
      document.getElementById(id).addEventListener(
        'click', () => Modal.close('modal-corregir-dia')));
    // OJO: NO es "distinto de recepcionista". Un asistente con el permiso
    // `caja` también llega a esta página (ver NAV_POR_RECURSO en app.js) y
    // puede cerrar caja como la vista de recepción, pero /caja/cortes,
    // /caja/cortes/<id> y /caja/reabrir/<id> son @require_role("admin") en el
    // backend (ver app/caja/routes.py) — ofrecerle el histórico a un
    // asistente solo produce 403 en la primera llamada. La vista de
    // recepción de arriba SÍ es para ambos roles.
    if (userRole === 'admin') {
      document.getElementById('vista-admin').classList.remove('hidden');

      // Las dos caras pasan a ser pestañas: el histórico vivía al fondo y el
      // admin bajaba dos pantallas y media para llegar. La recepcionista no ve
      // la barra —solo tiene una cara— y su página queda igual que siempre.
      document.getElementById('tabs-admin').classList.remove('hidden');
      document.querySelectorAll('.tab-caja').forEach(b =>
        b.addEventListener('click', () => activarPestana(b.dataset.tab)));
      activarPestana('hoy');

      // Rango por defecto: del día 1 del mes actual a hoy.
      const hoy = todayLocalISO();
      document.getElementById('f-desde').value = hoy.slice(0, 8) + '01';
      document.getElementById('f-hasta').value = hoy;
      document.getElementById('f-desde').addEventListener('change', cargarHistorico);
      document.getElementById('f-hasta').addEventListener('change', cargarHistorico);

      await cargarHistorico();
    }

    // El turno va antes del resumen: si no hay caja abierta, el modal se abre
    // solo y abrirla recarga el resumen (el fondo cambia el "a entregar").
    // Se le pasan el rol y las sucursales ya resueltos arriba para no volver a
    // pedir /auth/me ni /facturacion/sucursales.
    await TurnoCaja.iniciar({
      rol: userRole, sucursales: sucursales, alAbrir: cargarResumen,
      // La cara roja del botón lleva aquí. No puede caer en un 409: el rojo
      // implica turno vivo y día abierto, que son dos de las tres condiciones de
      // `puede_corregir_dia`, y la tercera (`fecha == hoy`) siempre se cumple en
      // esta pantalla, que solo mira el día en curso.
      alCorregir: abrirCorregirDia,
    });

    await cargarResumen();
  } catch (e) {
    console.error('corte-caja: init() falló', e);
    Toast.error('No se pudo cargar la página de corte de caja');
  }
}

init();
