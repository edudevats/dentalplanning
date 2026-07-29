"""Texto del estado de cuenta que el consultorio manda por WhatsApp.

Reproduce el formato que hoy escriben a mano en cada pago. Es puro: recibe
datos ya calculados y devuelve la cadena, para poder probarlo sin BD.
"""

MESES_LARGOS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

MESES_CORTOS = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


def fecha_larga(d):
    """10 de septiembre de 2025"""
    return f"{d.day} de {MESES_LARGOS[d.month - 1]} de {d.year}"


def fecha_corta(d):
    """10/sep/25"""
    return f"{d.day:02d}/{MESES_CORTOS[d.month - 1]}/{d.year % 100:02d}"


def monto_texto(valor):
    """28,000 — sin símbolo y sin centavos cuando la cifra es entera."""
    valor = round(float(valor or 0), 2)
    if abs(valor - round(valor)) < 0.005:
        return f"{int(round(valor)):,}"
    return f"{valor:,.2f}"


def _saludo(hora):
    if hora < 12:
        return "buenos días"
    if hora < 19:
        return "buenas tardes"
    return "buenas noches"


def _linea_abono(abono):
    metodo = abono.get("metodo") or "—"
    return f"- {fecha_corta(abono['fecha'])}: {monto_texto(abono['monto'])} {metodo}"


def construir_texto(*, paciente, fecha_inicio, total, anticipo, frecuencia,
                    num_parcialidades, parcialidades_pagadas,
                    abonos_anticipo, abonos_parcialidades, pagado, saldo,
                    devoluciones=None, hora=None):
    """Arma el estado de cuenta completo, listo para pegar en WhatsApp."""
    if hora is None:
        from app.facturacion.timezone_helper import now_mexico
        hora = now_mexico().hour

    bloques = [
        f"Hola, {_saludo(hora)}. Les compartimos su estado de cuenta respecto "
        f"al tratamiento de {paciente} 😊",
        f"Comenzaron el día {fecha_larga(fecha_inicio)}.",
        f"El costo total del tratamiento es de {monto_texto(total)} pesos.",
    ]

    if anticipo and anticipo > 0 and abonos_anticipo:
        lineas = [
            f"El pago inicial fue de {monto_texto(anticipo)} pesos que pagaron "
            "de la siguiente forma:"
        ]
        lineas += [_linea_abono(a) for a in abonos_anticipo]
        bloques.append("\n".join(lineas))

    if abonos_parcialidades:
        unidad = "quincenas" if frecuencia == "quincenal" else "meses"
        lineas = [
            f"Su tratamiento es de {num_parcialidades} {unidad}, "
            f"actualmente llevan {parcialidades_pagadas}:"
        ]
        lineas += [_linea_abono(a) for a in abonos_parcialidades]
        bloques.append("\n".join(lineas))

    if devoluciones:
        total_dev = sum(d["monto"] for d in devoluciones)
        lineas = [
            f"Se realizaron devoluciones por {monto_texto(total_dev)} pesos:"
        ]
        lineas += [_linea_abono(d) for d in devoluciones]
        bloques.append("\n".join(lineas))

    bloques.append(
        f"En resumen, han realizado el pago de {monto_texto(pagado)} pesos, "
        f"quedando pendientes {monto_texto(saldo)} pesos de los "
        f"{monto_texto(total)} pesos del costo del tratamiento. Quedamos al "
        "pendiente si tienen alguna duda al respecto 😁"
    )

    return "\n\n".join(bloques)
