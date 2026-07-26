"""Cálculo puro del plan de pagos: sin BD y sin Flask, todo entra por parámetros.

Vive aparte de services.py para poder probar la aritmética y el calendario sin
montar la aplicación.
"""
import math
from calendar import monthrange
from datetime import date, timedelta

# Diferencias por debajo de un centavo son ruido de punto flotante, no saldo.
TOLERANCIA = 0.01

# Un plan con saldo y sin pagos en este número de días se marca como
# "sin pagos recientes". No hay estado "vencido" por parcialidad: los pacientes
# pagan cuando pueden y un semáforo por fecha sería ruido permanente.
DIAS_ALERTA_SIN_PAGO = 45

FRECUENCIAS = ("mensual", "quincenal")

# Tope duro de parcialidades. Coincide con el máximo que valida la API y evita
# que un monto muy chico frente al saldo genere un calendario inmanejable.
MAX_PARCIALIDADES = 120


class PlanInvalido(ValueError):
    """Los parámetros capturados no producen un calendario válido."""


def _redondear_a_peso(valor):
    """Redondeo half-up a pesos enteros.

    `round()` de Python usa banker's rounding (round(2.5) == 2), que haría el
    calendario impredecible; aquí siempre se sube el medio peso.
    """
    return float(int(valor + 0.5))


