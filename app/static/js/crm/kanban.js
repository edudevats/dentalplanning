/* Tablero Kanban del CRM. Requiere app.js (API, Toast, lucide) y crm_common.js (esc). */
const Kanban = (() => {
  const COLS = [
    { estatus: 'prospecto', titulo: 'Prospecto', color: 'bg-amber-500' },
    { estatus: 'activo',    titulo: 'Activo',    color: 'bg-emerald-500' },
    { estatus: 'alta',      titulo: 'Alta',      color: 'bg-sky-500' },
    { estatus: 'baja',      titulo: 'Baja',      color: 'bg-slate-400' },
  ];
  let pacientes = [];
  const dragTokens = {};

  async function cargar() {
    try {
      const params = new URLSearchParams();
      const q = document.getElementById('kb-buscar').value.trim();
      if (q) params.set('q', q);
      const doc = document.getElementById('kb-doctor').value;
      if (doc) params.set('especialista_id', doc);
      if (document.getElementById('kb-solo-inactivos').checked) params.set('inactivos', 'true');
      const data = await API.get('/crm/pacientes?' + params.toString());
      pacientes = data.pacientes;
      pintar();
      pintarResumen();
    } catch (err) {
      Toast.error('No se pudieron cargar los pacientes');
    }
  }

  async function pintarResumen() {
    try {
      const r = await API.get('/crm/resumen');
      const items = [
        ['Inactivos', r.inactivos, 'alert-triangle'],
        ['Seguimientos hoy', r.seguimientos_hoy, 'calendar-check'],
        ['Vencidos', r.seguimientos_vencidos, 'bell-ring'],
        ['Pacientes', Object.values(r.por_estatus).reduce((a, b) => a + b, 0), 'users'],
      ];
      document.getElementById('kb-resumen').innerHTML = items.map(([label, val, icon]) => `
        <div class="bg-surface rounded-xl border border-border p-4 shadow-sm">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-text-secondary font-body">${label}</p>
            <i data-lucide="${icon}" class="h-4 w-4 text-primary-600"></i>
          </div>
          <p class="mt-2 text-2xl font-bold font-heading tabular-nums text-text-primary">${val}</p>
        </div>`).join('');
      lucide.createIcons();
    } catch { /* resumen es decorativo */ }
  }

  function badge(texto, clases) {
    return `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${clases}">${texto}</span>`;
  }

  function tarjeta(p) {
    const id = Number(p.id);
    const badges = [];
    if (p.inactivo) badges.push(badge('INACTIVO', 'bg-amber-100 text-amber-700'));
    if (p.es_problematico) badges.push(badge('PROBLEMÁTICO', 'bg-red-100 text-red-700'));
    if (p.siguiente_seguimiento && p.siguiente_seguimiento < new Date().toISOString().slice(0, 10))
      badges.push(badge('SEG. VENCIDO', 'bg-orange-100 text-orange-700'));
    return `
      <div draggable="true" data-id="${id}" onclick="abrirFicha(${id})"
           class="kb-card bg-surface rounded-lg border border-border p-3 shadow-sm cursor-pointer hover:shadow-md space-y-1.5">
        <div class="flex items-start justify-between gap-2">
          <p class="text-sm font-semibold font-body text-text-primary">${esc(p.nombre)}</p>
        </div>
        <div class="flex flex-wrap gap-1">${badges.join('')}</div>
        <p class="text-xs text-text-muted font-body">
          ${p.especialista_nombre ? '👨‍⚕️ ' + esc(p.especialista_nombre) + ' · ' : ''}
          Última visita: ${esc(p.ultima_visita) || '—'}
        </p>
      </div>`;
  }

  function pintar() {
    const cont = document.getElementById('kb-tablero');
    cont.innerHTML = COLS.map(col => {
      const items = pacientes.filter(p => p.estatus_crm === col.estatus);
      return `
        <div class="kb-col flex-shrink-0 w-72 bg-surface-hover/50 rounded-xl border border-border"
             data-estatus="${col.estatus}">
          <div class="flex items-center gap-2 px-4 py-3 border-b border-border">
            <span class="h-2.5 w-2.5 rounded-full ${col.color}"></span>
            <h2 class="text-sm font-semibold font-heading text-text-primary">${col.titulo}</h2>
            <span class="ml-auto text-xs font-bold text-text-muted">${items.length}</span>
          </div>
          <div class="p-3 space-y-2 min-h-[120px] kb-drop">${items.map(tarjeta).join('')}</div>
        </div>`;
    }).join('');
    activarDrag();
    lucide.createIcons();
  }

  function activarDrag() {
    let arrastradoId = null;
    document.querySelectorAll('.kb-card').forEach(card => {
      card.addEventListener('dragstart', () => { arrastradoId = card.dataset.id; });
    });
    document.querySelectorAll('.kb-col').forEach(col => {
      col.addEventListener('dragover', e => e.preventDefault());
      col.addEventListener('drop', async e => {
        e.preventDefault();
        if (!arrastradoId) return;
        const nuevo = col.dataset.estatus;
        const p = pacientes.find(x => String(x.id) === String(arrastradoId));
        if (!p || p.estatus_crm === nuevo) return;
        const anterior = p.estatus_crm;
        const token = (dragTokens[p.id] = (dragTokens[p.id] || 0) + 1);
        p.estatus_crm = nuevo;
        pintar(); // optimista
        try {
          await API.put(`/crm/pacientes/${p.id}/estatus`, { estatus_crm: nuevo });
        } catch (err) {
          if (dragTokens[p.id] === token) { // solo el request más reciente revierte
            p.estatus_crm = anterior;
            pintar();
          }
          Toast.error('No se pudo mover el paciente');
        }
      });
    });
  }

  async function cargarDoctores() {
    try {
      const docs = await API.get('/ajustes/especialistas');
      const sel = document.getElementById('kb-doctor');
      (docs || []).forEach(d => {
        const o = document.createElement('option');
        o.value = d.id; o.textContent = d.nombre;
        sel.appendChild(o);
      });
    } catch { /* sin doctores no bloquea el tablero */ }
  }

  function nuevoPaciente() {
    // La ficha (Task 10) implementa el modal en modo creación.
    if (typeof abrirFichaNueva === 'function') abrirFichaNueva();
    else Toast.warning('La ficha de paciente llega en la siguiente tarea');
  }

  let debounce = null;
  function init() {
    document.getElementById('kb-buscar').addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(cargar, 300);
    });
    document.getElementById('kb-doctor').addEventListener('change', cargar);
    document.getElementById('kb-solo-inactivos').addEventListener('change', cargar);
    cargarDoctores();
    cargar();
  }

  return { init, recargar: cargar, nuevoPaciente };
})();

// Stub hasta Task 10:
if (typeof abrirFicha !== 'function') {
  window.abrirFicha = (id) => { console.log('ficha', id); };
}

document.addEventListener('DOMContentLoaded', Kanban.init);
