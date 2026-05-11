// Three more screens: Category Detail, Transaction History, Metas

function CategoryDetail() {
  const cat = CATEGORIES.find(c => c.id === 'comida');
  const movs = GASTOS.filter(g => g.cat === cat.id).sort((a,b) => b.fecha.localeCompare(a.fecha));
  const total = movs.reduce((s,g) => s + g.monto, 0);
  const lastMonth = 5230;
  const trend = Math.round(((total - lastMonth) / lastMonth) * 100);
  const budget = 5000;
  const pct = Math.min(total / budget, 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Breadcrumb + header */}
      <div>
        <a href="index.html" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#0e7490', textDecoration: 'none', fontFamily: 'var(--font-body)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="arrow-left" size={14} /> Volver al resumen
        </a>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name={cat.icon} size={26} color={cat.color} />
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{cat.label}</div>
            <div style={{ fontSize: 13, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 2 }}>Abril 2026 · {movs.length} movimientos</div>
          </div>
        </div>
      </div>

      {/* Hero stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', gap: 16 }}>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>GASTADO ESTE MES</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 8 }}>
            <span style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em' }}>{fmt(total)}</span>
            <span style={{ fontSize: 13, color: trend >= 0 ? '#dc2626' : '#059669', fontWeight: 600, fontFamily: 'var(--font-body)' }}>
              {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}% vs marzo
            </span>
          </div>
          {/* budget progress */}
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#475569', fontFamily: 'var(--font-body)', marginBottom: 6 }}>
              <span>Presupuesto mensual</span>
              <span style={{ fontVariantNumeric: 'tabular-nums' }}><b style={{ color: '#164e63' }}>{fmt(total)}</b> de {fmt(budget)}</span>
            </div>
            <div style={{ height: 8, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: pct * 100 + '%', background: pct > 0.9 ? '#ef4444' : pct > 0.75 ? '#f59e0b' : cat.color, borderRadius: 9999 }} />
            </div>
            <div style={{ fontSize: 11, color: pct > 0.9 ? '#dc2626' : '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 6 }}>
              {pct > 0.9 ? 'Estás cerca del límite' : `Te quedan ${fmt(budget - total)} disponibles`}
            </div>
          </div>
        </Card>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>PROMEDIO DIARIO</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{fmt(total / 28)}</div>
          <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 4 }}>basado en 28 días</div>
        </Card>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>GASTO MÁS GRANDE</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{fmt(Math.max(...movs.map(m => m.monto)))}</div>
          <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 4 }}>{movs.find(m => m.monto === Math.max(...movs.map(x => x.monto)))?.concepto}</div>
        </Card>
      </div>

      {/* 6-month spark */}
      <Card padding={0}>
        <div style={{ padding: '20px 20px 8px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Evolución</div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>Últimos 6 meses · {cat.label}</div>
        </div>
        <div style={{ padding: '4px 14px 20px' }}>
          <BarChart data={[
            { name: 'Nov', ingresos: 0, gastos: 4200 },
            { name: 'Dic', ingresos: 0, gastos: 6100 },
            { name: 'Ene', ingresos: 0, gastos: 4800 },
            { name: 'Feb', ingresos: 0, gastos: 5400 },
            { name: 'Mar', ingresos: 0, gastos: 5230 },
            { name: 'Abr', ingresos: 0, gastos: total },
          ]} height={180} />
        </div>
      </Card>

      {/* Movements list */}
      <Card padding={0}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Todos los movimientos</div>
          <Badge variant="info">{movs.length} este mes</Badge>
        </div>
        <div>
          {movs.map(m => <MovementRow key={m.id} m={m} isIncome={false} />)}
        </div>
      </Card>
    </div>
  );
}

function TransactionHistory() {
  const [filter, setFilter] = React.useState('todos');
  const [search, setSearch] = React.useState('');
  const all = [
    ...INGRESOS.map(i => ({ ...i, _income: true })),
    ...GASTOS.map(g => ({ ...g, _income: false })),
  ].sort((a, b) => b.fecha.localeCompare(a.fecha));
  const filtered = all.filter(m => {
    if (filter === 'ingresos' && !m._income) return false;
    if (filter === 'gastos' && m._income) return false;
    if (search && !m.concepto.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  // Group by date
  const groups = filtered.reduce((acc, m) => {
    (acc[m.fecha] ??= []).push(m);
    return acc;
  }, {});

  const Tab = ({ id, label, count }) => (
    <button onClick={() => setFilter(id)} style={{
      padding: '8px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
      background: filter === id ? '#ecfeff' : 'transparent',
      color: filter === id ? '#0e7490' : '#475569',
      fontFamily: 'var(--font-body)', fontWeight: 500, fontSize: 13,
      display: 'inline-flex', alignItems: 'center', gap: 6,
    }}>
      {label}
      <span style={{ background: filter === id ? '#cffafe' : '#f1f5f9', color: filter === id ? '#0e7490' : '#94a3b8', borderRadius: 9999, padding: '1px 8px', fontSize: 11, fontWeight: 600 }}>{count}</span>
    </button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Historial de movimientos</div>
        <div style={{ fontSize: 13, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 4 }}>Abril 2026</div>
      </div>

      {/* Filters bar */}
      <Card padding={12}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 4, padding: 4, background: '#f8fafc', borderRadius: 10 }}>
            <Tab id="todos" label="Todos" count={all.length} />
            <Tab id="ingresos" label="Ingresos" count={all.filter(m => m._income).length} />
            <Tab id="gastos" label="Gastos" count={all.filter(m => !m._income).length} />
          </div>
          <div style={{ flex: 1, minWidth: 220, position: 'relative' }}>
            <Icon name="search" size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar concepto..." style={{
              width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 12px 8px 36px',
              minHeight: 38, fontSize: 14, fontFamily: 'var(--font-body)', color: '#164e63',
              background: '#fff', boxSizing: 'border-box', outline: 'none',
            }} />
          </div>
          <Button variant="secondary" icon="filter" size="md">Filtrar</Button>
          <Button variant="secondary" icon="download" size="md">Exportar</Button>
        </div>
      </Card>

      {/* Grouped list */}
      <Card padding={0}>
        {Object.keys(groups).length === 0 && (
          <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)', fontSize: 14 }}>
            <Icon name="inbox" size={32} color="#cbd5e1" />
            <div style={{ marginTop: 12 }}>Sin resultados</div>
          </div>
        )}
        {Object.entries(groups).map(([date, items]) => {
          const dayTotal = items.reduce((s, m) => s + (m._income ? m.monto : -m.monto), 0);
          const d = new Date(date);
          return (
            <div key={date}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', fontFamily: 'var(--font-body)', textTransform: 'capitalize', letterSpacing: '0.02em' }}>
                  {d.toLocaleDateString('es-MX', { weekday: 'long', day: '2-digit', month: 'long' })}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: dayTotal >= 0 ? '#059669' : '#dc2626', fontFamily: 'var(--font-body)', fontVariantNumeric: 'tabular-nums' }}>
                  {dayTotal >= 0 ? '+' : '−'}{fmt(Math.abs(dayTotal))}
                </div>
              </div>
              {items.map((m, i) => <MovementRow key={i} m={m} isIncome={m._income} />)}
            </div>
          );
        })}
      </Card>
    </div>
  );
}

