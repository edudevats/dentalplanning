"""
Núcleo contable unificado del sistema.

Este módulo centraliza las fórmulas, constantes y nombres de variables que
ANTES estaban duplicados/reimplementados en varios lugares (dashboard, edr,
finanzas_personales). El objetivo es que TODAS las partes del sistema contable
usen exactamente las mismas variables y la misma lógica, para evitar
confusiones y resultados que no cuadran entre pantallas.

Glosario de nombres canónicos (usar SIEMPRE estos):
─────────────────────────────────────────────────────────────────────────────
  ventas / total_ingresos        Suma de Ingreso.monto del periodo
  comisiones_bancarias           Suma de Ingreso.comision_bancaria
  comisiones_especialistas       Suma de Ingreso.comision_doctor  (mismo concepto)
  gastos_variables               GastoOperativo.tipo == "variable"
  gastos_fijos                   GastoOperativo.tipo == "fijo"
  pagos_doctores                 Suma de PagoDoctor.monto (salario + comisión)
  gastos_variables_totales       comisiones + gastos_variables + pagos_doctores
  utilidad_bruta                 ventas - gastos_variables_totales
  utilidad_neta                  utilidad_bruta - gastos_fijos   (ANTES de impuestos)
  impuestos                      Impuesto REAL pagado en el periodo (parámetro)
  impuestos_estimados            SOLO informativo: utilidad_neta * tasa_impuesto
  utilidad_despues_impuestos     utilidad_neta - impuestos (solo para presentación)
─────────────────────────────────────────────────────────────────────────────

IMPORTANTE sobre impuestos: `utilidad_neta` es SIEMPRE antes de impuestos y
es la base de la distribución de ingresos — no cambia. `impuestos` recibe el
monto real pagado; `utilidad_despues_impuestos` = utilidad_neta - impuestos
es SOLO para mostrar en pantalla. `impuestos_estimados` se conserva por
compatibilidad como estimación informativa (utilidad_neta * tasa_impuesto_pct).
"""
from datetime import date


# Etiquetas de mes en español (antes duplicadas 4 veces en finanzas_personales)
MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def parse_mes(mes_str):
    """Parsea 'YYYY-MM' -> (year, month). Cae al mes actual si es inválido.

    Antes estaba duplicado idéntico en dashboard/routes.py y edr/routes.py.
    """
    if not mes_str:
        today = date.today()
        return today.year, today.month
    try:
        parts = str(mes_str).split("-")
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except (IndexError, ValueError):
        today = date.today()
        return today.year, today.month


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo por tratamiento (compartido entre el motor de precios y el EDR)
# ─────────────────────────────────────────────────────────────────────────────

def costo_tratamiento(costo_materiales, comision_bancaria, comision_especialista,
                      costo_consultorio):
    """Costo total de un tratamiento — UNA sola definición.

    costo_venta       = materiales + comisión bancaria + comisión especialista
    costo_tratamiento = costo_venta + costo de consultorio
    """
    costo_venta = costo_materiales + comision_bancaria + comision_especialista
    return costo_venta + costo_consultorio


def ganancia_tratamiento(precio, costo_materiales, comision_bancaria,
                         comision_especialista, costo_consultorio):
    """Ganancia neta de un tratamiento = precio - costo_tratamiento.

    La usa tanto el motor de precios (planeación, comisiones del Tratamiento)
    como el resumen de pagos a doctores del EDR (realidad, comisiones del
    Ingreso). Misma fórmula, mismos nombres.
    """
    return precio - costo_tratamiento(
        costo_materiales, comision_bancaria, comision_especialista, costo_consultorio
    )


# ─────────────────────────────────────────────────────────────────────────────
# Estado de Resultados de un periodo (mensual / trimestral / distribución)
# ─────────────────────────────────────────────────────────────────────────────

def estado_resultados(*, ventas, comisiones_bancarias, comisiones_especialistas,
                      gastos_variables, gastos_fijos, pagos_doctores,
                      tasa_impuesto_pct=0.0, impuestos=0.0):
    """Estado de Resultados canónico de un periodo.

    Una sola definición usada por el resumen mensual, el trimestral y la
    distribución de ingresos, para que `utilidad_neta` / `ingreso_neto`
    SIEMPRE signifiquen lo mismo en todo el sistema.

    Devuelve un dict con los nombres canónicos del glosario de arriba.
    """
    gastos_variables_totales = (
        comisiones_bancarias
        + comisiones_especialistas
        + gastos_variables
        + pagos_doctores
    )
    utilidad_bruta = ventas - gastos_variables_totales
    pct_utilidad_bruta = utilidad_bruta / ventas if ventas > 0 else 0

    # utilidad neta canónica (ANTES de impuestos) — base de la distribución
    utilidad_neta = utilidad_bruta - gastos_fijos
    pct_utilidad = utilidad_neta / ventas if ventas > 0 else 0

    # Impuestos REALES pagados (registrados como gasto). Reemplazan la
    # estimación por porcentaje para la línea del Estado de Resultados.
    impuestos_pagados = round(impuestos, 2)
    utilidad_despues_impuestos = utilidad_neta - impuestos_pagados

    # Estimación legacy (informativa) — conservada por compatibilidad.
    impuestos_estimados = (
        round(utilidad_neta * tasa_impuesto_pct / 100, 2)
        if utilidad_neta > 0 and tasa_impuesto_pct > 0 else 0
    )

    # Punto de equilibrio (Excel: -GASTOS_FIJOS / %UTILIDAD_BRUTA)
    punto_equilibrio = (
        gastos_fijos / pct_utilidad_bruta if pct_utilidad_bruta != 0 else 0
    )

    return {
        "ventas": ventas,
        "comisiones_bancarias": comisiones_bancarias,
        "comisiones_especialistas": comisiones_especialistas,
        "gastos_variables": gastos_variables,
        "gastos_fijos": gastos_fijos,
        "pagos_doctores": pagos_doctores,
        "gastos_variables_totales": gastos_variables_totales,
        "utilidad_bruta": utilidad_bruta,
        "pct_utilidad_bruta": pct_utilidad_bruta,
        "utilidad_neta": utilidad_neta,
        "pct_utilidad": pct_utilidad,
        "tasa_impuesto_pct": tasa_impuesto_pct,
        "impuestos": impuestos_pagados,
        "impuestos_estimados": impuestos_estimados,
        "utilidad_despues_impuestos": utilidad_despues_impuestos,
        "punto_equilibrio": punto_equilibrio,
    }
