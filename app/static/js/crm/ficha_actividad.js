/* Pestaña "Actividad" de la ficha de paciente: chips de filtro, lista y detalle.
 * Requiere app.js (esc, fmt, formatDate, API, lucide). Lo usa ficha.js:
 *   FichaActividad.reiniciar()  al abrir otro paciente (limpia filtro, selección y caché)
 *   FichaActividad.pintar(items) cada vez que llega el timeline (conserva el filtro)
 */
const FichaActividad = (() => {
  const CHIPS = [
    { clave: 'todo',        etiqueta: 'Todo' },
    { clave: 'visita',      etiqueta: 'Visitas' },
    { clave: 'seguimiento', etiqueta: 'Seguimientos' },
    { clave: 'nota',        etiqueta: 'Notas' },
    { clave: 'cambios',     etiqueta: 'Cambios' },
  ];
  const SUBTIPOS = [
    { clave: 'llamada',  etiqueta: 'Llamada' },
    { clave: 'whatsapp', etiqueta: 'WhatsApp' },
    { clave: 'otro',     etiqueta: 'Otro' },
  ];
  const ETIQUETA_SUBTIPO = { llamada: 'Llamada', whatsapp: 'WhatsApp', otro: 'Otro' };
  const ICONO_SUBTIPO = { llamada: 'phone', whatsapp: 'message-circle', otro: 'bell' };
  const ICONOS = {
    visita: 'calendar-check', nota: 'sticky-note', cambio_estatus: 'shuffle', expediente: 'folder',
  };
  const FONDO_ICONO = {
    visita: 'bg-primary-50 text-primary-600',
    seguimiento: 'bg-warning-100 text-warning-700',
    nota: 'bg-accent-50 text-accent-600',
    cambio_estatus: 'bg-surface-hover text-text-secondary',
    expediente: 'bg-surface-hover text-text-secondary',
  };

  let items = [];
  let filtro = 'todo';
  let subtipos = new Set();     // vacío = todos los tipos de seguimiento
  let soloPendientes = false;
  let sel = null;               // { tipo, id }
  let verDetalle = false;       // en móvil: true = se ve el detalle en vez de la lista
  let cacheVisitas = new Map(); // id → detalle de /crm/visitas/<id>

  const $ = (id) => document.getElementById(id);

  // ── Helpers ────────────────────────────────────────────────────────────────
  function grupoDe(t) {
    return (t.tipo === 'cambio_estatus' || t.tipo === 'expediente') ? 'cambios' : t.tipo;
  }

  function pendiente(t) {
    return t.tipo === 'seguimiento' && t.completado === false;
  }

  function coincide(t) {
    if (filtro === 'todo') return true;
    if (grupoDe(t) !== filtro) return false;
    if (filtro === 'seguimiento') {
      if (subtipos.size && !subtipos.has(t.tipo_seguimiento)) return false;
      if (soloPendientes && !pendiente(t)) return false;
    }
    return true;
  }

  function esSel(t) {
    return !!sel && sel.tipo === t.tipo && sel.id === t.id;
  }

  // Los timestamps llegan en UTC sin zona: se marcan como UTC antes de parsear.
  function fechaHora(iso) {
    if (!iso) return '';
    const s = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + 'Z';
    const d = new Date(s);
    if (isNaN(d)) return '';
    return d.toLocaleString('es-MX', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  function titulo(t) {
    if (t.tipo === 'visita') {
      return t.detalle && t.detalle !== 'Visita' ? `Visita · ${t.detalle}` : 'Visita';
    }
    if (t.tipo === 'seguimiento') {
      const tipo = ETIQUETA_SUBTIPO[t.tipo_seguimiento] || 'Seguimiento';
      return t.notas ? `${tipo} · ${t.notas}` : tipo;
    }
    return t.detalle || '';
  }

  function meta(t) {
    const partes = [formatDate(t.fecha)];
    if (t.tipo === 'visita') {
      if (t.total != null) partes.push(fmt(t.total));
      else partes.push(t.cobrada ? 'cobrada' : 'sin cobro');
    } else if (t.tipo === 'seguimiento') {
      partes.push(pendiente(t) ? 'pendiente' : 'completado');
    } else if (t.autor) {
      partes.push(t.autor);
    }
    return partes.filter(Boolean).join(' · ');
  }

  function icono(t) {
    if (t.tipo === 'seguimiento') return ICONO_SUBTIPO[t.tipo_seguimiento] || 'phone';
    return ICONOS[t.tipo] || 'circle';
  }

  function chipHTML(accion, valor, etiqueta, activo, conteo, sub) {
    const base = 'inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium font-body cursor-pointer transition-colors duration-200';
    const estilo = activo
      ? 'bg-primary-600 border-primary-600 text-white'
      : `bg-surface ${sub ? 'border-dashed border-border-strong' : 'border-border'} text-text-secondary hover:bg-surface-hover`;
    const num = conteo == null ? '' :
      `<span class="${activo ? 'text-primary-100' : 'text-text-muted'}">${esc(conteo)}</span>`;
    return `<button type="button" data-accion="${esc(accion)}" data-valor="${esc(valor)}"
              aria-pressed="${activo ? 'true' : 'false'}" class="${base} ${estilo}">${esc(etiqueta)} ${num}</button>`;
  }

  // ── Pintado ────────────────────────────────────────────────────────────────
  function pintarFiltros() {
    const cont = $('fp-filtros');
    if (!cont) return;
    if (!items.length) { cont.innerHTML = ''; return; }
    const conteo = { todo: items.length, visita: 0, seguimiento: 0, nota: 0, cambios: 0 };
    items.forEach(t => { const g = grupoDe(t); if (g in conteo) conteo[g] += 1; });

    let html = `<div class="flex flex-wrap gap-1.5">${
      CHIPS.map(c => chipHTML('filtro', c.clave, c.etiqueta, filtro === c.clave, conteo[c.clave], false)).join('')
    }</div>`;

    if (filtro === 'seguimiento') {
      const segs = items.filter(t => t.tipo === 'seguimiento');
      const porTipo = {};
      segs.forEach(t => { porTipo[t.tipo_seguimiento] = (porTipo[t.tipo_seguimiento] || 0) + 1; });
      html += `<div class="flex flex-wrap items-center gap-1.5">${
        SUBTIPOS.map(s => chipHTML('subtipo', s.clave, s.etiqueta, subtipos.has(s.clave), porTipo[s.clave] || 0, true)).join('')
      }<span class="text-text-muted text-xs px-0.5">·</span>${
        chipHTML('pendientes', '1', 'Solo pendientes', soloPendientes, segs.filter(pendiente).length, true)
      }</div>`;
    }
    cont.innerHTML = html;
  }

  function pintarLista() {
    const cont = $('fp-timeline');
    if (!cont) return;
    if (!items.length) {
      cont.innerHTML = '<p class="text-xs text-text-muted font-body py-2">Sin actividad todavía.</p>';
      return;
    }
    const visibles = items.filter(coincide);
    if (!visibles.length) {
      cont.innerHTML = '<p class="text-xs text-text-muted font-body py-2">No hay eventos con este filtro</p>';
      return;
    }
    cont.innerHTML = visibles.map(t => {
      const activo = esSel(t);
      const fondo = pendiente(t) ? 'bg-warning-50' : 'bg-surface';
      const borde = activo
        ? 'border-primary-500 ring-2 ring-primary-200'
        : 'border-border hover:border-border-strong';
      // La fila no es un <button>: un seguimiento pendiente lleva además su botón
      // "Completar" y un botón dentro de otro no es HTML válido ni accesible.
      const completar = pendiente(t)
        ? `<button type="button" data-completar="${esc(t.id)}" title="Marcar como completado"
                   class="shrink-0 self-center inline-flex items-center gap-1 rounded-md bg-primary-500 hover:bg-primary-600 text-white px-2 py-1 text-[11px] font-medium cursor-pointer transition-colors duration-200">
             <i data-lucide="check" class="h-3 w-3"></i> Completar</button>`
        : '';
      return `
        <div class="flex items-stretch gap-2 rounded-lg border ${borde} ${fondo} p-2.5 transition-colors duration-200">
          <button type="button" data-tipo="${esc(t.tipo)}" data-id="${esc(t.id)}" aria-current="${activo ? 'true' : 'false'}"
                  class="flex-1 min-w-0 text-left flex items-start gap-2.5 cursor-pointer">
            <span class="h-7 w-7 shrink-0 rounded-md flex items-center justify-center ${FONDO_ICONO[t.tipo] || FONDO_ICONO.cambio_estatus}">
              <i data-lucide="${esc(icono(t))}" class="h-3.5 w-3.5"></i></span>
            <span class="flex-1 min-w-0">
              <span class="block text-xs font-body text-text-primary truncate">${esc(titulo(t))}</span>
              <span class="block text-[11px] text-text-muted font-body">${esc(meta(t))}</span>
            </span>
          </button>${completar}
        </div>`;
    }).join('');
  }

  function vacioDetalle() {
    return `<div class="flex flex-col items-center justify-center text-center py-10 text-text-muted">
              <i data-lucide="mouse-pointer-click" class="h-6 w-6 mb-2"></i>
              <p class="text-sm font-body">Selecciona un evento para ver su detalle.</p>
            </div>`;
  }

  function encabezadoDetalle(t, texto) {
    return `<h4 class="flex items-center gap-2 text-sm font-semibold font-heading text-text-primary mb-1">
              <span class="h-7 w-7 shrink-0 rounded-md flex items-center justify-center ${FONDO_ICONO[t.tipo] || FONDO_ICONO.cambio_estatus}">
                <i data-lucide="${esc(icono(t))}" class="h-3.5 w-3.5"></i></span>
              ${esc(texto)}</h4>`;
  }

  function lineaMeta(partes) {
    const txt = partes.filter(Boolean).join(' · ');
    return txt ? `<p class="text-xs text-text-muted font-body">${esc(txt)}</p>` : '';
  }

  function detalleSeguimiento(t) {
    const tipo = ETIQUETA_SUBTIPO[t.tipo_seguimiento];
    const tituloTxt = t.tipo_seguimiento === 'otro' || !tipo
      ? 'Seguimiento' : `Seguimiento por ${tipo === 'Llamada' ? 'llamada' : tipo}`;
    const estado = pendiente(t)
      ? `<button type="button" data-completar="${esc(t.id)}"
                 class="inline-flex items-center gap-1.5 rounded-lg bg-primary-500 hover:bg-primary-600 text-white px-3 py-1.5 text-xs font-medium cursor-pointer transition-colors duration-200">
           <i data-lucide="check" class="h-3.5 w-3.5"></i> Marcar completado</button>`
      : `<p class="inline-flex items-center gap-1.5 rounded-full bg-accent-50 text-accent-700 px-2.5 py-0.5 text-xs font-medium">
           <i data-lucide="check-circle" class="h-3.5 w-3.5"></i>
           Completado${t.fecha_completado ? ` el ${esc(formatDate(t.fecha_completado))}` : ''}</p>`;
    return `
      ${encabezadoDetalle(t, tituloTxt)}
      ${lineaMeta([`Programado para ${formatDate(t.fecha)}`, t.autor ? `por ${t.autor}` : null])}
      <p class="my-3 text-sm text-text-primary whitespace-pre-wrap break-words">${t.notas ? esc(t.notas) : '<span class="text-text-muted">Sin notas.</span>'}</p>
      ${estado}`;
  }

  function detalleSimple(t, tituloTxt) {
    return `
      ${encabezadoDetalle(t, tituloTxt)}
      ${lineaMeta([fechaHora(t.fecha_hora) || formatDate(t.fecha), t.autor ? `por ${t.autor}` : null])}
      <p class="mt-3 text-sm text-text-primary whitespace-pre-wrap break-words">${esc(t.detalle)}</p>`;
  }

  function detalleVisitaBase(t, cuerpo) {
    return `
      ${encabezadoDetalle(t, `Visita del ${formatDate(t.fecha)}`)}
      ${lineaMeta([t.detalle && t.detalle !== 'Visita' ? t.detalle : null, t.autor ? `registrada por ${t.autor}` : null])}
      <div class="mt-3">${cuerpo}</div>`;
  }

  function tablaVisita(d) {
    const dinero = d.montos_visibles;
    const conDescuento = dinero && d.lineas.some(l => l.descuento != null);
    const th = 'px-2 py-1.5 text-[11px] font-semibold text-text-muted uppercase tracking-wide';
    const td = 'px-2 py-1.5 text-xs text-text-primary';
    const filas = d.lineas.map(l => `
      <tr class="border-t border-border">
        <td class="${td}">${esc(l.tratamiento || '—')}</td>
        <td class="${td}">${esc(l.doctor || '—')}</td>
        ${conDescuento ? `<td class="${td} text-right whitespace-nowrap">${l.descuento != null ? esc('−' + fmt(l.descuento)) : ''}</td>` : ''}
        ${dinero ? `<td class="${td} text-right whitespace-nowrap">${esc(fmt(l.monto))}</td>` : ''}
      </tr>`).join('');
    const span = conDescuento ? 3 : 2;
    let totales = '';
    if (dinero) {
      const fila = (etq, v, fuerte) => `
        <tr class="${fuerte ? 'border-t border-border-strong' : ''}">
          <td colspan="${span}" class="${td} ${fuerte ? 'font-semibold' : 'text-text-secondary'}">${esc(etq)}</td>
          <td class="${td} text-right whitespace-nowrap ${fuerte ? 'font-semibold' : ''}">${esc(fmt(v))}</td>
        </tr>`;
      if (d.iva) totales = fila('Subtotal', d.subtotal) + fila('IVA', d.iva);
      totales += fila('Total cobrado', d.total, true);
    }
    return `
      <div class="overflow-x-auto rounded-lg border border-border bg-surface">
        <table class="w-full">
          <thead><tr>
            <th class="${th} text-left">Tratamiento</th>
            <th class="${th} text-left">Doctor</th>
            ${conDescuento ? `<th class="${th} text-right">Descuento</th>` : ''}
            ${dinero ? `<th class="${th} text-right">Monto</th>` : ''}
          </tr></thead>
          <tbody>${filas}${totales}</tbody>
        </table>
      </div>`;
  }

  function cuerpoVisita(d) {
    if (!d.cobrada) {
      return '<p class="text-sm text-text-muted">Visita registrada sin cobro.</p>';
    }
    const ticket = d.ticket
      ? [`Ticket ${d.ticket.folio}`, d.ticket.sucursal].filter(Boolean).join(' · ')
      : null;
    const cabecera = [ticket, (d.metodos_pago || []).join(', ') || null].filter(Boolean).join(' · ');
    const etiquetas = d.factura
      ? '<span class="inline-flex items-center rounded-full bg-primary-50 text-primary-700 px-2 py-0.5 text-[11px] font-medium">Con factura</span>'
      : '';
    const aviso = d.montos_visibles ? ''
      : '<p class="mt-2 text-xs text-text-muted">Tu usuario no tiene acceso a los montos de los ingresos.</p>';
    const comentarios = (d.comentarios || []).length
      ? `<div class="mt-3 space-y-1">${d.comentarios.map(c =>
          `<p class="text-xs text-text-secondary whitespace-pre-wrap break-words"><span class="font-medium">Comentario:</span> ${esc(c)}</p>`).join('')}</div>`
      : '';
    return `
      ${cabecera || etiquetas ? `<div class="flex flex-wrap items-center gap-2 mb-2">
        ${cabecera ? `<p class="text-xs text-text-secondary">${esc(cabecera)}</p>` : ''}${etiquetas}</div>` : ''}
      ${d.lineas.length ? tablaVisita(d) : ''}
      ${aviso}
      ${comentarios}`;
  }

  async function detalleVisita(t, cont) {
    if (!t.cobrada) {
      cont.innerHTML = detalleVisitaBase(t, '<p class="text-sm text-text-muted">Visita registrada sin cobro.</p>');
      return;
    }
    let d = cacheVisitas.get(t.id);
    if (!d) {
      cont.innerHTML = detalleVisitaBase(t, '<p class="text-sm text-text-muted">Cargando detalle…</p>');
      lucide.createIcons();
      try {
        d = await API.get(`/crm/visitas/${t.id}`);
        cacheVisitas.set(t.id, d);
      } catch (e) {
        if (esSel(t)) {
          cont.innerHTML = detalleVisitaBase(t,
            `<p class="text-sm text-danger-600">${esc(e.message || 'No se pudo cargar el detalle de la visita')}</p>`);
        }
        return;
      }
      if (!esSel(t)) return; // el usuario ya eligió otro evento
    }
    cont.innerHTML = detalleVisitaBase(t, cuerpoVisita(d));
  }

  async function pintarDetalle() {
    const cont = $('fp-detalle');
    if (!cont) return;
    const t = sel && items.find(esSel);
    if (!t) {
      cont.innerHTML = vacioDetalle();
    } else if (t.tipo === 'visita') {
      await detalleVisita(t, cont);
    } else if (t.tipo === 'seguimiento') {
      cont.innerHTML = detalleSeguimiento(t);
    } else if (t.tipo === 'nota') {
      cont.innerHTML = detalleSimple(t, 'Nota');
    } else if (t.tipo === 'expediente') {
      cont.innerHTML = detalleSimple(t, 'Cambio de expediente');
    } else {
      cont.innerHTML = detalleSimple(t, 'Cambio de estatus');
    }
    lucide.createIcons();
  }

  // En móvil se ve la lista o el detalle; desde md las dos columnas siempre.
  function aplicarVista() {
    const lista = $('fp-col-lista');
    const det = $('fp-col-detalle');
    if (!lista || !det) return;
    const mostrarDetalle = verDetalle && !!sel;
    lista.classList.toggle('hidden', mostrarDetalle);
    det.classList.toggle('hidden', !mostrarDetalle);
  }

  function repintar() {
    // Si el evento elegido ya no pasa el filtro (o desapareció), se suelta.
    if (sel && !items.some(t => esSel(t) && coincide(t))) { sel = null; verDetalle = false; }
    pintarFiltros();
    pintarLista();
    pintarDetalle();
    aplicarVista();
    lucide.createIcons();
  }

  // ── API pública ────────────────────────────────────────────────────────────
  function pintar(nuevos) {
    items = Array.isArray(nuevos) ? nuevos : [];
    repintar();
  }

  function reiniciar() {
    items = [];
    filtro = 'todo';
    subtipos = new Set();
    soloPendientes = false;
    sel = null;
    verDetalle = false;
    cacheVisitas = new Map();
    aplicarVista();
  }

  function seleccionar(tipo, id) {
    sel = { tipo, id: Number(id) };
    verDetalle = true;
    pintarLista();
    pintarDetalle();
    aplicarVista();
    lucide.createIcons();
    const det = $('fp-col-detalle');
    if (det) det.scrollTop = 0;
  }

  function volver() {
    verDetalle = false;
    aplicarVista();
  }

  function filtrar(clave) {
    filtro = clave;
    repintar();
  }

  // ── Eventos (delegados; el modal ya está en el DOM cuando carga este script) ─
  function enlazar() {
    const filtros = $('fp-filtros');
    const lista = $('fp-timeline');
    const detalle = $('fp-detalle');
    if (filtros) filtros.addEventListener('click', (ev) => {
      const b = ev.target.closest('button[data-accion]');
      if (!b) return;
      const valor = b.dataset.valor;
      if (b.dataset.accion === 'filtro') {
        filtrar(valor);
        return;
      }
      if (b.dataset.accion === 'subtipo') {
        if (subtipos.has(valor)) subtipos.delete(valor); else subtipos.add(valor);
      } else if (b.dataset.accion === 'pendientes') {
        soloPendientes = !soloPendientes;
      }
      repintar();
    });
    // "Completar" vive en la lista y en el detalle; en ambos llama a Ficha.
    const completar = (ev) => {
      const b = ev.target.closest('button[data-completar]');
      // `Ficha` es un const global de ficha.js (no cuelga de window).
      if (!b || typeof Ficha === 'undefined') return false;
      b.disabled = true;
      Promise.resolve(Ficha.completarSeguimiento(Number(b.dataset.completar)))
        .finally(() => { b.disabled = false; });
      return true;
    };
    if (lista) lista.addEventListener('click', (ev) => {
      if (completar(ev)) return; // no selecciona la fila
      const b = ev.target.closest('button[data-tipo]');
      if (b) seleccionar(b.dataset.tipo, b.dataset.id);
    });
    if (detalle) detalle.addEventListener('click', completar);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enlazar);
  else enlazar();

  return { pintar, reiniciar, seleccionar, volver, filtrar };
})();

window.FichaActividad = FichaActividad;
