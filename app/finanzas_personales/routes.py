from flask import Blueprint, request, jsonify, g
from marshmallow import ValidationError

from app.extensions import db
from app.middleware.tenant import require_auth
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso,
    IngresoPersonal, GastoPersonal,
    PresupuestoCategoria, MetaAhorro,
)
from app.finanzas_personales.schemas import (
    CategoriaPersonalSchema, FuenteIngresoSchema,
    IngresoPersonalSchema, GastoPersonalSchema,
    PresupuestoCategoriaSchema, MetaAhorroSchema,
    DashboardQuerySchema,
)
from app.finanzas_personales.services import (
    seed_defaults_for_user, build_dashboard_summary,
    list_movements, build_category_detail, _month_bounds,
)


finanzas_personales_bp = Blueprint(
    "finanzas_personales", __name__, url_prefix="/api/v1/finanzas-personales",
)


def _scope():
    return g.tenant_id, g.current_user.id


# Categorias

@finanzas_personales_bp.route("/categorias", methods=["GET"])
@require_auth
def listar_categorias():
    tenant_id, user_id = _scope()
    seed_defaults_for_user(tenant_id, user_id)
    cats = CategoriaPersonal.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(CategoriaPersonal.orden, CategoriaPersonal.nombre).all()
    return jsonify(CategoriaPersonalSchema(many=True).dump(cats))


