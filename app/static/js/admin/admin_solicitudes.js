// Panel super-admin / Bandeja de asientos de recepcionista
(function () {
  const VALID_ESTADOS = ['', 'pendiente', 'aprobada', 'activa', 'rechazada', 'cancelada'];

  let currentEstado = 'pendiente';

  // Sin el parámetro se queda en "pendiente", que es la vista de trabajo.
  // Con el parámetro vacío (?estado=) significa "Todas".
  function readEstadoFromUrl() {
    const p = new URL(window.location.href).searchParams;
    if (!p.has('estado')) return;
    const estado = p.get('estado') || '';
    currentEstado = VALID_ESTADOS.includes(estado) ? estado : 'pendiente';
  }

  // replaceState y no pushState: filtrar no debe llenar el historial.
  function syncUrl() {
    window.history.replaceState(null, '', `?estado=${encodeURIComponent(currentEstado)}`);
  }

  function onChange() {
    refresh().catch(err => {
      invDom.clearChildren(document.getElementById('asientos-rows'));
      Toast.show(err.message || 'Error al cargar los asientos', 'error');
    });
  }

  async function refresh() {
    const qs = currentEstado ? `?estado=${encodeURIComponent(currentEstado)}` : '';
    const data = await adminApi.get(`/asientos${qs}`);
    const asientos = data.asientos || [];

    const cont = document.getElementById('asientos-rows');
    invDom.clearChildren(cont);
    document.getElementById('empty-state').classList.toggle('hidden', asientos.length > 0);

    asientos.forEach(a => cont.appendChild(
      window.adminAsientos.renderRow(a, { onChange, showTenant: true })
    ));
  }

  function wireChips() {
    document.querySelectorAll('.estado-chip').forEach(chip => {
      chip.classList.toggle('active', chip.dataset.estado === currentEstado);
      chip.addEventListener('click', () => {
        document.querySelectorAll('.estado-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentEstado = chip.dataset.estado;
        syncUrl();
        onChange();
      });
    });
  }

  async function init() {
    readEstadoFromUrl();
    syncUrl();
    wireChips();
    try {
      await refresh();
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al cargar los asientos', 'error');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
