from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.tratamientos.models import Tratamiento, TratamientoMaterial
from app.tratamientos.schemas import TratamientoSchema, SimularSchema
from app.catalogo.models import Material
from app.configuracion.models import ConfigConsultorio
from app.engine.pricing_engine import calcular_precio_tratamiento

tratamientos_bp = Blueprint("tratamientos", __name__, url_prefix="/api/v1/tratamientos")


def _serialize_tratamiento(tx, config):
    calculos = calcular_precio_tratamiento(config, tx, tx.materiales)
    return {
        "id": tx.id,
        "nombre": tx.nombre,
        "horas_invertidas": tx.horas_invertidas,
        "precio_paciente": tx.precio_paciente,
        "comision_bancaria_pct": tx.comision_bancaria_pct,
        "comision_especialista": {
            "tipo": tx.comision_especialista_tipo,
            "valor": tx.comision_especialista_valor,
        },
        "materiales": calculos["materiales"],
        "calculos": {k: v for k, v in calculos.items() if k != "materiales"},
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
    }


@tratamientos_bp.route("", methods=["GET"])
@require_auth
def listar():
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    tratamientos = Tratamiento.query.filter_by(tenant_id=g.tenant_id).order_by(
        Tratamiento.nombre
    ).all()

    return jsonify([_serialize_tratamiento(tx, config) for tx in tratamientos])


@tratamientos_bp.route("/<int:tx_id>", methods=["GET"])
@require_auth
def obtener(tx_id):
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    tx = Tratamiento.query.filter_by(
        id=tx_id, tenant_id=g.tenant_id
    ).first_or_404()
    return jsonify(_serialize_tratamiento(tx, config))


@tratamientos_bp.route("", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear():
    schema = TratamientoSchema()
    data = schema.load(request.get_json())
    materiales_input = data.pop("materiales", [])

    existe = Tratamiento.query.filter_by(
        tenant_id=g.tenant_id, nombre=data["nombre"]
    ).first()
    if existe:
        return jsonify({"error": "Ya existe un tratamiento con ese nombre"}), 409

    tx = Tratamiento(tenant_id=g.tenant_id, **data)
    db.session.add(tx)
    db.session.flush()

    for mat_data in materiales_input:
        material = Material.query.filter_by(
            id=mat_data["material_id"], tenant_id=g.tenant_id
        ).first()
        if not material:
            db.session.rollback()
            return jsonify({"error": f"Material {mat_data['material_id']} no encontrado"}), 400
        tm = TratamientoMaterial(
            tratamiento_id=tx.id,
            material_id=mat_data["material_id"],
            cantidad=mat_data["cantidad"],
        )
        db.session.add(tm)

    db.session.commit()

    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    tx = db.session.get(Tratamiento, tx.id)
    return jsonify(_serialize_tratamiento(tx, config)), 201


@tratamientos_bp.route("/<int:tx_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar(tx_id):
    tx = Tratamiento.query.filter_by(
        id=tx_id, tenant_id=g.tenant_id
    ).first_or_404()

    schema = TratamientoSchema(partial=True)
    data = schema.load(request.get_json())
    materiales_input = data.pop("materiales", None)

    for key, value in data.items():
        setattr(tx, key, value)

    if materiales_input is not None:
        TratamientoMaterial.query.filter_by(tratamiento_id=tx.id).delete()
        for mat_data in materiales_input:
            material = Material.query.filter_by(
                id=mat_data["material_id"], tenant_id=g.tenant_id
            ).first()
            if not material:
                db.session.rollback()
                return jsonify({"error": f"Material {mat_data['material_id']} no encontrado"}), 400
            tm = TratamientoMaterial(
                tratamiento_id=tx.id,
                material_id=mat_data["material_id"],
                cantidad=mat_data["cantidad"],
            )
            db.session.add(tm)

    db.session.commit()

    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    tx = db.session.get(Tratamiento, tx.id)
    return jsonify(_serialize_tratamiento(tx, config))


@tratamientos_bp.route("/<int:tx_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar(tx_id):
    tx = Tratamiento.query.filter_by(
        id=tx_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(tx)
    db.session.commit()
    return jsonify({"message": "Tratamiento eliminado"})


@tratamientos_bp.route("/<int:tx_id>/duplicar", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def duplicar(tx_id):
    original = Tratamiento.query.filter_by(
        id=tx_id, tenant_id=g.tenant_id
    ).first_or_404()

    nuevo_nombre = f"{original.nombre}_copia"
    counter = 1
    while Tratamiento.query.filter_by(tenant_id=g.tenant_id, nombre=nuevo_nombre).first():
        counter += 1
        nuevo_nombre = f"{original.nombre}_copia_{counter}"

    nuevo = Tratamiento(
        tenant_id=g.tenant_id,
        nombre=nuevo_nombre,
        horas_invertidas=original.horas_invertidas,
        precio_paciente=original.precio_paciente,
        comision_bancaria_pct=original.comision_bancaria_pct,
        comision_especialista_tipo=original.comision_especialista_tipo,
        comision_especialista_valor=original.comision_especialista_valor,
    )
    db.session.add(nuevo)
    db.session.flush()

    for tm in original.materiales:
        nuevo_tm = TratamientoMaterial(
            tratamiento_id=nuevo.id,
            material_id=tm.material_id,
            cantidad=tm.cantidad,
        )
        db.session.add(nuevo_tm)

    db.session.commit()

    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    nuevo = db.session.get(Tratamiento, nuevo.id)
    return jsonify(_serialize_tratamiento(nuevo, config)), 201


@tratamientos_bp.route("/<int:tx_id>/simular", methods=["POST"])
@require_auth
def simular(tx_id):
    tx = Tratamiento.query.filter_by(
        id=tx_id, tenant_id=g.tenant_id
    ).first_or_404()

    schema = SimularSchema()
    data = schema.load(request.get_json())

    # Temporarily override values for simulation (don't save)
    original_precio = tx.precio_paciente
    original_com_pct = tx.comision_bancaria_pct
    original_com_tipo = tx.comision_especialista_tipo
    original_com_valor = tx.comision_especialista_valor

    tx.precio_paciente = data["precio_paciente"]
    if "comision_bancaria_pct" in data:
        tx.comision_bancaria_pct = data["comision_bancaria_pct"]
    if "comision_especialista_tipo" in data:
        tx.comision_especialista_tipo = data["comision_especialista_tipo"]
    if "comision_especialista_valor" in data:
        tx.comision_especialista_valor = data["comision_especialista_valor"]

    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    result = _serialize_tratamiento(tx, config)

    # Restore original values
    tx.precio_paciente = original_precio
    tx.comision_bancaria_pct = original_com_pct
    tx.comision_especialista_tipo = original_com_tipo
    tx.comision_especialista_valor = original_com_valor

    return jsonify(result)
