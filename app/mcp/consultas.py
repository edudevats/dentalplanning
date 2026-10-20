"""Consultas de solo lectura que expone el MCP.

Cada función recibe el tenant explícito y devuelve datos ya listos para Claude.
Los números financieros salen del mismo cálculo que las pantallas
(`calcular_resumen_mensual`, `venta_ajustada`), nunca de una fórmula paralela.

Privacidad: de un paciente solo sale el nombre. Nada de teléfono, correo,
notas ni datos clínicos.
"""
import re
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import joinedload

from app.ajustes.models import GastoConcepto
from app.catalogo.models import Material
from app.cobranza.models import Cotizacion, PagoProgramado
from app.cobranza.calculo import TOLERANCIA
from app.dashboard.routes import calcular_resumen_mensual, venta_ajustada
from app.edr.models import GastoOperativo, Ingreso
from app.edr.recurrentes import generar_pendientes_seguro
from app.facturacion.models import Sucursal
from app.facturacion.timezone_helper import get_today
from app.inventario.models import StockUbicacion
from app.inventario.services import calcular_alertas


class ConsultaInvalida(ValueError):
    """Parámetros que Claude puede corregir; el mensaje se le devuelve tal cual."""


_RE_MES = re.compile(r"^(\d{4})-(\d{2})$")


def _mes(valor, nombre="mes"):
    """'AAAA-MM' estricto. parse_mes cae al mes actual en silencio, y aquí eso
    haría que Claude reportara el mes equivocado sin enterarse."""
    m = _RE_MES.match((valor or "").strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ConsultaInvalida(f"{nombre} debe tener formato AAAA-MM, p. ej. 2026-03")
    return int(m.group(1)), int(m.group(2))


def _fecha(valor, nombre):
    try:
        return date.fromisoformat((valor or "").strip())
    except ValueError as error:
        raise ConsultaInvalida(f"{nombre} debe tener formato AAAA-MM-DD") from error


def _r(valor):
    return round(valor or 0.0, 2)


def _sucursales(tenant_id):
    return {
        s.id: s.nombre
        for s in Sucursal.query.filter_by(tenant_id=tenant_id).all()
    }


# ── Finanzas ──

def resumen_mes(tenant_id, mes):
    year, month = _mes(mes)
    resumen = calcular_resumen_mensual(tenant_id, year, month)
    # El balance día por día es largo y para eso está ventas_del_dia.
    resumen.pop("balance_diario", None)
    return resumen


_METRICAS_COMPARABLES = (
    "total_ingresos", "ingresos_efectivo", "ingresos_banco",
    "gastos_fijos", "gastos_variables", "impuestos",
    "total_pagos_doctores", "total_comisiones_bancarias",
    "total_egresos", "utilidad_neta",
)


def comparar_meses(tenant_id, mes_a, mes_b):
    ya, ma = _mes(mes_a, "mes_a")
    yb, mb = _mes(mes_b, "mes_b")
    a = calcular_resumen_mensual(tenant_id, ya, ma)
    b = calcular_resumen_mensual(tenant_id, yb, mb)
    comparacion = {}
    for clave in _METRICAS_COMPARABLES:
        va, vb = a[clave], b[clave]
        diferencia = _r(vb - va)
        comparacion[clave] = {
            a["mes"]: va,
            b["mes"]: vb,
            "diferencia": diferencia,
            "variacion_pct": round(diferencia / va * 100, 1) if va else None,
        }
    return {
        "mes_a": a["mes"],
        "mes_b": b["mes"],
        "nota": "diferencia = mes_b - mes_a; variacion_pct es relativa a mes_a",
        "metricas": comparacion,
    }


def ventas_del_dia(tenant_id, fecha=None):
    dia = _fecha(fecha, "fecha") if fecha else get_today()
    ingresos = Ingreso.query.options(
        joinedload(Ingreso.metodo_pago),
        joinedload(Ingreso.ticket),
    ).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.fecha == dia,
    ).all()

    sucursales = _sucursales(tenant_id)
    total = 0.0
    por_sucursal = defaultdict(float)
    por_metodo = defaultdict(float)
    # Un cobro (ticket) puede traer varios tratamientos: cuenta cobros, no filas.
    cobros = set()
    for i in ingresos:
        venta, _ = venta_ajustada(i)
        total += venta
        por_sucursal[sucursales.get(i.sucursal_id, "Sin sucursal")] += venta
        por_metodo[i.metodo_pago.nombre if i.metodo_pago else "Sin método"] += venta
        cobros.add(("ticket", i.ticket_id) if i.ticket_id else ("ingreso", i.id))

    return {
        "fecha": dia.isoformat(),
        "ventas": _r(total),
        "cobros": len(cobros),
        "tratamientos_cobrados": len(ingresos),
        "por_sucursal": {k: _r(v) for k, v in sorted(por_sucursal.items())},
        "por_metodo_pago": {k: _r(v) for k, v in sorted(por_metodo.items())},
    }


