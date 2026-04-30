from __future__ import annotations
from calendar import monthrange
from datetime import date
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso,
    IngresoPersonal, GastoPersonal,
    PresupuestoCategoria,
)


DEFAULT_CATEGORIES = [
    {"nombre": "Comida",          "icon": "utensils",        "color": "#f59e0b", "orden": 1},
    {"nombre": "Transporte",      "icon": "car",             "color": "#0891b2", "orden": 2},
    {"nombre": "Vivienda",        "icon": "home",            "color": "#8b5cf6", "orden": 3},
    {"nombre": "Entretenimiento", "icon": "film",            "color": "#ec4899", "orden": 4},
    {"nombre": "Salud",           "icon": "heart-pulse",     "color": "#059669", "orden": 5},
    {"nombre": "Otros",           "icon": "more-horizontal", "color": "#f97316", "orden": 6},
]

DEFAULT_FUENTES = [
    {"nombre": "Salario",   "icon": "briefcase", "orden": 1},
    {"nombre": "Extras",    "icon": "sparkles",  "orden": 2},
    {"nombre": "Freelance", "icon": "laptop",    "orden": 3},
]


def seed_defaults_for_user(tenant_id: int, user_id: int) -> None:
    """Idempotent — only inserts categories/fuentes if user has none."""
    has_cats = db.session.query(CategoriaPersonal.id).filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not has_cats:
        for c in DEFAULT_CATEGORIES:
            db.session.add(CategoriaPersonal(tenant_id=tenant_id, user_id=user_id, **c))

    has_fuentes = db.session.query(FuenteIngreso.id).filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not has_fuentes:
        for f in DEFAULT_FUENTES:
            db.session.add(FuenteIngreso(tenant_id=tenant_id, user_id=user_id, **f))

    db.session.commit()


def _month_bounds(year: int, month: int):
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start, end


def _prev_month(year: int, month: int):
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _money(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def build_dashboard_summary(tenant_id: int, user_id: int, year: int, month: int) -> dict:
    start, end = _month_bounds(year, month)

    ingresos_total = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= start, IngresoPersonal.fecha <= end,
    ).scalar())
    gastos_total = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
    ).scalar())

    balance = ingresos_total - gastos_total
    ahorro_pct = round((balance / ingresos_total) * 100) if ingresos_total else 0

    py, pm = _prev_month(year, month)
    pstart, pend = _month_bounds(py, pm)
    prev_ing = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= pstart, IngresoPersonal.fecha <= pend,
    ).scalar())
    prev_gas = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= pstart, GastoPersonal.fecha <= pend,
    ).scalar())
    trend_ing = round(((ingresos_total - prev_ing) / prev_ing) * 100) if prev_ing else 0
    trend_gas = round(((gastos_total - prev_gas) / prev_gas) * 100) if prev_gas else 0

    cat_rows = db.session.query(
        CategoriaPersonal.id, CategoriaPersonal.nombre, CategoriaPersonal.icon,
        CategoriaPersonal.color, func.coalesce(func.sum(GastoPersonal.monto), 0),
    ).outerjoin(
        GastoPersonal,
        (GastoPersonal.categoria_id == CategoriaPersonal.id)
        & (GastoPersonal.fecha >= start) & (GastoPersonal.fecha <= end)
        & (GastoPersonal.tenant_id == tenant_id) & (GastoPersonal.user_id == user_id),
    ).filter(
        CategoriaPersonal.tenant_id == tenant_id,
        CategoriaPersonal.user_id == user_id,
        CategoriaPersonal.activo.is_(True),
    ).group_by(CategoriaPersonal.id).all()

    by_cat = []
    for cid, nombre, icon, color, suma in cat_rows:
        v = _money(suma)
        if v <= 0:
            continue
        by_cat.append({
            "id": cid, "label": nombre, "icon": icon, "color": color,
            "value": v,
            "pct": round((v / gastos_total) * 100) if gastos_total else 0,
        })
    by_cat.sort(key=lambda c: c["value"], reverse=True)

    months_back = []
    yy, mm = year, month
    for _ in range(6):
        months_back.append((yy, mm))
        yy, mm = _prev_month(yy, mm)
    months_back.reverse()
    month_names_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    history6m = []
    for yy, mm in months_back:
        ms, me = _month_bounds(yy, mm)
        i = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
            IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
            IngresoPersonal.fecha >= ms, IngresoPersonal.fecha <= me,
        ).scalar())
        g = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
            GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
            GastoPersonal.fecha >= ms, GastoPersonal.fecha <= me,
        ).scalar())
        history6m.append({"name": month_names_es[mm - 1], "ingresos": i, "gastos": g})

    recent = []
    ing_q = db.session.query(IngresoPersonal, FuenteIngreso).outerjoin(
        FuenteIngreso, IngresoPersonal.fuente_id == FuenteIngreso.id,
    ).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= start, IngresoPersonal.fecha <= end,
    ).order_by(IngresoPersonal.fecha.desc(), IngresoPersonal.id.desc()).limit(6).all()
    for ing, fuente in ing_q:
        recent.append({
            "id": f"i{ing.id}", "kind": "ingreso",
            "fecha": ing.fecha.isoformat(), "concepto": ing.concepto,
            "monto": _money(ing.monto),
            "label": fuente.nombre if fuente else "Ingreso",
            "icon": fuente.icon if fuente else "trending-up",
            "color": "#059669",
        })
    gas_q = db.session.query(GastoPersonal, CategoriaPersonal).outerjoin(
        CategoriaPersonal, GastoPersonal.categoria_id == CategoriaPersonal.id,
    ).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
    ).order_by(GastoPersonal.fecha.desc(), GastoPersonal.id.desc()).limit(6).all()
    for gas, cat in gas_q:
        recent.append({
            "id": f"g{gas.id}", "kind": "gasto",
            "fecha": gas.fecha.isoformat(), "concepto": gas.concepto,
            "monto": _money(gas.monto),
            "label": cat.nombre if cat else "Gasto",
            "icon": cat.icon if cat else "circle",
            "color": cat.color if cat else "#94a3b8",
        })
    recent.sort(key=lambda m: m["fecha"], reverse=True)
    recent = recent[:6]

    insight = _build_insight(balance=balance, ahorro_pct=ahorro_pct, by_cat=by_cat, prev_gas=prev_gas)

    return {
        "month": {"year": year, "month": month},
        "totals": {
            "ingresos": ingresos_total, "gastos": gastos_total,
            "balance": balance, "ahorroPct": ahorro_pct,
        },
        "trends": {"ingresos": trend_ing, "gastos": trend_gas},
        "byCat": by_cat,
        "history6m": history6m,
        "recent": recent,
        "insight": insight,
    }


