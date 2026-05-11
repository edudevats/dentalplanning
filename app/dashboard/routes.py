from datetime import date
from flask import Blueprint, request, jsonify, g
from sqlalchemy import extract, func
from app.extensions import db
from app.middleware.tenant import require_auth
from app.edr.models import Ingreso, GastoOperativo, PagoDoctor
from app.tratamientos.models import Tratamiento
from app.configuracion.models import ConfigConsultorio
from app.ajustes.models import DistribucionConfig, DistribucionCategoria, DIST_CATEGORIAS_DEFAULT
from app.engine.pricing_engine import generar_dashboard_ganancias

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/v1")


def _parse_mes(mes_str):
    if not mes_str:
        today = date.today()
        return today.year, today.month
    parts = mes_str.split("-")
    return int(parts[0]), int(parts[1])


# ── DASHBOARD GANANCIAS (réplica hoja Ganancias del Excel PRECIOS) ──

@dashboard_bp.route("/dashboard/ganancias", methods=["GET"])
@require_auth
def ganancias():
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    tratamientos = Tratamiento.query.filter_by(tenant_id=g.tenant_id).all()

    comisiones_str = request.args.get("comision", "0,20,30")
    comisiones = [int(c) / 100 for c in comisiones_str.split(",")]

    tx_con_materiales = [(tx, tx.materiales) for tx in tratamientos]
    result = generar_dashboard_ganancias(config, tx_con_materiales, comisiones)
    return jsonify(result)


# ── RESUMEN MENSUAL (réplica hoja RESUMEN del Excel EDR) ──

