/* Ficha de paciente (modal). Requiere app.js y kanban.js. */
const Ficha = (() => {
  let actual = null; // null = modo creación

  const ICONOS = { visita: 'calendar-check', seguimiento: 'phone', cambio_estatus: 'shuffle', nota: 'sticky-note' };

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

  function pintarTimeline(items) {
    const cont = document.getElementById('fp-timeline');
    if (!items.length) {
      cont.innerHTML = '<p class="text-xs text-text-muted font-body">Sin actividad todavía.</p>';
      return;
    }
    cont.innerHTML = items.map(t => {
      const pendiente = t.tipo === 'seguimiento' && t.completado === false;
      return `
        <div class="flex items-start gap-2 rounded-lg border border-border p-2 ${pendiente ? 'bg-amber-50' : 'bg-surface'}">
          <i data-lucide="${ICONOS[t.tipo] || 'circle'}" class="h-4 w-4 shrink-0 mt-0.5 text-text-muted"></i>
          <div class="flex-1 min-w-0">
            <p class="text-xs font-body text-text-primary">${esc(t.detalle)}</p>
            <p class="text-[10px] text-text-muted">${esc(t.fecha)}</p>
          </div>
          ${pendiente ? `<button onclick="Ficha.completarSeguimiento(${t.id})"
              class="text-[10px] font-bold text-emerald-600 hover:underline cursor-pointer">Completar</button>` : ''}
        </div>`;
    }).join('');
  }

  function llenar(p) {
    document.getElementById('ficha-titulo').textContent = p ? p.nombre : 'Nuevo paciente';
    document.getElementById('fp-nombre').value = p ? p.nombre : '';
    document.getElementById('fp-telefono').value = (p && p.telefono) || '';
    document.getElementById('fp-whatsapp').value = (p && p.whatsapp) || '';
    document.getElementById('fp-email').value = (p && p.email) || '';
    document.getElementById('fp-estatus').value = p ? p.estatus_crm : 'prospecto';
    document.getElementById('fp-doctor').value = (p && p.especialista_id) || '';
    document.getElementById('fp-problematico').checked = !!(p && p.es_problematico);
    document.getElementById('fp-notas').value = (p && p.notas_generales) || '';
    document.getElementById('fp-panel-derecho').style.display = p ? '' : 'none';
    document.getElementById('fp-btn-eliminar').style.display = p ? '' : 'none';
    pintarTimeline((p && p.timeline) || []);
  }

  async function abrir(id) {
    await cargarDoctores();
    actual = await API.get(`/crm/pacientes/${id}`);
    llenar(actual);
    cerrarAccion();
    Modal.open('modal-ficha');
    lucide.createIcons();
  }

  async function abrirNueva() {
    await cargarDoctores();
    actual = null;
    llenar(null);
    cerrarAccion();
    Modal.open('modal-ficha');
    lucide.createIcons();
  }

  function payload() {
    return {
      nombre: document.getElementById('fp-nombre').value.trim(),
      telefono: document.getElementById('fp-telefono').value.trim() || null,
      whatsapp: document.getElementById('fp-whatsapp').value.trim() || null,
      email: document.getElementById('fp-email').value.trim() || null,
      estatus_crm: document.getElementById('fp-estatus').value,
      especialista_id: Number(document.getElementById('fp-doctor').value) || null,
      es_problematico: document.getElementById('fp-problematico').checked,
      notas_generales: document.getElementById('fp-notas').value.trim() || null,
    };
  }

  async function guardar() {
    const body = payload();
    if (!body.nombre) { Toast.warning('El nombre es obligatorio'); return; }
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
      await abrir(actual.id);
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
      await abrir(actual.id);
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
      await abrir(actual.id);
    } catch (e) { Toast.error(e.message || 'No se pudo agregar la nota'); }
  }

  async function completarSeguimiento(id) {
    try {
      await API.post(`/crm/seguimientos/${id}/completar`, {});
      if (actual) await abrir(actual.id);
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo completar'); }
  }

  return {
    abrir, abrirNueva, guardar, eliminar, registrarVisita,
    programarSeguimiento, agregarNota, completarSeguimiento, cerrarAccion,
  };
})();

window.abrirFicha = (id) => Ficha.abrir(id);
window.abrirFichaNueva = () => Ficha.abrirNueva();
