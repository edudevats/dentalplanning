"""Portal público de autofacturación (sin login). Scope por slug del tenant."""
from flask import Blueprint, request, jsonify, render_template, abort, Response
from marshmallow import ValidationError

from app.extensions import db
from app.auth.models import Tenant
from app.facturacion.models import (
    Ticket, ConfiguracionFiscal, TICKET_SIN_TIMBRAR, TICKET_ERROR,
)

# Estados desde los que el cliente todavía puede (re)facturar: nunca se emitió
# un CFDI vigente. 'error' es un intento fallido, así que se permite reintentar.
REFACTURABLE = (TICKET_SIN_TIMBRAR, TICKET_ERROR)
from app.facturacion.schemas import ReceptorSchema
from app.facturacion.cfdi import (
    _ventana_vencida, _conceptos_cfdi, timbrar_ticket, TimbradoError,
)

portal_bp = Blueprint("portal", __name__)

# Slugs que NO son consultorios (rutas del frontend / API). Devuelven 404 en el portal.
RESERVED_SLUGS = {
    "dashboard", "ingresos", "gastos", "pagos-doctores", "facturas", "ajustes",
    "materiales", "tratamientos", "reportes", "inventario", "admin", "login",
    "register", "registro-exitoso", "selector", "finanzas-personales",
    "api", "static", "favicon.ico",
}


def _split_folio(folio_str):
    s = str(folio_str or "").strip()
    if "-" in s:
        serie, _, num = s.rpartition("-")
        return serie, num
    return "", s


def _tenant_or_404(slug):
    if slug in RESERVED_SLUGS:
        abort(404)
    tenant = Tenant.query.filter_by(slug=slug, is_active=True).first()
    if not tenant:
        abort(404)
    return tenant


def _facturacion_habilitada(tenant_id):
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=tenant_id).first()
    return bool(cfg and cfg.facturacion_activa)


def _facturacion_disabled_response():
    return jsonify({
        "error": "La clínica no tiene activa la facturación electrónica."
    }), 403


def _resolver_ticket(tenant, data):
    """Resuelve el ticket por token (QR) o por folio+monto+fecha. None si no valida."""
    token = (data.get("token") or "").strip()
    q = Ticket.query.filter_by(tenant_id=tenant.id)
    if token:
        return q.filter_by(token=token).first()

    folio_str, monto, fecha = data.get("folio"), data.get("monto"), data.get("fecha")
    if not (folio_str and monto is not None and fecha):
        return None
    serie, num = _split_folio(folio_str)
    try:
        num = int(num)
    except (TypeError, ValueError):
        return None
    t = q.filter_by(serie=serie, folio=num).first()
    if not t:
        return None
    try:
        if abs(float(t.total or 0) - float(monto)) > 0.01:
            return None
    except (TypeError, ValueError):
        return None
    if t.fecha.isoformat() != str(fecha):
        return None
    return t


@portal_bp.route("/<slug>")
def portal_page(slug):
    tenant = _tenant_or_404(slug)
    if not _facturacion_habilitada(tenant.id):
        abort(404)
    # Versión del logo (longitud en bytes, sin cargar el BLOB) para cache-busting:
    # cambia cuando el consultorio sube otro logo, así el navegador no muestra el viejo.
    from app.configuracion.logo import logo_version
    return render_template("portal/autofactura.html",
                           slug=slug, tenant_nombre=tenant.name,
                           logo_ver=logo_version(tenant.id))


@portal_bp.route("/api/v1/portal/<slug>/logo")
def portal_logo(slug):
    """Logo del consultorio (público) para el encabezado del portal. 404 si no hay."""
    from app.configuracion.logo import logo_bytes, logo_mime

    tenant = _tenant_or_404(slug)
    data = logo_bytes(tenant.id)
    if not data:
        abort(404)
    resp = Response(data, mimetype=logo_mime(data))
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@portal_bp.route("/api/v1/portal/<slug>/buscar", methods=["POST"])
def portal_buscar(slug):
    tenant = _tenant_or_404(slug)
    t = _resolver_ticket(tenant, request.get_json() or {})
    if not t:
        return jsonify({"error": "No encontramos ese ticket. Verifica los datos."}), 404
    if not _facturacion_habilitada(tenant.id):
        return _facturacion_disabled_response()
    if t.estado not in REFACTURABLE:
        return jsonify({"ya_facturado": True, "estado": t.estado,
                        "folio": t.folio_display,
                        "mensaje": "Este ticket ya fue facturado."}), 200
    if _ventana_vencida(t):
        return jsonify({"error": "La fecha límite para facturar este ticket ya pasó."}), 400
    from app.facturacion.cfdi import desglose_ticket
    d = desglose_ticket(t)
    return jsonify({
        "estado": t.estado,
        "folio": t.folio_display,
        "fecha": t.fecha.isoformat(),
        "subtotal": d["subtotal"],
        "iva": d["iva"],
        "total": d["total"],
        "conceptos": [{"nombre": c["nombre"], "monto": c["importe"]} for c in d["conceptos"]],
    })


@portal_bp.route("/api/v1/portal/<slug>/facturar", methods=["POST"])
def portal_facturar(slug):
    tenant = _tenant_or_404(slug)
    data = request.get_json() or {}
    t = _resolver_ticket(tenant, data)
    if not t:
        return jsonify({"error": "No encontramos ese ticket."}), 404
    if not _facturacion_habilitada(tenant.id):
        return _facturacion_disabled_response()
    if t.estado not in REFACTURABLE:
        return jsonify({"error": "Este ticket ya fue facturado."}), 400

    try:
        receptor = ReceptorSchema().load(data.get("receptor") or {})
    except ValidationError as e:
        return jsonify({"error": "Datos fiscales incompletos o inválidos",
                        "detalles": e.messages}), 400

    # Validación régimen <-> uso CFDI con el motor probado
    from app.facturacion.cfdi_generator import CFDIGenerator
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=tenant.id).first()
    suc = t.sucursal
    val = CFDIGenerator(signer=None).validar_datos(
        receptor_rfc=receptor["rfc"], receptor_cp=receptor["cp"],
        receptor_regimen=receptor["regimen_fiscal"],
        receptor_uso_cfdi=receptor["uso_cfdi"],
        lugar_expedicion=(suc.codigo_postal if suc else ""),
        conceptos=(_conceptos_cfdi(t, cfg) if cfg else []),
    )
    if not val["valido"]:
        return jsonify({"error": "; ".join(val["errores"])}), 400

    try:
        timbrar_ticket(t, receptor)
    except TimbradoError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"success": True, "uuid": t.uuid,
                    "mensaje": "Factura generada y enviada a tu correo."})
