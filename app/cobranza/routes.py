"""API REST de cotizaciones y cobranza."""
from datetime import datetime
from io import BytesIO

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy.orm import joinedload, selectinload

from app.cobranza import services
from app.cobranza.models import Cotizacion, Pago
from app.cobranza.schemas import AprobarSchema, CotizacionSchema, PagoSchema
from app.middleware.tenant import require_auth, require_role


cobranza_bp = Blueprint(
    "cobranza", __name__, url_prefix="/api/v1/cobranza",
)


@cobranza_bp.errorhandler(services.CobranzaNotFound)
def _not_found(error):
    return jsonify({"error": str(error)}), 404


@cobranza_bp.errorhandler(services.CobranzaError)
def _business_error(error):
    return jsonify({"error": str(error)}), 400


def _fecha_param(nombre):
    valor = (request.args.get(nombre) or "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError as error:
        raise services.CobranzaError(
            f"{nombre} debe tener formato AAAA-MM-DD"
        ) from error


def _query_cotizaciones():
    return Cotizacion.query.options(
        joinedload(Cotizacion.paciente),
        joinedload(Cotizacion.especialista),
        selectinload(Cotizacion.conceptos),
        selectinload(Cotizacion.programados),
        selectinload(Cotizacion.pagos).joinedload(Pago.metodo_pago),
    ).filter(Cotizacion.tenant_id == g.tenant_id)


def _dump_pago(pago):
    data = PagoSchema().dump(pago)
    data["metodo_pago_nombre"] = (
        pago.metodo_pago.nombre if pago.metodo_pago else None
    )
    return data


def _dump(cotizacion, *, detallado=False):
    data = CotizacionSchema(
        exclude=() if detallado else ("conceptos", "programados", "pagos"),
    ).dump(cotizacion)
    data["paciente_nombre"] = (
        cotizacion.paciente.nombre if cotizacion.paciente else None
    )
    data["especialista_nombre"] = (
        cotizacion.especialista.nombre if cotizacion.especialista else None
    )
    data["pagado"] = services.total_pagado(cotizacion)
    data["saldo"] = services.saldo(cotizacion)
    data["parcialidades_pagadas"] = services.parcialidades_pagadas(cotizacion)
    data["vencida"] = services.esta_vencida(cotizacion)
    if data["vencida"]:
        data["estatus_base"] = cotizacion.estatus
        data["estatus"] = "vencida"
    ultima = services.ultima_fecha_pago(cotizacion)
    data["ultima_fecha_pago"] = ultima.isoformat() if ultima else None
    data["sin_pagos_recientes"] = services.sin_pagos_recientes(cotizacion)
    if cotizacion.estatus == "aprobada":
        referencia = (
            ultima
            or cotizacion.fecha_inicio_tratamiento
            or cotizacion.fecha
        )
        data["dias_sin_pago"] = max(
            (services._hoy() - referencia).days, 0,
        )
    else:
        data["dias_sin_pago"] = None
    if detallado:
        data["pagos"] = [_dump_pago(pago) for pago in cotizacion.pagos]
    return data


@cobranza_bp.route("/cotizaciones", methods=["GET"])
@require_auth
def listar_cotizaciones():
    query = _query_cotizaciones()
    estatus = (request.args.get("estatus") or "").strip()
    if estatus:
        if estatus == "vencida":
            query = query.filter(
                Cotizacion.estatus.in_(("borrador", "enviada")),
                Cotizacion.valida_hasta < services._hoy(),
            )
        else:
            query = query.filter(Cotizacion.estatus == estatus)

    paciente_id = request.args.get(
        "paciente_id", request.args.get("paciente"), type=int,
    )
    if paciente_id:
        query = query.filter(Cotizacion.paciente_id == paciente_id)

    fecha_desde = _fecha_param("fecha_desde")
    fecha_hasta = _fecha_param("fecha_hasta")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise services.CobranzaError(
            "fecha_desde no puede ser posterior a fecha_hasta"
        )
    if fecha_desde:
        query = query.filter(Cotizacion.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Cotizacion.fecha <= fecha_hasta)

    rows = query.order_by(
        Cotizacion.fecha.desc(), Cotizacion.id.desc(),
    ).all()
    return jsonify([_dump(cotizacion) for cotizacion in rows])


@cobranza_bp.route("/cotizaciones/<int:cotizacion_id>", methods=["GET"])
@require_auth
def obtener_cotizacion(cotizacion_id):
    cotizacion = _query_cotizaciones().filter(
        Cotizacion.id == cotizacion_id,
    ).first()
    if not cotizacion:
        raise services.CobranzaNotFound("Cotización no encontrada")
    return jsonify(_dump(cotizacion, detallado=True))


@cobranza_bp.route("/cotizaciones", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def crear_cotizacion():
    data = CotizacionSchema().load(request.get_json() or {})
    cotizacion = services.crear_cotizacion(
        g.tenant_id, g.current_user.id, data,
    )
    return jsonify(_dump(cotizacion, detallado=True)), 201


@cobranza_bp.route("/cotizaciones/<int:cotizacion_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def actualizar_cotizacion(cotizacion_id):
    data = CotizacionSchema().load(request.get_json() or {})
    cotizacion = services.actualizar_cotizacion(
        g.tenant_id, cotizacion_id, data,
    )
    return jsonify(_dump(cotizacion, detallado=True))


@cobranza_bp.route("/cotizaciones/<int:cotizacion_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_cotizacion(cotizacion_id):
    services.eliminar_cotizacion(g.tenant_id, cotizacion_id)
    return jsonify({"message": "Cotización eliminada"})


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/aprobar", methods=["POST"],
)
@require_auth
@require_role("admin")
def aprobar_cotizacion(cotizacion_id):
    data = AprobarSchema().load(request.get_json() or {})
    cotizacion = services.aprobar_cotizacion(
        g.tenant_id,
        g.current_user.id,
        cotizacion_id,
        sucursal_id=data.get("sucursal_id"),
    )
    return jsonify(_dump(cotizacion, detallado=True))


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/rechazar", methods=["POST"],
)
@require_auth
@require_role("admin", "editor")
def rechazar_cotizacion(cotizacion_id):
    cotizacion = services.rechazar_cotizacion(
        g.tenant_id, cotizacion_id,
    )
    return jsonify(_dump(cotizacion, detallado=True))


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/cancelar", methods=["POST"],
)
@require_auth
@require_role("admin")
def cancelar_cotizacion(cotizacion_id):
    cotizacion = services.cancelar_cotizacion(
        g.tenant_id, cotizacion_id,
    )
    return jsonify(_dump(cotizacion, detallado=True))


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/enviar", methods=["POST"],
)
@require_auth
@require_role("admin", "editor", "recepcionista")
def enviar_cotizacion(cotizacion_id):
    from app.cobranza.correo import enviar_cotizacion as enviar

    cotizacion = services.obtener_cotizacion(g.tenant_id, cotizacion_id)
    if cotizacion.estatus not in ("borrador", "enviada"):
        raise services.CobranzaError(
            "Sólo se pueden enviar cotizaciones sin aprobar"
        )
    if not enviar(cotizacion):
        return jsonify({
            "error": "No se pudo enviar el correo. Revisa la configuración SMTP."
        }), 502
    cotizacion = services.marcar_cotizacion_enviada(
        g.tenant_id, cotizacion_id,
    )
    return jsonify(_dump(cotizacion, detallado=True))


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/pagos", methods=["POST"],
)
@require_auth
@require_role("admin", "editor", "recepcionista")
def registrar_pago(cotizacion_id):
    data = PagoSchema().load(request.get_json() or {})
    if data.get("historico") and g.current_user.role != "admin":
        return jsonify({
            "error": "Sólo un administrador puede registrar pagos históricos"
        }), 403
    data["idempotency_key"] = request.headers.get("Idempotency-Key")
    pago = services.registrar_pago(
        g.tenant_id, g.current_user.id, cotizacion_id, data,
    )
    replay = bool(getattr(pago, "_idempotent_replay", False))
    cotizacion = services.obtener_cotizacion(g.tenant_id, cotizacion_id)
    return jsonify({
        "pago": _dump_pago(pago),
        "cotizacion": _dump(cotizacion, detallado=True),
        "idempotent_replay": replay,
        "facturacion": {
            "estado": cotizacion.facturacion_estado,
            "error": cotizacion.facturacion_error,
        },
    }), 200 if replay else 201


