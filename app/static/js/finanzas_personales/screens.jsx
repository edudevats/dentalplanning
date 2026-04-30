function useMonth() {
  const today = new Date();
  return useState({ year: today.getFullYear(), month: today.getMonth() + 1 });
}

function CategoryDetail() {
  const catId = parseInt(window.FP_CATEGORY_ID, 10);
  const [{ year, month }] = useMonth();
  const [data, setData] = useState(null);
  useEffect(() => {
    FP.categoriaDetalle(catId, year, month).then(setData).catch(console.error);
  }, [catId, year, month]);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  if (!data) return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>Cargando…</div>;
  const cat = data.categoria;
  const movs = data.movimientos;
  const total = data.total;
  const budget = data.presupuesto;
  const pct = budget ? Math.min(total / budget, 1) : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <a href="/finanzas-personales" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#0e7490', textDecoration: 'none', fontFamily: 'var(--font-body)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="arrow-left" size={14} /> Volver al resumen
        </a>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name={cat.icon} size={26} color={cat.color} />
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{cat.label}</div>
            <div style={{ fontSize: 13, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 2 }}>{movs.length} movimientos</div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', gap: 16 }}>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>GASTADO ESTE MES</div>
          <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{fmt(total)}</div>
          {budget && (
            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#475569', fontFamily: 'var(--font-body)', marginBottom: 6 }}>
                <span>Presupuesto mensual</span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt(total)} de {fmt(budget)}</span>
              </div>
              <div style={{ height: 8, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: pct * 100 + '%', background: pct > 0.9 ? '#ef4444' : pct > 0.75 ? '#f59e0b' : cat.color, borderRadius: 9999 }} />
              </div>
            </div>
          )}
        </Card>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>PROMEDIO DIARIO</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{fmt(data.promedioDiario)}</div>
        </Card>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>GASTO MAS GRANDE</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{data.max ? fmt(data.max.monto) : '—'}</div>
          {data.max && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{data.max.concepto}</div>}
        </Card>
      </div>

      <Card padding={0}>
        <div style={{ padding: '20px 20px 8px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Evolucion</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>Ultimos 6 meses · {cat.label}</div>
        </div>
        <div style={{ padding: '4px 14px 20px' }}>
          <BarChart data={data.history6m} height={180} />
        </div>
      </Card>

      <Card padding={0}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Todos los movimientos</div>
        {movs.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin movimientos en esta categoria este mes</div>}
        {movs.map(m => <MovementRow key={m.id} m={m} />)}
      </Card>
    </div>
  );
}

function TransactionHistory() {
  const [{ year, month }] = useMonth();
  const [filter, setFilter] = useState(null);
  const [search, setSearch] = useState('');
  const [items, setItems] = useState([]);

  useEffect(() => {
    FP.movimientos(year, month, filter).then(setItems).catch(console.error);
  }, [year, month, filter]);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  const filtered = items.filter(m =>
    !search || m.concepto.toLowerCase().includes(search.toLowerCase()),
  );
  const groups = filtered.reduce((acc, m) => { (acc[m.fecha] ??= []).push(m); return acc; }, {});

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
      </div>
      <Card padding={12}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 4, padding: 4, background: '#f8fafc', borderRadius: 10 }}>
            <Tab id={null}    label="Todos"    count={items.length} />
            <Tab id="ingreso" label="Ingresos" count={items.filter(m => m.kind === 'ingreso').length} />
            <Tab id="gasto"   label="Gastos"   count={items.filter(m => m.kind === 'gasto').length} />
          </div>
          <div style={{ flex: 1, minWidth: 220, position: 'relative' }}>
            <Icon name="search" size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar concepto..." style={{
              width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 12px 8px 36px',
              minHeight: 38, fontSize: 14, fontFamily: 'var(--font-body)', color: '#164e63', background: '#fff', boxSizing: 'border-box', outline: 'none',
            }} />
          </div>
        </div>
      </Card>
      <Card padding={0}>
        {Object.keys(groups).length === 0 && (
          <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)', fontSize: 14 }}>
            Sin resultados
          </div>
        )}
        {Object.entries(groups).map(([d, list]) => {
          const dayTotal = list.reduce((s, m) => s + (m.kind === 'ingreso' ? m.monto : -m.monto), 0);
          const dt = new Date(d);
          return (
            <div key={d}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'capitalize' }}>
                  {dt.toLocaleDateString('es-MX', { weekday: 'long', day: '2-digit', month: 'long' })}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: dayTotal >= 0 ? '#059669' : '#dc2626', fontVariantNumeric: 'tabular-nums' }}>
                  {dayTotal >= 0 ? '+' : '−'}{fmt(Math.abs(dayTotal))}
                </div>
              </div>
              {list.map(m => <MovementRow key={m.id} m={m} />)}
            </div>
          );
        })}
      </Card>
    </div>
  );
}

