// Dashboard screen — the main "Estado de Resultados Personal" view

function MonthSelector({ value, onChange }) {
  const months = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, background: '#fff', border: '1px solid #e2e8f0',
        borderRadius: 8, padding: '8px 14px', minHeight: 38, fontSize: 14, fontFamily: 'var(--font-body)',
        fontWeight: 500, color: '#164e63', cursor: 'pointer',
      }}>
        <Icon name="calendar" size={16} color="#0e7490" />
        {months[value]} 2026
        <Icon name="chevron-down" size={14} color="#94a3b8" />
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 44, left: 0, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, boxShadow: '0 10px 25px -5px rgb(0 0 0 / .1)', padding: 6, zIndex: 10, minWidth: 180 }}>
          {months.map((m, i) => (
            <button key={i} onClick={() => { onChange(i); setOpen(false); }} style={{
              display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 6,
              border: 'none', background: i === value ? '#ecfeff' : 'transparent', color: i === value ? '#0e7490' : '#164e63',
              fontSize: 14, fontFamily: 'var(--font-body)', cursor: 'pointer',
            }}>{m}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function InsightStrip({ summary }) {
  return (
    <div style={{
      background: 'linear-gradient(90deg, #ecfeff 0%, #d1fae5 100%)',
      border: '1px solid #a7f3d0', borderRadius: 12, padding: '14px 18px',
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{ width: 40, height: 40, borderRadius: 10, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name="sparkles" size={20} color="#059669" />
      </div>
      <div style={{ flex: 1, fontSize: 14, color: '#065f46', fontFamily: 'var(--font-body)', lineHeight: 1.5 }}>
        Llevas <b>{fmt(summary.balance)}</b> ahorrados este mes — <b>{summary.ahorroPct}%</b> de tus ingresos. Vas <b>3% por encima</b> de tu meta. Sigue así.
      </div>
      <button style={{ background: 'transparent', border: 'none', color: '#065f46', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, fontFamily: 'var(--font-body)', fontWeight: 600 }}>
        Ver detalle <Icon name="arrow-right" size={14} />
      </button>
    </div>
  );
}

function CategoryListItem({ cat, total }) {
  const pct = total ? Math.round((cat.value / total) * 100) : 0;
  return (
    <a href="category-detail.html" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid #f1f5f9', textDecoration: 'none', cursor: 'pointer' }}
       onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
       onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <div style={{ width: 36, height: 36, borderRadius: 10, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={cat.icon} size={16} color={cat.color} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', fontFamily: 'var(--font-body)' }}>{cat.label}</div>
        <div style={{ height: 4, background: '#f1f5f9', borderRadius: 9999, marginTop: 6, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: pct + '%', background: cat.color, borderRadius: 9999 }} />
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#164e63', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>{fmt(cat.value)}</div>
        <div style={{ fontSize: 11, color: '#94a3b8', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>{pct}%</div>
      </div>
    </a>
  );
}

function MovementRow({ m, isIncome }) {
  const cat = isIncome ? INCOME_SOURCES.find(s => s.id === m.source) : CATEGORIES.find(c => c.id === m.cat);
  const color = isIncome ? '#059669' : '#dc2626';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid #f1f5f9' }}>
      <div style={{ width: 38, height: 38, borderRadius: 10, background: isIncome ? '#d1fae5' : (cat?.color || '#94a3b8') + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={cat?.icon || 'circle'} size={16} color={isIncome ? '#059669' : cat?.color || '#475569'} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', fontFamily: 'var(--font-body)' }}>{m.concepto}</div>
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>
          {cat?.label} · {new Date(m.fecha).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
        </div>
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>
        {isIncome ? '+' : '−'}{fmt(m.monto)}
      </div>
    </div>
  );
}

function Dashboard({ onAdd }) {
  const [month, setMonth] = useState(3);
  const summary = buildSummary();
  const recent = [
    ...INGRESOS.map(i => ({ ...i, _income: true })),
    ...GASTOS.map(g => ({ ...g, _income: false })),
  ].sort((a, b) => b.fecha.localeCompare(a.fecha)).slice(0, 6);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Estado de Resultados Personal</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4, fontFamily: 'var(--font-body)' }}>Resumen del mes — saldo inicial {fmt(SALDO_INICIAL)}</div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <MonthSelector value={month} onChange={setMonth} />
          <Button variant="secondary" icon="filter" size="md">Filtros</Button>
        </div>
      </div>

      {/* Insight strip */}
      <InsightStrip summary={summary} />

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard label="Ingresos" value={fmt(summary.totalIngresos)} icon="trending-up" valueColor="#065f46" sub="vs mes anterior" trend={10} />
        <StatCard label="Gastos" value={fmt(summary.totalGastos)} icon="trending-down" valueColor="#164e63" sub="vs mes anterior" trend={-3} />
        <StatCard label="Balance" value={fmt(summary.balance)} icon="wallet" valueColor={summary.balance >= 0 ? '#0e7490' : '#dc2626'} sub="ingresos − gastos" />
        <StatCard label="Ahorro" value={summary.ahorroPct + '%'} icon="piggy-bank" valueColor="#0e7490" sub={`meta ${Math.round(META_AHORRO/summary.totalIngresos*100)}%`} />
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 20 }}>
        {/* Pie + legend */}
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Gastos por categoría</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>Abril 2026</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24, padding: '12px 20px 20px' }}>
            <Donut data={summary.byCat.map(c => ({ value: c.value, color: c.color }))} size={180} />
            <div style={{ flex: 1 }}>
              <CategoryLegend data={summary.byCat.map(c => ({ label: c.label, value: c.value, color: c.color }))} />
            </div>
          </div>
        </Card>
        {/* Bar */}
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ingresos vs Gastos</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>Últimos 6 meses</div>
          </div>
          <div style={{ padding: '4px 14px 16px' }}>
            <BarChart data={HISTORY_6M} height={220} />
          </div>
          <div style={{ display: 'flex', gap: 18, padding: '0 20px 18px', fontSize: 12, fontFamily: 'var(--font-body)', color: '#475569' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 2, background: '#0891b2' }} /> Ingresos</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 2, background: '#ef4444' }} /> Gastos</span>
          </div>
        </Card>
      </div>

      {/* Bottom row: top categorías + last movements */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Top categorías</div>
            <a href="#" style={{ fontSize: 13, color: '#0e7490', textDecoration: 'none', fontWeight: 500 }}>Ver todas</a>
          </div>
          <div style={{ padding: '4px 20px 16px' }}>
            {summary.byCat.slice(0, 5).map(c => <CategoryListItem key={c.id} cat={c} total={summary.totalGastos} />)}
          </div>
        </Card>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Últimos movimientos</div>
            <a href="#" style={{ fontSize: 13, color: '#0e7490', textDecoration: 'none', fontWeight: 500 }}>Ver historial</a>
          </div>
          <div>
            {recent.map((m, i) => <MovementRow key={i} m={m} isIncome={m._income} />)}
          </div>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { Dashboard, MonthSelector, InsightStrip, CategoryListItem, MovementRow });
