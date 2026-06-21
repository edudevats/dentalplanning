// Panel super-admin / Pagos
(function () {
  const { currency, formatDate, confirmAction, openModal,
          buildField, inputEl, selectEl, textareaEl } = window.adminUI;

  let tenantsCache = null;

  async function loadTenants() {
    if (!tenantsCache) {
      const data = await adminApi.get('/tenants');
      tenantsCache = data.tenants || [];
    }
    return tenantsCache;
  }

  async function populateTenantFilter() {
    const tenants = await loadTenants();
    const sel = document.getElementById('filter-tenant');
    tenants.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = t.name;
      sel.appendChild(opt);
    });
  }

  function getFilters() {
    return {
      tenant_id:   document.getElementById('filter-tenant').value,
      desde:       document.getElementById('filter-desde').value,
      hasta:       document.getElementById('filter-hasta').value,
      metodo:      document.getElementById('filter-metodo').value,
      clip_status: document.getElementById('filter-clip-status').value,
    };
  }

  async function refresh() {
    const f = getFilters();
    const params = new URLSearchParams();
    if (f.tenant_id) params.set('tenant_id', f.tenant_id);
    if (f.desde)     params.set('desde', f.desde);
    if (f.hasta)     params.set('hasta', f.hasta);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const data = await adminApi.get(`/payments${qs}`);
    let payments = data.payments || [];
    if (f.metodo) payments = payments.filter(p => p.metodo === f.metodo);
    if (f.clip_status) payments = payments.filter(p => p.clip_status === f.clip_status);
    renderRows(payments);
  }

  function renderRows(pagos) {
    const tbody = document.getElementById('pagos-rows');
    invDom.clearChildren(tbody);
    document.getElementById('empty-state').classList.toggle('hidden', pagos.length > 0);

    let total = 0;
    pagos.forEach(p => {
      total += Number(p.monto) || 0;
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-cs-surface-container transition-colors duration-200';

      const periodo = (p.periodo_inicio && p.periodo_fin)
        ? `${formatDate(p.periodo_inicio)} – ${formatDate(p.periodo_fin)}` : '—';

      const cells = [
        { v: formatDate(p.fecha) },
        { v: p.tenant_name || '—', cls: 'font-semibold text-cs-on-surface' },
        { v: currency(p.monto), cls: 'text-right font-cs-display font-semibold text-cs-on-surface' },
        { v: p.metodo },
        { v: p.clip_status || '—', badge: p.metodo === 'clip' && p.clip_status },
        { v: periodo },
        { v: p.comentarios || '—' },
      ];
      const BADGE_COLORS = {
        PAID:    'bg-green-500/15 text-green-400',
        PENDING: 'bg-yellow-500/15 text-yellow-400',
        FAILED:  'bg-red-500/15 text-red-400',
      };
      cells.forEach(({ v, cls, badge }) => {
        const td = document.createElement('td');
        td.className = `px-4 py-3 ${cls || 'text-cs-on-surface'}`;
        if (badge) {
          const span = document.createElement('span');
          span.className = `inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold uppercase ${BADGE_COLORS[v] || 'bg-cs-surface-container text-cs-on-surface-var'}`;
          span.textContent = v;
          td.appendChild(span);
        } else {
          td.textContent = v;
        }
        tr.appendChild(td);
      });

      const tdAct = document.createElement('td');
      tdAct.className = 'px-4 py-3 text-right';
      const del = document.createElement('button');
      del.className = 'text-cs-error text-xs font-semibold hover:underline cursor-pointer';
      del.textContent = 'Eliminar';
      del.addEventListener('click', () => onDelete(p));
      tdAct.appendChild(del);
      tr.appendChild(tdAct);

      tbody.appendChild(tr);
    });

    document.getElementById('total-pagos').textContent = currency(total);
    document.getElementById('conteo-pagos').textContent = `${pagos.length} pago${pagos.length === 1 ? '' : 's'}`;
  }

  async function onDelete(p) {
    const ok = await confirmAction({
      title: 'Eliminar pago',
      message: `¿Eliminar el pago de ${p.tenant_name || 'la clínica'} del ${formatDate(p.fecha)} por ${currency(p.monto)}?`,
      confirmLabel: 'Eliminar', destructive: true,
    });
    if (!ok) return;
    await adminApi.del(`/payments/${p.id}`);
    Toast.show('Pago eliminado', 'success');
    refresh();
  }

  async function openNewPayment() {
    const tenants = (await loadTenants()).filter(t => t.status === 'active');
    if (tenants.length === 0) {
      Toast.show('No hay clínicas activas para registrar un pago.', 'warning');
      return;
    }

    const wrap = document.createElement('div');
    wrap.className = 'grid grid-cols-1 md:grid-cols-2 gap-4';

    const tenantSel = selectEl('tenant_id', tenants.map(t => ({ value: t.id, label: t.name })));
    const today = new Date().toISOString().slice(0, 10);
    const fecha = inputEl('date', 'fecha', today);
    const monto = inputEl('number', 'monto', '');
    monto.step = '0.01'; monto.min = '0';
    const metodo = selectEl('metodo', [
      { value: 'transferencia', label: 'Transferencia' },
      { value: 'efectivo', label: 'Efectivo' },
      { value: 'tarjeta', label: 'Tarjeta' },
      { value: 'clip', label: 'Clip' },
      { value: 'otro', label: 'Otro' },
    ]);
    const pIni = inputEl('date', 'periodo_inicio', '');
    const pFin = inputEl('date', 'periodo_fin', '');
    const comen = textareaEl('comentarios', '', 2);

    wrap.appendChild(buildField('Clínica', tenantSel));
    wrap.appendChild(buildField('Fecha del pago', fecha));
    wrap.appendChild(buildField('Monto (MXN)', monto));
    wrap.appendChild(buildField('Método', metodo));
    wrap.appendChild(buildField('Periodo desde', pIni));
    wrap.appendChild(buildField('Periodo hasta', pFin));
    const fullCol = document.createElement('div');
    fullCol.className = 'md:col-span-2';
    fullCol.appendChild(buildField('Comentarios', comen));
    wrap.appendChild(fullCol);

    openModal({
      title: 'Registrar pago',
      content: wrap,
      primary: { label: 'Registrar', onClick: async () => {
        if (!fecha.value || !monto.value || parseFloat(monto.value) <= 0) {
          throw new Error('Fecha y monto son obligatorios.');
        }
        await adminApi.post('/payments', {
          tenant_id: parseInt(tenantSel.value, 10),
          fecha: fecha.value,
          monto: parseFloat(monto.value),
          metodo: metodo.value,
          periodo_inicio: pIni.value || undefined,
          periodo_fin: pFin.value || undefined,
          comentarios: comen.value || undefined,
        });
        Toast.show('Pago registrado', 'success');
        refresh();
      } },
    });
  }

  function wireFilters() {
    let timer;
    const onChange = () => {
      clearTimeout(timer);
      timer = setTimeout(refresh, 100);
    };
    document.getElementById('filter-tenant').addEventListener('change', onChange);
    document.getElementById('filter-desde').addEventListener('change', onChange);
    document.getElementById('filter-hasta').addEventListener('change', onChange);
    document.getElementById('filter-metodo').addEventListener('change', onChange);
    document.getElementById('filter-clip-status').addEventListener('change', onChange);

    document.getElementById('btn-clear-filters').addEventListener('click', () => {
      document.getElementById('filter-tenant').value = '';
      document.getElementById('filter-desde').value = '';
      document.getElementById('filter-hasta').value = '';
      document.getElementById('filter-metodo').value = '';
      document.getElementById('filter-clip-status').value = '';
      refresh();
    });

    document.getElementById('btn-nuevo-pago').addEventListener('click', openNewPayment);
    document.getElementById('btn-sync-clip').addEventListener('click', onSyncClip);
    document.getElementById('btn-export-csv').addEventListener('click', () => {
      const f = getFilters();
      const params = new URLSearchParams();
      if (f.tenant_id) params.set('tenant_id', f.tenant_id);
      if (f.desde) params.set('desde', f.desde);
      if (f.hasta) params.set('hasta', f.hasta);
      if (f.metodo) params.set('metodo', f.metodo);
      if (f.clip_status) params.set('clip_status', f.clip_status);
      const qs = params.toString() ? `?${params.toString()}` : '';
      adminApi.download(`/payments/export.csv${qs}`, 'pagos.csv');
    });
  }

  function setBtnContent(btn, iconName, label, spin) {
    while (btn.firstChild) btn.removeChild(btn.firstChild);
    const icon = document.createElement('i');
    icon.setAttribute('data-lucide', iconName);
    icon.className = 'h-4 w-4' + (spin ? ' animate-spin' : '');
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(' ' + label));
    if (window.lucide) window.lucide.createIcons();
  }

  async function onSyncClip() {
    const btn = document.getElementById('btn-sync-clip');
    btn.disabled = true;
    setBtnContent(btn, 'loader-2', 'Verificando...', true);

    try {
      const res = await adminApi.post('/payments/sync-clip', {});
      const u = res.updated || [];
      const e = res.errors || [];
      let msg;
      if (u.length === 0 && e.length === 0) {
        msg = `Sin cambios (${res.checked} pagos revisados).`;
      } else {
        const paidCount = u.filter(x => x.to === 'PAID').length;
        const otherCount = u.length - paidCount;
        msg = `Revisados: ${res.checked} · Marcados PAID: ${paidCount}`;
        if (otherCount) msg += ` · Otros cambios: ${otherCount}`;
        if (e.length) msg += ` · Errores: ${e.length}`;
      }
      Toast.show(msg, u.length > 0 ? 'success' : 'info');
      if (e.length) console.warn('Clip sync errors:', e);
      await refresh();
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al verificar con Clip', 'error');
    } finally {
      btn.disabled = false;
      setBtnContent(btn, 'refresh-cw', 'Verificar con Clip', false);
    }
  }

  async function init() {
    wireFilters();
    try {
      await populateTenantFilter();
      await refresh();
    } catch (err) {
      console.error(err);
      Toast.show(err.message || 'Error al cargar pagos', 'error');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
