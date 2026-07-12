/* Ficha de paciente (modal). Requiere app.js y kanban.js. */
const Ficha = (() => {
  let actual = null; // null = modo creación

  const ICONOS = { visita: '🦷', seguimiento: '📞', cambio_estatus: '🔀', nota: '📝' };

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
          <span>${ICONOS[t.tipo] || '•'}</span>
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
    Modal.open('modal-ficha');
    lucide.createIcons();
  }

  async function abrirNueva() {
    await cargarDoctores();
    actual = null;
    llenar(null);
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
    if (!confirm(`¿Eliminar a ${actual.nombre}? Se conserva su historial pero deja de aparecer.`)) return;
    try {
      await API.delete(`/crm/pacientes/${actual.id}`);
      Toast.success('Paciente eliminado');
      Modal.close('modal-ficha');
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo eliminar'); }
  }

  async function registrarVisita() {
    if (!actual) return;
    const fecha = prompt('Fecha de la visita (YYYY-MM-DD):', new Date().toISOString().slice(0, 10));
    if (!fecha) return;
    const motivo = prompt('Motivo (opcional):') || null;
    try {
      await API.post(`/crm/pacientes/${actual.id}/visitas`, { fecha, motivo });
      await abrir(actual.id);
      Kanban.recargar();
    } catch (e) { Toast.error(e.message || 'No se pudo registrar la visita'); }
  }

  async function programarSeguimiento() {
    if (!actual) return;
    const fecha = prompt('Fecha programada (YYYY-MM-DD):');
    if (!fecha) return;
    const tipo = (prompt('Tipo: llamada / whatsapp / otro', 'llamada') || 'llamada').toLowerCase();
    const notas = prompt('Notas (opcional):') || null;
    try {
      await API.post(`/crm/pacientes/${actual.id}/seguimientos`,
                     { tipo, fecha_programada: fecha, notas });
      await abrir(actual.id);
    } catch (e) { Toast.error(e.message || 'No se pudo programar'); }
  }

  async function agregarNota() {
    if (!actual) return;
    const texto = prompt('Nota:');
    if (!texto) return;
    try {
      await API.post(`/crm/pacientes/${actual.id}/notas`, { texto });
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
    programarSeguimiento, agregarNota, completarSeguimiento,
  };
})();

window.abrirFicha = (id) => Ficha.abrir(id);
window.abrirFichaNueva = () => Ficha.abrirNueva();
