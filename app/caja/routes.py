"""API del corte de caja. Las rutas solo traducen HTTP; la lógica vive en services."""
from datetime import date

from flask import Blueprint, g, jsonify, request
from marshmallow import ValidationError

from app.caja import services
from app.caja.models import CorteCaja
from app.caja.schemas import CierreSchema, ReaperturaSchema, SalidaSchema
from app.middleware.tenant import require_auth, require_role

caja_bp = Blueprint("caja", __name__, url_prefix="/api/v1/caja")

# Códigos de negocio que significan conflicto de estado, no dato inválido.
_CODIGOS_409 = {
    "ya_cerrado", "sin_clasificar", "sin_metodo_efectivo", "ya_abierto",
    "dia_cerrado",
}
_CODIGOS_404 = {"no_encontrado"}
_CODIGOS_403 = {"ajena"}


def _error(exc):
    cuerpo = {"error": exc.mensaje, "codigo": exc.codigo}
    cuerpo.update(exc.datos)
    if exc.codigo in _CODIGOS_404:
        return jsonify(cuerpo), 404
    if exc.codigo in _CODIGOS_403:
        return jsonify(cuerpo), 403
    if exc.codigo in _CODIGOS_409:
        return jsonify(cuerpo), 409
    return jsonify(cuerpo), 400


def _fecha_arg(nombre="fecha", default=None):
    valor = request.args.get(nombre)
    if not valor:
        return default if default is not None else date.today()
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


class _SucursalInvalida(Exception):
    """sucursal_id no es numérico.

    No podemos copiar el patrón de _fecha_arg (usar None como señal de
    "inválido") porque aquí None es un valor legítimo: significa "sin
    sucursal", es decir el corte de los movimientos que no tienen sucursal
    asignada, que es un corte real y no un error. Por eso la señal de
    "inválido" necesita ser algo distinto de None, y una excepción propia
    que la ruta capture es lo más simple.
    """


def _sucursal_arg():
    valor = request.args.get("sucursal_id")
    if valor in (None, "", "null"):
        return None
    try:
        return int(valor)
    except ValueError:
        raise _SucursalInvalida()


def _es_recepcion():
    """La recepcionista ve el día con los conceptos ajenos enmascarados."""
    return g.current_user.role == "recepcionista"


def _dump_corte(corte):
    return {
        "id": corte.id,
        "fecha": corte.fecha.isoformat(),
        "sucursal_id": corte.sucursal_id,
        "total_efectivo": corte.total_efectivo,
        "total_tarjeta": corte.total_tarjeta,
        "total_transferencia": corte.total_transferencia,
        "total_otro": corte.total_otro,
        "comision_tarjeta": corte.comision_tarjeta,
        "neto_tarjeta": corte.neto_tarjeta,
        "total_dia": corte.total_dia,
        "salidas_efectivo": corte.salidas_efectivo,
        "esperado_efectivo": corte.esperado_efectivo,
        "efectivo_contado": corte.efectivo_contado,
        "diferencia": corte.diferencia,
        "comentario": corte.comentario,
        "cerrado_por": corte.usuario.name if corte.usuario else None,
        "cerrado_at": corte.cerrado_at.isoformat() if corte.cerrado_at else None,
        "cerrado": corte.cerrado,
    }


@caja_bp.route("/corte", methods=["GET"])
@require_auth
@require_role("admin", "recepcionista", "asistente")
def ver_corte():
    fecha = _fecha_arg()
    if fecha is None:
        return jsonify({"error": "Fecha inválida"}), 400
    try:
        sucursal_id = _sucursal_arg()
    except _SucursalInvalida:
        return jsonify({"error": "Sucursal inválida"}), 400

    resumen = services.resumen_dia(g.tenant_id, sucursal_id, fecha)
    resumen["salidas"] = services.listar_salidas(
        g.tenant_id, sucursal_id, fecha,
        enmascarar_para=g.current_user.id if _es_recepcion() else None,
    )
    corte = services.obtener_corte(g.tenant_id, sucursal_id, fecha)
    cerrado = bool(corte and corte.cerrado)

    resumen.update({
        "fecha": fecha.isoformat(),
        "sucursal_id": sucursal_id,
        "estado": "cerrado" if cerrado else "abierto",
        "corte": _dump_corte(corte) if corte else None,
        "tolerancia": services.tolerancia(g.tenant_id),
        # La UI deshabilita el botón; el servicio vuelve a validarlo al cerrar.
        "puede_cerrar": not cerrado and not resumen["sin_clasificar"],
    })
    return jsonify(resumen)