@dashboard_bp.route("/reportes/resumen-mensual", methods=["GET"])
@require_auth
def resumen_mensual():
    year, month = _parse_mes(request.args.get("mes"))

    # Ingresos
    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).all()

    total_ingresos = sum(i.monto for i in ingresos)
    total_comisiones_bancarias = sum(i.comision_bancaria for i in ingresos)
    total_comisiones_doctores = sum(i.comision_doctor for i in ingresos)

    # Desglose efectivo vs banco
    ingresos_efectivo = sum(
        i.monto for i in ingresos
        if i.metodo_pago and i.metodo_pago.nombre.lower() == "efectivo"
    )
    ingresos_banco = total_ingresos - ingresos_efectivo

    # Gastos operativos
    gastos = GastoOperativo.query.filter(
        GastoOperativo.tenant_id == g.tenant_id,
        extract("year", GastoOperativo.fecha) == year,
        extract("month", GastoOperativo.fecha) == month,
    ).all()
    total_gastos_fijos = sum(g_.monto for g_ in gastos if g_.tipo == "fijo")
    total_gastos_variables = sum(g_.monto for g_ in gastos if g_.tipo == "variable")
    total_impuestos = sum(g_.monto for g_ in gastos if g_.tipo == "impuesto")

    # Pagos a doctores (unificados: salario + comision)
    pagos = PagoDoctor.query.filter(
        PagoDoctor.tenant_id == g.tenant_id,
        extract("year", PagoDoctor.fecha) == year,
        extract("month", PagoDoctor.fecha) == month,
    ).all()
    total_pagos_doctores   = sum(p.monto for p in pagos)
    pagos_doctores_salarios  = sum(p.monto for p in pagos if p.tipo == "salario")
    pagos_doctores_comisiones = sum(p.monto for p in pagos if p.tipo == "comision")

    # Estado de resultados
    total_egresos = (
        total_comisiones_bancarias
        + total_comisiones_doctores
        + total_gastos_fijos
        + total_gastos_variables
        + total_pagos_doctores
        + total_impuestos
    )
    utilidad_neta = total_ingresos - total_egresos

    # ── ESTADO DE RESULTADOS (réplica hoja RESUMEN del Excel) ──
    # VENTAS TOTALES = total de ingresos del período
    ventas_totales = total_ingresos
    # GASTOS VARIABLES = comisiones bancarias + comisiones especialistas
    #                    + gastos variables EDR + pagos a doctores
    gastos_variables_er = (
        total_comisiones_bancarias
        + total_comisiones_doctores
        + total_gastos_variables
        + total_pagos_doctores
    )
    # UTILIDAD BRUTA = ventas - gastos variables
    utilidad_bruta = ventas_totales - gastos_variables_er
    # % UTILIDAD BRUTA = utilidad_bruta / ventas_totales
    pct_utilidad_bruta = utilidad_bruta / ventas_totales if ventas_totales > 0 else 0
    # UTILIDAD ANTES DE IMPUESTOS = utilidad bruta - gastos fijos
    utilidad_antes_impuestos = utilidad_bruta - total_gastos_fijos
    # UTILIDAD DESPUES DE IMPUESTOS = utilidad antes - impuestos
    utilidad_despues_impuestos = utilidad_antes_impuestos - total_impuestos
    # % UTILIDAD = utilidad despues de impuestos / ventas totales
    pct_utilidad = utilidad_despues_impuestos / ventas_totales if ventas_totales > 0 else 0

    # ── PUNTO DE EQUILIBRIO ──
    # Fórmula Excel: =SI.ERROR(-D24/D23,0)
    # D24 = GASTOS FIJOS (negativo en Excel), D23 = % UTILIDAD BRUTA
    # Python: gastos_fijos / pct_utilidad_bruta
    punto_equilibrio = (
        total_gastos_fijos / pct_utilidad_bruta if pct_utilidad_bruta != 0 else 0
    )
    cincuenta_pct_ventas = ventas_totales * 0.5

    # Balance diario
    balance_diario = {}
    for i in ingresos:
        day = i.fecha.isoformat()
        if day not in balance_diario:
            balance_diario[day] = {"ingresos": 0, "egresos": 0}
        balance_diario[day]["ingresos"] += i.monto
        balance_diario[day]["egresos"] += i.comision_bancaria + i.comision_doctor
    for g_ in gastos:
        day = g_.fecha.isoformat()
        if day not in balance_diario:
            balance_diario[day] = {"ingresos": 0, "egresos": 0}
        balance_diario[day]["egresos"] += g_.monto
    for p in pagos:
        day = p.fecha.isoformat()
        if day not in balance_diario:
            balance_diario[day] = {"ingresos": 0, "egresos": 0}
        balance_diario[day]["egresos"] += p.monto

    balance_list = []
    saldo_acum = 0
    for day in sorted(balance_diario.keys()):
        d = balance_diario[day]
        saldo_acum += d["ingresos"] - d["egresos"]
        balance_list.append({
            "fecha": day,
            "ingresos": round(d["ingresos"], 2),
            "egresos": round(d["egresos"], 2),
            "saldo_acumulado": round(saldo_acum, 2),
        })

    return jsonify({
        "mes": f"{year}-{month:02d}",
        # ── Ingresos ──
        "total_ingresos": round(total_ingresos, 2),
        "total_comisiones_bancarias": round(total_comisiones_bancarias, 2),
        "total_comisiones_especialistas": round(total_comisiones_doctores, 2),
        "ingresos_efectivo": round(ingresos_efectivo, 2),
        "ingresos_banco": round(ingresos_banco, 2),
        # ── Egresos ──
        "gastos_fijos": round(total_gastos_fijos, 2),
        "gastos_variables": round(total_gastos_variables, 2),
        # Pagos a doctores: métrica unificada + desglose por tipo
        "total_pagos_doctores": round(total_pagos_doctores, 2),
        "pagos_doctores_desglose": {
            "salarios":  round(pagos_doctores_salarios, 2),
            "comisiones": round(pagos_doctores_comisiones, 2),
        },
        "total_egresos": round(total_egresos, 2),
        "utilidad_neta": round(utilidad_neta, 2),
        # ── Estado de Resultados ──
        "estado_de_resultados": {
            "ventas_totales": round(ventas_totales, 2),
            "gastos_variables": round(gastos_variables_er, 2),
            "utilidad_bruta": round(utilidad_bruta, 2),
            "pct_utilidad_bruta": round(pct_utilidad_bruta, 4),
            "gastos_fijos": round(total_gastos_fijos, 2),
            "utilidad_antes_impuestos": round(utilidad_antes_impuestos, 2),
            "impuestos": round(total_impuestos, 2),
            "pct_utilidad": round(pct_utilidad, 4),
            "utilidad_despues_impuestos": round(utilidad_despues_impuestos, 2),
        },
        # ── Punto de Equilibrio ──
        "punto_de_equilibrio": {
            "punto_equilibrio": round(punto_equilibrio, 2),
            "cincuenta_pct_ventas": round(cincuenta_pct_ventas, 2),
        },
        "balance_diario": balance_list,
    })