def _nombre_concepto(gasto):
    if gasto.concepto:
        return gasto.concepto.nombre
    return gasto.concepto_nombre or "Sin concepto"


def gastos_principales(tenant_id, desde, hasta, limite=10):
    inicio, fin = _fecha(desde, "desde"), _fecha(hasta, "hasta")
    if inicio > fin:
        raise ConsultaInvalida("desde no puede ser posterior a hasta")
    limite = max(1, min(int(limite or 10), 50))
    generar_pendientes_seguro(tenant_id)
    gastos = GastoOperativo.query.options(
        joinedload(GastoOperativo.concepto),
    ).filter(
        GastoOperativo.tenant_id == tenant_id,
        GastoOperativo.fecha >= inicio,
        GastoOperativo.fecha <= fin,
    ).all()

    montos = defaultdict(float)
    movimientos = defaultdict(int)
    for gasto in gastos:
        nombre = _nombre_concepto(gasto)
        montos[nombre] += gasto.monto or 0.0
        movimientos[nombre] += 1
    total = sum(montos.values())
    ranking = sorted(montos.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "desde": inicio.isoformat(),
        "hasta": fin.isoformat(),
        "total_gastos": _r(total),
        "conceptos": [
            {
                "concepto": nombre,
                "monto": _r(monto),
                "pct_del_total": round(monto / total * 100, 1) if total else 0,
                "movimientos": movimientos[nombre],
            }
            for nombre, monto in ranking[:limite]
        ],
        "conceptos_totales": len(ranking),
    }


def gasto_por_concepto(tenant_id, concepto, anio=None):
    texto = (concepto or "").strip()
    if not texto:
        raise ConsultaInvalida("Indica el concepto a buscar")
    anio = int(anio) if anio else get_today().year
    generar_pendientes_seguro(tenant_id)

    patron = f"%{texto}%"
    conceptos = GastoConcepto.query.filter(
        GastoConcepto.tenant_id == tenant_id,
        GastoConcepto.nombre.ilike(patron),
    ).all()
    ids = [c.id for c in conceptos]
    condicion = GastoOperativo.concepto_nombre.ilike(patron)
    if ids:
        condicion = condicion | GastoOperativo.concepto_id.in_(ids)
    gastos = GastoOperativo.query.options(
        joinedload(GastoOperativo.concepto),
    ).filter(
        GastoOperativo.tenant_id == tenant_id,
        GastoOperativo.fecha >= date(anio, 1, 1),
        GastoOperativo.fecha <= date(anio, 12, 31),
        condicion,
    ).all()

    if not gastos:
        disponibles = sorted({
            c.nombre for c in GastoConcepto.query.filter_by(tenant_id=tenant_id).all()
        })
        return {
            "concepto_buscado": texto,
            "anio": anio,
            "total": 0,
            "encontrado": False,
            "conceptos_disponibles": disponibles,
        }

    por_concepto = defaultdict(lambda: defaultdict(float))
    for gasto in gastos:
        por_concepto[_nombre_concepto(gasto)][gasto.fecha.month] += gasto.monto or 0.0
    detalle = []
    for nombre, meses in sorted(por_concepto.items()):
        detalle.append({
            "concepto": nombre,
            "total": _r(sum(meses.values())),
            "por_mes": {f"{anio}-{m:02d}": _r(v) for m, v in sorted(meses.items())},
        })
    return {
        "concepto_buscado": texto,
        "anio": anio,
        "encontrado": True,
        "total": _r(sum(d["total"] for d in detalle)),
        "conceptos": detalle,
    }