@caja_bp.route("/corte", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista", "asistente")
def cerrar():
    try:
        data = CierreSchema().load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Datos inválidos", "detalles": err.messages}), 400
    try:
        corte = services.cerrar_corte(
            g.tenant_id, g.current_user.id,
            fecha=data["fecha"], sucursal_id=data["sucursal_id"],
            efectivo_contado=data["efectivo_contado"],
            comentario=data.get("comentario"),
        )
    except services.CajaError as exc:
        return _error(exc)
    cuerpo = _dump_corte(corte)
    cuerpo["estado"] = "cerrado"
    return jsonify(cuerpo), 201


@caja_bp.route("/reabrir/<int:corte_id>", methods=["POST"])
@require_auth
@require_role("admin")
def reabrir(corte_id):
    try:
        data = ReaperturaSchema().load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Datos inválidos", "detalles": err.messages}), 400
    try:
        corte = services.reabrir_corte(
            g.tenant_id, g.current_user.id, corte_id, data["motivo"])
    except services.CajaError as exc:
        return _error(exc)
    cuerpo = _dump_corte(corte)
    cuerpo["estado"] = "abierto"
    return jsonify(cuerpo)


@caja_bp.route("/cortes", methods=["GET"])
@require_auth
@require_role("admin")
def listar_cortes():
    hoy = date.today()
    desde = _fecha_arg("desde", default=hoy.replace(day=1))
    hasta = _fecha_arg("hasta", default=hoy)
    if desde is None or hasta is None:
        return jsonify({"error": "Fecha inválida"}), 400
    try:
        sucursal_id = _sucursal_arg()
    except _SucursalInvalida:
        return jsonify({"error": "Sucursal inválida"}), 400
    filas = services.historico(g.tenant_id, desde, hasta, sucursal_id)
    for f in filas:
        f["fecha"] = f["fecha"].isoformat()
        if f["cerrado_at"]:
            f["cerrado_at"] = f["cerrado_at"].isoformat()
    return jsonify({"cortes": filas, "desde": desde.isoformat(),
                    "hasta": hasta.isoformat()})


@caja_bp.route("/cortes/<int:corte_id>", methods=["GET"])
@require_auth
@require_role("admin")
def detalle_corte(corte_id):
    corte = CorteCaja.query.filter_by(id=corte_id, tenant_id=g.tenant_id).first()
    if corte is None:
        return jsonify({"error": "Corte no encontrado"}), 404

    # El detalle recalcula el día para poder mostrar el delta contra la foto.
    vivo = services.resumen_dia(g.tenant_id, corte.sucursal_id, corte.fecha)
    delta = round(vivo["esperado_efectivo"] - corte.esperado_efectivo, 2)
    return jsonify({
        "corte": _dump_corte(corte),
        "ingresos": vivo["ingresos"],
        "salidas": services.listar_salidas(
            g.tenant_id, corte.sucursal_id, corte.fecha),
        "movimientos_posteriores": delta != 0,
        "delta_efectivo": delta,
        "eventos": [{
            "evento": e.evento,
            "usuario": e.usuario.name if e.usuario else None,
            "motivo": e.motivo,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in corte.eventos],
    })


@caja_bp.route("/salidas", methods=["GET"])
@require_auth
@require_role("admin", "recepcionista", "asistente")
def listar_salidas():
    fecha = _fecha_arg()
    if fecha is None:
        return jsonify({"error": "Fecha inválida"}), 400
    try:
        sucursal_id = _sucursal_arg()
    except _SucursalInvalida:
        return jsonify({"error": "Sucursal inválida"}), 400
    salidas = services.listar_salidas(
        g.tenant_id, sucursal_id, fecha,
        enmascarar_para=g.current_user.id if _es_recepcion() else None,
    )
    return jsonify({"salidas": salidas})


@caja_bp.route("/salidas", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista", "asistente")
def crear_salida():
    try:
        data = SalidaSchema().load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Datos inválidos", "detalles": err.messages}), 400
    try:
        services.exigir_dia_abierto(
            g.tenant_id, data["sucursal_id"], data["fecha"],
            es_admin=g.current_user.role == "admin",
        )
    except services.CajaError as exc:
        return _error(exc)
    try:
        gasto = services.registrar_salida(
            g.tenant_id, g.current_user.id, fecha=data["fecha"],
            concepto_nombre=data["concepto_nombre"], monto=data["monto"],
            sucursal_id=data["sucursal_id"],
        )
    except services.CajaError as exc:
        return _error(exc)
    return jsonify({
        "id": gasto.id, "concepto": gasto.concepto_nombre,
        "monto": round(float(gasto.monto), 2), "propia": True,
    }), 201


@caja_bp.route("/salidas/<int:gasto_id>", methods=["DELETE"])
@require_auth
@require_role("admin", "recepcionista", "asistente")
def borrar_salida(gasto_id):
    # Hay que saber de qué día es la salida antes de poder validar el candado.
    from app.edr.models import GastoOperativo
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=g.tenant_id, sale_de_caja=True).first()
    if gasto is not None:
        try:
            services.exigir_dia_abierto(
                g.tenant_id, gasto.sucursal_id, gasto.fecha,
                es_admin=g.current_user.role == "admin",
            )
        except services.CajaError as exc:
            return _error(exc)
    try:
        services.eliminar_salida(
            g.tenant_id, gasto_id,
            solo_de_usuario=g.current_user.id if _es_recepcion() else None,
        )
    except services.CajaError as exc:
        return _error(exc)
    return jsonify({"message": "Salida eliminada"})
