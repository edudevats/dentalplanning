const { useEffect: useEffectAnual } = React;

function CerrarAñoModal({ year, monto, onConfirm, onCancel }) {
  const montoFmt = monto >= 0 ? `+${fmt(monto)}` : `−${fmt(Math.abs(monto))}`;
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgb(0 0 0 / .4)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{ background: '#fff', borderRadius: 16, padding: 32, maxWidth: 420, width: '90%', boxShadow: '0 20px 60px -10px rgb(0 0 0 / .25)' }}>
        <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', marginBottom: 12 }}>
          Cerrar año {year}
        </div>
        <div style={{ fontSize: 14, color: '#475569', fontFamily: 'var(--font-body)', lineHeight: 1.6, marginBottom: 24 }}>
          El saldo acumulado de <strong>{year}</strong> es <strong style={{ color: monto >= 0 ? '#059669' : '#dc2626' }}>{montoFmt}</strong>.
          Este monto se transferirá como fondo inicial del año <strong>{year + 1}</strong>. ¿Confirmar?
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{
            padding: '10px 20px', borderRadius: 8, border: '1px solid #e2e8f0',
            background: '#fff', color: '#475569', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 14,
          }}>Cancelar</button>
          <button onClick={onConfirm} style={{
            padding: '10px 20px', borderRadius: 8, border: 'none',
            background: '#0891b2', color: '#fff', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 600,
          }}>Confirmar cierre</button>
        </div>
      </div>
    </div>
  );
}

function DashboardAnual({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [cerrando, setCerrando] = useState(false);

  useEffectAnual(() => {
    setLoading(true);
    FP.dashboardAnual(year)
      .then(d => { setData(d); setLoading(false); window.lucide && window.lucide.createIcons(); })
      .catch(err => { console.error(err); setLoading(false); });
  }, [year]);

  if (loading || !data) {
    return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)' }}>Cargando…</div>;
  }

  const today = new Date();
  const canClose = (year < today.getFullYear()) || (year === today.getFullYear() && today.getMonth() === 11);

  const handleCerrar = () => {
    setCerrando(true);
    FP.cerrarAño(year)
      .then(() => { window.location.href = `/finanzas-personales?view=año&year=${year + 1}`; })
      .catch(err => { alert(err.message); setCerrando(false); });
  };

  const t = data.totales;
  const saldoColor = data.saldo_acumulado >= 0 ? '#0e7490' : '#dc2626';
  const proyColor = data.proyeccion_cierre >= 0 ? '#059669' : '#dc2626';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {showModal && (
        <CerrarAñoModal
          year={year}
          monto={data.saldo_acumulado}
          onConfirm={handleCerrar}
          onCancel={() => setShowModal(false)}
        />
      )}

      {/* Tarjetas anuales */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard label="Ingresos del año"  value={fmt(t.ingresos)}             icon="trending-up"   valueColor="#065f46" sub={`ahorro ${t.ahorroPct}%`} />
        <StatCard label="Gastos del año"    value={fmt(t.gastos)}               icon="trending-down" valueColor="#164e63" sub="total anual" />
        <StatCard label="Saldo acumulado"   value={fmt(data.saldo_acumulado)}   icon="wallet"        valueColor={saldoColor} sub={`desde $${(data.saldo_inicial/1000).toFixed(0)}k fondo inicial`} />
        <StatCard label="Proyección cierre" value={fmt(data.proyeccion_cierre)} icon="target"        valueColor={proyColor} sub="a ritmo actual" />
      </div>

      {/* Días de reserva */}
      {data.dias_reserva !== null && (
        <div style={{
          background: '#ecfeff', border: '1px solid #a5f3fc', borderRadius: 12,
          padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <Icon name="shield-check" size={20} color="#0e7490" />
          <span style={{ fontSize: 14, color: '#164e63', fontFamily: 'var(--font-body)' }}>
            Con tu saldo actual puedes cubrir <strong>{data.dias_reserva} días</strong> de gastos a tu ritmo actual.
          </span>
        </div>
      )}

      {/* Gráfica de saldo acumulado */}
      <Card padding={0}>
        <div style={{ padding: '20px 20px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Saldo acumulado {year}</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>
              Fondo inicial: {fmt(data.saldo_inicial)}
            </div>
          </div>
          {canClose && (
            <button
              onClick={() => setShowModal(true)}
              disabled={cerrando}
              style={{
                padding: '8px 16px', borderRadius: 8, border: '1px solid #0891b2',
                background: '#fff', color: '#0891b2', cursor: 'pointer',
                fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
              }}
            >
              Cerrar año {year}
            </button>
          )}
        </div>
        <div style={{ padding: '8px 16px 20px' }}>
          <LineChart data={data.history12m} height={220} />
        </div>
      </Card>

      {/* Tabla 12 meses + donut por fuente */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>
            Detalle mensual {year}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                  {['Mes', 'Ingresos', 'Gastos', 'Balance', 'Saldo Acum.'].map(h => (
                    <th key={h} style={{ padding: '10px 16px', textAlign: h === 'Mes' ? 'left' : 'right', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.history12m.map((row, i) => {
                  const isFuture = row.ingresos === null;
                  const isCurrentMonth = !isFuture && i === (new Date().getMonth());
                  const rowStyle = {
                    color: isFuture ? '#cbd5e1' : '#164e63',
                    background: isCurrentMonth ? '#f0f9ff' : 'transparent',
                    borderBottom: '1px solid #f1f5f9',
                  };
                  return (
                    <tr key={i} style={rowStyle}>
                      <td style={{ padding: '10px 16px', fontWeight: isCurrentMonth ? 600 : 400 }}>{row.name}</td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', color: isFuture ? '#cbd5e1' : '#059669' }}>
                        {isFuture ? '---' : fmt(row.ingresos)}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', color: isFuture ? '#cbd5e1' : '#dc2626' }}>
                        {isFuture ? '---' : fmt(row.gastos)}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', color: isFuture ? '#cbd5e1' : (row.balance >= 0 ? '#059669' : '#dc2626') }}>
                        {isFuture ? '---' : (row.balance >= 0 ? '+' : '−') + fmt(Math.abs(row.balance))}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 600, color: isFuture ? '#cbd5e1' : (row.saldo_acum >= 0 ? '#0e7490' : '#dc2626') }}>
                        {isFuture ? '---' : fmt(row.saldo_acum)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ingresos por fuente</div>
          </div>
          {data.by_fuente.length > 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '12px 20px 20px' }}>
              <Donut data={data.by_fuente.map(f => ({ value: f.value, color: f.color }))} size={160} />
              <div style={{ flex: 1 }}>
                <CategoryLegend data={data.by_fuente.map(f => ({ label: f.label, value: f.value, color: f.color }))} />
              </div>
            </div>
          ) : (
            <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin ingresos registrados en {year}</div>
          )}
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { DashboardAnual, CerrarAñoModal });
