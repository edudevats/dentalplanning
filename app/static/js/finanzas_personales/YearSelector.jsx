function YearSelector({ year, onChange }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '4px 8px',
    }}>
      <button
        onClick={() => onChange(year - 1)}
        style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: '4px 6px', color: '#475569', borderRadius: 4 }}
      >
        <Icon name="chevron-left" size={16} />
      </button>
      <span style={{
        fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-body)',
        color: '#164e63', minWidth: 44, textAlign: 'center',
      }}>
        {year}
      </span>
      <button
        onClick={() => onChange(year + 1)}
        style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: '4px 6px', color: '#475569', borderRadius: 4 }}
      >
        <Icon name="chevron-right" size={16} />
      </button>
    </div>
  );
}

Object.assign(window, { YearSelector });
