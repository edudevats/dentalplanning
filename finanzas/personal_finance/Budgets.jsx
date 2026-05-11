// Budgets / Presupuestos screen — set monthly limits per category and watch progress

function BudgetRow({ cat, spent, budget }) {
  const pct = budget ? Math.min(spent / budget, 1) : 0;
  const pctNum = budget ? Math.round((spent / budget) * 100) : 0;
  const remaining = budget - spent;
  const status = pctNum >= 100 ? 'over' : pctNum >= 85 ? 'near' : 'ok';
  const statusColor = { ok: '#059669', near: '#d97706', over: '#dc2626' }[status];
  const statusBg = { ok: '#d1fae5', near: '#fef3c7', over: '#fee2e2' }[status];
  const statusLabel = { ok: 'En curso', near: 'Casi al tope', over: 'Excedido' }[status];

  return (
    <div style={{ padding: '18px 20px', borderBottom: '1px solid #f1f5f9' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon name={cat.icon} size={18} color={cat.color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: '#164e63', fontFamily: 'var(--font-body)' }}>{cat.label}</span>
            <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 9999, background: statusBg, color: statusColor, fontFamily: 'var(--font-body)' }}>{statusLabel}</span>
          </div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>
            {remaining >= 0
              ? <>Te quedan <b style={{ color: '#475569' }}>{fmt(remaining)}</b> de {fmt(budget)}</>
              : <>Excediste <b style={{ color: '#dc2626' }}>{fmt(-remaining)}</b> sobre tu límite</>}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#164e63', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-heading)' }}>{fmt(spent)}</div>
          <div style={{ fontSize: 11, color: '#94a3b8', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>de {fmt(budget)}</div>
        </div>
      </div>
      {/* progress */}
      <div style={{ height: 8, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden', position: 'relative' }}>
        <div style={{ height: '100%', width: (pct * 100) + '%', background: statusColor, borderRadius: 9999, transition: 'width .25s' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 11, color: '#94a3b8', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>
        <span>{pctNum}% usado</span>
        <span>Día 28 / 30 — esperado 93%</span>
      </div>
    </div>
  );
}

function Budgets() {
  // Mock budgets per category (would come from backend)
  const budgets = { comida: 5000, transporte: 2200, vivienda: 9000, entreten: 600, salud: 800, otros: 1000 };
  const summary = buildSummary();
  const totalBudget = Object.values(budgets).reduce((s, v) => s + v, 0);
  const totalSpent = summary.totalGastos;
  const totalPct = Math.round((totalSpent / totalBudget) * 100);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Presupuestos</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4, fontFamily: 'var(--font-body)' }}>Define un límite por categoría y te avisamos antes de excederlo</div>
        </div>
        <Button variant="primary" icon="plus">Nuevo presupuesto</Button>
      </div>

      {/* Hero */}
      <Card>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 24, alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>GASTADO TOTAL</div>
            <div style={{ fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{fmt(totalSpent)}</div>
            <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>de {fmt(totalBudget)} presupuestado</div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>USADO</div>
            <div style={{ fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-heading)', color: totalPct >= 100 ? '#dc2626' : '#0e7490', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{totalPct}%</div>
            <div style={{ height: 6, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden', marginTop: 8 }}>
              <div style={{ height: '100%', width: Math.min(totalPct, 100) + '%', background: totalPct >= 100 ? '#dc2626' : '#0891b2', borderRadius: 9999 }} />
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>DISPONIBLE</div>
            <div style={{ fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#065f46', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{fmt(totalBudget - totalSpent)}</div>
            <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>quedan 2 días del mes</div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>ESTADO</div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 12px', borderRadius: 9999, background: '#d1fae5', color: '#065f46', fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-body)', marginTop: 8 }}>
              <Icon name="check-circle-2" size={14} /> Dentro del plan
            </div>
            <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 8 }}>1 categoría requiere atención</div>
          </div>
        </div>
      </Card>

      {/* List */}
      <Card padding={0}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Por categoría</div>
          <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>Abril 2026</div>
        </div>
        {CATEGORIES.filter(c => budgets[c.id]).map(cat => (
          <BudgetRow
            key={cat.id}
            cat={cat}
            spent={GASTOS.filter(g => g.cat === cat.id).reduce((s, g) => s + g.monto, 0)}
            budget={budgets[cat.id]}
          />
        ))}
      </Card>

      {/* Tip */}
      <div style={{
        background: '#ecfeff', border: '1px solid #a5f3fc', borderRadius: 12, padding: '14px 18px',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon name="lightbulb" size={18} color="#0891b2" />
        </div>
        <div style={{ flex: 1, fontSize: 13, color: '#155e75', fontFamily: 'var(--font-body)', lineHeight: 1.5 }}>
          <b>Tip:</b> tu presupuesto de Comida está al 76% con 2 días por terminar el mes — vas bien. Considera bajar Vivienda 5% el próximo mes para acercarte a tu meta de ahorro.
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Budgets, BudgetRow });
