// Tiny fetch wrapper that reuses the JWT from localStorage.

const FP_BASE = '/api/v1/finanzas-personales';

// Finanzas Personales es una mini-app aparte que no carga app.js, así que la
// renovación del token vive aquí (single-flight) en vez de reusar Auth.
let _fpRefreshing = null;

function fpRefreshAccessToken() {
  if (_fpRefreshing) return _fpRefreshing;
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return Promise.resolve(null);
  _fpRefreshing = (async () => {
    try {
      const res = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: { Authorization: `Bearer ${refreshToken}` },
      });
      if (!res.ok) return null;
      const data = await res.json().catch(() => ({}));
      if (!data.access_token) return null;
      localStorage.setItem('token', data.access_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      _fpRefreshing = null;
    }
  })();
  return _fpRefreshing;
}

function fpLogout() {
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  window.location.href = '/login';
}

async function fpRequest(path, options = {}, _retry = true) {
  const token = localStorage.getItem('token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(FP_BASE + path, { ...options, headers });
  if (res.status === 401) {
    // Token vencido: renueva en silencio y reintenta una vez antes de rendirse.
    if (_retry) {
      const newToken = await fpRefreshAccessToken();
      if (newToken) return fpRequest(path, options, false);
    }
    fpLogout();
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

  dashboardAnual: (year) => fpRequest(`/dashboard/anual?year=${year}`),
  getSaldoInicial: (year) => fpRequest(`/saldo-inicial?year=${year}`),
  upsertSaldoInicial: (año, monto) =>
    fpRequest('/saldo-inicial', { method: 'POST', body: JSON.stringify({ año, monto }) }),
  cerrarAño: (año) =>
    fpRequest('/cerrar-año', { method: 'POST', body: JSON.stringify({ año }) }),
};

window.FP = FP;
