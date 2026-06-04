from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.ajustes.models import (
    Especialista,
    MetodoPago,
    GastoConcepto,
    EstrategiaMarketing,
    DistribucionConfig,
    DistribucionCategoria,
    DIST_CATEGORIAS_DEFAULT,
)
from app.ajustes.schemas import (
    EspecialistaSchema,
    MetodoPagoSchema,
    GastoConceptoSchema,
    EstrategiaMarketingSchema,
    DistribucionConfigSchema,
    DistribucionCategoriaSchema,
    DistribucionBatchSchema,
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
        data = schema.load(request.get_json() or {})
        item = model(tenant_id=g.tenant_id, **data)
        db.session.add(item)
        db.session.commit()
        return jsonify(schema.dump(item)), 201

    def actualizar(item_id):
        item = model.query.filter_by(
            id=item_id, tenant_id=g.tenant_id
        ).first_or_404()
        schema = schema_cls(partial=True)
        data = schema.load(request.get_json() or {})
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


# ── Distribución de Ingresos (legacy 5-column API, kept for reports) ──

@ajustes_bp.route("/distribucion", methods=["GET"])
@require_auth
def obtener_distribucion():
    # Fuente ÚNICA: DistribucionCategoria. Se exponen las 5 categorías del
    # sistema como llaves pct_* para compatibilidad con consumidores legacy.
    cats = DistribucionCategoria.query.filter_by(
        tenant_id=g.tenant_id, es_sistema=True
    ).all()
    if not cats:
        _seed_categorias(g.tenant_id)
        cats = DistribucionCategoria.query.filter_by(
            tenant_id=g.tenant_id, es_sistema=True
        ).all()

    result = {d["clave"]: d["porcentaje"] for d in DIST_CATEGORIAS_DEFAULT}
    for c in cats:
        if c.clave:
            result[c.clave] = c.porcentaje
    return jsonify(result)


@ajustes_bp.route("/distribucion", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_distribucion():
    schema = DistribucionConfigSchema()
    data = schema.load(request.get_json() or {})

    # Escribir sobre las categorías del sistema (fuente única)
    cats = DistribucionCategoria.query.filter_by(
        tenant_id=g.tenant_id, es_sistema=True
    ).all()
    if not cats:
        _seed_categorias(g.tenant_id)
        cats = DistribucionCategoria.query.filter_by(
            tenant_id=g.tenant_id, es_sistema=True
        ).all()

    for c in cats:
        if c.clave in data:
            c.porcentaje = data[c.clave]

    # DistribucionConfig queda como espejo derivado de las categorías
    _sync_config_from_categorias(g.tenant_id)
    db.session.commit()
    return jsonify(data)


# ── Distribución — Categorías dinámicas ──

def _seed_categorias(tenant_id):
    """Create the 5 system categories from DistribucionConfig values."""
    dist = DistribucionConfig.query.filter_by(tenant_id=tenant_id).first()
    for d in DIST_CATEGORIAS_DEFAULT:
        pct = getattr(dist, d["clave"], d["porcentaje"]) if dist else d["porcentaje"]
        cat = DistribucionCategoria(
            tenant_id=tenant_id,
            nombre=d["nombre"],
            clave=d["clave"],
            color=d["color"],
            porcentaje=pct,
            es_sistema=True,
            sort_order=d["sort_order"],
        )
        db.session.add(cat)
    db.session.commit()


def _sync_config_from_categorias(tenant_id):
    """Keep DistribucionConfig in sync with the 5 system categories."""
    dist = DistribucionConfig.query.filter_by(tenant_id=tenant_id).first()
    if not dist:
        dist = DistribucionConfig(tenant_id=tenant_id)
        db.session.add(dist)

    cats = DistribucionCategoria.query.filter_by(
        tenant_id=tenant_id, es_sistema=True
    ).all()
    for cat in cats:
        if cat.clave:
            setattr(dist, cat.clave, cat.porcentaje)


@ajustes_bp.route("/distribucion/categorias", methods=["GET"])
@require_auth
def listar_categorias():
    cats = DistribucionCategoria.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(DistribucionCategoria.sort_order).all()

    # Auto-seed on first access
    if not cats:
        _seed_categorias(g.tenant_id)
        cats = DistribucionCategoria.query.filter_by(
            tenant_id=g.tenant_id
        ).order_by(DistribucionCategoria.sort_order).all()

    return jsonify(DistribucionCategoriaSchema(many=True).dump(cats))


@ajustes_bp.route("/distribucion/categorias", methods=["POST"])
@require_auth
@require_role("admin")
def crear_categoria():
    schema = DistribucionCategoriaSchema()
    data = schema.load(request.get_json() or {})
    cat = DistribucionCategoria(
        tenant_id=g.tenant_id,
        es_sistema=False,
        **data,
    )
    db.session.add(cat)
    db.session.commit()
    return jsonify(schema.dump(cat)), 201


@ajustes_bp.route("/distribucion/categorias/<int:cat_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_categoria(cat_id):
    cat = DistribucionCategoria.query.filter_by(
        id=cat_id, tenant_id=g.tenant_id
    ).first_or_404()
    if cat.es_sistema:
        return jsonify({"error": "No se pueden eliminar las categorías del sistema"}), 400
    db.session.delete(cat)
    db.session.commit()
    return jsonify({"message": "Categoría eliminada"})


@ajustes_bp.route("/distribucion/categorias/batch", methods=["PUT"])
@require_auth
@require_role("admin")
def guardar_categorias_batch():
    """Save all categories at once, validating that percentages sum to 100."""
    body = request.get_json() or {}
    cats_payload = body.get("categorias", [])

    # Validate sum = 100
    total = sum(float(c.get("porcentaje", 0)) for c in cats_payload)
    if abs(total - 100) > 0.01:
        return jsonify({
            "error": f"Los porcentajes deben sumar 100%. Total actual: {total:.1f}%"
        }), 400

    # Apply updates
    for item in cats_payload:
        cat_id = item.get("id")
        if not cat_id:
            continue
        cat = DistribucionCategoria.query.filter_by(
            id=cat_id, tenant_id=g.tenant_id
        ).first()
        if not cat:
            continue
        cat.porcentaje = float(item.get("porcentaje", cat.porcentaje))
        if not cat.es_sistema:
            # Custom cats can also rename/recolor
            if "nombre" in item:
                cat.nombre = item["nombre"]
            if "color" in item:
                cat.color = item["color"]

    # Keep DistribucionConfig in sync
    _sync_config_from_categorias(g.tenant_id)
    db.session.commit()

    cats = DistribucionCategoria.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(DistribucionCategoria.sort_order).all()
    return jsonify(DistribucionCategoriaSchema(many=True).dump(cats))
