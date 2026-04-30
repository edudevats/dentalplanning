// Reusable atoms — load before screens
// All globals via window.* assignment at bottom

const { useState } = React;

const fmt = (n) => '$' + Number(n).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtShort = (n) => {
  const a = Math.abs(n);
  if (a >= 1000) return '$' + (n / 1000).toFixed(a >= 10000 ? 0 : 1) + 'k';
  return '$' + Math.round(n);
};
const signed = (n) => (n >= 0 ? '+' : '−') + fmt(Math.abs(n)).replace('$', '$');

function Icon({ name, size = 16, color, className = '', style }) {
  return <i data-lucide={name} className={className} style={{ width: size, height: size, color, display: 'inline-block', flexShrink: 0, ...style }}></i>;
}

function Button({ variant = 'primary', size = 'md', icon, children, onClick, type = 'button', disabled, full }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    borderRadius: 8, fontFamily: 'var(--font-body)', fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer', border: 'none', transition: 'background-color .15s, color .15s',
    width: full ? '100%' : 'auto',
    opacity: disabled ? 0.6 : 1,
  };
  const sizes = {
    sm: { padding: '6px 12px', fontSize: 12, minHeight: 32 },
    md: { padding: '8px 16px', fontSize: 14, minHeight: 38 },
    lg: { padding: '10px 18px', fontSize: 14, minHeight: 44 },
  };
  const variants = {
    primary: { background: '#0891b2', color: '#fff' },
    secondary: { background: '#fff', color: '#475569', border: '1px solid #e2e8f0' },
    danger: { background: '#ef4444', color: '#fff' },
    ghost: { background: 'transparent', color: '#0e7490' },
    accent: { background: '#059669', color: '#fff' },
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={{ ...base, ...sizes[size], ...variants[variant] }}>
      {icon && <Icon name={icon} size={size === 'sm' ? 14 : 16} />}
      {children}
    </button>
  );
}

function Card({ children, padding = 20, hoverable, onClick, style }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12,
        padding, boxShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        cursor: onClick || hoverable ? 'pointer' : 'default',
        transition: 'box-shadow .15s, border-color .15s',
        ...style,
      }}
      onMouseEnter={(e) => { if (hoverable || onClick) { e.currentTarget.style.boxShadow = '0 4px 6px -1px rgb(0 0 0 / 0.07), 0 2px 4px -2px rgb(0 0 0 / 0.05)'; e.currentTarget.style.borderColor = '#67e8f9'; } }}
      onMouseLeave={(e) => { if (hoverable || onClick) { e.currentTarget.style.boxShadow = '0 1px 2px 0 rgb(0 0 0 / 0.05)'; e.currentTarget.style.borderColor = '#e2e8f0'; } }}
    >
      {children}
    </div>
  );
}

function StatCard({ label, value, icon, valueColor = '#164e63', sub, trend }) {
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: '#475569', fontWeight: 500 }}>{label}</div>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: '#ecfeff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name={icon} color="#0e7490" size={16} />
        </div>
      </div>
      <div style={{ marginTop: 12, fontFamily: 'var(--font-heading)', fontSize: 26, fontWeight: 700, color: valueColor, fontVariantNumeric: 'tabular-nums', lineHeight: 1.15 }}>{value}</div>
      {sub && (
        <div style={{ marginTop: 4, fontFamily: 'var(--font-body)', fontSize: 12, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 4 }}>
          {trend !== undefined && (
            <span style={{ color: trend >= 0 ? '#059669' : '#dc2626', fontWeight: 600 }}>
              {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%
            </span>
          )}
          <span>{sub}</span>
        </div>
      )}
    </Card>
  );
}

function Badge({ children, variant = 'neutral' }) {
  const colors = {
    info: { bg: '#cffafe', fg: '#155e75' },
    warning: { bg: '#fef3c7', fg: '#b45309' },
    success: { bg: '#d1fae5', fg: '#065f46' },
    danger: { bg: '#fee2e2', fg: '#b91c1c' },
    neutral: { bg: '#f1f5f9', fg: '#475569' },
  };
  const c = colors[variant];
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', borderRadius: 9999, padding: '2px 10px', fontSize: 11, fontFamily: 'var(--font-body)', fontWeight: 600, background: c.bg, color: c.fg, whiteSpace: 'nowrap' }}>
      {children}
    </span>
  );
}

function Field({ label, children, error }) {
  return (
    <div>
      <label style={{ display: 'block', fontFamily: 'var(--font-body)', fontWeight: 500, fontSize: 14, color: '#475569', marginBottom: 4 }}>{label}</label>
      {children}
      {error && <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: '#dc2626', marginTop: 4 }}>{error}</div>}
    </div>
  );
}

const inputStyle = {
  width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, padding: '10px 12px',
  minHeight: 44, fontSize: 14, fontFamily: 'var(--font-body)', color: '#164e63',
  background: '#fff', boxSizing: 'border-box', outline: 'none',
};

function TextInput(props) {
  return <input {...props} style={{ ...inputStyle, ...(props.style || {}) }} />;
}

function Select({ value, onChange, options, placeholder }) {
  return (
    <select value={value} onChange={onChange} style={{ ...inputStyle, padding: '8px 12px', minHeight: 38 }}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

Object.assign(window, { Icon, Button, Card, StatCard, Badge, Field, TextInput, Select, fmt, fmtShort, signed });
