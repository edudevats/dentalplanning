// Mock data — single source of truth for all screens

const CATEGORIES = [
  { id: 'comida',     label: 'Comida',         icon: 'utensils',     color: '#f59e0b' },
  { id: 'transporte', label: 'Transporte',     icon: 'car',          color: '#0891b2' },
  { id: 'vivienda',   label: 'Vivienda',       icon: 'home',         color: '#8b5cf6' },
  { id: 'entreten',   label: 'Entretenimiento',icon: 'film',         color: '#ec4899' },
  { id: 'salud',      label: 'Salud',          icon: 'heart-pulse',  color: '#059669' },
  { id: 'otros',      label: 'Otros',          icon: 'more-horizontal', color: '#f97316' },
];

const INCOME_SOURCES = [
  { id: 'salario', label: 'Salario',     icon: 'briefcase' },
  { id: 'extra',   label: 'Extras',      icon: 'sparkles' },
  { id: 'freelance', label: 'Freelance', icon: 'laptop' },
];

const SALDO_INICIAL = 5400;

const INGRESOS = [
  { id: 1, fecha: '2026-04-01', source: 'salario',   concepto: 'Salario abril',     monto: 22000 },
  { id: 2, fecha: '2026-04-15', source: 'salario',   concepto: 'Quincena',          monto: 0 },
  { id: 3, fecha: '2026-04-18', source: 'freelance', concepto: 'Proyecto landing',  monto: 4500 },
  { id: 4, fecha: '2026-04-22', source: 'extra',     concepto: 'Reembolso seguro',  monto: 1200 },
];

const GASTOS = [
  { id: 1,  fecha: '2026-04-02', cat: 'vivienda',   concepto: 'Renta',              monto: 8500 },
  { id: 2,  fecha: '2026-04-03', cat: 'comida',     concepto: 'Súper Chedraui',     monto: 1840 },
  { id: 3,  fecha: '2026-04-05', cat: 'transporte', concepto: 'Gasolina',           monto: 950 },
  { id: 4,  fecha: '2026-04-07', cat: 'entreten',   concepto: 'Netflix',            monto: 219 },
  { id: 5,  fecha: '2026-04-10', cat: 'comida',     concepto: 'Restaurante',        monto: 680 },
  { id: 6,  fecha: '2026-04-12', cat: 'salud',      concepto: 'Farmacia',           monto: 340 },
  { id: 7,  fecha: '2026-04-14', cat: 'transporte', concepto: 'Uber',               monto: 180 },
  { id: 8,  fecha: '2026-04-16', cat: 'comida',     concepto: 'Súper Walmart',      monto: 1620 },
  { id: 9,  fecha: '2026-04-18', cat: 'entreten',   concepto: 'Spotify',            monto: 169 },
  { id: 10, fecha: '2026-04-20', cat: 'otros',      concepto: 'Regalo cumpleaños',  monto: 850 },
  { id: 11, fecha: '2026-04-22', cat: 'comida',     concepto: 'Café + brunch',      monto: 420 },
  { id: 12, fecha: '2026-04-24', cat: 'transporte', concepto: 'Verificación auto',  monto: 580 },
];

const META_AHORRO = 8000;

// Aggregated for charts
function buildSummary() {
  const totalIngresos = INGRESOS.reduce((s, x) => s + x.monto, 0);
  const totalGastos = GASTOS.reduce((s, x) => s + x.monto, 0);
  const balance = totalIngresos - totalGastos;
  const ahorroPct = totalIngresos ? Math.round((balance / totalIngresos) * 100) : 0;
  const byCat = CATEGORIES.map(c => ({
    ...c,
    value: GASTOS.filter(g => g.cat === c.id).reduce((s, g) => s + g.monto, 0),
  })).filter(c => c.value > 0).sort((a, b) => b.value - a.value);
  return { totalIngresos, totalGastos, balance, ahorroPct, byCat };
}

const HISTORY_6M = [
  { name: 'Nov',    ingresos: 24500, gastos: 17800 },
  { name: 'Dic',    ingresos: 28200, gastos: 22400 },
  { name: 'Ene',    ingresos: 22000, gastos: 16500 },
  { name: 'Feb',    ingresos: 23800, gastos: 18200 },
  { name: 'Mar',    ingresos: 25100, gastos: 16900 },
  { name: 'Abr',    ingresos: 27700, gastos: 16348 },
];

Object.assign(window, { CATEGORIES, INCOME_SOURCES, INGRESOS, GASTOS, SALDO_INICIAL, META_AHORRO, buildSummary, HISTORY_6M });
