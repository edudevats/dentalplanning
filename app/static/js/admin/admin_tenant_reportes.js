// Header de las páginas admin de reportes de un tenant: pone el nombre real de la
// clínica (fallback al placeholder "Clínica #<id>") y renderiza los iconos Lucide.
(function () {
  const root = document.querySelector('[data-tenant-reportes]');
  if (!root) return;
  const tenantId = root.dataset.tenantReportes;
  const titleEl = document.getElementById('tenant-reportes-title');
  adminApi.get('/tenants/' + tenantId)
    .then(t => { if (titleEl && t && t.name) titleEl.textContent = t.name; })
    .catch(() => { /* sin permiso o inexistente: se deja el placeholder */ });
  if (typeof lucide !== 'undefined') lucide.createIcons();
})();