def _build_insight(balance: float, ahorro_pct: int, by_cat: list, prev_gas: float) -> str:
    if balance <= 0:
        return "Estás gastando más de lo que ingresas. Revisa tus categorías más altas."
    top = by_cat[0] if by_cat else None
    if top and prev_gas > 0:
        return (
            f"Llevas ${balance:,.0f} ahorrados este mes ({ahorro_pct}% de tus ingresos). "
            f"Tu mayor gasto es {top['label']} (${top['value']:,.0f})."
        )
    return f"Llevas ${balance:,.0f} ahorrados este mes ({ahorro_pct}% de tus ingresos). Sigue así."


def list_movements(tenant_id: int, user_id: int, year: int, month: int,
                   kind: Optional[str] = None) -> list:
    """For the History screen. kind in (None, 'ingreso', 'gasto')."""
    start, end = _month_bounds(year, month)
    out = []
    if kind != "gasto":
        rows = db.session.query(IngresoPersonal, FuenteIngreso).outerjoin(
            FuenteIngreso, IngresoPersonal.fuente_id == FuenteIngreso.id,
        ).filter(
            IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
            IngresoPersonal.fecha >= start, IngresoPersonal.fecha <= end,
        ).all()
        for ing, fuente in rows:
            out.append({
                "id": f"i{ing.id}", "kind": "ingreso",
                "fecha": ing.fecha.isoformat(), "concepto": ing.concepto,
                "monto": _money(ing.monto),
                "label": fuente.nombre if fuente else "Ingreso",
                "icon": fuente.icon if fuente else "trending-up",
                "color": "#059669",
            })
    if kind != "ingreso":
        rows = db.session.query(GastoPersonal, CategoriaPersonal).outerjoin(
            CategoriaPersonal, GastoPersonal.categoria_id == CategoriaPersonal.id,
        ).filter(
            GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
            GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
        ).all()
        for gas, cat in rows:
            out.append({
                "id": f"g{gas.id}", "kind": "gasto",
                "fecha": gas.fecha.isoformat(), "concepto": gas.concepto,
                "monto": _money(gas.monto),
                "label": cat.nombre if cat else "Gasto",
                "icon": cat.icon if cat else "circle",
                "color": cat.color if cat else "#94a3b8",
            })
    out.sort(key=lambda m: m["fecha"], reverse=True)
    return out


def build_category_detail(tenant_id: int, user_id: int, categoria_id: int,
                          year: int, month: int) -> dict:
    cat = CategoriaPersonal.query.filter_by(
        id=categoria_id, tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not cat:
        return {}

    start, end = _month_bounds(year, month)
    movs_q = GastoPersonal.query.filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.categoria_id == categoria_id,
        GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
    ).order_by(GastoPersonal.fecha.desc()).all()

    movs = [{
        "id": f"g{m.id}", "kind": "gasto",
        "fecha": m.fecha.isoformat(), "concepto": m.concepto,
        "monto": _money(m.monto),
        "label": cat.nombre, "icon": cat.icon, "color": cat.color,
    } for m in movs_q]

    total = sum(m["monto"] for m in movs)
    days = (end - start).days + 1
    daily_avg = total / days if days else 0
    max_mov = max(movs, key=lambda m: m["monto"]) if movs else None

    months_back = []
    yy, mm = year, month
    for _ in range(6):
        months_back.append((yy, mm))
        yy, mm = _prev_month(yy, mm)
    months_back.reverse()
    month_names_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    history6m = []
    for yy, mm in months_back:
        ms, me = _month_bounds(yy, mm)
        s = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
            GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
            GastoPersonal.categoria_id == categoria_id,
            GastoPersonal.fecha >= ms, GastoPersonal.fecha <= me,
        ).scalar())
        history6m.append({"name": month_names_es[mm - 1], "ingresos": 0, "gastos": s})

    pres = PresupuestoCategoria.query.filter(
        PresupuestoCategoria.tenant_id == tenant_id,
        PresupuestoCategoria.user_id == user_id,
        PresupuestoCategoria.categoria_id == categoria_id,
        PresupuestoCategoria.vigente_desde <= end,
    ).order_by(PresupuestoCategoria.vigente_desde.desc()).first()

    return {
        "categoria": {"id": cat.id, "label": cat.nombre, "icon": cat.icon, "color": cat.color},
        "month": {"year": year, "month": month},
        "total": total,
        "promedioDiario": daily_avg,
        "max": max_mov,
        "movimientos": movs,
        "history6m": history6m,
        "presupuesto": _money(pres.monto_mensual) if pres else None,
    }
