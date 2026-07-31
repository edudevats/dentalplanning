const SIDEBAR_W = 256;

function ClinicIncomeWidget() {
  const [amount, setAmount] = React.useState(null);
  React.useEffect(() => {
    const today = new Date();
    FP.dashboard(today.getFullYear(), today.getMonth() + 1)
      .then(s => setAmount(s.ingreso_clinica))
      .catch(() => {});
  }, []);
  return (
    <div style={{
      margin: '4px 0', padding: '10px 12px', background: '#f8fafc',
      borderRadius: 8, border: '1px solid #e2e8f0',
    }}>
      <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)', marginBottom: 2 }}>
        Ingresos consultorio (este mes)
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: '#164e63', fontFamily: 'var(--font-body)' }}>
        {amount === null ? '---' : fmt(amount)}
      </div>
    </div>
  );
}

function Sidebar({ active = '/finanzas-personales' }) {
  const [dentalOpen, setDentalOpen] = useState(true);

  const fpItems = [
    { icon: 'piggy-bank',  label: 'Estado de Resultados', href: '/finanzas-personales' },
    { icon: 'list',        label: 'Historial',             href: '/finanzas-personales/historial' },
    { icon: 'wallet',      label: 'Presupuestos',          href: '/finanzas-personales/presupuestos' },
    { icon: 'target',      label: 'Metas de ahorro',       href: '/finanzas-personales/metas' },
  ];

  return (
    <aside style={{
      position: 'fixed', top: 0, bottom: 0, left: 0, width: SIDEBAR_W,
      background: '#fff', borderRight: '1px solid #e2e8f0', zIndex: 30,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', height: 64, borderBottom: '1px solid #e2e8f0', flexShrink: 0 }}>
        <img src="/static/imagenes/02-fondoblanco.jpg.jpeg" alt="Logo" style={{ height: 32, width: 32, objectFit: 'contain', borderRadius: 6 }} />
        <span style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Dental Planning</span>
      </div>

      <nav style={{ flex: 1, overflowY: 'auto', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 22 }}>
        {/* FINANZAS PERSONALES */}
        <div>
          <div style={{ padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'var(--font-body)' }}>
            Finanzas Personales
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {fpItems.map(it => {
              const isActive = it.href === active;
              return (
                <li key={it.href}>
                  <a href={it.href} style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
                    fontSize: 14, fontWeight: 500, fontFamily: 'var(--font-body)', textDecoration: 'none',
                    color: isActive ? '#0e7490' : '#475569',
                    background: isActive ? '#ecfeff' : 'transparent',
                  }}>
                    <Icon name={it.icon} size={18} />
                    {it.label}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>

        {/* RESUMEN DENTAL */}
        <div>
          <button
            onClick={() => setDentalOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              width: '100%', padding: '0 12px', marginBottom: dentalOpen ? 8 : 0,
              fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8',
              textTransform: 'uppercase', fontFamily: 'var(--font-body)',
              background: 'transparent', border: 'none', cursor: 'pointer',
            }}
          >
            Resumen Dental
            <Icon name={dentalOpen ? 'chevron-up' : 'chevron-down'} size={12} color="#94a3b8" />
          </button>
          {dentalOpen && (
            <div style={{ padding: '0 4px' }}>
              <ClinicIncomeWidget />
              <a href="/ingresos" style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', marginTop: 4,
                borderRadius: 8, fontSize: 13, fontWeight: 500, fontFamily: 'var(--font-body)',
                color: '#475569', textDecoration: 'none',
              }}>
                <Icon name="external-link" size={14} color="#94a3b8" />
                Ver ingresos completos
                <span style={{ fontSize: 10, background: '#fef9c3', color: '#92400e', borderRadius: 4, padding: '1px 5px', marginLeft: 'auto' }}>
                  cambia sistema
                </span>
              </a>
            </div>
          )}
        </div>

        {/* SISTEMA */}
        <div>
          <div style={{ padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'var(--font-body)' }}>
            Sistema
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            <li>
              <a href="/ajustes" style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
                fontSize: 14, fontWeight: 500, fontFamily: 'var(--font-body)', textDecoration: 'none',
                color: '/ajustes' === active ? '#0e7490' : '#475569',
                background: '/ajustes' === active ? '#ecfeff' : 'transparent',
              }}>
                <Icon name="settings" size={18} />Ajustes
              </a>
            </li>
          </ul>
        </div>
      </nav>

      <div style={{ padding: '0 12px 12px 12px', flexShrink: 0 }}>
        <a href="/selector" style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8,
          fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-body)', color: '#0e7490',
          background: '#ecfeff', textDecoration: 'none', letterSpacing: '.02em',
        }}>
          <Icon name="grid-2x2" size={14} /> Cambiar de Sistema
        </a>
      </div>
    </aside>
  );
}

function Topbar({ title }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20, height: 64, background: '#fff',
      borderBottom: '1px solid #e2e8f0', marginLeft: SIDEBAR_W,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
    }}>
      <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{title}</h1>
      <button
        onClick={() => { localStorage.removeItem('token'); localStorage.removeItem('refresh_token'); window.location.href = '/login'; }}
        style={{ padding: 8, borderRadius: 8, border: 'none', background: 'transparent', color: '#475569', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13 }}>
        Cerrar sesion
      </button>
    </header>
  );
}

function PageShell({ active, title, children, onAdd }) {
  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      <Sidebar active={active} />
      <Topbar title={title} />
      <main style={{ marginLeft: SIDEBAR_W, padding: 24 }}>{children}</main>
      {onAdd && (
        <button onClick={onAdd} style={{
          position: 'fixed', bottom: 28, right: 28, width: 56, height: 56, borderRadius: 9999,
          background: '#0891b2', color: '#fff', border: 'none', cursor: 'pointer',
          boxShadow: '0 8px 24px -4px rgb(8 145 178 / 0.45)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 25,
        }} title="Agregar movimiento">
          <Icon name="plus" size={24} />
        </button>
      )}
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, PageShell, SIDEBAR_W });
