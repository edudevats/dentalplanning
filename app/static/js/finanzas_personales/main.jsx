function App() {
  const [adding, setAdding] = useState(false);
  const [categorias, setCategorias] = useState([]);
  const [fuentes, setFuentes] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    Promise.all([FP.listCategorias(), FP.listFuentes()]).then(([c, f]) => {
      setCategorias(c.filter(x => x.activo));
      setFuentes(f.filter(x => x.activo));
    });
  }, []);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  const screen = window.FP_SCREEN || 'dashboard';
  const titles = {
    dashboard: 'Estado de Resultados Personal',
    category: 'Detalle de categoria',
    history: 'Historial',
    metas: 'Metas de ahorro',
    presupuestos: 'Presupuestos',
  };
  const actives = {
    dashboard: '/finanzas-personales',
    category: '/finanzas-personales',
    history: '/finanzas-personales/historial',
    metas: '/finanzas-personales/metas',
    presupuestos: '/finanzas-personales/presupuestos',
  };

  let body = null;
  if (screen === 'dashboard')         body = <Dashboard          key={reloadKey} />;
  else if (screen === 'category')     body = <CategoryDetail     key={reloadKey} />;
  else if (screen === 'history')      body = <TransactionHistory key={reloadKey} />;
  else if (screen === 'metas')        body = <MetasScreen        key={reloadKey} />;
  else if (screen === 'presupuestos') body = <Budgets            key={reloadKey} />;

  return (
    <PageShell active={actives[screen]} title={titles[screen]} onAdd={() => setAdding(true)}>
      {body}
      <AddMovementModal
        open={adding}
        onClose={() => setAdding(false)}
        onSaved={() => setReloadKey(k => k + 1)}
        categorias={categorias}
        fuentes={fuentes}
      />
    </PageShell>
  );
}

ReactDOM.createRoot(document.getElementById('fp-root')).render(<App />);
