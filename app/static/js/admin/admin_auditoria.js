// Panel super-admin / Auditoría
(function () {
  const { formatDate } = window.adminUI;

  function getFilters() {
    return {
      action: document.getElementById('filter-action').value,
      desde: document.getElementById('filter-desde').value,
      hasta: document.getElementById('filter-hasta').value,
    };
  }

  async function refresh() {
    const f = getFilters();
    const params = new URLSearchParams();
    if (f.action) params.set('action', f.action);
    if (f.desde) params.set('desde', f.desde);
    if (f.hasta) params.set('hasta', f.hasta);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const data = await adminApi.get(`/audit${qs}`);
    renderRows(data.events || []);
  }

  function renderRows(events) {
    const tbody = document.getElementById('audit-rows');
    invDom.clearChildren(tbody);
    document.getElementById('empty-state').classList.toggle('hidden', events.length > 0);
    events.forEach(e => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors duration-200';
      const clinic = document.createElement('td');
      clinic.className = 'px-4 py-2.5';
      if (e.tenant_id) {
        const a = document.createElement('a');
        a.href = `/admin/tenants/${e.tenant_id}`;
        a.className = 'text-cs-primary hover:underline';
        a.textContent = e.tenant_name || `#${e.tenant_id}`;
        clinic.appendChild(a);
      } else {
        clinic.textContent = '—';
        clinic.classList.add('text-cs-on-surface-var');
      }
      const make = (v) => {
        const td = document.createElement('td');
        td.className = 'px-4 py-2.5 text-cs-on-surface';
        td.textContent = v;
        return td;
      };
      tr.appendChild(make(formatDate(e.created_at)));
      tr.appendChild(make(e.actor_name || '—'));
      tr.appendChild(make(e.action));
      tr.appendChild(clinic);
      tr.appendChild(make(e.summary || '—'));
      tbody.appendChild(tr);
    });
  }

  function init() {
    ['filter-action', 'filter-desde', 'filter-hasta'].forEach(id => {
      document.getElementById(id).addEventListener('change', () => refresh().catch(err => Toast.show(err.message, 'error')));
    });
    document.getElementById('btn-clear').addEventListener('click', () => {
      document.getElementById('filter-action').value = '';
      document.getElementById('filter-desde').value = '';
      document.getElementById('filter-hasta').value = '';
      refresh().catch(err => Toast.show(err.message, 'error'));
    });
    refresh().catch(err => { console.error(err); Toast.show(err.message || 'Error al cargar auditoría', 'error'); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
