(async function () {
  const { makeOption, clearChildren } = window.invDom;

  const origenSel  = document.getElementById("cs-origen");
  const destinoSel = document.getElementById("cs-destino");
  const destTitle  = document.getElementById("cs-dest-title");
  const matSearch  = document.getElementById("cs-mat-search");
  const matSuggest = document.getElementById("cs-mat-suggest");
  const matSelected= document.getElementById("cs-mat-selected");
  const matName    = document.getElementById("cs-mat-name");
  const matSku     = document.getElementById("cs-mat-sku");
  const qtyInput   = document.getElementById("cs-qty");
  const qtyUnits   = document.getElementById("cs-qty-units");
  const impactCurr = document.getElementById("cs-impact-current");
  const impactPost = document.getElementById("cs-impact-post");
  const impactBar  = document.getElementById("cs-impact-bar");
  const confirmBtn = document.getElementById("cs-confirm");
  const errorEl    = document.getElementById("cs-error");

  let operatorios = [];
  let materiales  = [];
  let selectedMat = null;
  const detailCache = {};

  async function init() {
    const [ops, mats] = await Promise.all([
      invApi.get("/operatorios"),
      invApi.get("/materiales"),
    ]);
    operatorios = ops;
    materiales = mats;

    ops.forEach(op => {
      origenSel.appendChild(makeOption(op.id, op.nombre));
      destinoSel.appendChild(makeOption(op.id, op.nombre));
    });

    origenSel.addEventListener("change", refreshImpact);
    destinoSel.addEventListener("change", () => {
      const op = operatorios.find(o => String(o.id) === destinoSel.value);
      destTitle.textContent = op ? op.nombre + " Capacidad" : "Capacidad del Almacén Principal";
    });

    matSearch.addEventListener("input", onSearch);
    document.getElementById("cs-mat-clear").addEventListener("click", clearSelection);

    document.getElementById("cs-qty-minus").addEventListener("click", () => {
      qtyInput.value = Math.max(1, parseInt(qtyInput.value || "1") - 1);
      refreshImpact();
    });
    document.getElementById("cs-qty-plus").addEventListener("click", () => {
      qtyInput.value = parseInt(qtyInput.value || "1") + 1;
      refreshImpact();
    });
    let _qtyTimer;
    qtyInput.addEventListener("input", () => {
      clearTimeout(_qtyTimer);
      _qtyTimer = setTimeout(refreshImpact, 250);
    });

    confirmBtn.addEventListener("click", submit);
    // Clear validation error when the user changes any field.
    [origenSel, destinoSel, qtyInput, matSearch].forEach(el => {
      el.addEventListener("input",  () => errorEl.classList.add("hidden"));
      el.addEventListener("change", () => errorEl.classList.add("hidden"));
    });
  }

  function onSearch() {
    const q = matSearch.value.trim().toLowerCase();
    if (!q) { matSuggest.classList.add("hidden"); return; }
    const matches = materiales.filter(m => (m.nombre || "").toLowerCase().includes(q)).slice(0, 8);
    clearChildren(matSuggest);
    matches.forEach(m => {
      const li = document.createElement("li");
      li.className = "px-4 py-2.5 text-sm hover:bg-cs-surface-container cursor-pointer";
      li.textContent = m.nombre;
      li.addEventListener("click", () => selectMaterial(m));
      matSuggest.appendChild(li);
    });
    matSuggest.classList.toggle("hidden", matches.length === 0);
  }

  async function selectMaterial(m) {
    selectedMat = m;
    matSelected.classList.remove("hidden");
    matName.textContent = m.nombre ?? "—";
    matSku.textContent = "SKU: " + m.id;
    qtyUnits.textContent = "Unidades (" + (m.unidad_inventario || "pz") + ")";
    matSuggest.classList.add("hidden");
    matSearch.value = m.nombre ?? "";
    await refreshImpact();
  }

  function clearSelection() {
    selectedMat = null;
    matSelected.classList.add("hidden");
    matSearch.value = "";
    impactCurr.textContent = "—";
    impactPost.textContent = "—";
    impactBar.style.width = "100%";
    impactBar.style.backgroundColor = "";
  }

  async function fetchDetail(matId) {
    if (!detailCache[matId]) {
      detailCache[matId] = await invApi.get("/materiales/" + matId);
    }
    return detailCache[matId];
  }

  async function refreshImpact() {
    if (!selectedMat) return;
    try {
      const det = await fetchDetail(selectedMat.id);
      const origenId = origenSel.value ? parseInt(origenSel.value) : null;
      const row = (det.stock_por_ubicacion || []).find(s => s.operatorio_id === origenId);
      const current = row ? (row.cantidad ?? 0) : 0;
      const qty = Math.max(0, parseInt(qtyInput.value || "0"));
      const post = Math.max(0, current - qty);
      impactCurr.textContent = String(current);
      impactPost.textContent = String(post);
      impactBar.style.width = (current > 0 ? Math.round((post / current) * 100) : 0) + "%";
      impactBar.style.backgroundColor = qty > current
        ? "var(--color-cs-error)"
        : "var(--color-cs-primary)";
    } catch (err) {
      console.error("refreshImpact failed:", err);
    }
  }

  async function submit() {
    errorEl.classList.add("hidden");
    if (!selectedMat) { showErr("Selecciona un material."); return; }
    if (!destinoSel.value) { showErr("Selecciona destino."); return; }
    if (origenSel.value && origenSel.value === destinoSel.value) {
      showErr("El origen y el destino no pueden ser iguales.");
      return;
    }
    const qty = parseInt(qtyInput.value || "0");
    if (qty < 1) { showErr("La cantidad debe ser al menos 1."); return; }
    const body = {
      material_id: selectedMat.id,
      origen_operatorio_id: origenSel.value ? parseInt(origenSel.value) : null,
      destino_operatorio_id: parseInt(destinoSel.value),
      cantidad: qty,
      motivo: document.getElementById("cs-motivo").value || null,
    };
    try {
      await invApi.post("/transferencias", body);
      window.location.href = "/inventario?transfer=ok";
    } catch (err) {
      showErr(err.message || "Error al transferir");
    }
  }

  function showErr(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove("hidden");
  }

  await init();
})();
