(async function () {
  const { statusChip, lucideIcon, initials } = window.csShared;
  const { clearChildren } = window.invDom;

  const grid       = document.getElementById("cs-ops-grid");
  const detail     = document.getElementById("cs-op-detail");
  const detailName = document.getElementById("cs-op-detail-name");
  const itemsUl    = document.getElementById("cs-op-detail-items");
  const renameBtn  = document.getElementById("cs-op-rename-btn");

  let distribucion = [];
  let selectedOp   = null;

  // Represents a "full" operatory stock level for the progress bar visual.
  const FULL_STOCK_THRESHOLD = 1000;

  function cardFor(op) {
    const li = document.createElement("li");
    const pct = op.total_units > 0
      ? Math.min(100, Math.round((op.total_units / FULL_STOCK_THRESHOLD) * 100))
      : 0;
    li.className = "p-4 rounded-lg bg-cs-surface-container-lowest cursor-pointer transition-all duration-200 hover:bg-cs-surface-container-low";
    li.dataset.opId = op.id;

    const head = document.createElement("div");
    head.className = "flex items-start justify-between mb-4";

    const nameWrap = document.createElement("div");
    const iconWrap = document.createElement("div");
    iconWrap.className = "w-9 h-9 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center mb-2";
    iconWrap.appendChild(lucideIcon("briefcase-medical", "h-4 w-4"));
    const name = document.createElement("p");
    name.className = "text-sm font-semibold text-cs-on-surface";
    name.textContent = op.nombre ?? "—";
    const sub = document.createElement("p");
    sub.className = "text-xs text-cs-on-surface-var";
    sub.textContent = "Suite Cl\u00ednica";
    nameWrap.append(iconWrap, name, sub);

    const chip = statusChip(
      op.status === "stable" ? "Listo" : "Stock Bajo",
      op.status === "stable" ? "stable" : "low",
    );
    head.append(nameWrap, chip);

    const stats = document.createElement("p");
    stats.className = "text-[10px] uppercase tracking-widest text-cs-on-surface-var mb-1.5";
    stats.textContent = "Nivel de Stock";

    const bar = document.createElement("div");
    bar.className = "h-1.5 w-full rounded-full bg-cs-surface-container overflow-hidden";
    const fill = document.createElement("div");
    fill.className = "h-full rounded-full bg-cs-primary";
    fill.style.width = pct + "%";
    bar.appendChild(fill);

    const pctLabel = document.createElement("p");
    pctLabel.className = "mt-1.5 text-xs font-semibold text-cs-on-surface tabular-nums";
    pctLabel.textContent = pct + "%";

    li.append(head, stats, bar, pctLabel);
    li.addEventListener("click", () => selectOperatory(op));
    return li;
  }

  function setActiveCard(opId) {
    grid.querySelectorAll("li").forEach(li => {
      if (li.dataset.opId == String(opId)) {
        li.classList.add("bg-cs-surface-bright", "ring-2", "ring-cs-primary");
      } else {
        li.classList.remove("bg-cs-surface-bright", "ring-2", "ring-cs-primary");
      }
    });
  }

  async function selectOperatory(op) {
    selectedOp = op;
    setActiveCard(op.id);
    detail.classList.remove("hidden");
    detailName.textContent = op.nombre ?? "—";

    clearChildren(itemsUl);
    const skeleton = document.createElement("li");
    skeleton.className = "text-xs text-cs-on-surface-var py-3";
    skeleton.textContent = "Cargando inventario…";
    itemsUl.appendChild(skeleton);

    const mats = await invApi.get("/materiales");
    const details = await Promise.all(
      mats.slice(0, 30).map(m => invApi.get("/materiales/" + m.id))
    );

    clearChildren(itemsUl);
    let any = false;
    details.forEach(m => {
      const here = (m.stock_por_ubicacion || []).find(s => s.operatorio_id === op.id);
      const whse = (m.stock_por_ubicacion || []).find(s => s.operatorio_id === null);
      if (!here || here.cantidad === 0) return;
      any = true;

      const li = document.createElement("li");
      li.className = "flex items-center gap-3 p-3 rounded-md bg-cs-surface-container";

      const av = document.createElement("div");
      av.className = "w-8 h-8 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-[10px] font-semibold";
      av.textContent = initials(m.nombre);

      const info = document.createElement("div");
      info.className = "flex-1 min-w-0";
      const n = document.createElement("p");
      n.className = "text-sm font-semibold text-cs-on-surface truncate";
      n.textContent = m.nombre ?? "—";
      const sku = document.createElement("p");
      sku.className = "text-[10px] text-cs-on-surface-var";
      sku.textContent = "SKU " + m.id;
      info.append(n, sku);

      const inRoom = document.createElement("span");
      inRoom.className = "text-xs font-semibold text-cs-on-surface tabular-nums w-12 text-right";
      inRoom.textContent = String(here.cantidad);

      const warehouse = document.createElement("span");
      warehouse.className = "text-xs text-cs-on-surface-var tabular-nums w-12 text-right";
      warehouse.textContent = whse ? String(whse.cantidad) : "0";

      li.append(av, info, inRoom, warehouse);
      itemsUl.appendChild(li);
    });

    if (!any) {
      const li = document.createElement("li");
      li.className = "text-xs text-cs-on-surface-var py-3";
      li.textContent = "No hay stock en este operatorio aún.";
      itemsUl.appendChild(li);
    }
  }

  async function loadOps() {
    distribucion = await invApi.get("/operatorios/distribucion");
    clearChildren(grid);
    distribucion.forEach(op => grid.appendChild(cardFor(op)));
    if (window.lucide) lucide.createIcons();

    const hash = window.location.hash.replace("#", "");
    if (hash) {
      const op = distribucion.find(o => String(o.id) === hash);
      if (op) selectOperatory(op);
    }
  }

  document.getElementById("cs-op-detail-close").addEventListener("click", () => {
    detail.classList.add("hidden");
  });

  if (renameBtn) {
    renameBtn.addEventListener("click", async () => {
      if (!selectedOp) return;
      const nuevoNombre = prompt("Nuevo nombre para el operatorio:", selectedOp.nombre);
      if (nuevoNombre === null) return;
      const nombreLimpio = nuevoNombre.trim();
      if (!nombreLimpio) {
        Toast.error("El nombre no puede estar vacío");
        return;
      }
      if (nombreLimpio === selectedOp.nombre) return;
      try {
        const res = await invApi.put("/operatorios/" + selectedOp.id, { nombre: nombreLimpio });
        Toast.success("Operatorio renombrado con éxito");
        selectedOp.nombre = res.nombre;
        detailName.textContent = res.nombre;
        await loadOps();
      } catch (err) {
        Toast.error(err.message || "Error al renombrar el operatorio");
      }
    });
  }

  await loadOps();
})();
