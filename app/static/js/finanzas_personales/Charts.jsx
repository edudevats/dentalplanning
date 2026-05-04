// Charts: hand-rolled SVG so we don't depend on Chart.js loading

function Donut({ data, size = 200 }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const r = 80, cx = size / 2, cy = size / 2;
  let acc = 0;
  const arcs = data.map((d, i) => {
    const a0 = (acc / total) * Math.PI * 2 - Math.PI / 2;
    acc += d.value;
    const a1 = (acc / total) * Math.PI * 2 - Math.PI / 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    return <path key={i} d={`M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`} fill={d.color} stroke="#fff" strokeWidth="2" />;
  });
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {arcs}
      <circle cx={cx} cy={cy} r={48} fill="#fff" />
      <text x={cx} y={cy - 4} textAnchor="middle" fontFamily="var(--font-heading)" fontSize="11" fill="#94a3b8">Total</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontFamily="var(--font-heading)" fontSize="16" fontWeight="700" fill="#164e63">{fmtShort(total)}</text>
    </svg>
  );
}

function CategoryLegend({ data }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {data.map((d, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 10, height: 10, borderRadius: 9999, background: d.color, flexShrink: 0 }} />
          <span style={{ flex: 1, fontSize: 13, color: '#475569', fontFamily: 'var(--font-body)' }}>{d.label}</span>
          <span style={{ fontSize: 13, color: '#164e63', fontWeight: 600, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>{fmt(d.value)}</span>
          <span style={{ fontSize: 12, color: '#94a3b8', fontVariantNumeric: 'tabular-nums', minWidth: 36, textAlign: 'right' }}>{Math.round((d.value / total) * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

function BarChart({ data, height = 220 }) {
  const max = Math.max(...data.flatMap(d => [d.ingresos, d.gastos]), 1);
  const w = 600, padL = 36, padB = 28, padT = 12;
  const innerW = w - padL - 8, innerH = height - padT - padB;
  const groupW = innerW / data.length;
  const barW = (groupW - 12) / 2;

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${height}`} style={{ display: 'block' }}>
      {/* gridlines */}
      {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
        const y = padT + innerH * (1 - t);
        return <g key={i}>
          <line x1={padL} y1={y} x2={w - 8} y2={y} stroke="#e2e8f0" strokeDasharray={i === 0 ? '0' : '0'} />
          <text x={padL - 6} y={y + 3} textAnchor="end" fontSize="10" fill="#94a3b8" fontFamily="var(--font-body)">${Math.round((max * t) / 1000)}k</text>
        </g>;
      })}
      {data.map((d, i) => {
        const x0 = padL + groupW * i + 6;
        const hi = (d.ingresos / max) * innerH;
        const hg = (d.gastos / max) * innerH;
        return <g key={i}>
          <rect x={x0} y={padT + innerH - hi} width={barW} height={hi} fill="#0891b2" rx="3" />
          <rect x={x0 + barW + 4} y={padT + innerH - hg} width={barW} height={hg} fill="#ef4444" rx="3" />
          <text x={x0 + barW + 2} y={height - 10} textAnchor="middle" fontSize="11" fill="#94a3b8" fontFamily="var(--font-body)">{d.name}</text>
        </g>;
      })}
    </svg>
  );
}

function ProgressArc({ value, max, label, sub }) {
  const pct = Math.min(value / max, 1);
  const r = 60, cx = 80, cy = 80;
  const a0 = Math.PI * 0.75, a1 = Math.PI * 2.25;
  const a = a0 + (a1 - a0) * pct;
  const arc = (start, end) => {
    const x0 = cx + r * Math.cos(start), y0 = cy + r * Math.sin(start);
    const x1 = cx + r * Math.cos(end), y1 = cy + r * Math.sin(end);
    const large = end - start > Math.PI ? 1 : 0;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
  };
  return (
    <svg width="160" height="160" viewBox="0 0 160 160">
      <path d={arc(a0, a1)} fill="none" stroke="#ecfeff" strokeWidth="14" strokeLinecap="round" />
      <path d={arc(a0, a)} fill="none" stroke="#0891b2" strokeWidth="14" strokeLinecap="round" />
      <text x="80" y="80" textAnchor="middle" fontFamily="var(--font-heading)" fontSize="28" fontWeight="700" fill="#164e63">{Math.round(pct * 100)}%</text>
      <text x="80" y="100" textAnchor="middle" fontFamily="var(--font-body)" fontSize="11" fill="#94a3b8">{sub}</text>
    </svg>
  );
}

function Sparkline({ data, width = 120, height = 32, color = '#0e7490' }) {
  if (!data || data.length < 2) return null;
  const values = data.map(d => d.pct);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 2 - ((v - min) / range) * (height - 8);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

function LineChart({ data, height = 240 }) {
  const W = 520, H = height, PL = 72, PR = 16, PT = 12, PB = 28;
  const chartW = W - PL - PR;
  const chartH = H - PT - PB;

  const realData = data.filter(d => d.saldo_acum !== null);
  if (realData.length === 0) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: 13, fontFamily: 'var(--font-body)' }}>
        Sin datos para mostrar
      </div>
    );
  }

  const values = realData.map(d => d.saldo_acum);
  const minV = Math.min(...values, 0);
  const maxV = Math.max(...values, 0);
  const range = maxV - minV || 1;

  const toX = (i) => PL + (i / 11) * chartW;
  const toY = (v) => PT + chartH - ((v - minV) / range) * chartH;
  const zeroY = toY(0);

  const realPath = data
    .map((d, i) => (d.saldo_acum !== null ? `${i === 0 || data[i - 1].saldo_acum === null ? 'M' : 'L'} ${toX(i)} ${toY(d.saldo_acum)}` : null))
    .filter(Boolean)
    .join(' ');

  const fmtY = (v) => {
    const a = Math.abs(v);
    if (a >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
    if (a >= 1000) return '$' + (v / 1000).toFixed(0) + 'k';
    return '$' + Math.round(v);
  };

  const yTicks = [minV, minV + range * 0.5, maxV].map(v => Math.round(v));

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible', display: 'block' }}>
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PL} y1={toY(v)} x2={W - PR} y2={toY(v)} stroke="#f1f5f9" strokeWidth={1} />
          <text x={PL - 6} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="#94a3b8" fontFamily="var(--font-body)">
            {fmtY(v)}
          </text>
        </g>
      ))}
      <line x1={PL} y1={zeroY} x2={W - PR} y2={zeroY} stroke="#e2e8f0" strokeWidth={1} strokeDasharray="4 2" />
      <path d={realPath} fill="none" stroke="#0891b2" strokeWidth={2} strokeLinejoin="round" />
      {data.map((d, i) => d.saldo_acum !== null && (
        <circle key={i} cx={toX(i)} cy={toY(d.saldo_acum)} r={3} fill="#0891b2" />
      ))}
      {data.map((d, i) => (
        <text key={i} x={toX(i)} y={H - 4} textAnchor="middle" fontSize={9} fill="#94a3b8" fontFamily="var(--font-body)">
          {d.name}
        </text>
      ))}
    </svg>
  );
}

Object.assign(window, { Donut, CategoryLegend, BarChart, ProgressArc, Sparkline, LineChart });
