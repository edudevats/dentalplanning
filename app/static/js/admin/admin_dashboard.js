// Panel super-admin / Dashboard
(function () {
  const { kpiCard, currency, formatMonth, statusBadge } = window.adminUI;

  let mrrChart = null;

  async function loadKpis() {
    const data = await adminApi.get('/stats/overview');
    const grid = document.getElementById('kpi-grid');
    invDom.clearChildren(grid);
    grid.appendChild(kpiCard({
      label: 'Clínicas totales',
      value: data.total_tenants,
      icon: 'building-2',
    }));
    grid.appendChild(kpiCard({
      label: 'Activas',
      value: data.activos,
      icon: 'check-circle',
      hint: `${data.suspendidos} suspendidas, ${data.rechazados} rechazadas`,
    }));
    grid.appendChild(kpiCard({
      label: 'Pendientes',
      value: data.pendientes,
      icon: 'hourglass',
      hint: 'Esperando aprobación',
    }));
    grid.appendChild(kpiCard({
      label: 'Nuevas este mes',
      value: data.nuevos_este_mes,
      icon: 'sparkles',
      hint: `${data.total_users} usuarios totales`,
    }));

    if (data.en_gracia > 0) {
      grid.appendChild(kpiCard({
        label: 'En gracia',
        value: data.en_gracia,
        icon: 'clock',
        hint: 'Cobro pendiente, en periodo de gracia',
      }));
    }

    if (data.subs_by_plan && data.subs_by_plan.length > 0) {
      const planHint = data.subs_by_plan.map(s => `${s.plan}: ${s.count}`).join(', ');
      grid.appendChild(kpiCard({
        label: 'Suscripciones',
        value: data.subs_by_plan.reduce((sum, s) => sum + s.count, 0),
        icon: 'credit-card',
        hint: planHint,
      }));
    }

    await loadSolicitudesPendientes(grid);

    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  async function loadSolicitudesPendientes(grid) {
    try {
      const r = await adminApi.get('/asientos?estado=pendiente');
      const n = (r.asientos || []).length;
      grid.appendChild(adminUI.kpiCard({
        label: 'Solicitudes recepcionista',
        value: String(n),
        icon: 'user-plus',
        hint: n ? 'Pendientes de aprobar' : 'Sin pendientes',
      }));
    } catch (_) {}
  }

  async function loadMrr() {
    const data = await adminApi.get('/stats/mrr');
    document.getElementById('mrr-actual').textContent = currency(data.mrr_actual);
    const labels = data.serie.map(p => formatMonth(p.mes + '-01'));
    const values = data.serie.map(p => p.total);

    const ctx = document.getElementById('mrr-chart').getContext('2d');
    if (mrrChart) mrrChart.destroy();
    mrrChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'MRR',
          data: values,
          borderColor: '#005db6',
          backgroundColor: 'rgba(0, 93, 182, 0.12)',
          tension: 0.35,
          fill: true,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: '#005db6',
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: (c) => currency(c.parsed.y) },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: (v) => currency(v) },
            grid: { color: 'rgba(138, 145, 153, 0.15)' },
          },
          x: { grid: { display: false } },
        },
      },
    });
  }

  function saludGroup({ title, icon, rows, valueKey, emptyLabel }) {
    const { formatDate } = window.adminUI;
    const wrap = document.createElement('div');
    wrap.className = 'space-y-2';

    const head = document.createElement('div');
    head.className = 'flex items-center gap-2';
    const ic = document.createElement('span');
    const critical = rows.length > 0;
    ic.className = `inline-flex items-center justify-center w-7 h-7 rounded-md ${critical ? 'bg-cs-error-container/40 text-cs-on-error-container' : 'bg-cs-primary-container text-cs-on-primary-container'}`;
    const i = document.createElement('i');
    i.setAttribute('data-lucide', icon);
    i.className = 'h-3.5 w-3.5';
    ic.appendChild(i);
    const tx = document.createElement('span');
    tx.className = 'text-sm font-semibold text-cs-on-surface';
    tx.textContent = `${title} (${rows.length})`;
    head.appendChild(ic);
    head.appendChild(tx);
    wrap.appendChild(head);

    if (rows.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'text-xs text-cs-on-surface-var pl-9';
      empty.textContent = emptyLabel || 'Sin clínicas en este grupo.';
      wrap.appendChild(empty);
      return wrap;
    }

    rows.forEach(r => {
      const a = document.createElement('a');
      a.href = `/admin/tenants/${r.tenant_id}`;
      a.className = 'flex items-center justify-between gap-2 px-3 py-2 rounded-md bg-cs-surface-container hover:bg-cs-surface-container-high transition-colors';
      const left = document.createElement('span');
      left.className = 'text-sm text-cs-on-surface truncate';
      left.textContent = r.tenant_name || '—';
      const right = document.createElement('span');
      right.className = 'text-xs text-cs-on-surface-var shrink-0';
      const dateStr = r[valueKey];
      right.textContent = dateStr ? formatDate(dateStr) : '—';
      a.appendChild(left);
      a.appendChild(right);
      wrap.appendChild(a);
    });
    return wrap;
  }

  async function loadSalud() {
    const data = await adminApi.get('/stats/salud');
    const list = document.getElementById('salud-list');
    invDom.clearChildren(list);

    // Cola de aprobación: enlace directo a la lista filtrada
    if (data.cola_pendientes > 0) {
      const a = document.createElement('a');
      a.href = '/admin/tenants?status=pending';
      a.className = 'flex items-center justify-between gap-3 px-3 py-3 rounded-lg bg-cs-error-container/40 text-cs-on-error-container hover:opacity-90 transition-opacity';
      const lbl = document.createElement('span');
      lbl.className = 'text-sm font-semibold';
      lbl.textContent = 'Cola de aprobación';
      const v = document.createElement('span');
      v.className = 'font-cs-display text-xl font-bold';
      v.textContent = data.cola_pendientes;
      a.appendChild(lbl);
      a.appendChild(v);
      list.appendChild(a);
    }

    list.appendChild(saludGroup({
      title: 'En mora', icon: 'alert-triangle',
      rows: data.en_mora_list || [], valueKey: 'proximo_cobro',
    }));
    list.appendChild(saludGroup({
      title: 'En gracia', icon: 'clock',
      rows: data.en_gracia_list || [], valueKey: 'grace_expires_at',
    }));
    list.appendChild(saludGroup({
      title: 'Por vencer (7 días)', icon: 'calendar-clock',
      rows: data.por_vencer_7d_list || [], valueKey: 'proximo_cobro',
    }));

    if (typeof lucide !== 'undefined') lucide.createIcons();
  }

  async function loadUso(metric) {
    const data = await adminApi.get(`/stats/uso?metric=${encodeURIComponent(metric)}`);
    const tbody = document.getElementById('uso-rows');
    invDom.clearChildren(tbody);
    if (!data.top || data.top.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.className = 'py-6 text-center text-sm text-cs-on-surface-var';
      td.textContent = 'Sin datos todavía';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    data.top.forEach((row, idx) => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors';

      const tdNum = document.createElement('td');
      tdNum.className = 'py-2.5 pr-2 text-cs-on-surface-var font-mono text-xs';
      tdNum.textContent = String(idx + 1).padStart(2, '0');

      const tdName = document.createElement('td');
      tdName.className = 'py-2.5 pr-2 text-cs-on-surface font-medium';
      tdName.textContent = row.tenant_name;

      const tdCount = document.createElement('td');
      tdCount.className = 'py-2.5 pr-2 text-right font-cs-display font-semibold text-cs-on-surface';
      tdCount.textContent = row.count;

      const tdLink = document.createElement('td');
      tdLink.className = 'py-2.5 text-right';
      const a = document.createElement('a');
      a.href = `/admin/tenants/${row.tenant_id}`;
      a.className = 'inline-flex items-center gap-1 text-cs-primary text-xs font-semibold hover:underline';
      a.textContent = 'Ver';
      tdLink.appendChild(a);

      tr.appendChild(tdNum);
      tr.appendChild(tdName);
      tr.appendChild(tdCount);
      tr.appendChild(tdLink);
      tbody.appendChild(tr);
    });
  }

  async function init() {
    try {
      await Promise.all([loadKpis(), loadMrr(), loadSalud(), loadUso('tratamientos')]);
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al cargar el dashboard', 'error');
    }
    document.getElementById('uso-metric').addEventListener('change', (e) => {
      loadUso(e.target.value).catch(err => Toast.show(err.message, 'error'));
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
