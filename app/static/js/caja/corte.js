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
    return;
  }
  render();
}

function render() {
  document.getElementById('stat-efectivo').textContent = fmt(resumen.totales.efectivo);
  document.getElementById('stat-tarjeta').textContent = fmt(resumen.totales.tarjeta);
  document.getElementById('stat-tarjeta-neto').textContent =
    'Neto al banco: ' + fmt(resumen.neto_tarjeta);
  document.getElementById('stat-transferencia').textContent =
    fmt(resumen.totales.transferencia);
  document.getElementById('stat-salidas').textContent = fmt(resumen.salidas_efectivo);
  // `a_entregar` y NO `esperado_efectivo`: desde que el fondo entra en el
  // esperado (services.resumen_dia), el esperado incluye el fondo, y el fondo
  // se queda en el cajón para mañana. Lo que se entrega es lo otro.
  document.getElementById('stat-entregar').textContent = fmt(resumen.a_entregar);
  // La leyenda no cambia con el fondo a propósito: la resta que describe "a
  // entregar" es la misma (el fondo entra y sale). Lo que cambió es el dato de
  // arriba.
  document.getElementById('leyenda-entregar').textContent =
    'cobrado ' + fmt(resumen.totales.efectivo) + ' − gastado ' + fmt(resumen.salidas_efectivo);

  // El fondo solo se menciona cuando existe —en una caja sin fondo la línea
  // sería ruido permanente en la pantalla más usada—, salvo para quien puede
  // corregirlo: un fondo en cero es justo el caso que vino a arreglar.
  document.getElementById('leyenda-fondo').style.display =
    CorteUX.muestraLeyendaFondo(resumen) ? '' : 'none';
  document.getElementById('stat-fondo').textContent = fmt(resumen.fondo_inicial);
  // Quién puede corregir lo decide el servidor (`puede_editar_fondo`): repetir
  // aquí las tres condiciones sería una copia que se desincroniza a la primera.
  // `inline-flex` y no `''`: el botón nace con `display:none` en el marcado.
  document.getElementById('btn-editar-fondo').style.display =
    resumen.puede_editar_fondo ? 'inline-flex' : 'none';

  // "Otro" solo se asoma cuando hay algo que asomar (ver #aviso-otro en la
  // plantilla). `hidden` sí está en el marcado inicial de ese div y el div no
  // trae ninguna utilidad de display que le compita, así que el toggle basta
  // —medido con getComputedStyle: none → block al quitarla, none al reponerla—.
  const otro = Number(resumen.totales.otro || 0);
  document.getElementById('stat-otro').textContent = fmt(otro);
  document.getElementById('aviso-otro').classList.toggle('hidden', otro === 0);

  renderSinClasificar();
  renderSalidas();
  renderIngresos();
  renderEstadoCierre();
  renderCierre();
  lucide.createIcons();
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
      const btn = domEl('button', 'rounded-lg p-1.5 text-text-muted hover:bg-danger-50 hover:text-danger-600 transition-colors cursor-pointer');
      btn.type = 'button';
      btn.title = 'Eliminar salida';
      btn.setAttribute('aria-label', 'Eliminar salida');
      btn.appendChild(domIcon('trash-2'));
      btn.addEventListener('click', () => abrirEliminarSalida(id));
      return btn;
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

// Ingresos del día: solo lectura aquí, se editan desde /ingresos.
function renderIngresos() {
  const cols = [
    { key: 'paciente', label: 'Paciente', render: v => v || '—' },
    { key: 'concepto', label: 'Concepto', render: v => v || '—' },
    { key: 'metodo', label: 'Método', render: v => v || domEl('span', 'text-warning-600', 'Sin método') },
    { key: 'monto', label: 'Monto', align: 'right', render: v => domEl('span', 'tabular-nums font-medium', fmt(v)) },
  ];
  renderTable('tabla-ingresos', cols, resumen.ingresos || [], 'Sin ingresos registrados hoy', false);
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

  if (cerrado && resumen.corte) {
    const c = resumen.corte;
    document.getElementById('sello-texto').textContent =
      'Cerró: ' + (c.cerrado_por || '—') +
      (c.cerrado_at ? ' · ' + formatDate(c.cerrado_at) : '') +
      ' · Diferencia: ' + fmt(c.diferencia) +
      (c.comentario ? ' · ' + c.comentario : '');
  }
}

function abrirNuevaSalida() {
  document.getElementById('f-salida-concepto').value = '';
  document.getElementById('f-salida-monto').value = '';
  Modal.open('modal-salida');
}

async function guardarSalida() {
  const concepto = document.getElementById('f-salida-concepto').value.trim();
  const monto = CorteUX.normalizarMonto(document.getElementById('f-salida-monto').value);
  if (!concepto) { Toast.warning('Escribe de qué fue la salida'); return; }
  if (monto === null || monto === 0) { Toast.warning('El monto debe ser mayor a cero'); return; }
  try {
    await API.post('/caja/salidas', {
      fecha: todayLocalISO(), concepto_nombre: concepto, monto: monto,
      sucursal_id: sucursalSel || null,
    });
    Modal.close('modal-salida');
    await cargarResumen();
  } catch (e) {
    Toast.warning(e.message || 'No se pudo registrar la salida');
  }
}

function abrirEditarFondo() {
  // Arranca con el fondo vigente, no en blanco: casi siempre se corrige a
  // partir de lo que ya hay, y así el campo dice de dónde parte.
  document.getElementById('f-editar-fondo').value =
    Number(resumen.fondo_inicial || 0) !== 0 ? String(resumen.fondo_inicial) : '';
  document.getElementById('error-editar-fondo').style.display = 'none';
  Modal.open('modal-editar-fondo');
}

async function guardarFondo() {
  const err = document.getElementById('error-editar-fondo');
  const monto = CorteUX.normalizarMonto(document.getElementById('f-editar-fondo').value);
  if (monto === null) {
    // El error va dentro del modal y no en un toast: el dato malo está a la
    // vista, y el mensaje tiene que quedarse junto al campo que hay que
    // arreglar. Cero SÍ es válido — corregir a cero es una corrección legítima.
    err.textContent = 'Escribe un monto válido (0 o más)';
    err.style.display = '';
    return;
  }
  try {
    await API.patch('/caja/fondo', {
      fondo_inicial: monto, sucursal_id: sucursalSel || null,
    });
    Modal.close('modal-editar-fondo');
    Toast.success('Fondo inicial actualizado');
    // Recargar y no parchear el objeto en memoria: el fondo mueve el esperado
    // y la diferencia, y recalcularlos aquí sería duplicar `resumen_dia`.
    await cargarResumen();
  } catch (e) {
    err.textContent = e.message || 'No se pudo corregir el fondo';
    err.style.display = '';
  }
}

// El botón "Cerrar caja" no cierra directo: abre el modal de confirmación
// con la foto de esperado/contado/diferencia, y ese modal es el que llama
// a confirmarCierre().
function abrirConfirmarCierre() {
  const contadoTexto = document.getElementById('f-contado').value;
  const contado = CorteUX.normalizarMonto(contadoTexto);
  const dif = CorteUX.diferencia(resumen, contadoTexto);
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
      populateSelect(document.getElementById('sel-sucursal'),
        sucursales.map(s => ({ value: String(s.id), label: s.nombre })),
        '', 'Sin sucursal');
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

    // Corrección del fondo. Los listeners se enganchan siempre; quien no puede
    // corregir nunca ve el botón (`puede_editar_fondo`, en render()).
    document.getElementById('btn-editar-fondo').addEventListener('click', abrirEditarFondo);
    document.getElementById('btn-confirmar-fondo').addEventListener('click', guardarFondo);
    ['btn-cancelar-fondo', 'btn-cerrar-fondo', 'backdrop-fondo'].forEach(id =>
      document.getElementById(id).addEventListener(
        'click', () => Modal.close('modal-editar-fondo')));
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
    });

    await cargarResumen();
  } catch (e) {
    console.error('corte-caja: init() falló', e);
    Toast.error('No se pudo cargar la página de corte de caja');
  }
}

init();