function GoalCard({ goal }) {
  const pct = Math.min(goal.actual / goal.target, 1);
  const remaining = Math.max(goal.target - goal.actual, 0);
  const onTrack = pct >= goal.expectedPct;
  return (
    <Card padding={0}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '20px 20px 12px' }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: goal.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon name={goal.icon} size={22} color={goal.color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#164e63', fontFamily: 'var(--font-heading)' }}>{goal.label}</div>
          <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 2 }}>Meta para {goal.deadline}</div>
        </div>
        <Badge variant={onTrack ? 'success' : 'warning'}>{onTrack ? 'En curso' : 'Atrasada'}</Badge>
      </div>
      <div style={{ padding: '0 20px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: '#164e63', fontFamily: 'var(--font-heading)', fontVariantNumeric: 'tabular-nums' }}>{fmt(goal.actual)}</span>
          <span style={{ fontSize: 13, color: '#94a3b8', fontFamily: 'var(--font-body)', fontVariantNumeric: 'tabular-nums' }}>de {fmt(goal.target)}</span>
        </div>
        <div style={{ height: 10, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden', position: 'relative' }}>
          <div style={{ height: '100%', width: pct * 100 + '%', background: goal.color, borderRadius: 9999 }} />
          {/* expected marker */}
          <div style={{ position: 'absolute', top: -2, left: goal.expectedPct * 100 + '%', width: 2, height: 14, background: '#475569' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 8 }}>
          <span>{Math.round(pct * 100)}% completado</span>
          <span>Faltan {fmt(remaining)} · {goal.monthsLeft} meses</span>
        </div>
      </div>
    </Card>
  );
}

function MetasScreen() {
  const goals = [
    { id: 1, label: 'Fondo de emergencia', icon: 'shield', color: '#059669', target: 80000, actual: 45200, expectedPct: 0.55, deadline: 'dic 2026', monthsLeft: 8 },
    { id: 2, label: 'Vacaciones Japón', icon: 'plane', color: '#0891b2', target: 60000, actual: 18500, expectedPct: 0.4, deadline: 'oct 2026', monthsLeft: 6 },
    { id: 3, label: 'Equipo nuevo consultorio', icon: 'briefcase-medical', color: '#8b5cf6', target: 120000, actual: 92000, expectedPct: 0.7, deadline: 'jun 2026', monthsLeft: 2 },
    { id: 4, label: 'Auto', icon: 'car', color: '#f59e0b', target: 280000, actual: 35000, expectedPct: 0.2, deadline: 'mar 2027', monthsLeft: 11 },
  ];
  const totalSaved = goals.reduce((s, g) => s + g.actual, 0);
  const totalGoal = goals.reduce((s, g) => s + g.target, 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Metas de ahorro</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4, fontFamily: 'var(--font-body)' }}>4 metas activas · {Math.round((totalSaved/totalGoal)*100)}% completado en total</div>
        </div>
        <Button variant="primary" icon="plus">Nueva meta</Button>
      </div>

      {/* Summary hero */}
      <Card padding={0}>
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', alignItems: 'center', padding: 24, gap: 32 }}>
          <ProgressArc value={totalSaved} max={totalGoal} sub={`de ${fmtShort(totalGoal)}`} />
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)', letterSpacing: '0.04em' }}>AHORRADO EN TOTAL</div>
            <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.01em', marginTop: 4 }}>{fmt(totalSaved)}</div>
            <div style={{ fontSize: 13, color: '#475569', fontFamily: 'var(--font-body)', marginTop: 8, lineHeight: 1.5, maxWidth: 480 }}>
              A tu ritmo actual de <b>{fmt(6800)}/mes</b>, alcanzarás todas tus metas activas en aproximadamente <b>32 meses</b>. Aumenta tu ahorro mensual a <b>{fmt(8500)}</b> para reducirlo a 24 meses.
            </div>
          </div>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {goals.map(g => <GoalCard key={g.id} goal={g} />)}
      </div>
    </div>
  );
}

Object.assign(window, { CategoryDetail, TransactionHistory, MetasScreen, GoalCard });