# ── REPORTES TRIMESTRALES (réplica hoja %TRIMESTRALES) ──

@dashboard_bp.route("/reportes/trimestral", methods=["GET"])
@require_auth
def trimestral():
    year = request.args.get("year", date.today().year, type=int)

    meses = []
    for month in range(1, 13):
        total_ing = db.session.query(func.coalesce(func.sum(Ingreso.monto), 0)).filter(
            Ingreso.tenant_id == g.tenant_id,
            extract("year", Ingreso.fecha) == year,
            extract("month", Ingreso.fecha) == month,
        ).scalar()
        total_gas = db.session.query(func.coalesce(func.sum(GastoOperativo.monto), 0)).filter(
            GastoOperativo.tenant_id == g.tenant_id,
            extract("year", GastoOperativo.fecha) == year,
            extract("month", GastoOperativo.fecha) == month,
        ).scalar()
        meses.append({
            "mes": month,
            "total": round(float(total_ing), 2),
            "gastos": round(float(total_gas), 2),
        })

    # Trimestrales
    trimestres = []
    for t in range(4):
        start = t * 3
        meses_trim = meses[start:start + 3]
        total_trim = sum(m["total"] for m in meses_trim)
        total_gas_trim = sum(m["gastos"] for m in meses_trim)
        count_nonzero = sum(1 for m in meses_trim if m["total"] > 0)
        count_gas_nonzero = sum(1 for m in meses_trim if m["gastos"] > 0)
        promedio = total_trim / count_nonzero if count_nonzero > 0 else 0
        promedio_gas = total_gas_trim / count_gas_nonzero if count_gas_nonzero > 0 else 0
        trimestres.append({
            "trimestre": t + 1,
            "total": round(total_trim, 2),
            "promedio": round(promedio, 2),
            "total_gastos": round(total_gas_trim, 2),
            "promedio_gastos": round(promedio_gas, 2),
        })

    # % de crecimiento mes a mes
    crecimiento = []
    for i in range(1, 12):
        prev = meses[i - 1]["total"]
        curr = meses[i]["total"]
        pct = ((curr - prev) / prev) if prev > 0 else 0
        crecimiento.append({
            "de_mes": i,
            "a_mes": i + 1,
            "porcentaje": round(pct, 4),
        })

    total_anual = sum(m["total"] for m in meses)
    count_nonzero = sum(1 for m in meses if m["total"] > 0)

    return jsonify({
        "year": year,
        "meses": meses,
        "trimestres": trimestres,
        "crecimiento": crecimiento,
        "total_anual": round(total_anual, 2),
        "promedio_mensual": round(total_anual / count_nonzero, 2) if count_nonzero > 0 else 0,
    })


# ── DISTRIBUCIÓN DE INGRESOS (réplica sistema de ahorro del Excel) ──

