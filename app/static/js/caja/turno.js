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
      estadoCajas: Array.isArray(r.estado_cajas) ? r.estado_cajas : [],
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
   * hace el servicio, pero antes del viaje: el servidor sigue siendo la
   * autoridad, esto solo evita el rebote.
   *
   * Las tres capas de esta regla -esta función, `resolver_sucursal_del_turno`
   * en app/caja/services.py, y el `HAVING COUNT(*) = 1` de la migración de
   * backfill- tienen que decir exactamente lo mismo con exactamente una
   * sucursal: la IMPONEN, sin preguntar. Si esta función en vez de imponerla
   * se la EXIGIERA al usuario (como hacía antes), dependería de que
   * `abrirModal` la haya preseleccionado en el `<select>[esto cuelga de que
   * `populateSelect` ya esté cargado]`; el día que no lo esté -orden de
   * scripts, red lenta- el campo llega vacío y esta función rechazaría con
   * "Elige en qué sucursal vas a trabajar" DENTRO del modal bloqueante, donde
   * `cerrarModal` es un no-op: la recepcionista de un tenant de una sola
   * sucursal quedaría encerrada en la pantalla que se abre a primera hora
   * todos los días. Imponer aquí, igual que el servidor, cierra ese hueco.
   *
   * `sucursalesDisponibles` y no `separaSucursales`: la regla ya no es "¿el
   * corte separa por sucursal?" sino "¿hay alguna sucursal que elegir?". */
  function validarApertura(opts) {
    var o = opts || {};
    var total = Number(o.sucursalesDisponibles || 0);
    var hayQueElegir = total >= 2;

    if (hayQueElegir && !o.sucursalId) {
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

    // Con exactamente una, el valor viene de `unicaSucursalId` -que `confirmar`
    // saca de la misma lista que contó `total`- y NO de `sucursalId`: el select
    // puede llegar vacío o deshabilitado y aun así el payload tiene que salir
    // completo, igual que lo impone el servidor.
    //
    // `|| null` y no solo `Number(...)`: sin esto, un `unicaSucursalId` ausente
    // (nadie lo manda hoy, pero esta función tiene que ser TOTAL, no solo
    // correcta para su único llamador) daría `Number(undefined)` = `NaN`, y un
    // payload con `NaN` no es un valor válido para nada que lo consuma.
    var sucursalId = total === 1
      ? (Number(o.unicaSucursalId) || null)
      : (hayQueElegir ? Number(o.sucursalId) : null);

    return {
      ok: true,
      payload: {
        sucursal_id: sucursalId,
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

  /* La cara del botón de la cabecera.
   *
   * Para el admin ese botón dejó de ser una acción y pasó a ser un ESTADO: no
   * dice "abre tu caja" —el admin no captura— sino en qué situación está la
   * caja de la sucursal que está mirando. De ahí las dos caras.
   *
   * `cajaAjena` manda sobre el turno propio a propósito: si la caja está
   * abierta, lo que se necesita desde ese botón es corregirla, no volver a
   * abrirla, aunque quien mire sea justo quien la abrió. */
  function caraBotonInicio(turno, cajaAjena) {
    if (cajaAjena) {
      return {
        visible: true,
        tono: "abierta",
        texto: "Caja abierta" + (cajaAjena.por ? " · " + cajaAjena.por : ""),
      };
    }
    return { visible: !turno, tono: "abrir", texto: "Inicio de caja" };
  }

  /* "Ana", "Ana y Beatriz", "Ana, Beatriz y Carla". */
  function unirNombres(nombres) {
    var l = (nombres || []).filter(Boolean);
    if (!l.length) return "";
    if (l.length === 1) return l[0];
    return l.slice(0, -1).join(", ") + " y " + l[l.length - 1];
  }

  /* Qué sucursales están trabajando hoy y cuáles no, una línea por sede.
   *
   * Lista también las que NO están abiertas a propósito: la pregunta que
   * responde es "quién ya está trabajando", y eso solo se sabe viendo las dos
   * mitades. Tres estados, porque marcar como "sin abrir" una sucursal que ya
   * cuadró y cerró sugeriría que alguien debería ir a abrirla.
   *
   * Devuelve `{estado, texto, detalle}` y no HTML: el color lo pone quien
   * pinta, y así esta parte se prueba sin DOM. */
  function lineasEstadoCajas(cajas) {
    return (cajas || []).filter(Boolean).map(function (c) {
      var quien = unirNombres(c.abierto_por);
      var detalle = c.estado === "cerrada" ? "caja cerrada"
        : c.estado === "abierta" ? (quien || "abierta")
        : "sin abrir";
      return {
        estado: c.estado,
        // Sin sede que nombrar (el tenant no configuró ninguna) la línea se
        // quedaría con un punto de color y nada al lado.
        texto: c.sucursal || "Caja del día",
        detalle: detalle,
      };
    });
  }

  /* Qué enseña el aviso de "sin caja" de /ingresos y /gastos.
   *
   * El admin queda fuera del regaño y del botón: el backend lo exime del turno
   * (`exigir_turno_abierto` hace `if es_admin: return`), así que decirle
   * "todavía no abres tu caja" era decirle algo falso. De este aviso solo le
   * sirve la lista, y si NINGUNA caja está abierta tampoco eso: una lista
   * entera de "sin abrir" no le dice nada que necesite, porque nadie ha llegado
   * y él no tiene que abrir ninguna.
   *
   * Un rol `null` —lo que vale mientras /auth/me está en vuelo— cuenta como
   * no-admin: la duda no puede saldarse escondiéndole el botón a quien sí lo
   * necesita para poder trabajar. */
  function avisoDeTurno(turno, estadoCajas, rolActual) {
    var esAdmin = rolActual === "admin";
    // El turno propio calla el aviso para quien captura -ya esta trabajando y
    // sabe donde-, pero NO para el admin: el de una clinica pequena abre la
    // caja el mismo, y justo entonces es cuando quiere ver que sedes trabajan.
    // Como a el se le quitan el regano y el boton, lo que le queda es la lista
    // sola, que es exactamente lo que vino a ver.
    if (turno && !esAdmin) return { visible: false, pideAbrir: false, lineas: [] };
    var lineas = lineasEstadoCajas(estadoCajas);
    var algunaAbierta = lineas.some(function (l) { return l.estado === "abierta"; });
    if (esAdmin && !algunaAbierta) {
      return { visible: false, pideAbrir: false, lineas: [] };
    }
    return { visible: true, pideAbrir: !esAdmin, lineas: lineas };
  }

  /* Qué turno ve la PANTALLA que llamó a `iniciar`, que no es el mismo que ve
   * este módulo.
   *
   * Para el admin siempre `null`, aunque tenga su propia caja abierta. No es un
   * detalle: `ingresos.html` y `gastos.html` guardan este valor en `turnoDelDia`
   * y de él sacan la sucursal de TODO lo que se captura o se edita
   * (`handleSave`), además de bloquear la fecha y la sucursal del formulario
   * (`aplicarTurnoAlFormulario`). Devolverle su turno al admin hacía que editar
   * un ingreso viejo de otra sede lo reasignara en silencio a la sede de su
   * turno —el backend no puede frenarlo, porque `exigir_turno_abierto` lo
   * exime— y le bloqueaba la corrección de fecha y sucursal, que es justamente
   * la razón de que esté exento.
   *
   * El módulo SÍ guarda el turno del admin en `estado`: de ahí salen la cara
   * del botón y el aviso de cajas abiertas. Lo que no sale de aquí es el
   * permiso para que una pantalla de captura lo use como contexto. */
  function turnoParaLaPantalla(turno, rolActual) {
    return rolActual === "admin" ? null : turno;
  }

  // ── DOM ───────────────────────────────────────────────────────────────────

  var estado = { turno: null, separaSucursales: false, estadoCajas: [] };
  var sucursales = [];
  var rol = null;
  var alAbrir = null;      // callback que cada pantalla registra
  var bloqueante = false;  // el modal que se abrió solo no se puede descartar
  var alCorregir = null;   // qué hacer al clicar la cara roja
  var cajaAjena = null;    // {por} cuando la caja del contexto ya está abierta

  function el(id) { return document.getElementById(id); }

  /* El color va por `style` con variables del tema y NO por clases de Tailwind:
   * el JIT del navegador solo genera la regla de una clase que ve en el HTML al
   * cargar, y estas filas las crea el JS. Con la variable, el punto se pinta
   * igual en las dos plantillas sin depender de qué clases traiga cada una. */
  var COLOR_ESTADO = {
    abierta: "var(--color-accent-600)",
    cerrada: "var(--color-primary-600)",
    sin_abrir: "var(--color-text-muted)",
  };

  function filaEstadoCaja(linea) {
    var fila = document.createElement("li");
    fila.className = "flex items-center gap-2";

    // Sin ninguna clase de Tailwind: el punto lo crea el JS, y el JIT del
    // navegador solo genera la regla de las clases que ve en el HTML al
    // cargar. `rounded-full` sobrevivia de prestado por el avatar de la
    // cabecera (layout.html) y `inline-block` no existia en ningun lado -era
    // inocua solo porque el <li> es flex y blockifica a sus hijos-. Con todo
    // en `style` el punto deja de depender de marcado ajeno.
    var punto = document.createElement("span");
    var color = COLOR_ESTADO[linea.estado] || COLOR_ESTADO.sin_abrir;
    punto.style.width = "0.5rem";
    punto.style.height = "0.5rem";
    punto.style.flexShrink = "0";
    punto.style.borderRadius = "9999px";
    // La cerrada va hueca y no rellena: verde y cian en un punto de 8px son
    // casi el mismo color bajo deuteranopia, y esa es justo la distincion que
    // carga el significado ("trabajando" contra "ya termino"). Con el anillo se
    // distinguen por forma, no solo por tono.
    if (linea.estado === "cerrada") {
      punto.style.backgroundColor = "transparent";
      punto.style.border = "2px solid " + color;
    } else {
      punto.style.backgroundColor = color;
    }
    fila.appendChild(punto);

    var sede = document.createElement("span");
    sede.className = "font-medium";
    sede.textContent = linea.texto;
    fila.appendChild(sede);

    var detalle = document.createElement("span");
    detalle.textContent = "· " + linea.detalle;
    // El detalle se apaga cuando no hay nadie: lo que importa de esa línea es
    // el hueco, no el texto.
    detalle.style.opacity = linea.estado === "abierta" ? "1" : "0.7";
    fila.appendChild(detalle);

    return fila;
  }

  function render() {
    var btn = el("btn-inicio-caja");
    if (btn) {
      var cara = caraBotonInicio(estado.turno, cajaAjena);
      // `style.display` y no la clase `hidden`: el botón trae `inline-flex` en
      // el marcado y el JIT de Tailwind del navegador insertaría `.hidden`
      // después, perdiendo la cascada.
      btn.style.display = cara.visible ? "" : "none";
      // `bg-danger-500`/`hover:bg-danger-600` y NO otro tono de danger: son las
      // dos únicas que ya viven en el marcado inicial de corte.html, y el JIT
      // del navegador solo genera la regla de las clases que ve al cargar.
      var rojo = cara.tono === "abierta";
      btn.classList.toggle("bg-danger-500", rojo);
      btn.classList.toggle("hover:bg-danger-600", rojo);
      btn.classList.toggle("bg-accent-600", !rojo);
      btn.classList.toggle("hover:bg-accent-700", !rojo);
      var textoBtn = el("texto-inicio-caja");
      if (textoBtn) textoBtn.textContent = cara.texto;
      // El icono sigue a la cara: un candado abierto invita a abrir, y la cara
      // roja ya no abre nada — lleva a EDITAR el turno (mismo ícono que usa
      // "Editar turno" en corte.js), así que un candado ahí invitaría a lo
      // contrario de lo que hace. Solo existe en corte.html (único lugar con
      // el id); en ingresos/gastos `slot` sale null y el if no hace nada.
      var slot = el("icon-inicio-caja");
      if (slot) {
        // No se muta el <i> existente: lucide ya lo sustituyó por un <svg> en
        // el primer render (createIcons() reemplaza el nodo, no lo actualiza
        // in-place), así que cambiarle el atributo data-lucide a lo que quedó
        // no repinta nada — ese atributo ni siquiera sobrevive al reemplazo.
        // En vez de eso se recrea el <i> desde cero dentro de un wrapper que
        // lucide nunca toca, y se deja que createIcons() lo convierta de
        // nuevo. Mismo patrón que setBtnContent() en
        // app/static/js/admin/admin_pagos.js:216.
        slot.replaceChildren();
        var ic = document.createElement("i");
        ic.setAttribute("data-lucide", rojo ? "pencil" : "unlock");
        ic.className = "h-4 w-4";
        slot.appendChild(ic);
        if (typeof lucide !== "undefined") lucide.createIcons();
      }
    }
    var etiqueta = el("turno-actual");
    if (etiqueta) {
      etiqueta.style.display = estado.turno ? "" : "none";
      etiqueta.textContent = etiquetaTurno(estado.turno);
    }
    var aviso = el("aviso-sin-turno");
    if (aviso) {
      var av = avisoDeTurno(estado.turno, estado.estadoCajas, rol);
      aviso.style.display = av.visible ? "" : "none";
      // El regaño y el botón se quitan del flujo para el admin, no solo se
      // apagan: dejarle un hueco donde estaba el botón sugeriría que algo le
      // falta por hacer, y no le falta nada.
      ["aviso-turno-titulo", "aviso-turno-detalle", "btn-aviso-abrir-caja"]
        .forEach(function (id) {
          var e = el(id);
          if (e) e.style.display = av.pideAbrir ? "" : "none";
        });
      var lista = el("aviso-estado-cajas");
      if (lista) {
        lista.replaceChildren();
        lista.style.display = av.lineas.length ? "" : "none";
        av.lineas.forEach(function (linea) {
          lista.appendChild(filaEstadoCaja(linea));
        });
      }
    }
  }

  async function cargar() {
    try {
      estado = leerEstado(await API.get("/caja/turno"));
    } catch (e) {
      estado = { turno: null, separaSucursales: false, estadoCajas: [] };
    }
    render();
    return estado.turno;
  }

  /* Le dice al módulo que la caja de la sucursal que la pantalla está mirando ya
   * está abierta, y por quién.
   *
   * Solo /corte-caja la usa: es la única pantalla con selector de sucursal y por
   * tanto la única que puede estar mirando una caja que no es la de quien mira.
   *
   * El filtro por rol vive aquí y no en el llamador para que exista en UN solo
   * sitio: pintarle el rojo a una recepcionista le diría que no puede trabajar,
   * cuando la verdad es la contraria —la segunda del día abre su turno y hereda
   * el fondo, porque el cajón es uno solo que varias personas alimentan—. */
  function marcarCajaAjena(info) {
    var hay = rol === "admin" && !!(info && info.abierta);
    cajaAjena = hay ? { por: (info && info.por) || null } : null;
    render();
  }

  /* `forzado` = lo disparó la carga de la pantalla, no un clic. Ese modal no se
   * puede cerrar: sin turno no hay nada que hacer en la pantalla. Mismo patrón
   * que el cambio de contraseña obligatorio en app.js (forcedPwChange). */
  function abrirModal(forzado) {
    bloqueante = forzado === true;

    // El campo se muestra en cuanto exista UNA sucursal, no solo con dos o más:
    // con una sola se muestra ya elegida y bloqueada, para que quien abre vea
    // dónde va a caer el dinero. Con ninguna no hay nada que mostrar.
    var wrap = el("wrap-turno-sucursal");
    var unica = sucursales.length === 1;
    if (wrap) wrap.style.display = sucursales.length >= 1 ? "" : "none";
    var sel = el("f-turno-sucursal");
    if (sel && sucursales.length >= 1 && typeof populateSelect === "function") {
      populateSelect(sel,
        sucursales.map(function (s) {
          return { value: String(s.id), label: s.nombre };
        }),
        // Sin opción vacía cuando hay que elegir: "Sin sucursal" dejó de ser un
        // estado en el que se pueda abrir caja.
        unica ? String(sucursales[0].id) : "",
        unica ? null : "Selecciona la sucursal");
      // disabled y no readOnly: un <select> no tiene readOnly, y el valor no
      // viaja en ningún formulario — lo lee `confirmar` con .value, que sigue
      // funcionando en un select deshabilitado.
      sel.disabled = unica;
    }
    var etiquetaSuc = el("label-turno-sucursal");
    if (etiquetaSuc) {
      etiquetaSuc.textContent = unica
        ? "Sucursal"
        : "¿En qué sucursal vas a trabajar hoy?";
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
      sucursalesDisponibles: sucursales.length,
      // Con exactamente una sucursal, `validarApertura` la impone y no lee
      // `sucursalId` -este es el dato que de verdad usa en ese caso.
      unicaSucursalId: sucursales.length === 1 ? sucursales[0].id : null,
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
    alCorregir = o.alCorregir || null;

    var btn = el("btn-inicio-caja");
    if (btn) btn.addEventListener("click", function () {
      // La cara roja no abre caja: la caja ya está abierta. Lleva a corregirla,
      // que es lo único que se puede querer hacer desde ahí. La pantalla
      // registra ese callback; si no lo hizo, el clic no hace nada, que es
      // mejor que abrir un modal contra un 409 seguro.
      if (cajaAjena) {
        if (typeof alCorregir === "function") alCorregir();
        return;
      }
      abrirModal(false);
    });
    var confirmarBtn = el("btn-confirmar-turno");
    if (confirmarBtn) confirmarBtn.addEventListener("click", confirmar);
    ["btn-cancelar-turno", "btn-cerrar-turno", "backdrop-turno"].forEach(function (id) {
      var e = el(id);
      if (e) e.addEventListener("click", cerrarModal);
    });

    // El admin SÍ pide el turno, aunque el candado del backend lo exima de
    // tenerlo: de esta misma llamada sale la lista de cajas abiertas que el
    // aviso le muestra, que es el único trozo de este flujo que le sirve.
    // Antes salía temprano sin pedirla, y por eso el aviso le quedaba mudo.
    // Lo que no le aplica es el modal bloqueante, y de eso ya se encarga
    // `debeAbrirModal`, que lo deja fuera por rol.
    await cargar();
    if (debeAbrirModal(estado.turno, rol)) abrirModal(true);
    return turnoParaLaPantalla(estado.turno, rol);
  }

  var TurnoCaja = {
    // puro (probado en tests/js/turno.test.js)
    leerEstado: leerEstado,
    debeAbrirModal: debeAbrirModal,
    validarApertura: validarApertura,
    etiquetaTurno: etiquetaTurno,
    turnoParaLaPantalla: turnoParaLaPantalla,
    lineasEstadoCajas: lineasEstadoCajas,
    avisoDeTurno: avisoDeTurno,
    sucursalDelTurno: sucursalDelTurno,
    caraBotonInicio: caraBotonInicio,
    // DOM
    iniciar: iniciar,
    cargar: cargar,
    abrirModal: abrirModal,
    marcarCajaAjena: marcarCajaAjena,
    actual: function () { return estado.turno; },
  };

  if (typeof module !== "undefined" && module.exports) module.exports = TurnoCaja;
  root.TurnoCaja = TurnoCaja;
})(typeof window !== "undefined" ? window : globalThis);