@finanzas_personales_bp.route("/categorias", methods=["POST"])
@require_auth
def crear_categoria():
    tenant_id, user_id = _scope()
    try:
        data = CategoriaPersonalSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    cat = CategoriaPersonal(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(cat)
    db.session.commit()
    return jsonify(CategoriaPersonalSchema().dump(cat)), 201


@finanzas_personales_bp.route("/categorias/<int:cat_id>", methods=["PUT"])
@require_auth
def actualizar_categoria(cat_id):
    tenant_id, user_id = _scope()
    cat = CategoriaPersonal.query.filter_by(
        id=cat_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = CategoriaPersonalSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(cat, k, v)
    db.session.commit()
    return jsonify(CategoriaPersonalSchema().dump(cat))


@finanzas_personales_bp.route("/categorias/<int:cat_id>", methods=["DELETE"])
@require_auth
def eliminar_categoria(cat_id):
    tenant_id, user_id = _scope()
    cat = CategoriaPersonal.query.filter_by(
        id=cat_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    cat.activo = False
    db.session.commit()
    return jsonify({"message": "Categoria desactivada"})


# Fuentes

@finanzas_personales_bp.route("/fuentes", methods=["GET"])
@require_auth
def listar_fuentes():
    tenant_id, user_id = _scope()
    seed_defaults_for_user(tenant_id, user_id)
    fuentes = FuenteIngreso.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(FuenteIngreso.orden, FuenteIngreso.nombre).all()
    return jsonify(FuenteIngresoSchema(many=True).dump(fuentes))


@finanzas_personales_bp.route("/fuentes", methods=["POST"])
@require_auth
def crear_fuente():
    tenant_id, user_id = _scope()
    try:
        data = FuenteIngresoSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    f = FuenteIngreso(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(f)
    db.session.commit()
    return jsonify(FuenteIngresoSchema().dump(f)), 201


@finanzas_personales_bp.route("/fuentes/<int:f_id>", methods=["PUT"])
@require_auth
def actualizar_fuente(f_id):
    tenant_id, user_id = _scope()
    f = FuenteIngreso.query.filter_by(
        id=f_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = FuenteIngresoSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(f, k, v)
    db.session.commit()
    return jsonify(FuenteIngresoSchema().dump(f))


@finanzas_personales_bp.route("/fuentes/<int:f_id>", methods=["DELETE"])
@require_auth
def eliminar_fuente(f_id):
    tenant_id, user_id = _scope()
    f = FuenteIngreso.query.filter_by(
        id=f_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    f.activo = False
    db.session.commit()
    return jsonify({"message": "Fuente desactivada"})


# Ingresos / Gastos

def _parse_year_month():
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except (TypeError, ValueError):
        return None, None


@finanzas_personales_bp.route("/ingresos", methods=["GET"])
@require_auth
def listar_ingresos():
    tenant_id, user_id = _scope()
    year, month = _parse_year_month()
    q = IngresoPersonal.query.filter_by(tenant_id=tenant_id, user_id=user_id)
    if year and month:
        s, e = _month_bounds(year, month)
        q = q.filter(IngresoPersonal.fecha >= s, IngresoPersonal.fecha <= e)
    rows = q.order_by(IngresoPersonal.fecha.desc(), IngresoPersonal.id.desc()).all()
    return jsonify(IngresoPersonalSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/ingresos", methods=["POST"])
@require_auth
def crear_ingreso():
    tenant_id, user_id = _scope()
    try:
        data = IngresoPersonalSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    if data.get("fuente_id"):
        owns = FuenteIngreso.query.filter_by(
            id=data["fuente_id"], tenant_id=tenant_id, user_id=user_id,
        ).first()
        if not owns:
            return jsonify({"errors": {"fuente_id": ["Fuente no encontrada"]}}), 400
    ing = IngresoPersonal(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(ing)
    db.session.commit()
    return jsonify(IngresoPersonalSchema().dump(ing)), 201


@finanzas_personales_bp.route("/ingresos/<int:ing_id>", methods=["PUT"])
@require_auth
def actualizar_ingreso(ing_id):
    tenant_id, user_id = _scope()
    ing = IngresoPersonal.query.filter_by(
        id=ing_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = IngresoPersonalSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(ing, k, v)
    db.session.commit()
    return jsonify(IngresoPersonalSchema().dump(ing))


@finanzas_personales_bp.route("/ingresos/<int:ing_id>", methods=["DELETE"])
@require_auth
def eliminar_ingreso(ing_id):
    tenant_id, user_id = _scope()
    ing = IngresoPersonal.query.filter_by(
        id=ing_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(ing)
    db.session.commit()
    return jsonify({"message": "Ingreso eliminado"})


@finanzas_personales_bp.route("/gastos", methods=["GET"])
@require_auth
def listar_gastos():
    tenant_id, user_id = _scope()
    year, month = _parse_year_month()
    q = GastoPersonal.query.filter_by(tenant_id=tenant_id, user_id=user_id)
    if year and month:
        s, e = _month_bounds(year, month)
        q = q.filter(GastoPersonal.fecha >= s, GastoPersonal.fecha <= e)
    rows = q.order_by(GastoPersonal.fecha.desc(), GastoPersonal.id.desc()).all()
    return jsonify(GastoPersonalSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/gastos", methods=["POST"])
@require_auth
def crear_gasto():
    tenant_id, user_id = _scope()
    try:
        data = GastoPersonalSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    if data.get("categoria_id"):
        owns = CategoriaPersonal.query.filter_by(
            id=data["categoria_id"], tenant_id=tenant_id, user_id=user_id,
        ).first()
        if not owns:
            return jsonify({"errors": {"categoria_id": ["Categoria no encontrada"]}}), 400
    gas = GastoPersonal(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(gas)
    db.session.commit()
    return jsonify(GastoPersonalSchema().dump(gas)), 201


@finanzas_personales_bp.route("/gastos/<int:gas_id>", methods=["PUT"])
@require_auth
def actualizar_gasto(gas_id):
    tenant_id, user_id = _scope()
    gas = GastoPersonal.query.filter_by(
        id=gas_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = GastoPersonalSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(gas, k, v)
    db.session.commit()
    return jsonify(GastoPersonalSchema().dump(gas))


@finanzas_personales_bp.route("/gastos/<int:gas_id>", methods=["DELETE"])
@require_auth
def eliminar_gasto(gas_id):
    tenant_id, user_id = _scope()
    gas = GastoPersonal.query.filter_by(
        id=gas_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(gas)
    db.session.commit()
    return jsonify({"message": "Gasto eliminado"})


# Dashboard / agregados

@finanzas_personales_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    tenant_id, user_id = _scope()
    try:
        q = DashboardQuerySchema().load(request.args)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    seed_defaults_for_user(tenant_id, user_id)
    return jsonify(build_dashboard_summary(tenant_id, user_id, q["year"], q["month"]))


@finanzas_personales_bp.route("/movimientos", methods=["GET"])
@require_auth
def movimientos():
    tenant_id, user_id = _scope()
    try:
        q = DashboardQuerySchema().load(request.args)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    kind = request.args.get("kind")
    if kind not in (None, "ingreso", "gasto"):
        kind = None
    return jsonify(list_movements(tenant_id, user_id, q["year"], q["month"], kind=kind))


@finanzas_personales_bp.route("/categorias/<int:cat_id>/detalle", methods=["GET"])
@require_auth
def categoria_detalle(cat_id):
    tenant_id, user_id = _scope()
    try:
        q = DashboardQuerySchema().load(request.args)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    detail = build_category_detail(tenant_id, user_id, cat_id, q["year"], q["month"])
    if not detail:
        return jsonify({"error": "Categoria no encontrada"}), 404
    return jsonify(detail)


# Presupuestos

@finanzas_personales_bp.route("/presupuestos", methods=["GET"])
@require_auth
def listar_presupuestos():
    tenant_id, user_id = _scope()
    rows = PresupuestoCategoria.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(PresupuestoCategoria.vigente_desde.desc()).all()
    return jsonify(PresupuestoCategoriaSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/presupuestos", methods=["POST"])
@require_auth
def crear_presupuesto():
    tenant_id, user_id = _scope()
    try:
        data = PresupuestoCategoriaSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    owns = CategoriaPersonal.query.filter_by(
        id=data["categoria_id"], tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not owns:
        return jsonify({"errors": {"categoria_id": ["Categoria no encontrada"]}}), 400
    p = PresupuestoCategoria(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(p)
    db.session.commit()
    return jsonify(PresupuestoCategoriaSchema().dump(p)), 201


@finanzas_personales_bp.route("/presupuestos/<int:p_id>", methods=["PUT"])
@require_auth
def actualizar_presupuesto(p_id):
    tenant_id, user_id = _scope()
    p = PresupuestoCategoria.query.filter_by(
        id=p_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = PresupuestoCategoriaSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(p, k, v)
    db.session.commit()
    return jsonify(PresupuestoCategoriaSchema().dump(p))


@finanzas_personales_bp.route("/presupuestos/<int:p_id>", methods=["DELETE"])
@require_auth
def eliminar_presupuesto(p_id):
    tenant_id, user_id = _scope()
    p = PresupuestoCategoria.query.filter_by(
        id=p_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Presupuesto eliminado"})


# Metas

@finanzas_personales_bp.route("/metas", methods=["GET"])
@require_auth
def listar_metas():
    tenant_id, user_id = _scope()
    rows = MetaAhorro.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(MetaAhorro.created_at.desc()).all()
    return jsonify(MetaAhorroSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/metas", methods=["POST"])
@require_auth
def crear_meta():
    tenant_id, user_id = _scope()
    try:
        data = MetaAhorroSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    m = MetaAhorro(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(m)
    db.session.commit()
    return jsonify(MetaAhorroSchema().dump(m)), 201


@finanzas_personales_bp.route("/metas/<int:m_id>", methods=["PUT"])
@require_auth
def actualizar_meta(m_id):
    tenant_id, user_id = _scope()
    m = MetaAhorro.query.filter_by(
        id=m_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = MetaAhorroSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(m, k, v)
    db.session.commit()
    return jsonify(MetaAhorroSchema().dump(m))


@finanzas_personales_bp.route("/metas/<int:m_id>", methods=["DELETE"])
@require_auth
def eliminar_meta(m_id):
    tenant_id, user_id = _scope()
    m = MetaAhorro.query.filter_by(
        id=m_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(m)
    db.session.commit()
    return jsonify({"message": "Meta eliminada"})