def sumar_meses(origen, meses):
    """`origen` + `meses`, recortando al último día si el día no existe.

    31 de enero + 1 mes = 28 (o 29) de febrero.
    """
    indice = origen.month - 1 + meses
    anio = origen.year + indice // 12
    mes = indice % 12 + 1
    dia = min(origen.day, monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def fecha_vencimiento(fecha_primer_pago, k, frecuencia):
    """Vencimiento proyectado de la parcialidad `k` (1-based)."""
    if frecuencia == "quincenal":
        return fecha_primer_pago + timedelta(days=15 * (k - 1))
    return sumar_meses(fecha_primer_pago, k - 1)


def montos_por_numero(restante, n):
    """`n` parcialidades en pesos enteros; la última absorbe el residuo."""
    if n < 1:
        raise PlanInvalido("El número de parcialidades debe ser al menos 1")
    if n > MAX_PARCIALIDADES:
        raise PlanInvalido(
            f"El máximo son {MAX_PARCIALIDADES} parcialidades"
        )
    if restante <= TOLERANCIA:
        raise PlanInvalido("No queda saldo por diferir")
    if n == 1:
        return [round(restante, 2)]
    base = _redondear_a_peso(restante / n)
    if base <= 0:
        raise PlanInvalido(
            "Son demasiadas parcialidades para ese monto: cada pago quedaría en cero"
        )
    ultima = round(restante - base * (n - 1), 2)
    if ultima <= 0:
        raise PlanInvalido(
            "Son demasiadas parcialidades para ese monto: el último pago quedaría en cero"
        )
    return [base] * (n - 1) + [ultima]


def montos_por_monto(restante, monto):
    """Parcialidades fijas de `monto`; la última absorbe el resto."""
    if monto <= 0:
        raise PlanInvalido("El monto de la parcialidad debe ser mayor a cero")
    if restante <= TOLERANCIA:
        raise PlanInvalido("No queda saldo por diferir")
    # El round() previo absorbe el ruido de punto flotante: 18000/1000 puede
    # dar 17.999999999999996 y el ceil daría 18 de todos modos, pero 3/0.1 no.
    n = int(math.ceil(round(restante / monto, 6)))
    if n > MAX_PARCIALIDADES:
        raise PlanInvalido(
            f"Con ese monto salen más de {MAX_PARCIALIDADES} pagos: "
            "sube el monto de la parcialidad"
        )
    if n == 1:
        return [round(restante, 2)]
    ultima = round(restante - monto * (n - 1), 2)
    # Misma guarda que `montos_por_numero`: nunca se devuelve una parcialidad
    # final en cero (o negativa) por ruido de redondeo.
    if ultima <= 0:
        raise PlanInvalido(
            "Son demasiadas parcialidades para ese monto: el último pago quedaría en cero"
        )
    return [float(monto)] * (n - 1) + [ultima]


def calcular_plan(*, total, anticipo, frecuencia, fecha_primer_pago,
                  fecha_anticipo, num_parcialidades=None, monto_parcialidad=None):
    """Calendario completo del plan.

    Devuelve una lista de dicts `{"numero", "fecha_vencimiento", "monto"}`
    ordenada por número. El `numero` 0 es el anticipo y sólo aparece si hay.
    Se captura `num_parcialidades` O `monto_parcialidad`, nunca los dos.
    """
    if total <= 0:
        raise PlanInvalido("El total debe ser mayor a cero")
    if anticipo < 0:
        raise PlanInvalido("El anticipo no puede ser negativo")
    if anticipo > total + TOLERANCIA:
        raise PlanInvalido("El anticipo no puede ser mayor al total")
    if frecuencia not in FRECUENCIAS:
        raise PlanInvalido("La frecuencia debe ser mensual o quincenal")

    filas = []
    if anticipo > TOLERANCIA:
        filas.append({
            "numero": 0,
            "fecha_vencimiento": fecha_anticipo,
            "monto": round(anticipo, 2),
        })
    else:
        # Un anticipo por debajo de la tolerancia es ruido de captura, no
        # dinero: se descarta también al calcular el restante para que la
        # suma de las filas devueltas siga dando exactamente `total`.
        anticipo = 0

    restante = round(total - anticipo, 2)
    if restante <= TOLERANCIA:
        return filas

    if (num_parcialidades is None) == (monto_parcialidad is None):
        raise PlanInvalido(
            "Captura el número de parcialidades o el monto de cada una, no ambos"
        )

    if num_parcialidades is not None:
        montos = montos_por_numero(restante, num_parcialidades)
    else:
        montos = montos_por_monto(restante, monto_parcialidad)

    for k, monto in enumerate(montos, start=1):
        filas.append({
            "numero": k,
            "fecha_vencimiento": fecha_vencimiento(fecha_primer_pago, k, frecuencia),
            "monto": monto,
        })
    return filas


class Sobrepago(PlanInvalido):
    """El abono excede el saldo del plan."""


def aplicar_cascada(programados, pagos):
    """Reparte todos los pagos sobre el calendario, del más viejo al más nuevo.

    Recalcula desde cero en cada llamada (no acumula), así que es idempotente y
    sirve igual para registrar un pago nuevo que para revertir uno eliminado.

    `programados` se muta: se actualizan `monto_pagado` y `estatus`.
    Devuelve las asignaciones `(pago, programado, monto_aplicado)`, que el
    estado de cuenta usa para saber a qué bloque pertenece cada abono.
    """
    # Valida antes de mutar nada: si algo es inválido, `programados` debe
    # quedar exactamente como llegó (nada de mutación parcial).
    for pago in pagos:
        if pago.monto <= 0:
            raise PlanInvalido(
                "El monto de un abono debe ser mayor a cero. "
                "Para revertir un pago, quítalo de la lista en vez de "
                "capturarlo en cero."
            )

    total_pagos = round(sum(pago.monto for pago in pagos), 2)
    total_programado = round(
        sum(prog.monto_programado for prog in programados), 2
    )
    excedente = round(total_pagos - total_programado, 2)
    if excedente > TOLERANCIA:
        raise Sobrepago(
            f"El pago excede el saldo del plan por ${excedente:,.2f}. "
            "Ajusta el monto o revisa el plan."
        )

    for prog in programados:
        prog.monto_pagado = 0.0
        prog.estatus = "pendiente"

    asignaciones = []
    for pago in pagos:
        restante = round(pago.monto, 2)
        for prog in programados:
            if restante <= TOLERANCIA:
                break
            hueco = round(prog.monto_programado - prog.monto_pagado, 2)
            if hueco <= TOLERANCIA:
                continue
            aplicado = round(min(hueco, restante), 2)
            prog.monto_pagado = round(prog.monto_pagado + aplicado, 2)
            restante = round(restante - aplicado, 2)
            asignaciones.append((pago, prog, aplicado))
        if restante > TOLERANCIA:
            raise Sobrepago(
                f"El pago excede el saldo del plan por ${restante:,.2f}. "
                "Ajusta el monto o revisa el plan."
            )

    for prog in programados:
        if prog.monto_pagado >= prog.monto_programado - TOLERANCIA:
            prog.estatus = "pagado"
        elif prog.monto_pagado > TOLERANCIA:
            prog.estatus = "parcial"

    return asignaciones


def dias_sin_pago(fecha_ultimo_pago, hoy):
    """Días transcurridos desde el último pago. None si nunca ha habido uno."""
    if fecha_ultimo_pago is None:
        return None
    return (hoy - fecha_ultimo_pago).days