@dashboard_bp.route("/reportes/distribucion", methods=["GET"])
@require_auth
def distribucion():
    year, month = _parse_mes(request.args.get("mes"))

    total_ingresos = db.session.query(
        func.coalesce(func.sum(Ingreso.monto), 0)
    ).filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).scalar()

    total_gastos_var = db.session.query(
        func.coalesce(func.sum(GastoOperativo.monto), 0)
    ).filter(
        GastoOperativo.tenant_id == g.tenant_id,
        GastoOperativo.tipo == "variable",
        extract("year", GastoOperativo.fecha) == year,
        extract("month", GastoOperativo.fecha) == month,
    ).scalar()

    total_comisiones = db.session.query(
        func.coalesce(func.sum(Ingreso.comision_bancaria + Ingreso.comision_doctor), 0)
    ).filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).scalar()

    total_gastos_fijos = db.session.query(
        func.coalesce(func.sum(GastoOperativo.monto), 0)
    ).filter(
        GastoOperativo.tenant_id == g.tenant_id,
        GastoOperativo.tipo == "fijo",
        extract("year", GastoOperativo.fecha) == year,
        extract("month", GastoOperativo.fecha) == month,
    ).scalar()

    total_pagos_doc = db.session.query(
        func.coalesce(func.sum(PagoDoctor.monto), 0)
    ).filter(
        PagoDoctor.tenant_id == g.tenant_id,
        extract("year", PagoDoctor.fecha) == year,
        extract("month", PagoDoctor.fecha) == month,
    ).scalar()

    ingreso_neto = float(total_ingresos) - float(total_gastos_var) - float(total_comisiones) - float(total_gastos_fijos) - float(total_pagos_doc)

    # Use DistribucionCategoria (dynamic) — falls back to DistribucionConfig if not seeded yet
    cats = DistribucionCategoria.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(DistribucionCategoria.sort_order).all()

    if cats:
        cat_list = [{"id": c.id, "nombre": c.nombre, "color": c.color, "porcentaje": float(c.porcentaje)} for c in cats]
    else:
        # Fallback: read from legacy DistribucionConfig
        dist_cfg = DistribucionConfig.query.filter_by(tenant_id=g.tenant_id).first()
        cat_list = [
            {
                "id": None,
                "nombre": d["nombre"],
                "color": d["color"],
                "porcentaje": float(getattr(dist_cfg, d["clave"], d["porcentaje"])) if dist_cfg else float(d["porcentaje"]),
            }
            for d in DIST_CATEGORIAS_DEFAULT
        ]

    # Build dynamic categorias response
    categorias_resp = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "color": c["color"],
            "porcentaje": c["porcentaje"],
            "monto": round(ingreso_neto * c["porcentaje"] / 100, 2),
        }
        for c in cat_list
    ]

    # Legacy keys kept for backward compat with existing consumers
    legacy_pcts = {c["nombre"].lower().replace(" ", "_"): c["porcentaje"] for c in cat_list}
    legacy_dist = {c["nombre"].lower().replace(" ", "_"): round(ingreso_neto * c["porcentaje"] / 100, 2) for c in cat_list}

    return jsonify({
        "mes": f"{year}-{month:02d}",
        "ingreso_neto": round(ingreso_neto, 2),
        "categorias": categorias_resp,
        "distribucion": legacy_dist,
        "porcentajes": legacy_pcts,
    })


# ── MARKETING (réplica reporte por estrategia) ──

@dashboard_bp.route("/reportes/marketing", methods=["GET"])
@require_auth
def marketing():
    year, month = _parse_mes(request.args.get("mes"))

    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).all()

    por_estrategia = {}
    for i in ingresos:
        nombre = i.estrategia.nombre if i.estrategia else "Sin estrategia"
        if nombre not in por_estrategia:
            por_estrategia[nombre] = {"cantidad": 0, "total": 0}
        por_estrategia[nombre]["cantidad"] += 1
        por_estrategia[nombre]["total"] += i.monto

    result = [
        {"estrategia": k, "cantidad": v["cantidad"], "total": round(v["total"], 2)}
        for k, v in sorted(por_estrategia.items(), key=lambda x: -x[1]["total"])
    ]

    return jsonify({"mes": f"{year}-{month:02d}", "por_estrategia": result})


# ── TRATAMIENTOS REALIZADOS (réplica hoja TRATAMIENTOS del EDR) ──

@dashboard_bp.route("/reportes/tratamientos-realizados", methods=["GET"])
@require_auth
def tratamientos_realizados():
    year, month = _parse_mes(request.args.get("mes"))

    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).all()

    por_tx = {}
    for i in ingresos:
        nombre = i.nombre_tratamiento or "Otro"
        if nombre not in por_tx:
            por_tx[nombre] = {"cantidad": 0, "total": 0}
        por_tx[nombre]["cantidad"] += 1
        por_tx[nombre]["total"] += i.monto

    result = [
        {"tratamiento": k, "cantidad": v["cantidad"], "ingreso": round(v["total"], 2)}
        for k, v in sorted(por_tx.items(), key=lambda x: -x[1]["total"])
    ]

    return jsonify({
        "mes": f"{year}-{month:02d}",
        "tratamientos": result,
        "total_general": round(sum(r["ingreso"] for r in result), 2),
    })
