(async function () {
  const { currency, statusChip, lucideIcon, initials } = window.csShared;
  const { clearChildren, makeOption } = window.invDom;

  const tbody    = document.getElementById("cs-almacen-body");
  const emptyMsg = document.getElementById("cs-almacen-empty");
  const footer   = document.getElementById("cs-almacen-footer");
  const search   = document.getElementById("cs-search");
  const catSel   = document.getElementById("cs-categoria");
  const alertSel = document.getElementById("cs-alerta");

  async function loadKpis() {
    const kpis = await invApi.get("/dashboard");
    function setKpi(attr, value) {
      const el = document.querySelector('[data-kpi="' + attr + '"]');
      if (el) el.textContent = value;
    }
    setKpi("total-value", currency(kpis.total_asset_value));
    setKpi("low-count",   String(kpis.critical_items));
    setKpi("exp-count",   "—");
  }

  async function loadCategories() {
    const cats = await invApi.get("/categorias");
    cats.forEach(c => catSel.appendChild(makeOption(c.nombre, c.nombre)));
  }

  function buildQuery() {
    const p = new URLSearchParams();
    if (search.value)   p.set("busqueda", search.value);
    if (catSel.value)   p.set("categoria", catSel.value);
    return "/materiales?" + p;
  }

  function rowFor(m) {
    const tr = document.createElement("tr");
    tr.className = "group transition-colors duration-200 cursor-pointer hover:bg-cs-surface-container-low";
    tr.addEventListener("click", () => { window.location.href = "/inventario/material/" + m.id; });

    const tdMat = document.createElement("td");
    tdMat.className = "py-4 pr-4";
    const wrap = document.createElement("div");
    wrap.className = "flex items-center gap-3";
    const avatar = document.createElement("div");
    avatar.className = "w-9 h-9 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-xs font-semibold font-cs-display shrink-0";
    avatar.textContent = initials(m.nombre);
    const meta = document.createElement("div");
    const name = document.createElement("p");
    name.className = "text-sm font-semibold text-cs-on-surface";
    name.textContent = m.nombre ?? "—";
    const sku = document.createElement("p");
    sku.className = "text-xs text-cs-on-surface-var";
    sku.textContent = "SKU: " + m.id;
    meta.append(name, sku);
    wrap.append(avatar, meta);
    tdMat.appendChild(wrap);

    const tdStock = document.createElement("td");
    tdStock.className = "py-4 px-4 text-right text-sm font-semibold text-cs-on-surface tabular-nums";
    tdStock.textContent = String(m.total_global ?? "—") + " " + (m.unidad_inventario || "");

    const tdMinMax = document.createElement("td");
    tdMinMax.className = "py-4 px-4 text-right text-xs text-cs-on-surface-var tabular-nums";
    tdMinMax.textContent = "—";

    const tdStatus = document.createElement("td");
    tdStatus.className = "py-4 px-4";
    tdStatus.appendChild(statusChip("En Stock", "stable"));

    const tdExp = document.createElement("td");
    tdExp.className = "py-4 px-4 text-xs text-cs-on-surface-var";
    tdExp.textContent = m.expira ? "Varía por lote" : "N/A";

    const tdActions = document.createElement("td");
    tdActions.className = "py-4 pl-4 text-right";
    const btn = document.createElement("button");
    btn.className = "p-2 rounded-md text-cs-on-surface-var hover:text-cs-primary hover:bg-cs-primary-container transition-colors opacity-0 group-hover:opacity-100";
    btn.setAttribute("aria-label", "Editar material");
    btn.appendChild(lucideIcon("pencil", "h-4 w-4"));
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      window.location.href = "/inventario/material/" + m.id;
    });
    tdActions.appendChild(btn);

    tr.append(tdMat, tdStock, tdMinMax, tdStatus, tdExp, tdActions);
    return tr;
  }

  async function load() {
    try {
      const mats = await invApi.get(buildQuery());
      clearChildren(tbody);
      if (mats.length === 0) {
        emptyMsg.classList.remove("hidden");
        emptyMsg.textContent = "No se encontraron materiales con los filtros actuales.";
        footer.textContent = "";
      } else {
        emptyMsg.classList.add("hidden");
        mats.forEach(m => tbody.appendChild(rowFor(m)));
        footer.textContent = "Mostrando " + mats.length + " resultados";
      }
    } catch (err) {
      clearChildren(tbody);
      emptyMsg.classList.remove("hidden");
      emptyMsg.textContent = "No se pudieron cargar los materiales. Por favor recarga la página.";
      footer.textContent = "";
      console.error("Almacen load failed:", err);
    }
    if (window.lucide) lucide.createIcons();
  }

  [catSel, alertSel].forEach(el => el.addEventListener("change", load));
  search.addEventListener("input", () => setTimeout(load, 200));

  const url = new URL(window.location);
  if (url.searchParams.get("filtro")) {
    alertSel.value = url.searchParams.get("filtro");
  }

  const results = await Promise.allSettled([loadKpis(), loadCategories()]);
  results.forEach((r, i) => {
    if (r.status === "rejected") console.error("Almacen init panel " + i + " failed:", r.reason);
  });
  await load();
})();
