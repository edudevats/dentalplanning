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

async function req(method, path, body, _retry = true) {
  const opts = { method, headers: authHeaders() };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  if (r.status === 401) {
    // Token vencido: renueva en silencio con el refresh token y reintenta una
    // vez. Solo si la renovación falla se cierra la sesión.
    if (_retry) {
      let newToken = null;
      try { newToken = await Auth.refreshAccessToken(); } catch (_) {}
      if (newToken) return req(method, path, body, false);
    }
    try { Auth.logout(); } catch (_) {
      localStorage.removeItem("token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
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