@cobranza_bp.route("/pagos/<int:pago_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_pago(pago_id):
    services.eliminar_pago(g.tenant_id, pago_id)
    return jsonify({"message": "Pago eliminado"})


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/estado-cuenta", methods=["GET"],
)
@require_auth
def estado_cuenta(cotizacion_id):
    return jsonify(services.datos_estado_cuenta(
        g.tenant_id, cotizacion_id,
    ))


def _respuesta_pdf(contenido, filename):
    return send_file(
        BytesIO(contenido),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/pdf", methods=["GET"],
)
@require_auth
def descargar_cotizacion(cotizacion_id):
    from app.cobranza.pdf import nombre_archivo, pdf_cotizacion

    cotizacion = services.obtener_cotizacion(g.tenant_id, cotizacion_id)
    return _respuesta_pdf(
        pdf_cotizacion(cotizacion), nombre_archivo(cotizacion),
    )


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/estado-cuenta.pdf", methods=["GET"],
)
@require_auth
def descargar_estado_cuenta(cotizacion_id):
    from app.cobranza.pdf import nombre_archivo, pdf_estado_cuenta

    cotizacion = services.obtener_cotizacion(g.tenant_id, cotizacion_id)
    datos = services.datos_estado_cuenta(g.tenant_id, cotizacion_id)
    return _respuesta_pdf(
        pdf_estado_cuenta(cotizacion, datos),
        nombre_archivo(cotizacion, "Estado-de-cuenta"),
    )


@cobranza_bp.route(
    "/cotizaciones/<int:cotizacion_id>/facturacion/reintentar",
    methods=["POST"],
)
@require_auth
@require_role("admin")
def reintentar_facturacion(cotizacion_id):
    return jsonify(services.procesar_facturacion_liquidacion(
        g.tenant_id, cotizacion_id,
    ))


@cobranza_bp.route("/resumen", methods=["GET"])
@require_auth
def resumen():
    return jsonify(services.resumen_cobranza(g.tenant_id))
