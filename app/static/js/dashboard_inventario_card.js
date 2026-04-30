(async function () {
  let token = null;
  try { token = Auth.getToken(); } catch (_) {}
  if (!token) token = localStorage.getItem("token");
  if (!token) return;
  try {
    const r = await fetch("/api/v1/inventario/alertas/resumen", {
      headers: { "Authorization": "Bearer " + token },
    });
    if (!r.ok) return;
    const data = await r.json();
    const bajoEl = document.getElementById("inv-bajo");
    const altoEl = document.getElementById("inv-alto");
    const cadEl = document.getElementById("inv-caduca");
    if (bajoEl) bajoEl.textContent = String(data.bajo);
    if (altoEl) altoEl.textContent = String(data.alto);
    if (cadEl) cadEl.textContent = String(data.caducidad);
  } catch (_) {
    // silent
  }
})();
