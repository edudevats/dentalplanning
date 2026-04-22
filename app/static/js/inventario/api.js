const BASE = "/api/v1/inventario";

function authHeaders() {
  let token = null;
  try { token = Auth.getToken(); } catch (_) {}
  if (!token) token = localStorage.getItem("token");
  return {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/json",
  };
}

async function req(method, path, body) {
  const opts = { method, headers: authHeaders() };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ error: r.statusText }));
    throw new Error(err.error || JSON.stringify(err.errors || err));
  }
  if (r.status === 204) return null;
  return r.json();
}

window.invApi = {
  get: (p) => req("GET", p),
  post: (p, b) => req("POST", p, b),
  put: (p, b) => req("PUT", p, b),
  del: (p) => req("DELETE", p),
};
