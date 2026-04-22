(async function () {
  const { addCell, clearChildren, makeOption } = window.invDom;
  const tbody = document.querySelector("#tabla-compras tbody");
  const modal = document.getElementById("modal-compra");
  const form = document.getElementById("form-compra");

  async function llenarSelects() {
    const [mats, ops] = await Promise.all([
      invApi.get("/materiales"), invApi.get("/operatorios"),
    ]);
    const selM = form.querySelector('[name="material_id"]');
    clearChildren(selM);
    mats.forEach(m => selM.appendChild(makeOption(m.id, m.nombre)));
    const selO = form.querySelector('[name="operatorio_destino_id"]');
    [...selO.querySelectorAll('option:not([value=""])')].forEach(o => o.remove());
    ops.forEach(op => selO.appendChild(makeOption(op.id, op.nombre)));
  }

  async function cargar() {
    const compras = await invApi.get("/compras");
    clearChildren(tbody);
    compras.forEach(c => {
      const tr = document.createElement("tr");
      addCell(tr, c.fecha);
      addCell(tr, c.material_id);
      addCell(tr, c.cantidad);
      addCell(tr, c.precio_unitario);
      addCell(tr, c.comentarios || "");
      tbody.appendChild(tr);
    });
  }

  document.getElementById("btn-nueva-compra").addEventListener("click", () => {
    modal.classList.remove("hidden");
  });
  document.getElementById("cancelar-compra").addEventListener("click", () => {
    modal.classList.add("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
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
    try {
      await invApi.post("/compras", body);
      modal.classList.add("hidden");
      form.reset();
      await cargar();
    } catch (err) {
      alert("Error: " + err.message);
    }
  });

  await Promise.all([llenarSelects(), cargar()]);
})();