function GoalCard({ goal, onDelete }) {
  const target = parseFloat(goal.monto_objetivo);
  const actual = parseFloat(goal.monto_actual);
  const pct = target ? Math.min(actual / target, 1) : 0;
  return (
    <Card padding={0}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '20px 20px 12px' }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: goal.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon name={goal.icon} size={22} color={goal.color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#164e63', fontFamily: 'var(--font-heading)' }}>{goal.label}</div>
          {goal.fecha_objetivo && <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>Meta para {goal.fecha_objetivo}</div>}
        </div>
        <button onClick={() => onDelete(goal.id)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><Icon name="trash-2" size={16} /></button>
      </div>
      <div style={{ padding: '0 20px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: '#164e63', fontFamily: 'var(--font-heading)', fontVariantNumeric: 'tabular-nums' }}>{fmt(actual)}</span>
          <span style={{ fontSize: 13, color: '#94a3b8' }}>de {fmt(target)}</span>
        </div>
        <div style={{ height: 10, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: pct * 100 + '%', background: goal.color, borderRadius: 9999 }} />
        </div>
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>{Math.round(pct * 100)}% completado</div>
      </div>
    </Card>
  );
}

function MetasScreen() {
  const [goals, setGoals] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ label: '', monto_objetivo: '', monto_actual: '0', fecha_objetivo: '', icon: 'target', color: '#059669' });

  const reload = () => FP.listMetas().then(setGoals);
  useEffect(() => { reload(); }, []);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  const submit = async () => {
    await FP.createMeta({ ...form, fecha_objetivo: form.fecha_objetivo || null });
    setShowForm(false);
    setForm({ label: '', monto_objetivo: '', monto_actual: '0', fecha_objetivo: '', icon: 'target', color: '#059669' });
    reload();
  };
  const remove = async (id) => { await FP.deleteMeta(id); reload(); };

  const totalSaved = goals.reduce((s, g) => s + parseFloat(g.monto_actual), 0);
  const totalGoal = goals.reduce((s, g) => s + parseFloat(g.monto_objetivo), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Metas de ahorro</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4 }}>{goals.length} metas activas</div>
        </div>
        <Button variant="primary" icon="plus" onClick={() => setShowForm(true)}>Nueva meta</Button>
      </div>

      {goals.length > 0 && (
        <Card padding={0}>
          <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', alignItems: 'center', padding: 24, gap: 32 }}>
            <ProgressArc value={totalSaved} max={totalGoal || 1} sub={`de ${fmtShort(totalGoal)}`} />
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>AHORRADO EN TOTAL</div>
              <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{fmt(totalSaved)}</div>
            </div>
          </div>
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
        {goals.map(g => <GoalCard key={g.id} goal={g} onDelete={remove} />)}
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Nueva meta de ahorro">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Nombre"><TextInput value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} placeholder="Ej. Vacaciones" /></Field>
          <Field label="Monto objetivo"><TextInput type="number" value={form.monto_objetivo} onChange={e => setForm({ ...form, monto_objetivo: e.target.value })} placeholder="60000" /></Field>
          <Field label="Monto actual"><TextInput type="number" value={form.monto_actual} onChange={e => setForm({ ...form, monto_actual: e.target.value })} placeholder="0" /></Field>
          <Field label="Fecha objetivo (opcional)"><TextInput type="date" value={form.fecha_objetivo} onChange={e => setForm({ ...form, fecha_objetivo: e.target.value })} /></Field>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setShowForm(false)}>Cancelar</Button>
            <Button variant="primary" icon="check" onClick={submit}>Guardar</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

Object.assign(window, { CategoryDetail, TransactionHistory, MetasScreen, GoalCard });