# ── Inventario ──

def inventario_bajo(tenant_id):
    alertas = calcular_alertas(tenant_id=tenant_id)
    bajo = [
        {
            "material": a["material_nombre"],
            "ubicacion": a["ubicacion"],
            "cantidad": a["cantidad"],
            "minimo": a["minimo"],
        }
        for a in alertas["bajo"]
    ]

    totales = defaultdict(int)
    for su in StockUbicacion.query.filter_by(tenant_id=tenant_id).all():
        totales[su.material_id] += su.cantidad or 0
    sin_existencia = sorted(
        m.nombre
        for m in Material.query.filter_by(tenant_id=tenant_id, en_inventario=True).all()
        if totales.get(m.id, 0) <= 0
    )
    return {
        "bajo_minimo": sorted(bajo, key=lambda x: (x["material"] or "", x["ubicacion"])),
        "sin_existencia": sin_existencia,
        "nota": "bajo_minimo es por ubicación; sin_existencia suma todas las ubicaciones",
    }


# ── Cobranza ──

def pagos_vencidos(tenant_id):
    """Planes aprobados con parcialidades cuya fecha ya pasó y no están cubiertas.

    La pantalla de cobranza no usa este semáforo (marca "sin pagos recientes"
    a los 45 días); aquí se cuenta contra el calendario porque es la pregunta
    que hace el admin: quién debe, cuánto y desde cuándo.
    """
    hoy = get_today()
    filas = PagoProgramado.query.join(
        Cotizacion, PagoProgramado.cotizacion_id == Cotizacion.id,
    ).filter(
        PagoProgramado.tenant_id == tenant_id,
        Cotizacion.tenant_id == tenant_id,
        Cotizacion.estatus == "aprobada",
        PagoProgramado.fecha_vencimiento < hoy,
        PagoProgramado.estatus != "pagado",
    ).all()

    por_cotizacion = defaultdict(list)
    for fila in filas:
        if (fila.monto_programado or 0) - (fila.monto_pagado or 0) > TOLERANCIA:
            por_cotizacion[fila.cotizacion_id].append(fila)
    if not por_cotizacion:
        return {"fecha": hoy.isoformat(), "total_vencido": 0, "pacientes": []}

    cotizaciones = {
        c.id: c
        for c in Cotizacion.query.options(joinedload(Cotizacion.paciente)).filter(
            Cotizacion.tenant_id == tenant_id,
            Cotizacion.id.in_(list(por_cotizacion)),
        ).all()
    }
    resultado = []
    for cot_id, vencidas in por_cotizacion.items():
        cot = cotizaciones[cot_id]
        monto = sum(f.monto_programado - f.monto_pagado for f in vencidas)
        mas_vieja = min(f.fecha_vencimiento for f in vencidas)
        resultado.append({
            "paciente": cot.paciente.nombre if cot.paciente else None,
            "folio": cot.folio,
            "monto_vencido": _r(monto),
            "dias_atraso": (hoy - mas_vieja).days,
            "parcialidades_vencidas": len(vencidas),
        })
    resultado.sort(key=lambda x: (-x["dias_atraso"], -x["monto_vencido"]))
    return {
        "fecha": hoy.isoformat(),
        "total_vencido": _r(sum(r["monto_vencido"] for r in resultado)),
        "pacientes": resultado,
    }
