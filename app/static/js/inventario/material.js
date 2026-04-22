(async function () {
  const { currency, timeAgo, statusChip, lucideIcon, initials } = window.csShared;
  const { clearChildren } = window.invDom;

  const app = document.getElementById("material-app");
  const id = app.dataset.materialId;

  // ── Helpers ──────────────────────────────────────────────────────────
  function showToast(msg) {
    const toast = document.getElementById("cs-toast");
    const text = document.getElementById("cs-toast-msg");
    text.textContent = msg;
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), 2500);
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "numeric" });
  }

  function expiryBadge(isoDate, expira) {
    if (!expira || !isoDate) {
      const span = document.createElement("span");
      span.className = "inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-cs-surface-container text-cs-on-surface-var";
      span.textContent = "No caduca";
      return span;
    }
    const now = new Date();
    const exp = new Date(isoDate);
    const diffDays = Math.ceil((exp - now) / (1000 * 60 * 60 * 24));
    let tone, label;
    if (diffDays < 0) {
      tone = "bg-cs-error-container text-cs-on-error-container";
      label = "Caducado";
    } else if (diffDays <= 30) {
      tone = "bg-cs-error-container/30 text-cs-error";
      label = diffDays + " días";
    } else if (diffDays <= 90) {
      tone = "bg-amber-100 text-amber-800";
      label = diffDays + " días";
    } else {
      tone = "bg-cs-primary-container text-cs-on-primary-container";
      label = formatDate(isoDate);
    }
    const span = document.createElement("span");
    span.className = "inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold " + tone;
    span.textContent = label;
    return span;
  }

  function tipoChip(tipo) {
    const map = {
      compra: { label: "Compra", icon: "truck", tone: "bg-cs-primary-container text-cs-on-primary-container" },
      transferencia: { label: "Transferencia", icon: "arrow-right-left", tone: "bg-cs-surface-container text-cs-on-surface-var" },
      ajuste: { label: "Ajuste", icon: "sliders-horizontal", tone: "bg-amber-100 text-amber-800" },
    };
    const cfg = map[tipo] || { label: tipo, icon: "package", tone: "bg-cs-surface-container text-cs-on-surface-var" };
    const span = document.createElement("span");
    span.className = "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold " + cfg.tone;
    span.appendChild(lucideIcon(cfg.icon, "h-3 w-3"));
    const txt = document.createTextNode(cfg.label);
    span.appendChild(txt);
    return span;
  }

  // ── Load data ───────────────────────────────────────────────────────
  let data, operatorios, operatorioMap;
  try {
    [data, operatorios] = await Promise.all([
      invApi.get("/materiales/" + id),
      invApi.get("/operatorios"),
    ]);
  } catch (err) {
    console.error("Failed to load material:", err);
    return;
  }

  operatorioMap = {};
  operatorios.forEach(op => { operatorioMap[op.id] = op.nombre; });

  function ubicacionNombre(opId) {
    if (opId == null) return "Almacén Principal";
    return operatorioMap[opId] || ("Operatorio #" + opId);
  }

  function ubicacionIcon(opId) {
    return opId == null ? "warehouse" : "briefcase-medical";
  }

  // ── Header ──────────────────────────────────────────────────────────
  document.getElementById("cs-avatar").textContent = initials(data.nombre);
  document.getElementById("cs-nombre").textContent = data.nombre || "—";
  document.getElementById("cs-sku").textContent = data.id;
  document.getElementById("cs-unit").textContent = "Unidad: " + (data.unidad_inventario || "pz");

  const catContainer = document.getElementById("cs-categories");
  (data.categorias || []).forEach(c => {
    const chip = document.createElement("span");
    chip.className = "inline-flex items-center px-2 py-0.5 rounded-md bg-cs-surface-container text-[10px] font-semibold text-cs-on-surface-var uppercase tracking-wider";
    chip.textContent = c.nombre;
    catContainer.appendChild(chip);
  });

  // ── KPIs ────────────────────────────────────────────────────────────
  const totalStock = (data.stock_por_ubicacion || []).reduce((sum, s) => sum + (s.cantidad || 0), 0);
  const locationsWithStock = (data.stock_por_ubicacion || []).filter(s => s.cantidad > 0).length;

  document.getElementById("cs-kpi-total").textContent = totalStock + " " + (data.unidad_inventario || "pz");
  document.getElementById("cs-kpi-locations").textContent = String(locationsWithStock);

  const expiryKpi = document.getElementById("cs-kpi-expiry");
  const expirySub = document.getElementById("cs-kpi-expiry-sub");
  const expiraToggle = document.getElementById("cs-expira-toggle");

  function updateExpiryDisplay(expira) {
    if (expira) {
      const futureLotes = (data.lotes || []).filter(l => l.fecha_caducidad);
      if (futureLotes.length > 0) {
        const closest = futureLotes.reduce((min, l) => {
          const d = new Date(l.fecha_caducidad);
          return d < min ? d : min;
        }, new Date("2999-01-01"));
        const diffDays = Math.ceil((closest - new Date()) / (1000 * 60 * 60 * 24));
        expiryKpi.textContent = diffDays + " días";
        if (diffDays <= 30) {
          expiryKpi.className = "mt-3 font-cs-display text-3xl font-bold text-cs-error";
          expirySub.textContent = "Próxima caducidad más cercana";
        } else {
          expiryKpi.className = "mt-3 font-cs-display text-3xl font-bold text-cs-on-surface";
          expirySub.textContent = "Próxima caducidad más cercana";
        }
      } else {
        expiryKpi.textContent = "—";
        expiryKpi.className = "mt-3 font-cs-display text-3xl font-bold text-cs-on-surface";
        expirySub.textContent = "Sin lotes con caducidad";
      }
    } else {
      expiryKpi.textContent = "N/A";
      expiryKpi.className = "mt-3 font-cs-display text-3xl font-bold text-cs-on-surface-var";
      expirySub.textContent = "Este material no caduca";
    }
  }

  expiraToggle.checked = data.expira;
  updateExpiryDisplay(data.expira);

  expiraToggle.addEventListener("change", async () => {
    const newVal = expiraToggle.checked;
    try {
      await invApi.put("/materiales/" + id, { expira: newVal });
      data.expira = newVal;
      updateExpiryDisplay(newVal);
      showToast(newVal ? "Caducidad activada" : "Caducidad desactivada");
    } catch (err) {
      expiraToggle.checked = !newVal;
      console.error("Toggle expira failed:", err);
    }
  });

  // ── Stock por Ubicación ─────────────────────────────────────────────
  const stockGrid = document.getElementById("cs-stock-grid");
  const stockEmpty = document.getElementById("cs-stock-empty");
  const stocks = data.stock_por_ubicacion || [];

  // Ensure almacen entry exists
  if (!stocks.find(s => s.operatorio_id == null)) {
    stocks.unshift({ operatorio_id: null, cantidad: 0, minimo: null, maximo: null });
  }

  if (stocks.length === 0) {
    stockEmpty.classList.remove("hidden");
  } else {
    stocks.forEach(s => {
      const card = document.createElement("div");
      card.className = "p-5 rounded-lg bg-cs-surface-container transition-all duration-200 hover:bg-cs-surface-container-low";

      // Header
      const header = document.createElement("div");
      header.className = "flex items-center gap-3 mb-4";
      const iconWrap = document.createElement("div");
      iconWrap.className = "w-10 h-10 rounded-md flex items-center justify-center shrink-0 " +
        (s.operatorio_id == null
          ? "bg-cs-primary-container text-cs-on-primary-container"
          : "bg-cs-surface-container-lowest text-cs-on-surface-var");
      iconWrap.appendChild(lucideIcon(ubicacionIcon(s.operatorio_id), "h-5 w-5"));
      const headerText = document.createElement("div");
      headerText.className = "flex-1 min-w-0";
      const locName = document.createElement("p");
      locName.className = "text-sm font-semibold text-cs-on-surface truncate";
      locName.textContent = ubicacionNombre(s.operatorio_id);
      const locSub = document.createElement("p");
      locSub.className = "text-[10px] text-cs-on-surface-var uppercase tracking-widest";
      locSub.textContent = s.operatorio_id == null ? "Almacenamiento Central" : "Operatorio";
      headerText.append(locName, locSub);
      header.append(iconWrap, headerText);

      // Stock quantity + bar
      const maxRef = s.maximo || Math.max(s.cantidad || 1, 100);
      const pct = Math.min(100, Math.round(((s.cantidad || 0) / maxRef) * 100));
      const isLow = s.minimo != null && s.cantidad < s.minimo;

      const qtySection = document.createElement("div");
      qtySection.className = "mb-4";
      const qtyVal = document.createElement("p");
      qtyVal.className = "font-cs-display text-2xl font-bold tabular-nums " + (isLow ? "text-cs-error" : "text-cs-on-surface");
      qtyVal.textContent = (s.cantidad || 0) + " " + (data.unidad_inventario || "pz");
      const barOuter = document.createElement("div");
      barOuter.className = "mt-2 h-1.5 w-full rounded-full bg-cs-surface-container-lowest overflow-hidden";
      const barInner = document.createElement("div");
      barInner.className = "h-full rounded-full transition-all duration-500 " + (isLow ? "bg-cs-error" : "bg-cs-primary");
      barInner.style.width = pct + "%";
      barOuter.appendChild(barInner);

      if (isLow) {
        const alertBadge = statusChip("Stock Bajo", "low");
        alertBadge.className += " mt-2";
        qtySection.append(qtyVal, barOuter, alertBadge);
      } else {
        qtySection.append(qtyVal, barOuter);
      }

      // Min/Max inputs
      const thresholds = document.createElement("div");
      thresholds.className = "grid grid-cols-2 gap-3";

      function makeInput(label, field, value) {
        const wrap = document.createElement("div");
        const lbl = document.createElement("label");
        lbl.className = "block text-[10px] font-semibold uppercase tracking-widest text-cs-on-surface-var mb-1.5";
        lbl.textContent = label;
        const inp = document.createElement("input");
        inp.type = "number";
        inp.min = "0";
        inp.value = value == null ? "" : value;
        inp.placeholder = "—";
        inp.dataset.op = s.operatorio_id == null ? "" : String(s.operatorio_id);
        inp.dataset.campo = field;
        inp.className = "w-full rounded-md bg-cs-surface-container-lowest px-3 py-2 text-sm font-semibold tabular-nums text-cs-on-surface focus:outline-none focus:ring-2 focus:ring-cs-primary/30 placeholder:text-cs-outline";
        wrap.append(lbl, inp);
        return wrap;
      }

      thresholds.append(
        makeInput("Mínimo", "minimo", s.minimo),
        makeInput("Máximo", "maximo", s.maximo),
      );

      card.append(header, qtySection, thresholds);
      stockGrid.appendChild(card);
    });
  }

  // Save thresholds
  document.getElementById("cs-save-thresholds").addEventListener("click", async () => {
    const byOp = {};
    stockGrid.querySelectorAll("input").forEach(inp => {
      const key = inp.dataset.op || "null";
      if (!byOp[key]) {
        byOp[key] = {
          operatorio_id: inp.dataset.op ? parseInt(inp.dataset.op) : null,
        };
      }
      byOp[key][inp.dataset.campo] = inp.value === "" ? null : parseInt(inp.value);
    });
    try {
      await invApi.put("/materiales/" + id, { umbrales: Object.values(byOp) });
      showToast("Umbrales guardados correctamente");
    } catch (err) {
      console.error("Save thresholds failed:", err);
      showToast("Error al guardar umbrales");
    }
  });

  // ── Lotes Activos ───────────────────────────────────────────────────
  const lotesBody = document.getElementById("cs-lotes-body");
  const lotesEmpty = document.getElementById("cs-lotes-empty");
  const lotesCount = document.getElementById("cs-lotes-count");
  const lotes = data.lotes || [];
  lotesCount.textContent = lotes.length + " lote" + (lotes.length !== 1 ? "s" : "");

  if (lotes.length === 0) {
    lotesEmpty.classList.remove("hidden");
  } else {
    lotes.forEach((lt, idx) => {
      const tr = document.createElement("tr");
      tr.className = "group transition-colors duration-200 hover:bg-cs-surface-container-low";

      // Lote ID badge
      const tdLote = document.createElement("td");
      tdLote.className = "py-4 pr-4";
      const loteBadge = document.createElement("div");
      loteBadge.className = "flex items-center gap-3";
      const loteIcon = document.createElement("div");
      loteIcon.className = "w-9 h-9 rounded-md bg-cs-surface-container text-cs-on-surface-var flex items-center justify-center";
      loteIcon.appendChild(lucideIcon("package", "h-4 w-4"));
      const loteInfo = document.createElement("div");
      const loteName = document.createElement("p");
      loteName.className = "text-sm font-semibold text-cs-on-surface";
      loteName.textContent = "Lote #" + lt.id;
      const loteQty = document.createElement("p");
      loteQty.className = "text-xs text-cs-on-surface-var";
      loteQty.textContent = "Inicial: " + (lt.cantidad_inicial || "—") + " " + (data.unidad_inventario || "pz");
      loteInfo.append(loteName, loteQty);
      loteBadge.append(loteIcon, loteInfo);
      tdLote.appendChild(loteBadge);

      // Fecha surtido
      const tdSurtido = document.createElement("td");
      tdSurtido.className = "py-4 px-4 text-sm text-cs-on-surface";
      tdSurtido.textContent = formatDate(lt.fecha_surtido);

      // Caducidad
      const tdCaducidad = document.createElement("td");
      tdCaducidad.className = "py-4 px-4";
      tdCaducidad.appendChild(expiryBadge(lt.fecha_caducidad, data.expira));

      // Precio
      const tdPrecio = document.createElement("td");
      tdPrecio.className = "py-4 px-4 text-sm font-semibold text-cs-on-surface text-right tabular-nums";
      tdPrecio.textContent = lt.precio_unitario != null ? currency(lt.precio_unitario) : "—";

      // Ubicaciones
      const tdUbics = document.createElement("td");
      tdUbics.className = "py-4 pl-4";
      const ubicsWrap = document.createElement("div");
      ubicsWrap.className = "flex flex-wrap gap-1.5";
      (lt.ubicaciones || []).forEach(u => {
        const chip = document.createElement("span");
        chip.className = "inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-cs-surface-container text-[10px] font-semibold text-cs-on-surface-var";
        chip.textContent = ubicacionNombre(u.operatorio_id) + ": " + u.cantidad_restante;
        ubicsWrap.appendChild(chip);
      });
      if ((lt.ubicaciones || []).length === 0) {
        ubicsWrap.textContent = "—";
        ubicsWrap.className = "text-xs text-cs-on-surface-var";
      }
      tdUbics.appendChild(ubicsWrap);

      tr.append(tdLote, tdSurtido, tdCaducidad, tdPrecio, tdUbics);
      lotesBody.appendChild(tr);
    });
  }

  // ── Historial ───────────────────────────────────────────────────────
  const historyBody = document.getElementById("cs-history-body");
  const historyEmpty = document.getElementById("cs-history-empty");
  let movs = [];
  try {
    movs = await invApi.get("/movimientos?material_id=" + id);
  } catch (err) {
    console.error("Load history failed:", err);
  }

  if (movs.length === 0) {
    historyEmpty.classList.remove("hidden");
  } else {
    movs.forEach(mv => {
      const tr = document.createElement("tr");
      tr.className = "group transition-colors duration-200 hover:bg-cs-surface-container-low";

      // Fecha
      const tdFecha = document.createElement("td");
      tdFecha.className = "py-4 pr-4";
      const fechaWrap = document.createElement("div");
      const fechaMain = document.createElement("p");
      fechaMain.className = "text-sm font-semibold text-cs-on-surface";
      fechaMain.textContent = formatDate(mv.fecha);
      const fechaSub = document.createElement("p");
      fechaSub.className = "text-[10px] text-cs-on-surface-var uppercase tracking-widest";
      fechaSub.textContent = timeAgo(mv.fecha);
      fechaWrap.append(fechaMain, fechaSub);
      tdFecha.appendChild(fechaWrap);

      // Tipo
      const tdTipo = document.createElement("td");
      tdTipo.className = "py-4 px-4";
      tdTipo.appendChild(tipoChip(mv.tipo));

      // Origen
      const tdOrigen = document.createElement("td");
      tdOrigen.className = "py-4 px-4 text-sm text-cs-on-surface";
      tdOrigen.textContent = ubicacionNombre(mv.origen_operatorio_id);

      // Destino
      const tdDestino = document.createElement("td");
      tdDestino.className = "py-4 px-4 text-sm text-cs-on-surface";
      tdDestino.textContent = ubicacionNombre(mv.destino_operatorio_id);

      // Cantidad
      const tdCantidad = document.createElement("td");
      tdCantidad.className = "py-4 px-4 text-right";
      const qtyBadge = document.createElement("span");
      const isPositive = mv.tipo === "compra" || (mv.tipo === "ajuste" && mv.cantidad > 0);
      qtyBadge.className = "inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold tabular-nums " +
        (isPositive ? "bg-cs-primary-container text-cs-on-primary-container" : "bg-cs-surface-container text-cs-on-surface-var");
      qtyBadge.textContent = (isPositive ? "+" : "") + mv.cantidad + " " + (data.unidad_inventario || "pz");
      tdCantidad.appendChild(qtyBadge);

      // Motivo
      const tdMotivo = document.createElement("td");
      tdMotivo.className = "py-4 pl-4 text-xs text-cs-on-surface-var max-w-[150px] truncate";
      tdMotivo.textContent = mv.motivo || "—";
      tdMotivo.title = mv.motivo || "";

      tr.append(tdFecha, tdTipo, tdOrigen, tdDestino, tdCantidad, tdMotivo);
      historyBody.appendChild(tr);
    });
  }

  // ── Hydrate icons ───────────────────────────────────────────────────
  if (window.lucide) lucide.createIcons();
})();
