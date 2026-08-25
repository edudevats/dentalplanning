/* Reglas del corte de caja, sin DOM ni red: se prueban con `node --test`.
   Mismo patrón que app/static/js/factura_ux.js. */
(function (root) {
  "use strict";

  function redondear(n) {
    return Math.round((n + Number.EPSILON) * 100) / 100;
  }

  /* Acepta "4250", "4250.50", "4250,50", "4,250.50", "4,250" y "1.234,56".
     Null si no es un monto válido. Cero SÍ es válido: una caja vacía es un
     dato, no un campo sin llenar.

     El caso delicado es un separador SOLO: en México la coma agrupa miles y el
     punto es decimal, así que "4,250" son cuatro mil doscientos cincuenta pesos
     —es literalmente lo que fmt() imprime en pantalla— y no $4.25. Se resuelve
     por la forma del número, no por el carácter: si el texto completo tiene
     pinta de agrupación de miles (1 a 3 dígitos y luego grupos de exactamente
     tres) el separador agrupa; en cualquier otro caso es decimal. Así "4,250" y
     "4.250" dan 4250, mientras "4,25" y "4.25" dan 4.25. */
  function normalizarMonto(texto) {
    if (texto === null || texto === undefined) return null;
    var limpio = String(texto).trim();
    if (!limpio) return null;
    limpio = limpio.replace(/\s/g, "");

    var coma = limpio.lastIndexOf(",");
    var punto = limpio.lastIndexOf(".");
    if (coma > -1 && punto > -1) {
      // Con los dos separadores no hay ambigüedad: el ÚLTIMO es el decimal y
      // el otro agrupa miles. Cubre "1,234.56" (es-MX) y "1.234,56" (europeo).
      var decimal = coma > punto ? "," : ".";
      var miles = decimal === "," ? "." : ",";
      limpio = limpio.split(miles).join("").split(decimal).join(".");
    } else if (coma > -1 || punto > -1) {
      var sep = coma > -1 ? "," : ".";
      var escapado = sep === "." ? "\\." : ",";
      var esMiles = new RegExp("^\\d{1,3}(" + escapado + "\\d{3})+$");
      limpio = esMiles.test(limpio)
        ? limpio.split(sep).join("")
        : limpio.split(sep).join(".");
    }

    if (!/^\d+(\.\d+)?$/.test(limpio)) return null;
    var n = Number(limpio);
    if (!isFinite(n) || n < 0) return null;
    return redondear(n);
  }

  function diferencia(resumen, contadoTexto) {
    var contado = normalizarMonto(contadoTexto);
    if (contado === null) return null;
    return redondear(contado - Number(resumen.esperado_efectivo || 0));
  }

  function excedeTolerancia(resumen, contadoTexto) {
    var dif = diferencia(resumen, contadoTexto);
    if (dif === null) return false;
    return Math.abs(dif) > Number(resumen.tolerancia || 0);
  }

  /* Única fuente de verdad de si el botón "Cerrar caja" se habilita.
     El servidor vuelve a validar todo: esto es cortesía, no seguridad. */
  function puedeCerrar(resumen, contadoTexto, comentarioTexto) {
    if (resumen.estado === "cerrado") {
      return { ok: false, motivo: "La caja de este día ya fue cerrada" };
    }
    if ((resumen.sin_clasificar || []).length) {
      return {
        ok: false,
        motivo: "Hay ingresos sin método de pago: asígnales uno antes de cerrar",
      };
    }
    if (normalizarMonto(contadoTexto) === null) {
      return { ok: false, motivo: "Escribe cuánto efectivo contaste" };
    }
    var comentario = String(comentarioTexto || "").trim();
    if (excedeTolerancia(resumen, contadoTexto) && !comentario) {
      return { ok: false, motivo: "La diferencia necesita un comentario" };
    }
    return { ok: true, motivo: null };
  }

  function etiquetaDiferencia(dif) {
    var n = Number(dif || 0);
    if (n < 0) {
      return { texto: "Faltan $" + Math.abs(n).toFixed(2),
               clase: "text-danger-600" };
    }
    if (n > 0) {
      return { texto: "Sobran $" + n.toFixed(2), clase: "text-warning-600" };
    }
    return { texto: "La caja cuadra", clase: "text-accent-700" };
  }

  function muestraLeyendaFondo(resumen) {
    // Un fondo en cero es ruido para quien solo lo lee, pero es la puerta de
    // entrada para quien puede corregirlo: escondérselo dejaría la corrección
    // sin dónde empezar.
    return Number((resumen || {}).fondo_inicial || 0) !== 0
      || !!(resumen || {}).puede_editar_fondo;
  }

  var CorteUX = {
    normalizarMonto: normalizarMonto,
    diferencia: diferencia,
    excedeTolerancia: excedeTolerancia,
    puedeCerrar: puedeCerrar,
    etiquetaDiferencia: etiquetaDiferencia,
    muestraLeyendaFondo: muestraLeyendaFondo,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = CorteUX;
  root.CorteUX = CorteUX;
})(typeof window !== "undefined" ? window : globalThis);
