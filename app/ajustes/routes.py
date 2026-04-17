from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.ajustes.models import (
    Especialista,
    MetodoPago,
    GastoConcepto,
    EstrategiaMarketing,
    DistribucionConfig,
)
from app.ajustes.schemas import (
    EspecialistaSchema,
    MetodoPagoSchema,
    GastoConceptoSchema,
    EstrategiaMarketingSchema,
    DistribucionConfigSchema,
)

ajustes_bp = Blueprint("ajustes", __name__, url_prefix="/api/v1/ajustes")


# ── Generic CRUD helper ──

def _crud_routes(model, schema_cls, name):
    """Returns (list, create, update, delete) route functions."""

    def listar():
        items = model.query.filter_by(tenant_id=g.tenant_id).all()
        return jsonify(schema_cls(many=True).dump(items))

    def crear():
        schema = schema_cls()
        data = schema.load(request.get_json())
        item = model(tenant_id=g.tenant_id, **data)
        db.session.add(item)
        db.session.commit()
        return jsonify(schema.dump(item)), 201

    def actualizar(item_id):
        item = model.query.filter_by(
            id=item_id, tenant_id=g.tenant_id
        ).first_or_404()
        schema = schema_cls(partial=True)
        data = schema.load(request.get_json())
        for key, value in data.items():
            setattr(item, key, value)
        db.session.commit()
        return jsonify(schema_cls().dump(item))

    def eliminar(item_id):
        item = model.query.filter_by(
            id=item_id, tenant_id=g.tenant_id
        ).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return jsonify({"message": f"{name} eliminado"})

    return listar, crear, actualizar, eliminar


# ── Especialistas ──

_esp_list, _esp_create, _esp_update, _esp_delete = _crud_routes(
    Especialista, EspecialistaSchema, "Especialista"
)

ajustes_bp.add_url_rule(
    "/especialistas", "listar_especialistas",
    require_auth(_esp_list), methods=["GET"]
)
ajustes_bp.add_url_rule(
    "/especialistas", "crear_especialista",
    require_auth(require_role("admin")(_esp_create)), methods=["POST"]
)
ajustes_bp.add_url_rule(
    "/especialistas/<int:item_id>", "actualizar_especialista",
    require_auth(require_role("admin")(_esp_update)), methods=["PUT"]
)
ajustes_bp.add_url_rule(
    "/especialistas/<int:item_id>", "eliminar_especialista",
    require_auth(require_role("admin")(_esp_delete)), methods=["DELETE"]
)


# ── Métodos de Pago ──

_mp_list, _mp_create, _mp_update, _mp_delete = _crud_routes(
    MetodoPago, MetodoPagoSchema, "Método de pago"
)

ajustes_bp.add_url_rule(
    "/metodos-pago", "listar_metodos_pago",
    require_auth(_mp_list), methods=["GET"]
)
ajustes_bp.add_url_rule(
    "/metodos-pago", "crear_metodo_pago",
    require_auth(require_role("admin")(_mp_create)), methods=["POST"]
)
ajustes_bp.add_url_rule(
    "/metodos-pago/<int:item_id>", "actualizar_metodo_pago",
    require_auth(require_role("admin")(_mp_update)), methods=["PUT"]
)
ajustes_bp.add_url_rule(
    "/metodos-pago/<int:item_id>", "eliminar_metodo_pago",
    require_auth(require_role("admin")(_mp_delete)), methods=["DELETE"]
)


# ── Conceptos de Gasto ──

_gc_list, _gc_create, _gc_update, _gc_delete = _crud_routes(
    GastoConcepto, GastoConceptoSchema, "Concepto de gasto"
)

ajustes_bp.add_url_rule(
    "/gastos-conceptos", "listar_gastos_conceptos",
    require_auth(_gc_list), methods=["GET"]
)
ajustes_bp.add_url_rule(
    "/gastos-conceptos", "crear_gasto_concepto",
    require_auth(require_role("admin")(_gc_create)), methods=["POST"]
)
ajustes_bp.add_url_rule(
    "/gastos-conceptos/<int:item_id>", "actualizar_gasto_concepto",
    require_auth(require_role("admin")(_gc_update)), methods=["PUT"]
)
ajustes_bp.add_url_rule(
    "/gastos-conceptos/<int:item_id>", "eliminar_gasto_concepto",
    require_auth(require_role("admin")(_gc_delete)), methods=["DELETE"]
)


# ── Estrategias Marketing ──

_em_list, _em_create, _em_update, _em_delete = _crud_routes(
    EstrategiaMarketing, EstrategiaMarketingSchema, "Estrategia"
)

ajustes_bp.add_url_rule(
    "/estrategias", "listar_estrategias",
    require_auth(_em_list), methods=["GET"]
)
ajustes_bp.add_url_rule(
    "/estrategias", "crear_estrategia",
    require_auth(require_role("admin")(_em_create)), methods=["POST"]
)
ajustes_bp.add_url_rule(
    "/estrategias/<int:item_id>", "actualizar_estrategia",
    require_auth(require_role("admin")(_em_update)), methods=["PUT"]
)
ajustes_bp.add_url_rule(
    "/estrategias/<int:item_id>", "eliminar_estrategia",
    require_auth(require_role("admin")(_em_delete)), methods=["DELETE"]
)


# ── Distribución de Ingresos ──

@ajustes_bp.route("/distribucion", methods=["GET"])
@require_auth
def obtener_distribucion():
    dist = DistribucionConfig.query.filter_by(tenant_id=g.tenant_id).first()
    if not dist:
        return jsonify({
            "pct_sueldo": 50, "pct_bonos": 10, "pct_mcmp": 20,
            "pct_fondo_emergencia": 10, "pct_marketing": 10,
        })
    return jsonify(DistribucionConfigSchema().dump(dist))


@ajustes_bp.route("/distribucion", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_distribucion():
    schema = DistribucionConfigSchema()
    data = schema.load(request.get_json())

    dist = DistribucionConfig.query.filter_by(tenant_id=g.tenant_id).first()
    if not dist:
        dist = DistribucionConfig(tenant_id=g.tenant_id)
        db.session.add(dist)

    for key, value in data.items():
        setattr(dist, key, value)

    db.session.commit()
    return jsonify(schema.dump(dist))
