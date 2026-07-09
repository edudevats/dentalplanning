/* Feedback de UX para el timbrado de facturas (portal público y recepción).
   Sin dependencias: se carga tanto en autofactura.html (standalone) como en
   facturas/list.html. Expone window.FacturaUX; también exporta para Node (tests). */
(function (root) {
  "use strict";

  var RFC_RE = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/;
  var CP_RE = /^\d{5}$/;
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function validar(receptor) {
    receptor = receptor || {};
    var campos = {};
    var rfc = (receptor.rfc || "").trim().toUpperCase();
    var cp = (receptor.cp || "").trim();
    var email = (receptor.email || "").trim();
    var nombre = (receptor.nombre || "").trim();

    if (!rfc) campos.rfc = "Captura el RFC.";
    else if (!RFC_RE.test(rfc)) campos.rfc = "El RFC no tiene un formato válido.";

    if (!cp) campos.cp = "Captura el código postal.";
    else if (!CP_RE.test(cp)) campos.cp = "El código postal debe tener 5 dígitos.";

    if (!nombre) campos.nombre = "Captura el nombre o razón social.";

    if (!email) campos.email = "Captura un correo.";
    else if (!EMAIL_RE.test(email)) campos.email = "El correo no tiene un formato válido.";

    return { ok: Object.keys(campos).length === 0, campos: campos };
  }

  // Minúsculas basta para detectar las palabras clave (rfc/postal/cp no llevan
  // acentos), así evitamos un regex de diacríticos frágil en el navegador.
  function _norm(s) {
    return String(s || "").toLowerCase();
  }

  var _CAMPOS_DETALLES = ["rfc", "cp", "email", "nombre", "regimen_fiscal", "uso_cfdi"];

  function normalizarError(status, data) {
    data = data || {};
    var campos = {};
    var general = null;

    var detalles = data.detalles || data.details;
    if (detalles && typeof detalles === "object") {
      for (var i = 0; i < _CAMPOS_DETALLES.length; i++) {
        var k = _CAMPOS_DETALLES[i];
        if (detalles[k]) {
          var m = detalles[k];
          campos[k] = Array.isArray(m) ? m[0] : String(m);
        }
      }
    }

    var texto = data.error || data.message || "";
    if (texto) {
      var t = _norm(texto);
      if (!campos.rfc && t.indexOf("rfc") !== -1) campos.rfc = texto;
      else if (!campos.cp && (t.indexOf("postal") !== -1 || /\bc\.?p\b/.test(t))) campos.cp = texto;
      else general = texto;
    }

    if (!general && Object.keys(campos).length === 0) {
      general = "No se pudo generar la factura. Inténtalo de nuevo.";
    }
    return { campos: campos, general: general };
  }

  function marcarCampos(fieldMap, campos) {
    fieldMap = fieldMap || {};
    var primero = null;
    var sinCampo = [];
    for (var campo in campos) {
      if (!campos.hasOwnProperty(campo)) continue;
      var msg = campos[campo];
      if (!msg) continue;
      var ref = fieldMap[campo];
      if (ref) {
        if (ref.input) ref.input.classList.add("fux-invalid");
        if (ref.errorEl) { ref.errorEl.textContent = msg; ref.errorEl.classList.remove("hidden"); }
        if (!primero && ref.input) primero = ref.input;
      } else {
        sinCampo.push(msg);
      }
    }
    if (primero && primero.focus) primero.focus();
    return sinCampo;
  }

  function limpiar(fieldMap) {
    for (var campo in fieldMap) {
      if (!fieldMap.hasOwnProperty(campo)) continue;
      var ref = fieldMap[campo];
      if (ref.input) ref.input.classList.remove("fux-invalid");
      if (ref.errorEl) { ref.errorEl.textContent = ""; ref.errorEl.classList.add("hidden"); }
    }
  }

  function progreso(pasos, render, intervaloMs) {
    pasos = pasos && pasos.length ? pasos : [""];
    intervaloMs = intervaloMs || 900;
    var i = 0;
    render(pasos[0], 0);
    var id = setInterval(function () {
      if (i >= pasos.length - 1) { clearInterval(id); return; }
      i += 1;
      render(pasos[i], i);
    }, intervaloMs);
    return function stop() { clearInterval(id); };
  }

  var FacturaUX = {
    validar: validar,
    normalizarError: normalizarError,
    marcarCampos: marcarCampos,
    limpiar: limpiar,
    progreso: progreso,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = FacturaUX;
  root.FacturaUX = FacturaUX;
})(typeof window !== "undefined" ? window : globalThis);
