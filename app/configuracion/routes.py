from flask import Blueprint, request, jsonify, g
from marshmallow import Schema, ValidationError, fields, validate
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.configuracion.models import ConfigConsultorio
from app.configuracion.schemas import ConfigSchema
from app.inventario.models import Operatorio
from app.inventario.schemas import OperatorioSchema
from app.inventario.services import (
    CapacidadDecreaseError, ajustar_numero_operatorios,
)

config_bp = Blueprint("configuracion", __name__, url_prefix="/api/v1/config")


def _calculados(config):
    return {
        "horas_semana": round(config.horas_semana, 2),
        "horas_mes": round(config.horas_mes, 2),
        "costo_hora": round(config.costo_hora, 2),
        "costo_operario_hora": round(config.costo_operario_hora, 2),
    }


@config_bp.route("/logo", methods=["POST"])
@require_auth
@require_role("admin")
def subir_logo():
    from app.configuracion.logo import LOGO_MAX_UPLOAD, procesar_logo

    archivo = request.files.get("logo")
    if not archivo:
        return jsonify({"error": "Se requiere el archivo del logo"}), 400
    raw = archivo.read()
    if len(raw) > LOGO_MAX_UPLOAD:
        return jsonify({"error": "El logo no debe superar 8MB"}), 400
    try:
        procesado = procesar_logo(raw)
    except ValueError:
        return jsonify({
            "error": "El archivo no es una imagen válida (usa PNG o JPG)",
        }), 400

    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    if not config:
        config = ConfigConsultorio(tenant_id=g.tenant_id)
        db.session.add(config)
    config.logo = procesado
    db.session.commit()
    return jsonify({"message": "Logo actualizado"})


@config_bp.route("/logo", methods=["GET"])
@require_auth
def ver_logo():
    """Logo guardado, para la vista previa en Ajustes. 404 si no hay."""
    from flask import Response
    from app.configuracion.logo import logo_bytes, logo_mime

    data = logo_bytes(g.tenant_id)
    if not data:
        return jsonify({"error": "Sin logo"}), 404
    resp = Response(data, mimetype=logo_mime(data))
    resp.headers["Cache-Control"] = "no-store"  # siempre muestra el actual
    return resp


@config_bp.route("", methods=["GET"])
@require_auth
def obtener():
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first_or_404()
    schema = ConfigSchema()
    data = schema.dump(config)
    data["calculado"] = _calculados(config)
    return jsonify(data)


@config_bp.route("", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar():
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first_or_404()
    schema = ConfigSchema(partial=True)
    data = schema.load(request.get_json() or {})

    for key, value in data.items():
        setattr(config, key, value)

    db.session.commit()

    result = schema.dump(config)
    result["calculado"] = _calculados(config)
    return jsonify(result)


class _OperatoriosCapacidadSchema(Schema):
    numero_unidades = fields.Int(required=True, validate=validate.Range(min=1))


@config_bp.route("/operatorios", methods=["GET"])
@require_auth
def listar_operatorios_config():
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first_or_404()
    ops = (
        Operatorio.query.filter_by(tenant_id=g.tenant_id)
        .order_by(Operatorio.orden, Operatorio.nombre)
        .all()
    )
    return jsonify({
        "numero_unidades": config.numero_unidades,
        "operatorios": OperatorioSchema(many=True).dump(ops),
        "calculado": _calculados(config),
    })


@config_bp.route("/operatorios", methods=["PUT"])
@require_auth
@require_role("admin")
def ajustar_operatorios_config():
    try:
        payload = _OperatoriosCapacidadSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    try:
        ajustar_numero_operatorios(g.tenant_id, payload["numero_unidades"])
        db.session.commit()
    except CapacidadDecreaseError as e:
        db.session.rollback()
        return jsonify({
            "error": str(e),
            "operatorios": e.operatorios,
        }), 409
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first_or_404()
    ops = (
        Operatorio.query.filter_by(tenant_id=g.tenant_id)
        .order_by(Operatorio.orden, Operatorio.nombre)
        .all()
    )
    return jsonify({
        "numero_unidades": config.numero_unidades,
        "operatorios": OperatorioSchema(many=True).dump(ops),
        "calculado": _calculados(config),
    })
