(async function () {
  const { clearChildren } = window.invDom;
  const lista = document.getElementById("lista-op");
  const form = document.getElementById("form-nuevo-op");

  async function cargar() {
    const ops = await invApi.get("/operatorios");
    clearChildren(lista);
    ops.forEach(op => {
      const li = document.createElement("li");
      li.textContent = op.nombre + " (orden " + op.orden + ") ";
      const btn = document.createElement("button");
      btn.textContent = "Borrar";
      btn.addEventListener("click", async () => {
        try {
          await invApi.del("/operatorios/" + op.id);
          cargar();
        } catch (err) {
          alert(err.message);
        }
      });
      li.appendChild(btn);
      lista.appendChild(li);
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    await invApi.post("/operatorios", {
      nombre: fd.get("nombre"),
      orden: parseInt(fd.get("orden") || "0"),
    });
    form.reset();
    cargar();
  });

  await cargar();
})();
