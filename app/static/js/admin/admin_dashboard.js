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

    if (typeof lucide !== 'undefined') lucide.createIcons();
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

  async function loadSalud() {
    const data = await adminApi.get('/stats/salud');
    const list = document.getElementById('salud-list');
    invDom.clearChildren(list);

    const items = [
      {
        icon: 'hourglass',
        label: 'Cola de aprobación',
        value: data.cola_pendientes,
        href: '/admin/tenants?status=pending',
        critical: data.cola_pendientes > 0,
      },
      {
        icon: 'alert-triangle',
        label: 'Suscripciones en mora',
        value: data.en_mora,
        href: '/admin/tenants',
        critical: data.en_mora > 0,
      },
      {
        icon: 'clock',
        label: 'En periodo de gracia',
        value: data.en_gracia,
        href: '/admin/tenants',
        critical: data.en_gracia > 0,
      },
    ];

    items.forEach(item => {
      const a = document.createElement('a');
      a.href = item.href;
      a.className = 'flex items-center justify-between gap-3 px-3 py-3 rounded-lg bg-cs-surface-container hover:bg-cs-surface-container-high transition-colors duration-200';
      const left = document.createElement('div');
      left.className = 'flex items-center gap-3 min-w-0';
      const ic = document.createElement('span');
      const icBg = item.critical && item.value > 0
        ? 'bg-cs-error-container/40 text-cs-on-error-container'
        : 'bg-cs-primary-container text-cs-on-primary-container';
      ic.className = `inline-flex items-center justify-center w-9 h-9 rounded-md ${icBg}`;
      const i = document.createElement('i');
      i.setAttribute('data-lucide', item.icon);
      i.className = 'h-4 w-4';
      ic.appendChild(i);
      const tx = document.createElement('span');
      tx.className = 'text-sm font-medium text-cs-on-surface truncate';
      tx.textContent = item.label;
      left.appendChild(ic);
      left.appendChild(tx);

      const v = document.createElement('span');
      v.className = 'font-cs-display text-xl font-bold text-cs-on-surface';
      v.textContent = item.value;

      a.appendChild(left);
      a.appendChild(v);
      list.appendChild(a);
    });

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
