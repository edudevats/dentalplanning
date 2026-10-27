/* Ficha de paciente (modal). Requiere app.js y kanban.js. */
const Ficha = (() => {
  let actual = null; // null = modo creación

  let tab = 'datos';

  // Configuración de expedientes (una carga por página; null = aún no cargada).
  let cfgExp = null; // { formato, letras, siguiente, esAdmin }
  // Elección del usuario en el campo "No. de expediente".
  let exp = { cambiando: false, modo: '', letra: '', valor: '' };

  const ESTATUS = {
    prospecto: { texto: 'Prospecto', cls: 'bg-warning-100 text-warning-700' },
    activo:    { texto: 'Activo',    cls: 'bg-accent-100 text-accent-700' },
    alta:      { texto: 'Alta',      cls: 'bg-primary-100 text-primary-700' },
    baja:      { texto: 'Baja',      cls: 'bg-surface-hover text-text-secondary' },
  };
  const TAB_ON = ['border-primary-600', 'text-primary-700', 'font-semibold'];
  const TAB_OFF = ['border-transparent', 'text-text-muted'];

  async function cargarDoctores() {
    const sel = document.getElementById('fp-doctor');
    if (sel.options.length > 1) return;
    try {
      const docs = await API.get('/ajustes/especialistas');
      (docs || []).forEach(d => {
        const o = document.createElement('option');
        o.value = d.id; o.textContent = d.nombre;
        sel.appendChild(o);
      });
    } catch { /* opcional */ }
  }

  async function cargarConfigExpediente() {
    if (cfgExp) return;
    try {
      const c = await API.get('/crm/config');
      cfgExp = { ...c.expediente, esAdmin: !!c.es_admin };
    } catch { cfgExp = null; /* se reintenta en la próxima ficha */ }
  }

  const TXT_EXP = 'text-sm font-body text-text-secondary';

  function pintarExpediente() {
    const slot = document.getElementById('fp-expediente-slot');
    if (!slot) return;
    const etiqueta = '<label class="block text-sm font-medium text-text-secondary mb-1 font-body">No. de expediente</label>';
    if (!cfgExp) {
      slot.innerHTML = `${etiqueta}<p class="${TXT_EXP}">No se pudo cargar la configuración de expedientes.</p>`;
      return;
    }
    if (!cfgExp.formato) {
      slot.innerHTML = cfgExp.esAdmin
        ? `${etiqueta}<p class="${TXT_EXP}">Aún no eligen cómo numerar. <button type="button" onclick="Ficha.abrirConfigExpediente()" class="font-medium text-primary-600 hover:underline cursor-pointer">Configurar</button></p>`
        : `${etiqueta}<p class="${TXT_EXP}">El admin aún no configura los expedientes</p>`;
      return;
    }
    const actualExp = actual && actual.expediente;
    const editable = !actual || actual.expediente_editable !== false;
    if (actualExp && !editable) {
      slot.innerHTML = `${etiqueta}<p class="text-sm font-semibold font-body text-text-primary">${esc(actualExp)}</p>`;
      return;
    }
    if (actualExp && !exp.cambiando) {
      slot.innerHTML = `${etiqueta}
        <div class="flex items-center gap-3">
          <span class="text-sm font-semibold font-body text-text-primary">${esc(actualExp)}</span>
          <button type="button" onclick="Ficha.cambiarExpediente()"
                  class="text-xs font-medium font-body text-primary-600 hover:underline cursor-pointer">Cambiar</button>
        </div>`;
      return;
    }
    const opciones = [
      ['', actualExp ? 'Sin cambios' : 'Sin expediente por ahora'],
      ['auto', 'Generar automático'],
      ['manual', 'Escribir a mano'],
      ...(actualExp ? [['quitar', 'Quitar expediente']] : []),
    ];
    const letras = cfgExp.letras || [];
    const conLetra = cfgExp.formato === 'letra';
    const selLetra = conLetra && exp.modo === 'auto' && letras.length > 1 ? `
      <select id="fp-exp-letra" class="${INPUT_CLS}" aria-label="Letra del expediente">
        ${letras.map(l => `<option value="${esc(l)}" ${l === exp.letra ? 'selected' : ''}>${esc(l)}</option>`).join('')}
      </select>` : '';
    const manual = exp.modo === 'manual' ? `
      <input id="fp-exp-valor" type="text" maxlength="10" value="${esc(exp.valor)}"
             placeholder="${conLetra ? 'Ej. A245' : 'Ej. 245'}" class="${INPUT_CLS}" />
      <p class="text-[11px] text-text-muted font-body">${conLetra ? 'Letra y número; el número se completa con ceros hasta 6 dígitos.' : 'El número se completa con ceros hasta 7 dígitos.'}</p>` : '';
    slot.innerHTML = `${etiqueta}
      <div class="space-y-2">
        <div class="flex gap-2 items-center">
          <select id="fp-exp-modo" class="${INPUT_CLS}" aria-label="Cómo asignar el expediente">
            ${opciones.map(([v, t]) => `<option value="${v}" ${v === exp.modo ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
          ${actualExp ? '<button type="button" onclick="Ficha.cancelarCambioExpediente()" class="text-xs font-medium font-body text-text-muted hover:underline cursor-pointer whitespace-nowrap">Cancelar</button>' : ''}
        </div>
        ${selLetra}${manual}
      </div>`;
    document.getElementById('fp-exp-modo').addEventListener('change', (ev) => {
      exp.modo = ev.target.value;
      if (exp.modo === 'auto' && !exp.letra) exp.letra = letras[0] || '';
      pintarExpediente();
      const f = document.getElementById('fp-exp-valor');
      if (f) f.focus();
    });
    const l = document.getElementById('fp-exp-letra');
    if (l) l.addEventListener('change', (ev) => { exp.letra = ev.target.value; });
    const v = document.getElementById('fp-exp-valor');
    if (v) v.addEventListener('input', (ev) => { exp.valor = ev.target.value; });
  }

  function reiniciarExpediente() {
    exp = { cambiando: false, modo: '', letra: '', valor: '' };
    pintarExpediente();
  }

  function cambiarExpediente() { exp.cambiando = true; pintarExpediente(); }
  function cancelarCambioExpediente() { reiniciarExpediente(); }

  // ── Diálogo de primera configuración (solo admin, mientras no haya formato) ──
  function abrirConfigExpediente() {
    document.querySelectorAll('input[name="cfg-exp-formato"]').forEach(r => { r.checked = false; });
    document.getElementById('cfg-exp-letras').value = '';
    cambiarFormatoConfig();
    Modal.open('modal-config-expediente');
  }

  function cambiarFormatoConfig() {
    const r = document.querySelector('input[name="cfg-exp-formato"]:checked');
    document.getElementById('cfg-exp-letras-caja').classList.toggle('hidden', !(r && r.value === 'letra'));
  }

  async function guardarConfigExp() {
    const r = document.querySelector('input[name="cfg-exp-formato"]:checked');
    try {
      const c = await guardarConfigExpediente(r && r.value, document.getElementById('cfg-exp-letras').value);
      cfgExp = { ...c, esAdmin: true };
      Modal.close('modal-config-expediente');
      pintarExpediente();
      Toast.success('Numeración de expedientes configurada');
    } catch (e) { Toast.error(e.message || 'No se pudo guardar la configuración'); }
  }

  // Cada vez que se abre una ficha: el admin vuelve a ver el diálogo mientras no elija.
  function avisarSiFaltaConfig() {
    if (cfgExp && !cfgExp.formato && cfgExp.esAdmin) abrirConfigExpediente();
  }

  function mostrarTab(nombre) {
    // Paciente nuevo: solo existe la pestaña Datos.
    tab = actual && nombre === 'actividad' ? 'actividad' : 'datos';
    const datos = tab === 'datos';
    document.getElementById('fp-panel-datos').style.display = datos ? '' : 'none';
    document.getElementById('fp-panel-actividad').style.display = datos ? 'none' : '';
    [['ficha-tab-datos', datos], ['ficha-tab-actividad', !datos]].forEach(([id, on]) => {
      const b = document.getElementById(id);
      b.classList.remove(...TAB_ON, ...TAB_OFF);
      b.classList.add(...(on ? TAB_ON : TAB_OFF));
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }

  function pintarEncabezado(p) {
    document.getElementById('ficha-titulo').textContent = p ? p.nombre : 'Nuevo paciente';
    const exp = document.getElementById('ficha-encabezado-expediente');
    const est = document.getElementById('ficha-encabezado-estatus');
    const contacto = document.getElementById('ficha-encabezado-contacto');
    exp.style.display = p ? '' : 'none';
    est.style.display = p ? '' : 'none';
    if (!p) { contacto.textContent = ''; return; }
    exp.textContent = p.expediente ? `Exp. ${p.expediente}` : 'Sin expediente';
    exp.classList.toggle('bg-primary-50', !!p.expediente);
    exp.classList.toggle('text-primary-700', !!p.expediente);
    exp.classList.toggle('bg-surface-hover', !p.expediente);
    exp.classList.toggle('text-text-muted', !p.expediente);
    const e = ESTATUS[p.estatus_crm] || { texto: p.estatus_crm || '', cls: ESTATUS.baja.cls };
    est.textContent = e.texto;
    est.className = `inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium font-body whitespace-nowrap ${e.cls}`;
    contacto.textContent = [p.telefono, p.especialista_nombre].filter(Boolean).join(' · ');
  }

  function textoEdad(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    const hoy = new Date();
    let anios = hoy.getFullYear() - y;
    if (hoy.getMonth() + 1 < m || (hoy.getMonth() + 1 === m && hoy.getDate() < d)) anios -= 1;
    return `(${anios} años)`;
  }

  function abrirOdontograma() {
    if (actual) window.location.href = `/crm/pacientes/${actual.id}/odontograma`;
  }

  function llenar(p, conservarTab) {
    pintarEncabezado(p);
    document.getElementById('fp-nombre').value = p ? p.nombre : '';
    document.getElementById('fp-telefono').value = (p && p.telefono) || '';
    document.getElementById('fp-whatsapp').value = (p && p.whatsapp) || '';
    document.getElementById('fp-email').value = (p && p.email) || '';
    document.getElementById('fp-nacimiento').value = (p && p.fecha_nacimiento) || '';
    document.getElementById('fp-edad').textContent = textoEdad(p && p.fecha_nacimiento);
    document.getElementById('fp-estatus').value = p ? p.estatus_crm : 'prospecto';
    document.getElementById('fp-doctor').value = (p && p.especialista_id) || '';
    document.getElementById('fp-problematico').checked = !!(p && p.es_problematico);
    document.getElementById('fp-notas').value = (p && p.notas_generales) || '';
    document.getElementById('ficha-tab-actividad').style.display = p ? '' : 'none';
    document.getElementById('fp-btn-eliminar').style.display = p ? '' : 'none';
    FichaActividad.pintar((p && p.timeline) || []);
    // Al recargar tras una acción se conserva lo que el usuario ya eligió en el campo.
    if (conservarTab) pintarExpediente(); else reiniciarExpediente();
    // Paciente existente abre en Actividad; al recargar tras una acción se queda donde estaba.
    mostrarTab(p ? (conservarTab ? tab : 'actividad') : 'datos');
  }

  // `recarga` = true cuando se vuelve a pedir el mismo paciente tras guardar una
  // acción: se conservan filtro, selección y pestaña. Abrirlo desde fuera reinicia.
  async function abrir(id, recarga = false) {
    await Promise.all([cargarDoctores(), cargarConfigExpediente()]);
    const p = await API.get(`/crm/pacientes/${id}`);
    const mismo = recarga && !!actual && actual.id === p.id;
    if (!mismo) FichaActividad.reiniciar();
    actual = p;
    llenar(actual, mismo);
    cerrarAccion();
    Modal.open('modal-ficha');
    lucide.createIcons();
    // Recargar la misma ficha tras una acción no vuelve a mostrar el aviso.
    if (!mismo) avisarSiFaltaConfig();
  }

  async function abrirNueva() {
    await Promise.all([cargarDoctores(), cargarConfigExpediente()]);
    actual = null;
    FichaActividad.reiniciar();
    llenar(null);
    cerrarAccion();
    Modal.open('modal-ficha');
    lucide.createIcons();
    avisarSiFaltaConfig();
  }

  // Solo si el usuario eligió algo en el campo; si no, no se toca el expediente.
  function expedienteCambio() {
    if (!cfgExp || !cfgExp.formato || !exp.modo) return null;
    if (exp.modo === 'quitar') return { modo: 'quitar' };
    if (exp.modo === 'manual') return { modo: 'manual', valor: exp.valor.trim() };
    const c = { modo: 'auto' };
    if (cfgExp.formato === 'letra') c.letra = exp.letra || (cfgExp.letras || [])[0] || '';
    return c;
  }

  function payload() {
    const cambio = expedienteCambio();
    return {
      ...(cambio ? { expediente_cambio: cambio } : {}),
      nombre: document.getElementById('fp-nombre').value.trim(),
      telefono: document.getElementById('fp-telefono').value.trim() || null,
      whatsapp: document.getElementById('fp-whatsapp').value.trim() || null,
      email: document.getElementById('fp-email').value.trim() || null,
      fecha_nacimiento: document.getElementById('fp-nacimiento').value || null,
      estatus_crm: document.getElementById('fp-estatus').value,
      especialista_id: Number(document.getElementById('fp-doctor').value) || null,
      es_problematico: document.getElementById('fp-problematico').checked,
      notas_generales: document.getElementById('fp-notas').value.trim() || null,
    };
  }

  async function guardar() {
    const body = payload();
    if (!body.nombre) { Toast.warning('El nombre es obligatorio'); return; }
    const cambio = body.expediente_cambio;
    if (cambio && cambio.modo === 'manual' && !cambio.valor) {
      Toast.warning('Escribe el número de expediente'); return;
    }
    if (cambio && cambio.modo === 'quitar') {
      const ok = await Confirm.show({
        title: 'Quitar expediente',
        message: `¿Quitar el expediente ${actual.expediente} de ${actual.nombre}? El número queda libre para capturarse a mano.`,
        confirmText: 'Quitar',
        cancelText: 'Cancelar',
        danger: true,
      });
      if (!ok) return;
    }
    try {
      if (actual) await API.put(`/crm/pacientes/${actual.id}`, body);
      else await API.post('/crm/pacientes', body);
      Toast.success('Paciente guardado');
      Modal.close('modal-ficha');
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo guardar'); }
  }

  async function eliminar() {
    if (!actual) return;
    const ok = await Confirm.show({
      title: 'Eliminar paciente',
      message: `¿Eliminar a ${actual.nombre}? Se conserva su historial pero deja de aparecer en el tablero.`,
      confirmText: 'Eliminar',
      cancelText: 'Cancelar',
      danger: true,
    });
    if (!ok) return;
    try {
      await API.delete(`/crm/pacientes/${actual.id}`);
      Toast.success('Paciente eliminado');
      Modal.close('modal-ficha');
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo eliminar'); }
  }

  // ── Formularios inline de acción ────────────────────────────────────────────
  const INPUT_CLS =
    'block w-full rounded-lg border border-border px-3 py-2 text-sm font-body bg-surface min-h-[40px]';

  function cerrarAccion() {
    const c = document.getElementById('fp-accion');
    if (!c) return;
    c.innerHTML = '';
    c.classList.add('hidden');
  }

  function abrirAccion(icono, titulo, camposHTML, onGuardar) {
    const c = document.getElementById('fp-accion');
    if (!c) return;
    c.innerHTML = `
      <div class="rounded-lg border border-primary-200 bg-primary-50/60 p-3 space-y-2">
        <p class="text-xs font-semibold font-heading text-text-primary flex items-center gap-1.5">
          <i data-lucide="${icono}" class="h-3.5 w-3.5"></i> ${titulo}</p>
        ${camposHTML}
        <div class="flex gap-2 pt-1">
          <button type="button" id="acc-guardar"
                  class="flex-1 rounded-lg bg-primary-500 hover:bg-primary-600 text-white px-3 py-1.5 text-xs font-medium cursor-pointer transition-colors duration-200">Guardar</button>
          <button type="button" id="acc-cancelar"
                  class="rounded-lg border border-border hover:bg-surface-hover px-3 py-1.5 text-xs font-medium cursor-pointer transition-colors duration-200">Cancelar</button>
        </div>
      </div>`;
    c.classList.remove('hidden');
    document.getElementById('acc-guardar').addEventListener('click', onGuardar);
    document.getElementById('acc-cancelar').addEventListener('click', cerrarAccion);
    lucide.createIcons();
    const f = c.querySelector('input, select, textarea');
    if (f) f.focus();
  }

  function registrarVisita() {
    if (!actual) return;
    const hoy = new Date().toISOString().slice(0, 10);
    abrirAccion('calendar-check', 'Registrar visita', `
      <div>
        <label class="block text-[11px] font-medium text-text-secondary mb-1 font-body">Fecha</label>
        <input id="acc-fecha" type="date" value="${hoy}" class="${INPUT_CLS}" />
      </div>
      <div>
        <label class="block text-[11px] font-medium text-text-secondary mb-1 font-body">Motivo (opcional)</label>
        <input id="acc-motivo" type="text" placeholder="Ej. Limpieza dental" class="${INPUT_CLS}" />
      </div>`, guardarVisita);
  }

  async function guardarVisita() {
    const fecha = document.getElementById('acc-fecha').value;
    if (!fecha) { Toast.warning('La fecha es obligatoria'); return; }
    const motivo = document.getElementById('acc-motivo').value.trim() || null;
    try {
      await API.post(`/crm/pacientes/${actual.id}/visitas`, { fecha, motivo });
      Toast.success('Visita registrada');
      cerrarAccion();
      await abrir(actual.id, true);
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo registrar la visita'); }
  }

  function programarSeguimiento() {
    if (!actual) return;
    abrirAccion('phone', 'Programar seguimiento', `
      <div>
        <label class="block text-[11px] font-medium text-text-secondary mb-1 font-body">Fecha programada</label>
        <input id="acc-fecha" type="date" class="${INPUT_CLS}" />
      </div>
      <div>
        <label class="block text-[11px] font-medium text-text-secondary mb-1 font-body">Tipo</label>
        <select id="acc-tipo" class="${INPUT_CLS}">
          <option value="llamada">Llamada</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="otro">Otro</option>
        </select>
      </div>
      <div>
        <label class="block text-[11px] font-medium text-text-secondary mb-1 font-body">Notas (opcional)</label>
        <textarea id="acc-notas" rows="2" class="block w-full rounded-lg border border-border px-3 py-2 text-sm font-body bg-surface"></textarea>
      </div>`, guardarSeguimiento);
  }

  async function guardarSeguimiento() {
    const fecha = document.getElementById('acc-fecha').value;
    if (!fecha) { Toast.warning('La fecha es obligatoria'); return; }
    const tipo = document.getElementById('acc-tipo').value;
    const notas = document.getElementById('acc-notas').value.trim() || null;
    try {
      await API.post(`/crm/pacientes/${actual.id}/seguimientos`,
                     { tipo, fecha_programada: fecha, notas });
      Toast.success('Seguimiento programado');
      cerrarAccion();
      await abrir(actual.id, true);
    } catch (e) { Toast.error(e.message || 'No se pudo programar'); }
  }

  function agregarNota() {
    if (!actual) return;
    abrirAccion('sticky-note', 'Agregar nota', `
      <div>
        <label class="block text-[11px] font-medium text-text-secondary mb-1 font-body">Nota</label>
        <textarea id="acc-texto" rows="3" placeholder="Escribe una nota…" class="block w-full rounded-lg border border-border px-3 py-2 text-sm font-body bg-surface"></textarea>
      </div>`, guardarNota);
  }

  async function guardarNota() {
    const texto = document.getElementById('acc-texto').value.trim();
    if (!texto) { Toast.warning('La nota no puede estar vacía'); return; }
    try {
      await API.post(`/crm/pacientes/${actual.id}/notas`, { texto });
      Toast.success('Nota agregada');
      cerrarAccion();
      await abrir(actual.id, true);
    } catch (e) { Toast.error(e.message || 'No se pudo agregar la nota'); }
  }

  async function completarSeguimiento(id) {
    try {
      await API.post(`/crm/seguimientos/${id}/completar`, {});
      if (actual) await abrir(actual.id, true);
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo completar'); }
  }

  return {
    abrir, abrirNueva, guardar, eliminar, registrarVisita, abrirOdontograma,
    programarSeguimiento, agregarNota, completarSeguimiento, cerrarAccion, mostrarTab,
    cambiarExpediente, cancelarCambioExpediente, abrirConfigExpediente,
    cambiarFormatoConfig, guardarConfigExpediente: guardarConfigExp,
  };
})();

window.abrirFicha = (id) => Ficha.abrir(id);
window.abrirFichaNueva = () => Ficha.abrirNueva();
