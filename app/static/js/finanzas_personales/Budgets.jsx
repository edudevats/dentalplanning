function BudgetRow({ cat, spent, budget, onEdit }) {
  const pct = budget ? Math.min(spent / budget, 1) : 0;
  const pctNum = budget ? Math.round((spent / budget) * 100) : 0;
  const remaining = budget - spent;
  const status = pctNum >= 100 ? 'over' : pctNum >= 85 ? 'near' : 'ok';
  const color = { ok: '#059669', near: '#d97706', over: '#dc2626' }[status];
  const bg = { ok: '#d1fae5', near: '#fef3c7', over: '#fee2e2' }[status];
  const label = { ok: 'En curso', near: 'Casi al tope', over: 'Excedido' }[status];
  return (
    <div style={{ padding: '18px 20px', borderBottom: '1px solid #f1f5f9' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name={cat.icon} size={18} color={cat.color} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: '#164e63' }}>{cat.label}</span>
            {budget > 0 && <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 9999, background: bg, color }}>{label}</span>}
          </div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
            {budget > 0
              ? (remaining >= 0 ? `Te quedan ${fmt(remaining)} de ${fmt(budget)}` : `Excediste ${fmt(-remaining)}`)
              : 'Sin presupuesto definido'}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#164e63', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-heading)' }}>{fmt(spent)}</div>
          {budget > 0 && <div style={{ fontSize: 11, color: '#94a3b8' }}>de {fmt(budget)}</div>}
        </div>
        <button onClick={() => onEdit(cat)} style={{ marginLeft: 12, background: 'transparent', border: '1px solid #e2e8f0', borderRadius: 8, padding: 8, cursor: 'pointer', color: '#475569' }}>
          <Icon name="edit-2" size={14} />
        </button>
      </div>
      {budget > 0 && (
        <div style={{ height: 8, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: pct * 100 + '%', background: color, borderRadius: 9999 }} />
        </div>
      )}
    </div>
  );
}

function Budgets() {
  const today = new Date();
  const [year] = useState(today.getFullYear());
  const [month] = useState(today.getMonth() + 1);
  const [summary, setSummary] = useState(null);
  const [budgets, setBudgets] = useState([]);
  const [allCats, setAllCats] = useState([]);
  const [editing, setEditing] = useState(null);
  const [amount, setAmount] = useState('');

  const reload = async () => {
    const [s, b, c] = await Promise.all([
      FP.dashboard(year, month), FP.listPresupuestos(), FP.listCategorias(),
    ]);
    setSummary(s);
    setBudgets(b);
    setAllCats(c.filter(x => x.activo));
  };
  useEffect(() => { reload(); }, []);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  if (!summary) return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>Cargando…</div>;

  const budgetByCat = {};
  for (const b of budgets) {
    const cur = budgetByCat[b.categoria_id];
    if (!cur || b.vigente_desde > cur.vigente_desde) budgetByCat[b.categoria_id] = b;
  }
  const spendByCat = Object.fromEntries(summary.byCat.map(c => [c.id, c.value]));

  const save = async () => {
    await FP.upsertPresupuesto({
      categoria_id: editing.id,
      monto_mensual: parseFloat(amount).toFixed(2),
      vigente_desde: new Date().toISOString().slice(0, 10),
    });
    setEditing(null);
    reload();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Presupuestos</div>
        <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4 }}>Define limites mensuales por categoria</div>
      </div>
      <Card padding={0}>
        {allCats.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8' }}>Aun no hay categorias</div>}
        {allCats.map(c => (
          <BudgetRow
            key={c.id}
            cat={{ id: c.id, label: c.nombre, icon: c.icon, color: c.color }}
            spent={spendByCat[c.id] || 0}
            budget={budgetByCat[c.id] ? parseFloat(budgetByCat[c.id].monto_mensual) : 0}
            onEdit={cat => { setEditing(cat); setAmount(budgetByCat[cat.id] ? budgetByCat[cat.id].monto_mensual : ''); }}
          />
        ))}
      </Card>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing ? `Presupuesto: ${editing.label}` : ''}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Monto mensual"><TextInput type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" /></Field>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button variant="primary" icon="check" onClick={save}>Guardar</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

Object.assign(window, { Budgets, BudgetRow });
