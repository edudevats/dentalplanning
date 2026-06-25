from flask import Blueprint, request, jsonify, g
from marshmallow import ValidationError
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.catalogo.models import MaterialMaster, Material
from app.catalogo.schemas import MaterialMasterSchema, MaterialSchema, ImportMasterSchema
from app.inventario.services import _inicializar_stock_material

catalogo_bp = Blueprint("catalogo", __name__, url_prefix="/api/v1/materiales")


@catalogo_bp.route("/master", methods=["GET"])
@require_auth
def listar_master():
    """Listar catálogo global de materiales (para onboarding/agregar)."""
    categoria = request.args.get("categoria")
    q = request.args.get("q")

    query = MaterialMaster.query
    if categoria:
        query = query.filter_by(categoria=categoria)
    if q:
        query = query.filter(MaterialMaster.nombre.ilike(f"%{q}%"))

    materiales = query.order_by(MaterialMaster.nombre).all()
    schema = MaterialMasterSchema(many=True)
    return jsonify(schema.dump(materiales))


@catalogo_bp.route("/importar-master", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def importar_master():
    """Importar materiales seleccionados del catálogo master al tenant."""
    schema = ImportMasterSchema()
    data = schema.load(request.get_json() or {})

    masters = MaterialMaster.query.filter(
        MaterialMaster.id.in_(data["material_ids"])
    ).all()

    importados = 0
    for master in masters:
        existe = Material.query.filter_by(
            tenant_id=g.tenant_id, nombre=master.nombre
        ).first()
        if existe:
            if not existe.en_inventario:
                existe.en_inventario = True
                db.session.flush()
                _inicializar_stock_material(g.tenant_id, existe.id)
            continue

        # Las llaves de `costos` se deserializan como int (ImportMasterSchema:
        # keys=fields.Int()), así que la búsqueda debe usar el id int, no str.
        costo_info = data["costos"].get(master.id, {})
        material = Material(
            tenant_id=g.tenant_id,
            master_id=master.id,
            nombre=master.nombre,
            es_medible=master.es_medible,
            costo_paquete=costo_info.get("costo_paquete", 0),
            unidades_paquete=int(costo_info.get("unidades_paquete", 1)),
            expira=master.expira,
            unidad_inventario=master.unidad_inventario,
            en_inventario=True,
        )
        db.session.add(material)
        db.session.flush()
        _inicializar_stock_material(g.tenant_id, material.id)
        importados += 1

    db.session.commit()
    return jsonify({"message": f"{importados} materiales importados"}), 201


@catalogo_bp.route("", methods=["GET"])
@require_auth
def listar():
    """Listar materiales del tenant (paginado, filtrable)."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    q = request.args.get("q")

    query = Material.query.filter_by(tenant_id=g.tenant_id)
    if q:
        query = query.filter(Material.nombre.ilike(f"%{q}%"))

    pagination = query.order_by(Material.nombre).paginate(
        page=page, per_page=per_page, error_out=False
    )

    schema = MaterialSchema(many=True)
    return jsonify({
        "materiales": schema.dump(pagination.items),
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
    })


@catalogo_bp.route("/<int:material_id>", methods=["GET"])
@require_auth
def obtener(material_id):
    material = Material.query.filter_by(
        id=material_id, tenant_id=g.tenant_id
    ).first_or_404()
    return jsonify(MaterialSchema().dump(material))


@catalogo_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear():
    """Crear material propio del tenant."""
    schema = MaterialSchema()
    data = schema.load(request.get_json() or {})

    existe = Material.query.filter_by(
        tenant_id=g.tenant_id, nombre=data["nombre"]
    ).first()
    if existe:
        return jsonify({"error": "Ya existe un material con ese nombre"}), 409

    material = Material(tenant_id=g.tenant_id, **data)
    material.en_inventario = True
    db.session.add(material)
    db.session.flush()
    _inicializar_stock_material(g.tenant_id, material.id)
    db.session.commit()
    return jsonify(schema.dump(material)), 201


@catalogo_bp.route("/<int:material_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar(material_id):
    material = Material.query.filter_by(
        id=material_id, tenant_id=g.tenant_id
    ).first_or_404()

    schema = MaterialSchema(partial=True)
    data = schema.load(request.get_json() or {})

    for key, value in data.items():
        setattr(material, key, value)

    db.session.commit()
    return jsonify(MaterialSchema().dump(material))


@catalogo_bp.route("/<int:material_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar(material_id):
    material = Material.query.filter_by(
        id=material_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(material)
    db.session.commit()
    return jsonify({"message": "Material eliminado"})
