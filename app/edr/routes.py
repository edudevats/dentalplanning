from datetime import date
from flask import Blueprint, request, jsonify, g
from sqlalchemy import extract
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.edr.models import Ingreso, GastoOperativo, PagoDoctor
from app.edr.schemas import IngresoSchema, GastoOperativoSchema, PagoDoctorSchema
from app.ajustes.models import MetodoPago, Especialista

edr_bp = Blueprint("edr", __name__, url_prefix="/api/v1/edr")


def _parse_mes(mes_str):
    """Parse 'YYYY-MM' to (year, month)."""
    if not mes_str:
        today = date.today()
        return today.year, today.month
    try:
        parts = mes_str.split("-")
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except (IndexError, ValueError):
        today = date.today()
        return today.year, today.month


def _enrich_ingreso(ingreso):
    data = IngresoSchema().dump(ingreso)
    data["especialista_nombre"] = ingreso.especialista.nombre if ingreso.especialista else None
    data["metodo_pago_nombre"] = ingreso.metodo_pago.nombre if ingreso.metodo_pago else None
    data["estrategia_nombre"] = ingreso.estrategia.nombre if ingreso.estrategia else None
    return data


# ── INGRESOS ──

@edr_bp.route("/ingresos", methods=["GET"])
@require_auth
def listar_ingresos():
    year, month = _parse_mes(request.args.get("mes"))
    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).order_by(Ingreso.fecha).all()

    return jsonify([_enrich_ingreso(i) for i in ingresos])


@edr_bp.route("/ingresos", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_ingreso():
    schema = IngresoSchema()
    data = schema.load(request.get_json() or {})

    # Auto-calculate commissions if metodo_pago or especialista provided
    if data.get("metodo_pago_id") and data.get("comision_bancaria", 0) == 0:
        mp = MetodoPago.query.filter_by(
            id=data["metodo_pago_id"], tenant_id=g.tenant_id
        ).first()
        if mp:
            data["comision_bancaria"] = round(data["monto"] * (mp.comision_pct / 100), 2)

    if data.get("especialista_id") and data.get("comision_doctor", 0) == 0:
        esp = Especialista.query.filter_by(
            id=data["especialista_id"], tenant_id=g.tenant_id
        ).first()
        if esp:
            data["comision_doctor"] = round(data["monto"] * (esp.comision_pct / 100), 2)

    ingreso = Ingreso(tenant_id=g.tenant_id, **data)
    db.session.add(ingreso)
    db.session.commit()
    return jsonify(_enrich_ingreso(ingreso)), 201


@edr_bp.route("/ingresos/<int:ingreso_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_ingreso(ingreso_id):
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()

    schema = IngresoSchema(partial=True)
    data = schema.load(request.get_json() or {})
    for key, value in data.items():
        setattr(ingreso, key, value)
    db.session.commit()
    return jsonify(_enrich_ingreso(ingreso))


@edr_bp.route("/ingresos/<int:ingreso_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_ingreso(ingreso_id):
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(ingreso)
    db.session.commit()
    return jsonify({"message": "Ingreso eliminado"})


# ── GASTOS OPERATIVOS ──

@edr_bp.route("/gastos", methods=["GET"])
@require_auth
def listar_gastos():
    year, month = _parse_mes(request.args.get("mes"))
    gastos = GastoOperativo.query.filter(
        GastoOperativo.tenant_id == g.tenant_id,
        extract("year", GastoOperativo.fecha) == year,
        extract("month", GastoOperativo.fecha) == month,
    ).order_by(GastoOperativo.fecha).all()

    return jsonify(GastoOperativoSchema(many=True).dump(gastos))


@edr_bp.route("/gastos", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_gasto():
    schema = GastoOperativoSchema()
    data = schema.load(request.get_json() or {})
    gasto = GastoOperativo(tenant_id=g.tenant_id, **data)
    db.session.add(gasto)
    db.session.commit()
    return jsonify(schema.dump(gasto)), 201


@edr_bp.route("/gastos/<int:gasto_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_gasto(gasto_id):
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=g.tenant_id
    ).first_or_404()
    schema = GastoOperativoSchema(partial=True)
    data = schema.load(request.get_json() or {})
    for key, value in data.items():
        setattr(gasto, key, value)
    db.session.commit()
    return jsonify(GastoOperativoSchema().dump(gasto))


@edr_bp.route("/gastos/<int:gasto_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_gasto(gasto_id):
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(gasto)
    db.session.commit()
    return jsonify({"message": "Gasto eliminado"})


# ── PAGOS A DOCTORES ──

@edr_bp.route("/pagos-doctores", methods=["GET"])
@require_auth
def listar_pagos():
    year, month = _parse_mes(request.args.get("mes"))
    pagos = PagoDoctor.query.filter(
        PagoDoctor.tenant_id == g.tenant_id,
        extract("year", PagoDoctor.fecha) == year,
        extract("month", PagoDoctor.fecha) == month,
    ).order_by(PagoDoctor.fecha).all()

    result = []
    for p in pagos:
        data = PagoDoctorSchema().dump(p)
        data["especialista_nombre"] = p.especialista.nombre if p.especialista else None
        result.append(data)
    return jsonify(result)


@edr_bp.route("/pagos-doctores", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_pago():
    schema = PagoDoctorSchema()
    data = schema.load(request.get_json() or {})
    pago = PagoDoctor(tenant_id=g.tenant_id, **data)
    db.session.add(pago)
    db.session.commit()
    return jsonify(schema.dump(pago)), 201


@edr_bp.route("/pagos-doctores/<int:pago_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_pago(pago_id):
    pago = PagoDoctor.query.filter_by(
        id=pago_id, tenant_id=g.tenant_id
    ).first_or_404()
    schema = PagoDoctorSchema(partial=True)
    data = schema.load(request.get_json() or {})
    for key, value in data.items():
        setattr(pago, key, value)
    db.session.commit()
    return jsonify(PagoDoctorSchema().dump(pago))


@edr_bp.route("/pagos-doctores/<int:pago_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_pago(pago_id):
    pago = PagoDoctor.query.filter_by(
        id=pago_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(pago)
    db.session.commit()
    return jsonify({"message": "Pago eliminado"})
