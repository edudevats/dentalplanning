/* Turno de caja: la única fuente de verdad del contexto de trabajo.
 *
 * Lo comparten las tres pantallas por las que entra dinero (/corte-caja,
 * /ingresos, /gastos). De aquí salen la sucursal y la fecha que el backend le
 * impone a todo lo que se capture (app/caja/services.py, exigir_turno_abierto),
 * así que duplicar esta lógica por pantalla sería multiplicar el 409.
 *
 * La parte pura (leerEstado, debeAbrirModal, validarApertura, etiquetaTurno) se
 * prueba en tests/js/turno.test.js. La parte de DOM se verifica en el navegador.
 *
 * Depende de corte_ux.js (normalizarMonto) y, en el navegador, de app.js
 * (API, Toast, Modal, populateSelect).
 */
(function (root) {
  "use strict";

  var UX = (typeof module !== "undefined" && module.exports)
    ? require("./corte_ux.js")
    : root.CorteUX;

  function fmt(n) {
    return "$" + Number(n || 0).toFixed(2);
  }

  // ── Lógica pura ───────────────────────────────────────────────────────────

  /* Normaliza la respuesta de GET /caja/turno.
   *
   * Fail-closed a propósito: cualquier cosa que no sea una respuesta sana se
   * lee como "no hay turno". Si el GET falló, asumir caja abierta dejaría
   * capturar contra un 409 garantizado; asumir cerrada solo pide abrirla. */
  function leerEstado(respuesta) {
    var r = (respuesta && typeof respuesta === "object") ? respuesta : {};
    return {
      turno: r.turno || null,
      separaSucursales: r.separa_sucursales === true,
    };
  }

  /* ¿Se abre el modal solo al entrar a la pantalla?
   *
   * El admin queda fuera porque el candado del backend lo exime: bloquearle la
   * pantalla sería inventar una regla que el servidor no tiene. Cualquier otro
   * rol —incluido `null`, que es lo que vale mientras /auth/me está en vuelo—
   * sí queda dentro: la duda no puede saldarse a favor de dejar capturar. */
  function debeAbrirModal(turno, rol) {
    if (rol === "admin") return false;
    return !turno;
  }

  /* Valida lo que el modal va a mandar a POST /caja/turno.
   *
   * Devuelve {ok:true, payload} o {ok:false, error}. Los mismos rechazos que
   * hace el servicio (sucursal_requerida, fondo_invalido), pero antes del
   * viaje: el servidor sigue siendo la autoridad, esto solo evita el rebote. */
  function validarApertura(opts) {
    var o = opts || {};
    var separa = o.separaSucursales === true;

    if (separa && !o.sucursalId) {
      return { ok: false, error: "Elige en qué sucursal vas a trabajar" };
    }

    // Un fondo vacío es cero, no un error: "hoy arranco sin cambio" es un dato
    // válido, y el servicio lo acepta. Se resuelve ANTES de normalizarMonto,
    // que devuelve null tanto para "" como para "abc" y no los distingue.
    var texto = String(o.fondoTexto == null ? "" : o.fondoTexto).trim();
    var fondo = 0;
    if (texto !== "") {
      fondo = UX.normalizarMonto(texto);
      if (fondo === null) {
        return { ok: false, error: "El fondo inicial no es un monto válido" };
      }
    }

    return {
      ok: true,
      payload: {
        sucursal_id: separa ? Number(o.sucursalId) : null,
        fondo_inicial: fondo,
      },
    };
  }

  function etiquetaTurno(turno) {
    if (!turno) return "";
    return "Caja abierta" +
      (turno.sucursal ? " · " + turno.sucursal : "") +
      " · fondo " + fmt(turno.fondo_inicial);
  }

  /* La sucursal que va en el payload de captura. Sale del turno, nunca de un
   * campo del formulario: es el dato que este diseño saca de las manos de
   * quien captura. */
  function sucursalDelTurno(turno) {
    return (turno && turno.sucursal_id) ? turno.sucursal_id : null;
  }

  // ── DOM ───────────────────────────────────────────────────────────────────

  var estado = { turno: null, separaSucursales: false };
  var sucursales = [];
  var rol = null;
  var alAbrir = null;      // callback que cada pantalla registra
  var bloqueante = false;  // el modal que se abrió solo no se puede descartar

  function el(id) { return document.getElementById(id); }

  function render() {
    var btn = el("btn-inicio-caja");
    var etiqueta = el("turno-actual");
    // Con turno abierto el botón sobra: se quita del flujo, no solo se apaga.
    // `style.display` y no la clase `hidden`: el botón trae `inline-flex` en el
    // marcado y el JIT de Tailwind del navegador insertaría `.hidden` después,
    // perdiendo la cascada (ver la trampa documentada en el plan).
    if (btn) btn.style.display = estado.turno ? "none" : "";
    if (etiqueta) {
      etiqueta.style.display = estado.turno ? "" : "none";
      etiqueta.textContent = etiquetaTurno(estado.turno);
    }
    var aviso = el("aviso-sin-turno");
    if (aviso) aviso.style.display = estado.turno ? "none" : "";
  }

  async function cargar() {
    try {
      estado = leerEstado(await API.get("/caja/turno"));
    } catch (e) {
      estado = { turno: null, separaSucursales: false };
    }
    render();
    return estado.turno;
  }

  /* `forzado` = lo disparó la carga de la pantalla, no un clic. Ese modal no se
   * puede cerrar: sin turno no hay nada que hacer en la pantalla. Mismo patrón
   * que el cambio de contraseña obligatorio en app.js (forcedPwChange). */
  function abrirModal(forzado) {
    bloqueante = forzado === true;

    var wrap = el("wrap-turno-sucursal");
    if (wrap) wrap.style.display = estado.separaSucursales ? "" : "none";
    if (estado.separaSucursales && typeof populateSelect === "function") {
      populateSelect(el("f-turno-sucursal"),
        sucursales.map(function (s) {
          return { value: String(s.id), label: s.nombre };
        }), "", "Selecciona la sucursal");
    }

    var campo = el("f-turno-fondo");
    if (campo) campo.value = "";

    // El botón de cancelar sobra cuando el modal es la única salida.
    var cancelar = el("btn-cancelar-turno");
    if (cancelar) cancelar.style.display = bloqueante ? "none" : "";
    var cerrar = el("btn-cerrar-turno");
    if (cerrar) cerrar.style.display = bloqueante ? "none" : "";

    Modal.open("modal-inicio-caja");
  }

  function cerrarModal() {
    if (bloqueante) return;   // sin turno no hay pantalla que usar
    Modal.close("modal-inicio-caja");
  }

  async function confirmar() {
    var btn = el("btn-confirmar-turno");
    var texto = el("texto-confirmar-turno");
    var v = validarApertura({
      separaSucursales: estado.separaSucursales,
      sucursalId: el("f-turno-sucursal") ? el("f-turno-sucursal").value : "",
      fondoTexto: el("f-turno-fondo") ? el("f-turno-fondo").value : "",
    });
    if (!v.ok) { Toast.warning(v.error); return; }

    if (btn) btn.disabled = true;
    if (texto) texto.textContent = "Abriendo...";
    try {
      await API.post("/caja/turno", v.payload);
      bloqueante = false;
      Modal.close("modal-inicio-caja");
      Toast.success("Caja abierta");
      await cargar();
      if (typeof alAbrir === "function") await alAbrir(estado.turno);
    } catch (e) {
      Toast.warning((e && e.message) || "No se pudo abrir la caja");
    } finally {
      if (btn) btn.disabled = false;
      if (texto) texto.textContent = "Abrir caja";
    }
  }

  /* Arranca el turno en una pantalla.
   *
   * `opts.rol` y `opts.sucursales` los resuelve la pantalla (ya pide /auth/me y
   * /facturacion/sucursales en su init, no se piden dos veces). `opts.alAbrir`
   * corre después de abrir la caja, para que cada pantalla recargue lo suyo. */
  async function iniciar(opts) {
    var o = opts || {};
    rol = o.rol || null;
    sucursales = o.sucursales || [];
    alAbrir = o.alAbrir || null;

    var btn = el("btn-inicio-caja");
    if (btn) btn.addEventListener("click", function () { abrirModal(false); });
    var confirmarBtn = el("btn-confirmar-turno");
    if (confirmarBtn) confirmarBtn.addEventListener("click", confirmar);
    ["btn-cancelar-turno", "btn-cerrar-turno", "backdrop-turno"].forEach(function (id) {
      var e = el(id);
      if (e) e.addEventListener("click", cerrarModal);
    });

    // El admin no necesita turno para nada de esta pantalla, y pedírselo solo
    // gastaría una llamada: el candado del backend ya lo exime.
    if (rol === "admin") { render(); return null; }

    await cargar();
    if (debeAbrirModal(estado.turno, rol)) abrirModal(true);
    return estado.turno;
  }

  var TurnoCaja = {
    // puro (probado en tests/js/turno.test.js)
    leerEstado: leerEstado,
    debeAbrirModal: debeAbrirModal,
    validarApertura: validarApertura,
    etiquetaTurno: etiquetaTurno,
    sucursalDelTurno: sucursalDelTurno,
    // DOM
    iniciar: iniciar,
    cargar: cargar,
    abrirModal: abrirModal,
    actual: function () { return estado.turno; },
    separaSucursales: function () { return estado.separaSucursales; },
  };

  if (typeof module !== "undefined" && module.exports) module.exports = TurnoCaja;
  root.TurnoCaja = TurnoCaja;
})(typeof window !== "undefined" ? window : globalThis);
