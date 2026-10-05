// Odontograma del paciente: arcadas SVG animadas, pendientes por asignar y
// ficha del diente. Todo el estado viene de GET /crm/pacientes/<id>/odontograma
// y cada escritura devuelve el odontograma completo para repintar.
const Odonto = (() => {
  const root = document.getElementById('odo-root');
  const PID = Number(root.dataset.pacienteId);
  const URL_BASE = `/crm/pacientes/${PID}/odontograma`;
  const NS = 'http://www.w3.org/2000/svg';
  const CX = 340;
  const CARAS = ['O', 'M', 'D', 'V', 'L'];
  const ESTADOS = ['presente', 'ausente', 'extraido', 'exfoliado', 'no_erupcionado'];
  const AUSENTES = ['ausente', 'extraido', 'exfoliado'];

  const PERM_SUP = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
  const PERM_INF = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];
  const TEMP_SUP = [55, 54, 53, 52, 51, 61, 62, 63, 64, 65];
  const TEMP_INF = [85, 84, 83, 82, 81, 71, 72, 73, 74, 75];

  let data = null;
  let seleccionado = null;  // número de diente
  let modo = null;          // { pendiente, elegidos: Map<numero, Set<cara>> }
  let emerger = null;       // número que debe animarse al aparecer

  const esAdmin = () => ['admin', 'editor'].includes(window.__userRole);
  const puedeCapturar = () => window.__userRole && window.__userRole !== 'viewer';
  const el = (tag, attrs = {}) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  };
  const diente = (n) => data.dientes.find(d => d.numero === n);

  // ── Geometría ────────────────────────────────────────────────────────────
  function tipo(n) {
    const d = n % 10;
    if (n > 50) return d <= 2 ? 'incisivo' : d === 3 ? 'canino' : 'molar';
    return d <= 2 ? 'incisivo' : d === 3 ? 'canino' : d <= 5 ? 'premolar' : 'molar';
  }
  const SILUETA = {
    molar: 'M-11,-8 Q-12,-14 -6,-14 Q0,-11 6,-14 Q12,-14 11,-8 L10,8 Q9,13 4,12 Q0,9 -4,12 Q-9,13 -10,8 Z',
    premolar: 'M-8,-8 Q-8,-13 0,-13 Q8,-13 8,-8 L7,8 Q6,12 0,12 Q-6,12 -7,8 Z',
    canino: 'M-6,-6 Q0,-16 6,-6 L6,8 Q5,12 0,12 Q-5,12 -6,8 Z',
    incisivo: 'M-6,-11 L6,-11 Q7,-11 7,-8 L6,8 Q5,12 0,12 Q-5,12 -6,8 L-7,-8 Q-7,-11 -6,-11 Z',
  };
  // Anteriores: la cara oclusal se rotula incisal. Superiores: lingual = palatino.
  const anterior = (n) => ['incisivo', 'canino'].includes(tipo(n));
  const superior = (n) => [1, 2, 5, 6].includes(Math.floor(n / 10));
  const etiquetaCara = (n, c) =>
    c === 'O' && anterior(n) ? 'I' : c === 'L' && superior(n) ? 'P' : c;

  // Dientes a distancia uniforme sobre la longitud de arco de la semielipse
  // (no por ángulo igual: en los extremos el ángulo apelmaza los molares).
  function arco(fila, rx, ry, cy, arriba, escala) {
    const A0 = Math.PI * 0.04, A1 = Math.PI * 0.96, PASOS = 400;
    const pts = [], acum = [0];
    for (let k = 0; k <= PASOS; k++) {
      const ang = A0 + (A1 - A0) * (k / PASOS);
      pts.push([CX - Math.cos(ang) * rx, Math.sin(ang) * ry]);
      if (k) acum.push(acum[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]));
    }
    const total = acum[PASOS];
    return fila.map((n, i) => {
      const objetivo = total * (i + 0.5) / fila.length;
      let k = 1;
      while (k < PASOS && acum[k] < objetivo) k++;
      const f = (objetivo - acum[k - 1]) / ((acum[k] - acum[k - 1]) || 1);
      const x = pts[k - 1][0] + (pts[k][0] - pts[k - 1][0]) * f;
      const sy = pts[k - 1][1] + (pts[k][1] - pts[k - 1][1]) * f;
      return { n, x, y: arriba ? cy - sy : cy + sy, arriba, escala };
    });
  }

  function layout() {
    const den = data.paciente.denticion;
    if (den === 'temporal') {
      return [...arco(TEMP_SUP, 250, 90, 140, true, 1.8), ...arco(TEMP_INF, 250, 90, 190, false, 1.8)];
    }
    const perm = [...arco(PERM_SUP, 310, 110, 150, true, 1.55), ...arco(PERM_INF, 310, 110, 190, false, 1.55)];
    if (den === 'mixta') {
      return [...perm, ...arco(TEMP_SUP, 170, 55, 155, true, 1.3), ...arco(TEMP_INF, 170, 55, 185, false, 1.3)];
    }
    return perm;
  }

  // ── Pintado ──────────────────────────────────────────────────────────────
  function claseCorona(d) {
    if (d.tratamientos.some(t => t.estatus === 'realizado')) return 'odo-crown real';
    if (d.tratamientos.some(t => t.estatus === 'planeado')) return 'odo-crown plan';
    return 'odo-crown';
  }

  function claseGrupo(d) {
    const c = ['odo-g'];
    if (AUSENTES.includes(d.estado)) c.push('aus');
    if (d.estado === 'no_erupcionado') c.push('fantasma');
    if (modo) {
      if (d.estado !== 'presente') c.push('atenuado');
      if (modo.elegidos.has(d.numero)) c.push('elegido');
    } else if (seleccionado === d.numero) {
      c.push('sel');
    }
    if (emerger === d.numero) c.push('emerge');
    return c.join(' ');
  }

  function pintarArcadas() {
    const svg = document.getElementById('odo-svg');
    svg.innerHTML = '';
    layout().forEach(({ n, x, y, arriba, escala }) => {
      const d = diente(n);
      if (!d) return;
      const g = el('g', { class: claseGrupo(d), transform: `translate(${x},${y})`, 'data-n': n });
      const t = el('g', { class: 'odo-tooth' });
      const s = el('g', { transform: `scale(${escala},${arriba ? escala : -escala})` });
      s.appendChild(el('path', { d: SILUETA[tipo(n)], class: claseCorona(d) }));
      if (AUSENTES.includes(d.estado)) {
        s.appendChild(el('line', { x1: -9, y1: -9, x2: 9, y2: 9, class: 'odo-x' }));
        s.appendChild(el('line', { x1: 9, y1: -9, x2: -9, y2: 9, class: 'odo-x' }));
      }
      t.appendChild(s);
      g.appendChild(t);
      const num = el('text', { x: 0, y: arriba ? -14 * escala - 4 : 14 * escala + 12, class: 'odo-num' });
      num.textContent = n;
      g.appendChild(num);
      g.addEventListener('click', () => clicDiente(n));
      svg.appendChild(g);
    });
    emerger = null;
  }

  function pintarEncabezado() {
    const p = data.paciente;
    const den = { temporal: 'Temporal', mixta: 'Mixta', permanente: 'Permanente' }[p.denticion];
    document.getElementById('odo-nombre').textContent = p.nombre;
    document.getElementById('odo-sub').textContent =
      `${p.edad != null ? p.edad + ' años · ' : ''}Dentición ${den.toLowerCase()}`;
    document.getElementById('odo-aviso').classList.toggle('hidden', !p.sin_fecha_nacimiento);
  }

  function pintarPendientes() {
    const cont = document.getElementById('odo-pendientes');
    if (!data.pendientes.length) {
      cont.innerHTML = '<p class="text-xs text-text-muted font-body">Sin tratamientos por asignar.</p>';
      return;
    }
    cont.innerHTML = data.pendientes.map((p, i) => {
      const activo = modo && modo.pendiente.origen_tipo === p.origen_tipo && modo.pendiente.origen_id === p.origen_id;
      return `<button type="button" data-i="${i}"
          class="w-full flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs font-body cursor-pointer transition-colors duration-200
                 ${activo ? 'border-primary-500 bg-primary-50' : 'border-border hover:bg-surface-hover'}">
          <span class="min-w-0">
            <span class="block font-medium text-text-primary truncate">${esc(p.descripcion)}</span>
            <span class="block text-[10px] text-text-muted">${esc(p.origen)} · ${esc(p.fecha)}</span>
          </span>
          <span class="font-bold text-text-primary">${p.asignadas}/${p.unidades}</span>
        </button>`;
    }).join('');
    cont.querySelectorAll('button[data-i]').forEach(b =>
      b.addEventListener('click', () => { if (puedeCapturar()) iniciarAsignacion(data.pendientes[Number(b.dataset.i)]); }));
  }

  function chipsCaras(n, activas, accion) {
    return CARAS.map(c => `<button type="button" data-n="${n}" data-cara="${c}" data-accion="${accion}"
        class="w-7 h-7 rounded border text-xs font-bold cursor-pointer
               ${activas.has(c) ? 'bg-primary-500 border-primary-500 text-white' : 'border-border text-text-secondary'}">
        ${etiquetaCara(n, c)}</button>`).join('');
  }

  function pintarAsignando() {
    const cont = document.getElementById('odo-asignando');
    if (!modo) { cont.classList.add('hidden'); cont.innerHTML = ''; return; }
    const p = modo.pendiente;
    const faltan = p.unidades - p.asignadas;
    const filas = [...modo.elegidos.entries()].map(([n, caras]) => `
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-bold text-text-primary w-8">${n}</span>
        <div class="flex gap-1">${chipsCaras(n, caras, 'cara-asignar')}</div>
      </div>`).join('');
    cont.classList.remove('hidden');
    cont.innerHTML = `
      <p class="text-xs font-body text-text-secondary">Asignando <b>${esc(p.descripcion)}</b>:
        elige ${faltan === 1 ? '1 diente' : `hasta ${faltan} dientes`} en el odontograma
        (${modo.elegidos.size}/${faltan}). Las caras son opcionales.</p>
      ${filas}
      <div class="flex gap-2 pt-1">
        <button type="button" id="odo-guardar-asig" class="flex-1 rounded-lg bg-primary-500 hover:bg-primary-600 text-white px-3 py-1.5 text-xs font-medium cursor-pointer"
          ${modo.elegidos.size ? '' : 'disabled'}>Guardar</button>
        <button type="button" id="odo-cancelar-asig" class="rounded-lg border border-border px-3 py-1.5 text-xs cursor-pointer">Cancelar</button>
      </div>`;
    cont.querySelectorAll('button[data-accion="cara-asignar"]').forEach(b => b.addEventListener('click', () => {
      const set = modo.elegidos.get(Number(b.dataset.n));
      set.has(b.dataset.cara) ? set.delete(b.dataset.cara) : set.add(b.dataset.cara);
      pintarAsignando();
    }));
    document.getElementById('odo-guardar-asig').addEventListener('click', (ev) => {
      ev.currentTarget.disabled = true;
      guardarAsignacion();
    });
    document.getElementById('odo-cancelar-asig').addEventListener('click', () => { modo = null; pintar(); });
  }

  function diagramaCaras(d) {
    const real = new Set(), plan = new Set();
    d.tratamientos.forEach(t => {
      const caras = t.caras.length ? t.caras : CARAS;
      caras.forEach(c => (t.estatus === 'realizado' ? real : plan).add(c));
    });
    const cls = (c) => `odo-cara${real.has(c) ? ' real' : plan.has(c) ? ' plan' : ''}`;
    return `<svg viewBox="0 0 60 60" width="72" height="72" class="shrink-0">
      <polygon class="${cls('V')}" points="0,0 60,0 45,15 15,15"/>
      <polygon class="${cls('D')}" points="60,0 60,60 45,45 45,15"/>
      <polygon class="${cls('L')}" points="0,60 60,60 45,45 15,45"/>
      <polygon class="${cls('M')}" points="0,0 0,60 15,45 15,15"/>
      <rect class="${cls('O')}" x="15" y="15" width="30" height="30"/>
    </svg>`;
  }

  function pintarDiente() {
    const titulo = document.getElementById('odo-diente-titulo');
    const cont = document.getElementById('odo-diente');
    const d = seleccionado != null ? diente(seleccionado) : null;
    if (!d) {
      titulo.textContent = 'Diente';
      cont.innerHTML = 'Haz clic en un diente para ver su historial.';
      return;
    }
    titulo.textContent = `Diente ${d.numero} · ${d.estado.replace('_', ' ')}`;
    const historial = d.tratamientos.length ? d.tratamientos.map(t => `
      <li class="py-2 border-b border-border last:border-0">
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs font-medium text-text-primary">${esc(t.descripcion)}
            ${t.caras.length ? `<span class="text-text-muted">(${t.caras.map(c => etiquetaCara(d.numero, c)).join(', ')})</span>` : ''}</span>
          <span class="text-[10px] px-1.5 rounded-full ${t.estatus === 'realizado' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}">${t.estatus}</span>
        </div>
        <p class="text-[10px] text-text-muted">${t.fecha_realizado ? esc(t.fecha_realizado) + ' · ' : ''}${esc(t.especialista_nombre || 'Sin doctor')} · ${esc(t.origen || 'origen eliminado')}${t.origen_eliminado ? ' (eliminado)' : ''}</p>
        <div class="flex gap-3 mt-1">
          ${t.estatus === 'planeado' && puedeCapturar() ? `<button type="button" data-accion="realizar" data-id="${t.id}" class="text-[10px] font-bold text-emerald-600 hover:underline cursor-pointer">Marcar realizado</button>` : ''}
          ${esAdmin() ? `<button type="button" data-accion="editar" data-id="${t.id}" class="text-[10px] font-bold text-primary-600 hover:underline cursor-pointer">Editar</button>
          <button type="button" data-accion="desasignar" data-id="${t.id}" class="text-[10px] font-bold text-red-600 hover:underline cursor-pointer">Desasignar</button>` : ''}
        </div>
        <div data-editor="${t.id}"></div>
      </li>`).join('') : '<li class="py-2 text-xs text-text-muted">Sin tratamientos.</li>';

    const estadoAdmin = esAdmin() ? `
      <div class="flex items-center gap-2 pt-2">
        <select id="odo-estado" class="flex-1 rounded-lg border border-border px-2 py-1 text-xs bg-surface">
          ${ESTADOS.map(e => `<option value="${e}" ${e === d.estado ? 'selected' : ''}>${e.replace('_', ' ')}</option>`).join('')}
        </select>
        <button type="button" id="odo-guardar-estado" class="rounded-lg border border-border px-2 py-1 text-xs cursor-pointer">Cambiar estado</button>
      </div>` : '';

    cont.innerHTML = `<div class="flex gap-3 items-start">${diagramaCaras(d)}
      <ul class="flex-1 min-w-0">${historial}</ul></div>${estadoAdmin}`;

    cont.querySelectorAll('button[data-accion="realizar"]').forEach(b =>
      b.addEventListener('click', () => accion(() => API.post(`${URL_BASE}/asignaciones/${b.dataset.id}/realizar`, {}), 'Marcado como realizado')));
    cont.querySelectorAll('button[data-accion="desasignar"]').forEach(b =>
      b.addEventListener('click', () => accion(() => API.delete(`${URL_BASE}/asignaciones/${b.dataset.id}`), 'Tratamiento desasignado')));
    cont.querySelectorAll('button[data-accion="editar"]').forEach(b =>
      b.addEventListener('click', () => abrirEditor(d, d.tratamientos.find(t => t.id === Number(b.dataset.id)))));
    const btnEstado = document.getElementById('odo-guardar-estado');
    if (btnEstado) btnEstado.addEventListener('click', () => cambiarEstado(d));
  }

  function abrirEditor(d, t) {
    const caja = document.getElementById('odo-diente').querySelector(`[data-editor="${t.id}"]`);
    const caras = new Set(t.caras);
    const render = () => {
      caja.innerHTML = `<div class="mt-2 space-y-2 rounded-lg border border-border p-2">
        <div class="flex gap-1">${chipsCaras(d.numero, caras, 'cara-editar')}</div>
        ${t.estatus === 'realizado' ? `<input type="date" id="odo-ed-fecha" value="${t.fecha_realizado || ''}" class="rounded-lg border border-border px-2 py-1 text-xs bg-surface">` : ''}
        <button type="button" id="odo-ed-guardar" class="rounded-lg bg-primary-500 text-white px-3 py-1 text-xs cursor-pointer">Guardar cambios</button>
      </div>`;
      caja.querySelectorAll('button[data-accion="cara-editar"]').forEach(b => b.addEventListener('click', () => {
        caras.has(b.dataset.cara) ? caras.delete(b.dataset.cara) : caras.add(b.dataset.cara);
        render();
      }));
      caja.querySelector('#odo-ed-guardar').addEventListener('click', () => {
        const body = { caras: [...caras] };
        const f = caja.querySelector('#odo-ed-fecha');
        if (f && f.value) body.fecha_realizado = f.value;
        accion(() => API.put(`${URL_BASE}/asignaciones/${t.id}`, body), 'Tratamiento actualizado');
      });
    };
    render();
  }

  function pintar() {
    pintarEncabezado();
    pintarArcadas();
    pintarPendientes();
    pintarAsignando();
    pintarDiente();
    if (window.lucide) lucide.createIcons();
  }

  // ── Acciones ─────────────────────────────────────────────────────────────
  async function accion(llamada, mensaje, alFallar, alExito) {
    try {
      data = await llamada();
      if (alExito) alExito();
      Toast.success(mensaje);
      pintar();
    } catch (e) {
      Toast.error(e.message || 'No se pudo guardar');
      if (alFallar) alFallar();
    }
  }

  function clicDiente(n) {
    const d = diente(n);
    if (modo) {
      if (d.estado !== 'presente') return;
      const faltan = modo.pendiente.unidades - modo.pendiente.asignadas;
      if (modo.elegidos.has(n)) modo.elegidos.delete(n);
      else if (modo.elegidos.size >= faltan) { Toast.warning(`Solo faltan ${faltan} por asignar`); return; }
      else modo.elegidos.set(n, new Set());
      pintarArcadas();
      pintarAsignando();
      return;
    }
    seleccionado = n;
    pintarArcadas();
    pintarDiente();
  }

  function iniciarAsignacion(p) {
    modo = { pendiente: p, elegidos: new Map() };
    pintar();
  }

  function guardarAsignacion() {
    const p = modo.pendiente;
    const body = {
      origen_tipo: p.origen_tipo,
      origen_id: p.origen_id,
      dientes: [...modo.elegidos.entries()].map(([numero, caras]) => ({ numero, caras: [...caras] })),
    };
    accion(() => API.post(`${URL_BASE}/asignaciones`, body), 'Tratamiento asignado',
      () => pintarAsignando(), () => { modo = null; });
  }

  function cambiarEstado(d) {
    const estado = document.getElementById('odo-estado').value;
    if (estado === d.estado) return;
    const btn = document.getElementById('odo-guardar-estado');
    if (btn) btn.disabled = true;
    const fallo = () => { emerger = null; pintar(); };
    const llamar = () => accion(() => API.put(`${URL_BASE}/dientes/${d.numero}/estado`, { estado }),
      'Estado actualizado', fallo);
    if (!AUSENTES.includes(estado)) { llamar(); return; }
    // El diente "se cae" antes de repintar; si es temporal, su sucesor emerge.
    if (estado === 'exfoliado' && d.numero > 50) {
      emerger = (Math.floor(d.numero / 10) - 4) * 10 + (d.numero % 10);
    }
    const g = document.querySelector(`#odo-svg g[data-n="${d.numero}"]`);
    const reducir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (g && !reducir) { g.classList.add('cae'); setTimeout(llamar, 700); } else { llamar(); }
  }

  async function cargar() {
    try {
      data = await API.get(URL_BASE);
      pintar();
    } catch (e) { Toast.error(e.message || 'No se pudo cargar el odontograma'); }
  }

  return { cargar };
})();

document.addEventListener('DOMContentLoaded', () => Odonto.cargar());
