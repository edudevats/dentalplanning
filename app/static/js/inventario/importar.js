(async function () {
  const { addCell, addCellNode, clearChildren } = window.invDom;
  const tbody = document.querySelector("#tabla-master tbody");
  const busq = document.getElementById("busqueda");
  const filtro = document.getElementById("filtro-cat");
  const btn = document.getElementById("btn-importar");
  const selAll = document.getElementById("seleccionar-todo");

  async function cargar() {
    const params = new URLSearchParams();
    if (busq.value) params.set("busqueda", busq.value);
    if (filtro.value) params.set("categoria", filtro.value);
    const masters = await invApi.get("/master-disponibles?" + params);
    clearChildren(tbody);
    masters.forEach(m => {
      const tr = document.createElement("tr");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = String(m.id);
      cb.classList.add("sel");
      addCellNode(tr, cb);
      addCell(tr, m.nombre);
      addCell(tr, (m.categorias || []).join(", "));
      tbody.appendChild(tr);
    });
  }

  busq.addEventListener("input", () => setTimeout(cargar, 200));
  filtro.addEventListener("change", cargar);
  selAll.addEventListener("change", () => {
    document.querySelectorAll(".sel").forEach(c => c.checked = selAll.checked);
  });
  btn.addEventListener("click", async () => {
    const ids = [...document.querySelectorAll(".sel:checked")]
      .map(c => parseInt(c.value));
    if (ids.length === 0) return alert("Selecciona al menos uno");
    const r = await invApi.post("/materiales/importar-master", { master_ids: ids });
    alert(r.importados + " materiales importados");
    await cargar();
  });

  await cargar();
})();
