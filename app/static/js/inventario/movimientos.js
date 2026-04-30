(async function () {
  const { addCell, clearChildren } = window.invDom;
  const tbody = document.querySelector("#tabla-mov tbody");
  const filtro = document.getElementById("filtro-tipo");

  async function cargar() {
    const params = filtro.value ? "?tipo=" + filtro.value : "";
    const movs = await invApi.get("/movimientos" + params);
    clearChildren(tbody);
    movs.forEach(mv => {
      const tr = document.createElement("tr");
      addCell(tr, mv.fecha.slice(0, 16).replace("T", " "));
      addCell(tr, mv.tipo);
      addCell(tr, mv.material_id);
      addCell(tr, mv.origen_operatorio_id == null ? "Almacén" : mv.origen_operatorio_id);
      addCell(tr, mv.destino_operatorio_id == null ? "Almacén" : mv.destino_operatorio_id);
      addCell(tr, mv.cantidad);
      addCell(tr, mv.motivo || "");
      tbody.appendChild(tr);
    });
  }

  filtro.addEventListener("change", cargar);
  await cargar();
})();
