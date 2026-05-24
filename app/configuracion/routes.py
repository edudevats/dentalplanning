from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.configuracion.models import ConfigConsultorio
from app.configuracion.schemas import ConfigSchema

config_bp = Blueprint("configuracion", __name__, url_prefix="/api/v1/config")


@config_bp.route("", methods=["GET"])
@require_auth
def obtener():
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first_or_404()
    schema = ConfigSchema()
    data = schema.dump(config)
    data["calculado"] = {
        "horas_semana": round(config.horas_semana, 2),
        "horas_mes": round(config.horas_mes, 2),
        "costo_hora": round(config.costo_hora, 2),
    }
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
    result["calculado"] = {
        "horas_semana": round(config.horas_semana, 2),
        "horas_mes": round(config.horas_mes, 2),
        "costo_hora": round(config.costo_hora, 2),
    }
    return jsonify(result)
