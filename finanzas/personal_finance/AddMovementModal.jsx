// Add Movement modal — handles both ingreso and gasto

function Modal({ open, onClose, title, children, maxWidth = 520 }) {
  if (!open) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, overflow: 'auto' }}>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)' }} />
      <div style={{ minHeight: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
        <div style={{ position: 'relative', background: '#fff', borderRadius: 16, boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.10), 0 8px 10px -6px rgb(0 0 0 / 0.05)', width: '100%', maxWidth }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #e2e8f0' }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{title}</h2>
            <button onClick={onClose} style={{ padding: 8, borderRadius: 8, border: 'none', background: 'transparent', color: '#94a3b8', cursor: 'pointer' }}>
              <Icon name="x" size={16} />
            </button>
          </div>
          <div style={{ padding: '20px 24px' }}>{children}</div>
        </div>
      </div>
    </div>
  );
}

function TypeToggle({ value, onChange }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: 4, background: '#f1f5f9', borderRadius: 10 }}>
      <button onClick={() => onChange('ingreso')} style={{
        padding: '10px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
        background: value === 'ingreso' ? '#fff' : 'transparent',
        color: value === 'ingreso' ? '#065f46' : '#94a3b8',
        fontWeight: 600, fontSize: 14, fontFamily: 'var(--font-body)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
        boxShadow: value === 'ingreso' ? '0 1px 2px 0 rgb(0 0 0 / .05)' : 'none',
      }}>
        <Icon name="trending-up" size={16} /> Ingreso
      </button>
      <button onClick={() => onChange('gasto')} style={{
        padding: '10px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
        background: value === 'gasto' ? '#fff' : 'transparent',
        color: value === 'gasto' ? '#b91c1c' : '#94a3b8',
        fontWeight: 600, fontSize: 14, fontFamily: 'var(--font-body)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
        boxShadow: value === 'gasto' ? '0 1px 2px 0 rgb(0 0 0 / .05)' : 'none',
      }}>
        <Icon name="trending-down" size={16} /> Gasto
      </button>
    </div>
  );
}

function CategoryGrid({ value, onChange, options }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
      {options.map(o => {
        const sel = value === o.id;
        return (
          <button key={o.id} onClick={() => onChange(o.id)} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
            padding: '14px 8px', borderRadius: 10, cursor: 'pointer',
            border: sel ? '2px solid #0891b2' : '1px solid #e2e8f0',
            background: sel ? '#ecfeff' : '#fff',
            color: '#164e63', fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 500,
          }}>
            <div style={{ width: 36, height: 36, borderRadius: 9999, background: (o.color || '#0891b2') + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon name={o.icon} size={18} color={o.color || '#0e7490'} />
            </div>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function AddMovementModal({ open, onClose, onSave }) {
  const [type, setType] = useState('gasto');
  const [monto, setMonto] = useState('');
  const [cat, setCat] = useState('comida');
  const [src, setSrc] = useState('salario');
  const [concepto, setConcepto] = useState('');
  const [fecha, setFecha] = useState('2026-04-28');

  return (
    <Modal open={open} onClose={onClose} title={type === 'ingreso' ? 'Nuevo Ingreso' : 'Nuevo Gasto'}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <TypeToggle value={type} onChange={setType} />

        {/* Big amount entry */}
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 12, padding: '18px 20px' }}>
          <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)', fontWeight: 500 }}>Monto</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: type === 'ingreso' ? '#065f46' : '#b91c1c', fontFamily: 'var(--font-heading)' }}>
              {type === 'ingreso' ? '+' : '−'}$
            </span>
            <input
              value={monto} onChange={e => setMonto(e.target.value)}
              placeholder="0.00" inputMode="decimal"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none',
                       fontSize: 32, fontWeight: 700, color: '#164e63', fontFamily: 'var(--font-heading)',
                       fontVariantNumeric: 'tabular-nums' }}
            />
          </div>
        </div>

        <Field label={type === 'ingreso' ? 'Origen' : 'Categoría'}>
          <CategoryGrid
            value={type === 'ingreso' ? src : cat}
            onChange={type === 'ingreso' ? setSrc : setCat}
            options={type === 'ingreso' ? INCOME_SOURCES : CATEGORIES}
          />
        </Field>

        <Field label="Concepto">
          <TextInput value={concepto} onChange={e => setConcepto(e.target.value)} placeholder="¿En qué fue?" />
        </Field>

        <Field label="Fecha">
          <TextInput type="date" value={fecha} onChange={e => setFecha(e.target.value)} />
        </Field>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, paddingTop: 8, borderTop: '1px solid #e2e8f0' }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button variant={type === 'ingreso' ? 'accent' : 'primary'} icon="check" onClick={onSave}>Guardar</Button>
        </div>
      </div>
    </Modal>
  );
}

Object.assign(window, { Modal, AddMovementModal, TypeToggle, CategoryGrid });
