"""
Motor de cálculo de precios — Réplica exacta de las fórmulas del Excel PRECIOS_EJEMPLO_2025.

FÓRMULAS MAPEADAS:
─────────────────────────────────────────────────────────────
EXCEL                              │ PYTHON
─────────────────────────────────────────────────────────────
F13 = E13/G13                      │ material.costo_unitario
I25 = SUM(I16:I22)                 │ config.horas_semana
I28 = I25 * 4                      │ config.horas_mes
I34 = Gastofijo/Horasalmes/Uni     │ config.costo_hora
D5  = D4 * B5                      │ costo_consultorio_tx
D3  = SUM(materiales+comisiones)   │ costo_venta
D17 = D7 * (C17/100)               │ comision_bancaria
D18 = IF(tipo="Comisión %",...)    │ comision_especialista
D6  = D3 + D5                      │ costo_tratamiento
D8  = D7 - D6                      │ ganancia_neta
D9  = (D8 / D7) * 100              │ pct_ganancia
E10 = D6 / (1 - 0.3)              │ precio_minimo_sugerido
─────────────────────────────────────────────────────────────
"""
from app.engine import accounting


def calcular_precio_tratamiento(config, tratamiento, materiales_tx):
    """
    Calcula todos los valores de un tratamiento.

    Args:
        config: ConfigConsultorio instance
        tratamiento: Tratamiento instance
        materiales_tx: list of TratamientoMaterial instances

    Returns:
        dict con todos los cálculos
    """
    # 1. Costo hora consultorio
    costo_hora = config.costo_hora

    # 2. Costo de consultorio por tratamiento
    costo_consultorio = tratamiento.horas_invertidas * costo_hora

    # 3. Costo de materiales
    detalle_materiales = []
    costo_materiales = 0
    for tm in materiales_tx:
        mat = tm.material
        costo_unit = mat.costo_unitario
        costo_en_tx = costo_unit * tm.cantidad
        costo_materiales += costo_en_tx
        detalle_materiales.append({
            "material_id": mat.id,
            "nombre": mat.nombre,
            "costo_paquete": mat.costo_paquete,
            "unidades_paquete": mat.unidades_paquete,
            "costo_unitario": round(costo_unit, 4),
            "cantidad": tm.cantidad,
            "costo_en_tratamiento": round(costo_en_tx, 2),
        })

    precio = tratamiento.precio_paciente

    # 4. Comisión bancaria
    comision_bancaria = precio * (tratamiento.comision_bancaria_pct / 100)

    # 5. Comisión especialista
    if tratamiento.comision_especialista_tipo == "porcentaje":
        comision_especialista = precio * (tratamiento.comision_especialista_valor / 100)
    else:
        comision_especialista = tratamiento.comision_especialista_valor

    # 6. Costo de venta
    costo_venta = costo_materiales + comision_bancaria + comision_especialista

    # 7. Costo total del tratamiento (fórmula compartida con el EDR)
    costo_tratamiento = accounting.costo_tratamiento(
        costo_materiales, comision_bancaria, comision_especialista, costo_consultorio
    )

    # 8. Ganancia neta
    ganancia_neta = precio - costo_tratamiento

    # 9. Porcentaje de ganancia
    pct_ganancia = ganancia_neta / precio if precio > 0 else 0

    # 10. Precio mínimo sugerido (30% margen)
    precio_minimo = costo_tratamiento / 0.7 if costo_tratamiento > 0 else 0

    # Descuentos
    descuentos = calcular_descuentos(costo_tratamiento, precio)

    return {
        "costo_hora_consultorio": round(costo_hora, 2),
        "costo_consultorio_tx": round(costo_consultorio, 2),
        "costo_materiales": round(costo_materiales, 2),
        "comision_bancaria": round(comision_bancaria, 2),
        "comision_especialista": round(comision_especialista, 2),
        "costo_venta": round(costo_venta, 2),
        "costo_tratamiento": round(costo_tratamiento, 2),
        "ganancia_neta": round(ganancia_neta, 2),
        "pct_ganancia": round(pct_ganancia * 100, 2),
        "precio_minimo_sugerido": round(precio_minimo, 2),
        "materiales": detalle_materiales,
        "descuentos": descuentos,
    }


def calcular_descuentos(costo_tratamiento, precio, porcentajes=None):
    """
    Calcula escenarios de descuento (réplica de las 4 columnas G/J del Excel).
    """
    if porcentajes is None:
        porcentajes = [0.10, 0.20, 0.30, 0.50]

    resultados = []
    for pct in porcentajes:
        descuento = pct * precio
        precio_con_descuento = precio - descuento
        ganancia = precio_con_descuento - costo_tratamiento
        pct_ganancia = ganancia / precio_con_descuento if precio_con_descuento > 0 else 0
        resultados.append({
            "porcentaje": round(pct * 100),
            "monto_descuento": round(descuento, 2),
            "precio_con_descuento": round(precio_con_descuento, 2),
            "ganancia": round(ganancia, 2),
            "pct_ganancia": round(pct_ganancia * 100, 2),
        })
    return resultados


def generar_dashboard_ganancias(config, tratamientos_con_materiales, comisiones=None):
    """
    Genera resumen tipo hoja 'Ganancias' para todos los tratamientos.

    Args:
        config: ConfigConsultorio
        tratamientos_con_materiales: list of (tratamiento, materiales_tx)
        comisiones: list of commission percentages to show scenarios [0, 0.20, 0.30]
    """
    if comisiones is None:
        comisiones = [0, 0.20, 0.30]

    resumen = []
    for tx, materiales_tx in tratamientos_con_materiales:
        calculos = calcular_precio_tratamiento(config, tx, materiales_tx)
        precio = tx.precio_paciente

        escenarios = []
        for com_pct in comisiones:
            com_monto = precio * com_pct
            ganancia = calculos["ganancia_neta"] - com_monto
            pct_gan = ganancia / precio if precio > 0 else 0
            escenarios.append({
                "comision_pct": round(com_pct * 100),
                "ganancia": round(ganancia, 2),
                "pct_ganancia": round(pct_gan * 100, 2),
            })

        resumen.append({
            "tratamiento_id": tx.id,
            "tratamiento": tx.nombre,
            "precio": precio,
            "ganancia_base": calculos["ganancia_neta"],
            "porcentaje_ganancia_base": calculos["pct_ganancia"],
            "escenarios_comision": escenarios,
        })

    total_tx = len(resumen)
    avg_pct = (
        sum(r["porcentaje_ganancia_base"] for r in resumen) / total_tx
        if total_tx > 0
        else 0
    )
    mas_rentable = max(resumen, key=lambda r: r["porcentaje_ganancia_base"], default=None)
    menos_rentable = min(resumen, key=lambda r: r["porcentaje_ganancia_base"], default=None)

    return {
        "resumen": resumen,
        "totales": {
            "total_tratamientos": total_tx,
            "ganancia_promedio_pct": round(avg_pct, 4),
            "tratamiento_mas_rentable": mas_rentable["tratamiento"] if mas_rentable else None,
            "tratamiento_menos_rentable": menos_rentable["tratamiento"] if menos_rentable else None,
        },
    }
