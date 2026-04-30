// Tiny fetch wrapper that reuses the JWT from localStorage.

const FP_BASE = '/api/v1/finanzas-personales';

async function fpRequest(path, options = {}) {
  const token = localStorage.getItem('token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(FP_BASE + path, { ...options, headers });
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || JSON.stringify(body.errors || body) || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

const FP = {
  listCategorias: () => fpRequest('/categorias'),
  createCategoria: (data) => fpRequest('/categorias', { method: 'POST', body: JSON.stringify(data) }),
  updateCategoria: (id, data) => fpRequest('/categorias/' + id, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCategoria: (id) => fpRequest('/categorias/' + id, { method: 'DELETE' }),

  listFuentes: () => fpRequest('/fuentes'),
  createFuente: (data) => fpRequest('/fuentes', { method: 'POST', body: JSON.stringify(data) }),

  createIngreso: (data) => fpRequest('/ingresos', { method: 'POST', body: JSON.stringify(data) }),
  createGasto: (data) => fpRequest('/gastos', { method: 'POST', body: JSON.stringify(data) }),
  deleteIngreso: (id) => fpRequest('/ingresos/' + id, { method: 'DELETE' }),
  deleteGasto: (id) => fpRequest('/gastos/' + id, { method: 'DELETE' }),

  dashboard: (year, month) => fpRequest(`/dashboard?year=${year}&month=${month}`),
  movimientos: (year, month, kind) => {
    const q = new URLSearchParams({ year, month });
    if (kind) q.set('kind', kind);
    return fpRequest('/movimientos?' + q.toString());
  },
  categoriaDetalle: (catId, year, month) =>
    fpRequest(`/categorias/${catId}/detalle?year=${year}&month=${month}`),

  listPresupuestos: () => fpRequest('/presupuestos'),
  upsertPresupuesto: (data) => fpRequest('/presupuestos', { method: 'POST', body: JSON.stringify(data) }),

  listMetas: () => fpRequest('/metas'),
  createMeta: (data) => fpRequest('/metas', { method: 'POST', body: JSON.stringify(data) }),
  updateMeta: (id, data) => fpRequest('/metas/' + id, { method: 'PUT', body: JSON.stringify(data) }),
  deleteMeta: (id) => fpRequest('/metas/' + id, { method: 'DELETE' }),
};

window.FP = FP;
