// Clinical Sanctuary — Compras view
(async function () {
  const { clearChildren, makeOption } = window.invDom;
  const { currency } = window.csShared;

  const tbody    = document.getElementById("cs-compras-body");
  const emptyEl  = document.getElementById("cs-compras-empty");
  const footerEl = document.getElementById("cs-compras-footer");
  const search   = document.getElementById("cs-compras-search");
  const modal    = document.getElementById("modal-compra");
  const form     = document.getElementById("form-compra");

  // KPIs
  const kpiTotal     = document.getElementById("kpi-total-compras");
  const kpiUnidades  = document.getElementById("kpi-unidades");
  const kpiInversion = document.getElementById("kpi-inversion");

  // Caches
  let materialsMap = {};
  let operatoriesMap = {};
  let materialsList = [];
  let allData = [];

  // Material picker (autocompletado)
  const matSearchInput = document.getElementById("compra-mat-search");
  const matHidden = form.querySelector('[name="material_id"]');
  // Al teclear se invalida la seleccion previa hasta elegir de la lista.
  matSearchInput.addEventListener("input", () => { matHidden.value = ""; });
  Combobox({
    input: matSearchInput,
    getItems: () => materialsList,
    getLabel: m => m.nombre,
    onSelect: (m) => { matHidden.value = String(m.id); matSearchInput.value = m.nombre; },
    clearOnSelect: false,
    emptyText: "Sin materiales",
    classes: {
      menu: "absolute z-50 left-0 right-0 mt-1 max-h-64 overflow-y-auto rounded-md bg-cs-surface-container-lowest shadow-lg",
      item: "px-4 py-2.5 text-sm cursor-pointer flex items-center justify-between gap-3",
      itemBase: "text-cs-on-surface hover:bg-cs-surface-container",
      itemActive: "bg-cs-surface-container text-cs-on-surface",
      meta: "text-xs text-cs-on-surface-var tabular-nums shrink-0",
      empty: "px-4 py-2.5 text-sm text-cs-on-surface-var",
    },
  });

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

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
    return d.toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }

  function render(data) {
    clearChildren(tbody);

    // KPIs — computed from full dataset (allData), not filtered
    const totalUnits = allData.reduce((s, c) => s + (c.cantidad || 0), 0);
    const totalInv = allData.reduce((s, c) => s + ((c.cantidad || 0) * (c.precio_unitario || 0)), 0);
    kpiTotal.textContent = String(allData.length);
    kpiUnidades.textContent = totalUnits.toLocaleString("es-MX");
    kpiInversion.textContent = currency(totalInv);

    if (!data.length) {
      emptyEl.classList.remove("hidden");
      footerEl.textContent = "";
      return;
    }
    emptyEl.classList.add("hidden");

    data.forEach(c => {
      const tr = document.createElement("tr");
      tr.className = "border-b border-cs-outline-variant/30 hover:bg-cs-surface-container/50 transition-colors duration-100";

      // Fecha
      const tdDate = document.createElement("td");
      tdDate.className = "py-3 pr-4 text-sm text-cs-on-surface tabular-nums";
      tdDate.textContent = formatDate(c.fecha || c.fecha_surtido);
      tr.appendChild(tdDate);

      // Material
      const tdMat = document.createElement("td");
      tdMat.className = "py-3 px-4 text-sm font-medium text-cs-on-surface";
      tdMat.textContent = materialName(c.material_id);
      tr.appendChild(tdMat);

      // Destino
      const tdDest = document.createElement("td");
      tdDest.className = "py-3 px-4 text-sm text-cs-on-surface-var";
      tdDest.textContent = locationName(c.operatorio_destino_id);
      tr.appendChild(tdDest);

      // Cantidad
      const tdQty = document.createElement("td");
      tdQty.className = "py-3 px-4 text-sm font-semibold text-cs-on-surface tabular-nums text-right";
      tdQty.textContent = String(c.cantidad);
      tr.appendChild(tdQty);

      // Precio unitario
      const tdPrice = document.createElement("td");
      tdPrice.className = "py-3 px-4 text-sm text-cs-on-surface-var tabular-nums text-right";
      tdPrice.textContent = currency(c.precio_unitario);
      tr.appendChild(tdPrice);

      // Total
      const tdTotal = document.createElement("td");
      tdTotal.className = "py-3 px-4 text-sm font-semibold text-cs-primary tabular-nums text-right";
      tdTotal.textContent = currency((c.cantidad || 0) * (c.precio_unitario || 0));
      tr.appendChild(tdTotal);

      // Comentarios
      const tdComment = document.createElement("td");
      tdComment.className = "py-3 pl-4 text-sm text-cs-on-surface-var";
      tdComment.textContent = c.comentarios || "—";
      tr.appendChild(tdComment);

      tbody.appendChild(tr);
    });

    footerEl.textContent = data.length + " compra" + (data.length !== 1 ? "s" : "") + " encontrada" + (data.length !== 1 ? "s" : "");
  }

  async function cargar() {
    try {
      allData = await invApi.get("/compras");
      applySearch();
    } catch (err) {
      clearChildren(tbody);
      emptyEl.textContent = "Error al cargar compras.";
      emptyEl.classList.remove("hidden");
    }
  }

  function applySearch() {
    const q = (search.value || "").trim().toLowerCase();
    if (!q) {
      render(allData);
      return;
    }
    const filtered = allData.filter(c => {
      const mat = materialName(c.material_id).toLowerCase();
      const comment = (c.comentarios || "").toLowerCase();
      return mat.includes(q) || comment.includes(q);
    });
    render(filtered);
  }

  // Search
  search.addEventListener("input", applySearch);

  // Modal
  function openModal() {
    modal.classList.remove("hidden");
    if (typeof lucide !== "undefined") lucide.createIcons();
  }
  function closeModal() {
    modal.classList.add("hidden");
  }

  document.getElementById("btn-nueva-compra").addEventListener("click", openModal);
  document.getElementById("cancelar-compra").addEventListener("click", closeModal);
  document.getElementById("cancelar-compra-2").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  // Populate selects
  async function llenarSelects() {
    const [mats, ops] = await Promise.all([
      invApi.get("/materiales"),
      invApi.get("/operatorios"),
    ]);
    materialsList = mats;

    const selO = form.querySelector('[name="operatorio_destino_id"]');
    [...selO.querySelectorAll('option:not([value=""])')].forEach(o => o.remove());
    ops.forEach(op => selO.appendChild(makeOption(op.id, op.nombre)));
  }

  // Submit
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);

    if (!fd.get("material_id")) {
      let errP = form.querySelector(".cs-form-error");
      if (!errP) {
        errP = document.createElement("p");
        errP.className = "cs-form-error text-xs font-medium text-cs-error text-center mt-2";
        form.querySelector('[type="submit"]').parentElement.appendChild(errP);
      }
      errP.textContent = "Selecciona un material de la lista.";
      matSearchInput.focus();
      return;
    }

    const body = {
      material_id: parseInt(fd.get("material_id")),
      cantidad: parseInt(fd.get("cantidad")),
      precio_unitario: parseFloat(fd.get("precio_unitario")),
      fecha_surtido: fd.get("fecha_surtido"),
      fecha_caducidad: fd.get("fecha_caducidad") || null,
      no_caduca: fd.get("no_caduca") === "on",
      operatorio_destino_id: fd.get("operatorio_destino_id")
        ? parseInt(fd.get("operatorio_destino_id")) : null,
      comentarios: fd.get("comentarios") || null,
      actualizar_costo_master: fd.get("actualizar_costo_master") === "on",
    };

    const submitBtn = form.querySelector('[type="submit"]');
    const origText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Guardando...";

    try {
      await invApi.post("/compras", body);
      closeModal();
      form.reset();
      matSearchInput.value = "";
      matHidden.value = "";
      await cargar();
    } catch (err) {
      // Show inline error
      let errP = form.querySelector(".cs-form-error");
      if (!errP) {
        errP = document.createElement("p");
        errP.className = "cs-form-error text-xs font-medium text-cs-error text-center mt-2";
        submitBtn.parentElement.appendChild(errP);
      }
      errP.textContent = "Error: " + err.message;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = origText;
    }
  });

  await loadLookups();
  await Promise.all([llenarSelects(), cargar()]);
})();
