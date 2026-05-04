function ViewToggle({ value, onChange }) {
  return (
    <div style={{
      display: 'inline-flex', background: '#f1f5f9', borderRadius: 8, padding: 3, gap: 0,
    }}>
      {['mes', 'año'].map(v => (
        <button
          key={v}
          onClick={() => onChange(v)}
          style={{
            padding: '6px 18px', borderRadius: 6, border: 'none', cursor: 'pointer',
            fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
            background: value === v ? '#fff' : 'transparent',
            color: value === v ? '#0e7490' : '#64748b',
            boxShadow: value === v ? '0 1px 3px rgb(0 0 0 / .1)' : 'none',
            transition: 'all .15s',
          }}
        >
          {v === 'mes' ? 'Mes' : 'Año'}
        </button>
      ))}
    </div>
  );
}

Object.assign(window, { ViewToggle });
