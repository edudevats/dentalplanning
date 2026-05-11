// Sidebar + Topbar — replicates the app shell exactly
const SIDEBAR_W = 256;

function Sidebar({ active = '/edr-personal' }) {
  const sections = [
    { eyebrow: 'PRINCIPAL', items: [{ icon: 'layout-dashboard', label: 'Dashboard', href: '/dashboard' }] },
    { eyebrow: 'FINANZAS PERSONALES', items: [
      { icon: 'piggy-bank', label: 'Estado de Resultados', href: '/edr-personal' },
      { icon: 'trending-up', label: 'Ingresos', href: '/edr-personal/ingresos' },
      { icon: 'trending-down', label: 'Gastos', href: '/edr-personal/gastos' },
      { icon: 'wallet', label: 'Presupuestos', href: '/edr-personal/presupuestos' },
      { icon: 'target', label: 'Metas de ahorro', href: '/edr-personal/metas' },
    ]},
    { eyebrow: 'CONSULTORIO', items: [
      { icon: 'calculator', label: 'Tratamientos', href: '/tratamientos' },
      { icon: 'package', label: 'Inventario', href: '/inventario' },
      { icon: 'bar-chart-3', label: 'Reportes', href: '/reportes/resumen' },
    ]},
    { eyebrow: 'SISTEMA', items: [{ icon: 'settings', label: 'Ajustes', href: '/ajustes' }] },
  ];

  return (
    <aside style={{
      position: 'fixed', top: 0, bottom: 0, left: 0, width: SIDEBAR_W,
      background: '#fff', borderRight: '1px solid #e2e8f0', zIndex: 30,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', height: 64, borderBottom: '1px solid #e2e8f0', flexShrink: 0 }}>
        <img src="../../assets/logo.jpeg" alt="Logo" style={{ height: 32, width: 32, objectFit: 'contain', borderRadius: 6 }} />
        <span style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Dental Planning</span>
      </div>
      {/* Switcher */}
      <div style={{ padding: '12px 12px 0 12px' }}>
        <a href="#" style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8,
          fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-body)', color: '#0e7490',
          background: '#ecfeff', textDecoration: 'none', letterSpacing: '.02em',
        }}>
          <Icon name="grid-2x2" size={14} /> Cambiar de Sistema
        </a>
      </div>
      {/* Nav */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 22 }}>
        {sections.map((s) => (
          <div key={s.eyebrow}>
            <div style={{ padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'var(--font-body)' }}>{s.eyebrow}</div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
              {s.items.map((it) => {
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
        ))}
      </nav>
      {/* User */}
      <div style={{ borderTop: '1px solid #e2e8f0', padding: 16, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9999, background: '#cffafe', color: '#155e75', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 13 }}>DR</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Dr. Ramírez</div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>Administrador</div>
          </div>
          <button style={{ padding: 8, borderRadius: 8, border: 'none', background: 'transparent', color: '#94a3b8', cursor: 'pointer' }}>
            <Icon name="log-out" size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ title, onAdd }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20, height: 64, background: '#fff',
      borderBottom: '1px solid #e2e8f0', marginLeft: SIDEBAR_W,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
    }}>
      <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{title}</h1>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button style={{ position: 'relative', padding: 8, borderRadius: 8, border: 'none', background: 'transparent', color: '#475569', cursor: 'pointer' }}>
          <Icon name="bell" size={20} />
          <span style={{ position: 'absolute', top: 6, right: 6, width: 8, height: 8, borderRadius: 9999, background: '#ef4444' }} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 8, paddingLeft: 12, borderLeft: '1px solid #e2e8f0' }}>
          <div style={{ width: 32, height: 32, borderRadius: 9999, background: '#cffafe', color: '#155e75', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-heading)', fontWeight: 600, fontSize: 12 }}>DR</div>
          <span style={{ fontSize: 14, fontWeight: 500, color: '#164e63' }}>Dr. Ramírez</span>
        </div>
      </div>
    </header>
  );
}

function PageShell({ active, title, children, onAdd }) {
  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      <Sidebar active={active} />
      <Topbar title={title} onAdd={onAdd} />
      <main style={{ marginLeft: SIDEBAR_W, padding: 24 }}>{children}</main>
      {/* Floating Action Button */}
      <button onClick={onAdd} style={{
        position: 'fixed', bottom: 28, right: 28, width: 56, height: 56, borderRadius: 9999,
        background: '#0891b2', color: '#fff', border: 'none', cursor: 'pointer',
        boxShadow: '0 8px 24px -4px rgb(8 145 178 / 0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 25,
      }} title="Agregar movimiento">
        <Icon name="plus" size={24} />
      </button>
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, PageShell, SIDEBAR_W });
