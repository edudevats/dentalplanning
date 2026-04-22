(async function () {
  const { setText, addCell, addCellNode, clearChildren, makeOption, makeLink } = window.invDom;
  const tbody = document.querySelector("#tabla-inventario tbody");
  const filtroCat = document.getElementById("filtro-categoria");
  const filtroAlerta = document.getElementById("filtro-alerta");
  const busqueda = document.getElementById("busqueda");

  async function cargarCategorias() {
    const cats = await invApi.get("/categorias");
    cats.forEach(c => filtroCat.appendChild(makeOption(c.nombre, c.nombre)));
  }

  function buildUrl() {
    const params = new URLSearchParams();
    if (busqueda.value) params.set("busqueda", busqueda.value);
    if (filtroCat.value) params.set("categoria", filtroCat.value);
    if (filtroAlerta.value) params.set("alerta", filtroAlerta.value);
    return "/materiales?" + params;
  }

  async function cargar() {
    const mats = await invApi.get(buildUrl());
    clearChildren(tbody);
    mats.forEach(m => {
      const tr = document.createElement("tr");
      addCellNode(tr, makeLink("/inventario/material/" + m.id, m.nombre));
      addCell(tr, (m.categorias || []).join(", "));
      addCell(tr, m.total_global);
      tbody.appendChild(tr);
    });
  }

  [filtroCat, filtroAlerta].forEach(el => el.addEventListener("change", cargar));
  busqueda.addEventListener("input", () => setTimeout(cargar, 200));

  document.getElementById("btn-compra").addEventListener("click", () => {
    window.location.href = "/inventario/compras";
  });

  const modalT = document.getElementById("modal-transferir");
  const formT = document.getElementById("form-transferir");

  async function prefillTransferir() {
    const [mats, ops] = await Promise.all([
      invApi.get("/materiales"), invApi.get("/operatorios"),
    ]);
    const selMat = formT.querySelector('[name="material_id"]');
    while (selMat.firstChild) selMat.removeChild(selMat.firstChild);
    mats.forEach(m => selMat.appendChild(makeOption(m.id, m.nombre)));
    ["origen_operatorio_id", "destino_operatorio_id"].forEach(name => {
      const sel = formT.querySelector('[name="' + name + '"]');
      [...sel.querySelectorAll('option:not([value=""])')].forEach(o => o.remove());
      ops.forEach(op => sel.appendChild(makeOption(op.id, op.nombre)));
    });
  }

  document.getElementById("btn-transferir").addEventListener("click", async () => {
    await prefillTransferir();
    modalT.classList.remove("hidden");
  });
  document.getElementById("cancelar-transferir").addEventListener("click", () => {
    modalT.classList.add("hidden");
  });
  formT.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(formT);
    const body = {
      material_id: parseInt(fd.get("material_id")),
      origen_operatorio_id: fd.get("origen_operatorio_id")
        ? parseInt(fd.get("origen_operatorio_id")) : null,
      destino_operatorio_id: fd.get("destino_operatorio_id")
        ? parseInt(fd.get("destino_operatorio_id")) : null,
      cantidad: parseInt(fd.get("cantidad")),
      motivo: fd.get("motivo") || null,
    };
    try {
      await invApi.post("/transferencias", body);
      modalT.classList.add("hidden"); formT.reset();
      await cargar();
    } catch (err) {
      alert(err.message);
    }
  });

  await cargarCategorias();
  await cargar();
})();
