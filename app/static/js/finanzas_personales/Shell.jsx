const SIDEBAR_W = 256;

// ── Clinical Sanctuary palette — igual que el sidebar de CRM (tokens cs- de base.html) ──
const CS = {
  bg: '#f1f5f9',                  // surface-container-low (fondo del sidebar)
  lowest: '#ffffff',              // surface-container-lowest
  hover: '#e8eff3',               // surface-container (hover)
  onSurface: '#2a3439',
  onVar: '#475569',
  primary: '#005db6',
  primaryContainer: '#d5e3f7',
  onPrimaryContainer: '#001c3b',
  outline: '#8a9199',
  containerHigh: '#dde6ec',
  display: "'Manrope', system-ui, sans-serif",
  body: "'Inter', system-ui, sans-serif",
};

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
      margin: '4px 0', padding: '10px 12px', background: CS.lowest,
      borderRadius: 8, border: `1px solid ${CS.containerHigh}`,
    }}>
      <div style={{ fontSize: 11, color: CS.onVar, fontFamily: CS.body, marginBottom: 2 }}>
        Ingresos consultorio (este mes)
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: CS.onSurface, fontFamily: CS.body }}>
        {amount === null ? '---' : fmt(amount)}
      </div>
    </div>
  );
}

// Enlace de navegacion estilo cs-nav-link de CRM (hover + estado activo con barra lateral).
function CsNavLink({ href, icon, label, active }) {
  const [hover, setHover] = useState(false);
  const isActive = href === active;
  const bg = isActive ? CS.lowest : (hover ? CS.hover : 'transparent');
  const color = isActive ? CS.primary : (hover ? CS.onSurface : CS.onVar);
  return (
    <a href={href}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
        fontSize: 14, fontWeight: isActive ? 600 : 500, fontFamily: CS.body, textDecoration: 'none',
        color, background: bg,
        boxShadow: isActive ? `inset 3px 0 0 0 ${CS.primary}` : 'none',
        transition: 'background-color .2s, color .2s',
      }}>
      <Icon name={icon} size={18} />
      {label}
    </a>
  );
}

// Enlace tenue del bloque inferior (Configuracion / Cambiar de Sistema), como en CRM.
function CsBottomLink({ href, icon, label }) {
  const [hover, setHover] = useState(false);
  return (
    <a href={href}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', borderRadius: 8,
        fontSize: 14, fontWeight: 500, fontFamily: CS.body, textDecoration: 'none',
        color: CS.onVar, background: hover ? CS.hover : 'transparent',
        transition: 'background-color .2s, color .2s',
      }}>
      <Icon name={icon} size={18} />
      {label}
    </a>
  );
}

// Tarjeta de usuario inferior, igual que la de CRM. Los datos vienen de /auth/me.
function SidebarUserCard() {
  const [name, setName] = useState('Usuario');
  React.useEffect(() => {
    const token = localStorage.getItem('token');
    fetch('/api/v1/auth/me', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { const u = d && (d.user || d); if (u && u.name) setName(u.name); })
      .catch(() => {});
  }, []);
  const initials = name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '??';
  return (
    <div style={{
      marginTop: 12, display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 12px', borderRadius: 8, background: CS.lowest,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 6, background: CS.primaryContainer,
        color: CS.onPrimaryContainer, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, fontWeight: 600, fontFamily: CS.display, flexShrink: 0,
      }}>{initials}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: CS.onSurface, fontFamily: CS.body, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</div>
        <div style={{ fontSize: 12, color: CS.onVar, fontFamily: CS.body }}>Ver Perfil</div>
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

  const sectionLabel = {
    padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600,
    letterSpacing: '.06em', color: CS.outline, textTransform: 'uppercase', fontFamily: CS.body,
  };

  return (
    <aside style={{
      position: 'fixed', top: 0, bottom: 0, left: 0, width: SIDEBAR_W,
      background: CS.bg, zIndex: 30,
      display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16,
    }}>
      <div style={{ padding: '0 8px', marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, fontFamily: CS.display, color: CS.onSurface, lineHeight: 1.2 }}>
          Finanzas Personales
        </h2>
        <p style={{ margin: '2px 0 0', fontSize: 12, color: CS.onVar, letterSpacing: '.05rem', fontFamily: CS.body }}>
          Ingresos, Gastos y Metas
        </p>
      </div>

      <nav style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 22 }}>
        {/* FINANZAS PERSONALES */}
        <div>
          <div style={sectionLabel}>Finanzas Personales</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {fpItems.map(it => (
              <CsNavLink key={it.href} href={it.href} icon={it.icon} label={it.label} active={active} />
            ))}
          </div>
        </div>

        {/* RESUMEN DENTAL */}
        <div>
          <button
            onClick={() => setDentalOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              width: '100%', padding: '0 12px', marginBottom: dentalOpen ? 8 : 0,
              fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: CS.outline,
              textTransform: 'uppercase', fontFamily: CS.body,
              background: 'transparent', border: 'none', cursor: 'pointer',
            }}
          >
            Resumen Dental
            <Icon name={dentalOpen ? 'chevron-up' : 'chevron-down'} size={12} color={CS.outline} />
          </button>
          {dentalOpen && (
            <div style={{ padding: '0 4px' }}>
              <ClinicIncomeWidget />
              <a href="/ingresos" style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', marginTop: 4,
                borderRadius: 8, fontSize: 13, fontWeight: 500, fontFamily: CS.body,
                color: CS.onVar, textDecoration: 'none',
              }}>
                <Icon name="external-link" size={14} color={CS.outline} />
                Ver ingresos completos
                <span style={{ fontSize: 10, background: '#fef9c3', color: '#92400e', borderRadius: 4, padding: '1px 5px', marginLeft: 'auto' }}>
                  cambia sistema
                </span>
              </a>
            </div>
          )}
        </div>
      </nav>

      <div style={{ paddingTop: 16, display: 'flex', flexDirection: 'column', gap: 2, flexShrink: 0 }}>
        <CsBottomLink href="/ajustes" icon="settings" label="Configuración" />
        <CsBottomLink href="/selector" icon="grid-2x2" label="Cambiar de Sistema" />
        <SidebarUserCard />
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
