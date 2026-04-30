(async function () {
  const { currency, compactNumber, timeAgo, statusChip, lucideIcon } = window.csShared;
  const { clearChildren } = window.invDom;

  async function loadKpis() {
    const kpis = await invApi.get("/dashboard");
    function setKpi(attr, value) {
      const el = document.querySelector('[data-kpi="' + attr + '"]');
      if (el) el.textContent = value;
    }
    setKpi("asset-value",   currency(kpis.total_asset_value));
    setKpi("active-count",  compactNumber(kpis.active_materials));
    setKpi("active-sub",    "En todas las categorías");
    setKpi("critical-count", String(kpis.critical_items));
    setKpi("critical-sub",
      kpis.critical_items === 0 ? "Todos los artículos dentro del umbral" : "Artículos por debajo del umbral mínimo");
  }

  async function loadOperatoryDistribution() {
    const rows = await invApi.get("/operatorios/distribucion");
    const list = document.getElementById("cs-operatory-list");
    clearChildren(list);
    if (rows.length === 0) {
      const li = document.createElement("li");
      li.className = "text-sm text-cs-on-surface-var py-3 px-4";
      li.textContent = "No hay operatorios aún.";
      list.appendChild(li);
      return;
    }
    rows.forEach((op, idx) => {
      const li = document.createElement("li");
      li.className = "flex items-center gap-4 p-4 rounded-md bg-cs-surface-container-lowest hover:bg-cs-surface-container-low transition-colors duration-200 cursor-pointer";
      li.addEventListener("click", () => { window.location.href = "/inventario/operatorios#" + op.id; });

      const badge = document.createElement("div");
      badge.className = "w-10 h-10 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-xs font-semibold font-cs-display shrink-0";
      badge.textContent = "O" + String(idx + 1).padStart(2, "0");

      const info = document.createElement("div");
      info.className = "flex-1 min-w-0";
      const title = document.createElement("p");
      title.className = "text-sm font-semibold text-cs-on-surface truncate";
      title.textContent = op.nombre ?? "—";
      const subtitle = document.createElement("p");
      subtitle.className = "text-xs text-cs-on-surface-var truncate";
      subtitle.textContent = "Operatorio";
      info.append(title, subtitle);

      const units = document.createElement("div");
      units.className = "text-right shrink-0";
      const unitsVal = document.createElement("p");
      unitsVal.className = "text-sm font-semibold text-cs-on-surface tabular-nums";
      unitsVal.textContent = compactNumber(op.total_units);
      const unitsLabel = document.createElement("p");
      unitsLabel.className = "text-[10px] uppercase tracking-widest text-cs-on-surface-var";
      unitsLabel.textContent = "Unidades";
      units.append(unitsVal, unitsLabel);

      const chip = statusChip(
        op.status === "stable" ? "Estable" : "Reabastecer",
        op.status === "stable" ? "stable"  : "low",
      );

      li.append(badge, info, units, chip);
      list.appendChild(li);
    });
  }

  async function loadRecentFeed() {
    const items = await invApi.get("/movimientos/recientes");
    const feed = document.getElementById("cs-recent-feed");
    clearChildren(feed);
    if (items.length === 0) {
      const li = document.createElement("li");
      li.className = "text-sm text-cs-on-surface-var";
      li.textContent = "No hay movimientos recientes.";
      feed.appendChild(li);
      return;
    }
    items.forEach((mv) => {
      const li = document.createElement("li");
      li.className = "flex items-start gap-3";

      const iconWrap = document.createElement("div");
      iconWrap.className = "w-9 h-9 rounded-md bg-cs-surface-container text-cs-on-surface-var flex items-center justify-center shrink-0 mt-0.5";
      const iconName = {
        compra: "truck",
        transferencia: "arrow-right-left",
        ajuste: "sliders-horizontal",
      }[mv.tipo] || "package";
      iconWrap.appendChild(lucideIcon(iconName, "h-4 w-4"));

      const body = document.createElement("div");
      body.className = "flex-1 min-w-0";
      const title = document.createElement("p");
      title.className = "text-sm font-semibold text-cs-on-surface";
      let label;
      if (mv.tipo === "compra")         label = "Envío Entrante";
      else if (mv.tipo === "ajuste")    label = "Ajuste de Stock";
      else                              label = "Transferencia: " + mv.destino_nombre;
      title.textContent = label;

      const detail = document.createElement("p");
      detail.className = "text-xs text-cs-on-surface-var mt-0.5";
      detail.textContent = (mv.cantidad ?? "?") + "× " + (mv.material_nombre ?? "—");

      const when = document.createElement("p");
      when.className = "text-[10px] uppercase tracking-widest text-cs-on-surface-var mt-1";
      when.textContent = timeAgo(mv.fecha);

      body.append(title, detail, when);
      li.append(iconWrap, body);
      feed.appendChild(li);
    });
    if (window.lucide) lucide.createIcons();
  }

  const results = await Promise.allSettled([loadKpis(), loadOperatoryDistribution(), loadRecentFeed()]);
  results.forEach((r, i) => {
    if (r.status === "rejected") {
      console.error("Dashboard panel " + i + " failed:", r.reason);
    }
  });
})();
