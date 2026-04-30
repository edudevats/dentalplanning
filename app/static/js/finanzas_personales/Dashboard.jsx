const { useEffect } = React;

function MonthSelector({ year, month, onChange }) {
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
        {months[month - 1]} {year}
        <Icon name="chevron-down" size={14} color="#94a3b8" />
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 44, left: 0, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, boxShadow: '0 10px 25px -5px rgb(0 0 0 / .1)', padding: 6, zIndex: 10, minWidth: 180 }}>
          {months.map((m, i) => (
            <button key={i} onClick={() => { onChange(year, i + 1); setOpen(false); }} style={{
              display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 6,
              border: 'none', background: (i + 1) === month ? '#ecfeff' : 'transparent', color: (i + 1) === month ? '#0e7490' : '#164e63',
              fontSize: 14, fontFamily: 'var(--font-body)', cursor: 'pointer',
            }}>{m}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function InsightStrip({ insight }) {
  if (!insight) return null;
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
        {insight}
      </div>
    </div>
  );
}

function CategoryListItem({ cat }) {
  return (
    <a href={`/finanzas-personales/categoria/${cat.id}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid #f1f5f9', textDecoration: 'none' }}>
      <div style={{ width: 36, height: 36, borderRadius: 10, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={cat.icon} size={16} color={cat.color} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', fontFamily: 'var(--font-body)' }}>{cat.label}</div>
        <div style={{ height: 4, background: '#f1f5f9', borderRadius: 9999, marginTop: 6, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: cat.pct + '%', background: cat.color, borderRadius: 9999 }} />
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#164e63', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>{fmt(cat.value)}</div>
        <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>{cat.pct}%</div>
      </div>
    </a>
  );
}

function MovementRow({ m }) {
  const isIncome = m.kind === 'ingreso';
  const color = isIncome ? '#059669' : '#dc2626';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid #f1f5f9' }}>
      <div style={{ width: 38, height: 38, borderRadius: 10, background: (m.color || '#94a3b8') + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={m.icon || 'circle'} size={16} color={m.color || '#475569'} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', fontFamily: 'var(--font-body)' }}>{m.concepto}</div>
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>
          {m.label} · {new Date(m.fecha).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
        </div>
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>
        {isIncome ? '+' : '−'}{fmt(m.monto)}
      </div>
    </div>
  );
}

function Dashboard() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    FP.dashboard(year, month)
      .then(s => { setSummary(s); setLoading(false); window.lucide && window.lucide.createIcons(); })
      .catch(err => { console.error(err); setLoading(false); });
  }, [year, month]);

  if (loading || !summary) {
    return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)' }}>Cargando…</div>;
  }

  const t = summary.totals;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Estado de Resultados Personal</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4, fontFamily: 'var(--font-body)' }}>Resumen del mes</div>
        </div>
        <MonthSelector year={year} month={month} onChange={(y, m) => { setYear(y); setMonth(m); }} />
      </div>

      <InsightStrip insight={summary.insight} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard label="Ingresos" value={fmt(t.ingresos)} icon="trending-up"  valueColor="#065f46" sub="vs mes anterior" trend={summary.trends.ingresos} />
        <StatCard label="Gastos"   value={fmt(t.gastos)}   icon="trending-down" valueColor="#164e63" sub="vs mes anterior" trend={summary.trends.gastos} />
        <StatCard label="Balance"  value={fmt(t.balance)}  icon="wallet"        valueColor={t.balance >= 0 ? '#0e7490' : '#dc2626'} sub="ingresos − gastos" />
        <StatCard label="Ahorro"   value={t.ahorroPct + '%'} icon="piggy-bank"  valueColor="#0e7490" sub="del ingreso del mes" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Gastos por categoria</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24, padding: '12px 20px 20px' }}>
            <Donut data={summary.byCat.map(c => ({ value: c.value, color: c.color }))} size={180} />
            <div style={{ flex: 1 }}>
              <CategoryLegend data={summary.byCat.map(c => ({ label: c.label, value: c.value, color: c.color }))} />
            </div>
          </div>
        </Card>
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ingresos vs Gastos</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>Ultimos 6 meses</div>
          </div>
          <div style={{ padding: '4px 14px 16px' }}>
            <BarChart data={summary.history6m} height={220} />
          </div>
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Top categorias</div>
          </div>
          <div style={{ padding: '4px 20px 16px' }}>
            {summary.byCat.slice(0, 5).map(c => <CategoryListItem key={c.id} cat={c} />)}
            {summary.byCat.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin gastos este mes</div>}
          </div>
        </Card>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ultimos movimientos</div>
            <a href="/finanzas-personales/historial" style={{ fontSize: 13, color: '#0e7490', textDecoration: 'none', fontWeight: 500 }}>Ver historial</a>
          </div>
          <div>
            {summary.recent.map(m => <MovementRow key={m.id} m={m} />)}
            {summary.recent.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin movimientos este mes</div>}
          </div>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { Dashboard, MonthSelector, InsightStrip, CategoryListItem, MovementRow });
