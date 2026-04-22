// Clinical Sanctuary — Movimientos view
(async function () {
  const { clearChildren } = window.invDom;
  const { statusChip, timeAgo } = window.csShared;

  const tbody   = document.getElementById("cs-mov-body");
  const emptyEl = document.getElementById("cs-mov-empty");
  const footerEl= document.getElementById("cs-mov-footer");
  const filtro  = document.getElementById("filtro-tipo");
  const search  = document.getElementById("cs-mov-search");

  // KPIs
  const kpiTotal = document.getElementById("kpi-total");
  const kpiCompras = document.getElementById("kpi-compras");
  const kpiTransferencias = document.getElementById("kpi-transferencias");

  // Cache for material names and operatory names
  let materialsMap = {};
  let operatoriesMap = {};

  // Load lookup data
  async function loadLookups() {
    try {
      const [mats, ops] = await Promise.all([
        invApi.get("/materiales"),
        invApi.get("/operatorios"),
      ]);
      mats.forEach(m => { materialsMap[m.id] = m.nombre; });
      ops.forEach(o => { operatoriesMap[o.id] = o.nombre; });
    } catch (_) { /* continue with IDs */ }
  }

  function materialName(id) {
    return materialsMap[id] || ("Material #" + id);
  }

  function locationName(id) {
    if (id == null) return "Almacén";
    return operatoriesMap[id] || ("Operatorio #" + id);
  }

  function typeChip(tipo) {
    const map = {
      compra:        { label: "Compra",        variant: "stable" },
      transferencia: { label: "Transferencia", variant: "neutral" },
      ajuste:        { label: "Ajuste",        variant: "low" },
    };
    const cfg = map[tipo] || { label: tipo || "—", variant: "neutral" };
    return statusChip(cfg.label, cfg.variant);
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }) + " " + d.toLocaleTimeString("es-MX", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  let allData = [];

  function render(data) {
    clearChildren(tbody);

    // KPIs
    kpiTotal.textContent = String(data.length);
    kpiCompras.textContent = String(data.filter(m => m.tipo === "compra").length);
    kpiTransferencias.textContent = String(data.filter(m => m.tipo === "transferencia").length);

    if (!data.length) {
      emptyEl.classList.remove("hidden");
      footerEl.textContent = "";
      return;
    }
    emptyEl.classList.add("hidden");

    data.forEach(mv => {
      const tr = document.createElement("tr");
      tr.className = "border-b border-cs-outline-variant/30 hover:bg-cs-surface-container/50 transition-colors duration-100";

      // Fecha
      const tdDate = document.createElement("td");
      tdDate.className = "py-3 pr-4 text-sm text-cs-on-surface tabular-nums";
      tdDate.textContent = formatDate(mv.fecha);
      tr.appendChild(tdDate);

      // Tipo (chip)
      const tdTipo = document.createElement("td");
      tdTipo.className = "py-3 px-4";
      tdTipo.appendChild(typeChip(mv.tipo));
      tr.appendChild(tdTipo);

      // Material
      const tdMat = document.createElement("td");
      tdMat.className = "py-3 px-4 text-sm font-medium text-cs-on-surface";
      tdMat.textContent = materialName(mv.material_id);
      tr.appendChild(tdMat);

      // Origen
      const tdOrigen = document.createElement("td");
      tdOrigen.className = "py-3 px-4 text-sm text-cs-on-surface-var";
      tdOrigen.textContent = locationName(mv.origen_operatorio_id);
      tr.appendChild(tdOrigen);

      // Destino
      const tdDestino = document.createElement("td");
      tdDestino.className = "py-3 px-4 text-sm text-cs-on-surface-var";
      tdDestino.textContent = locationName(mv.destino_operatorio_id);
      tr.appendChild(tdDestino);

      // Cantidad
      const tdQty = document.createElement("td");
      tdQty.className = "py-3 px-4 text-sm font-semibold text-cs-on-surface tabular-nums text-right";
      tdQty.textContent = String(mv.cantidad);
      tr.appendChild(tdQty);

      // Motivo
      const tdMotivo = document.createElement("td");
      tdMotivo.className = "py-3 pl-4 text-sm text-cs-on-surface-var";
      tdMotivo.textContent = mv.motivo || "—";
      tr.appendChild(tdMotivo);

      tbody.appendChild(tr);
    });

    footerEl.textContent = data.length + " movimiento" + (data.length !== 1 ? "s" : "") + " encontrado" + (data.length !== 1 ? "s" : "");

    // Hydrate lucide icons if any
    if (typeof lucide !== "undefined") lucide.createIcons();
  }

  async function cargar() {
    const params = filtro.value ? "?tipo=" + filtro.value : "";
    try {
      allData = await invApi.get("/movimientos" + params);
      applySearch();
    } catch (err) {
      clearChildren(tbody);
      emptyEl.textContent = "Error al cargar movimientos.";
      emptyEl.classList.remove("hidden");
    }
  }

  function applySearch() {
    const q = (search.value || "").trim().toLowerCase();
    if (!q) {
      render(allData);
      return;
    }
    const filtered = allData.filter(mv => {
      const mat = materialName(mv.material_id).toLowerCase();
      const motivo = (mv.motivo || "").toLowerCase();
      const tipo = (mv.tipo || "").toLowerCase();
      return mat.includes(q) || motivo.includes(q) || tipo.includes(q);
    });
    render(filtered);
  }

  filtro.addEventListener("change", cargar);
  search.addEventListener("input", applySearch);

  await loadLookups();
  await cargar();
})();
