import calendar
from datetime import date
from flask import Blueprint, request, jsonify, g, current_app
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.auth.models import Tenant
from app.facturacion.models import ConfiguracionFiscal, Sucursal, Ticket
from app.facturacion.schemas import (
    ConfiguracionFiscalSchema, SucursalSchema, TicketSchema, ReceptorSchema,
    CancelacionSchema,
)
from app.facturacion.cfdi import timbrar_ticket, cancelar_ticket, TimbradoError
from app.engine.accounting import parse_mes, filtro_mes
from app.facturacion import crypto
from app.facturacion.csd import validar_csd, validar_fiel, CSDInvalido

facturacion_bp = Blueprint("facturacion", __name__, url_prefix="/api/v1/facturacion")


def _get_or_create_config():
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    if not cfg:
        cfg = ConfiguracionFiscal(tenant_id=g.tenant_id)
        db.session.add(cfg)
        db.session.commit()
    return cfg


# ── CONFIGURACIÓN FISCAL ──

@facturacion_bp.route("/configuracion", methods=["GET"])
@require_auth
def obtener_configuracion():
    cfg = _get_or_create_config()
    return jsonify(ConfiguracionFiscalSchema().dump(cfg))


@facturacion_bp.route("/configuracion", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_configuracion():
    cfg = _get_or_create_config()
    data = ConfiguracionFiscalSchema(partial=True).load(request.get_json() or {})
    for k, v in data.items():
        setattr(cfg, k, v)
    db.session.commit()
    return jsonify(ConfiguracionFiscalSchema().dump(cfg))


@facturacion_bp.route("/configuracion/csd", methods=["POST"])
@require_auth
@require_role("admin")
def subir_csd():
    cer = request.files.get("cer")
    key = request.files.get("key")
    password = request.form.get("password", "")
    if not cer or not key or not password:
        return jsonify({"error": "Se requieren los archivos .cer, .key y la contraseña"}), 400

    cer_bytes = cer.read()
    key_bytes = key.read()
    try:
        meta = validar_csd(cer_bytes, key_bytes, password)
    except CSDInvalido as e:
        return jsonify({"error": str(e)}), 400

    cfg = _get_or_create_config()
    cfg.csd_cer = cer_bytes
    cfg.csd_key_cifrada = crypto.encrypt(key_bytes)
    cfg.csd_password_cifrada = crypto.encrypt(password)
    cfg.csd_no_certificado = meta["no_certificado"]
    cfg.csd_valido_desde = meta["valido_desde"]
    cfg.csd_valido_hasta = meta["valido_hasta"]
    if not cfg.rfc:
        cfg.rfc = meta["rfc"]
    if not cfg.razon_social:
        cfg.razon_social = meta["razon_social"]
    db.session.commit()
    return jsonify(ConfiguracionFiscalSchema().dump(cfg))


@facturacion_bp.route("/configuracion/fiel", methods=["POST"])
@require_auth
@require_role("admin")
def subir_fiel():
    cer = request.files.get("cer")
    key = request.files.get("key")
    password = request.form.get("password", "")
    if not cer or not key or not password:
        return jsonify({"error": "Se requieren los archivos .cer, .key y la contraseña"}), 400
    cer_bytes, key_bytes = cer.read(), key.read()
    try:
        meta = validar_fiel(cer_bytes, key_bytes, password)
    except CSDInvalido as e:
        return jsonify({"error": str(e)}), 400
    cfg = _get_or_create_config()
    cfg.fiel_cer = cer_bytes
    cfg.fiel_key_cifrada = crypto.encrypt(key_bytes)
    cfg.fiel_password_cifrada = crypto.encrypt(password)
    cfg.fiel_no_certificado = meta["no_certificado"]
    cfg.fiel_valido_desde = meta["valido_desde"]
    cfg.fiel_valido_hasta = meta["valido_hasta"]
    db.session.commit()
    return jsonify(ConfiguracionFiscalSchema().dump(cfg))


@facturacion_bp.route("/configuracion/logo", methods=["POST"])
@require_auth
@require_role("admin")
def subir_logo():
    logo = request.files.get("logo")
    if not logo:
        return jsonify({"error": "Se requiere el archivo del logo"}), 400
    cfg = _get_or_create_config()
    cfg.logo = logo.read()
    db.session.commit()
    return jsonify({"message": "Logo actualizado"})


# ── SUCURSALES ──

@facturacion_bp.route("/sucursales", methods=["GET"])
@require_auth
def listar_sucursales():
    sucs = Sucursal.query.filter_by(tenant_id=g.tenant_id).order_by(Sucursal.nombre).all()
    return jsonify(SucursalSchema(many=True).dump(sucs))


@facturacion_bp.route("/sucursales", methods=["POST"])
@require_auth
@require_role("admin")
def crear_sucursal():
    data = SucursalSchema().load(request.get_json() or {})
    suc = Sucursal(tenant_id=g.tenant_id, **data)
    db.session.add(suc)
    db.session.commit()
    return jsonify(SucursalSchema().dump(suc)), 201


@facturacion_bp.route("/sucursales/<int:sucursal_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_sucursal(sucursal_id):
    suc = Sucursal.query.filter_by(
        id=sucursal_id, tenant_id=g.tenant_id
    ).first_or_404()
    data = SucursalSchema(partial=True).load(request.get_json() or {})
    for k, v in data.items():
        setattr(suc, k, v)
    db.session.commit()
    return jsonify(SucursalSchema().dump(suc))


@facturacion_bp.route("/sucursales/<int:sucursal_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_sucursal(sucursal_id):
    suc = Sucursal.query.filter_by(
        id=sucursal_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(suc)
    db.session.commit()
    return jsonify({"message": "Sucursal eliminada"})


# ── TICKETS ──

@facturacion_bp.route("/tickets", methods=["GET"])
@require_auth
def listar_tickets():
    year, month = parse_mes(request.args.get("mes"))
    tickets = Ticket.query.filter(
        Ticket.tenant_id == g.tenant_id,
        *filtro_mes(Ticket.fecha, year, month),
    ).order_by(Ticket.fecha.desc(), Ticket.folio.desc()).all()
    return jsonify(TicketSchema(many=True).dump(tickets))


@facturacion_bp.route("/tickets/<int:ticket_id>", methods=["GET"])
@require_auth
def obtener_ticket(ticket_id):
    t = Ticket.query.filter_by(
        id=ticket_id, tenant_id=g.tenant_id
    ).first_or_404()
    data = TicketSchema().dump(t)
    data["sucursal_nombre"] = t.sucursal.nombre if t.sucursal else None
    data["conceptos"] = [
        {
            "nombre_tratamiento": i.nombre_tratamiento or "Tratamiento",
            "monto": round(i.monto or 0.0, 2),
        }
        for i in t.ingresos
    ]
    return jsonify(data)


@facturacion_bp.route("/tickets/<int:ticket_id>/impresion", methods=["GET"])
@require_auth
def ticket_impresion(ticket_id):
    t = Ticket.query.filter_by(
        id=ticket_id, tenant_id=g.tenant_id
    ).first_or_404()
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    suc = t.sucursal
    tenant = db.session.get(Tenant, g.tenant_id)

    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    slug = tenant.slug if tenant else ""
    qr_url = f"{base}/{slug}?t={t.token}" if t.token else f"{base}/{slug}"

    ultimo = calendar.monthrange(t.fecha.year, t.fecha.month)[1]
    facturable_hasta = date(t.fecha.year, t.fecha.month, ultimo)

    return jsonify({
        "empresa": (cfg.razon_social if cfg and cfg.razon_social else (tenant.name if tenant else "")),
        "rfc": cfg.rfc if cfg else None,
        "regimen": cfg.regimen_fiscal if cfg else None,
        "sucursal": suc.nombre if suc else None,
        "direccion": suc.direccion if suc else None,
        "codigo_postal": suc.codigo_postal if suc else None,
        "telefono": suc.telefono if suc else None,
        "folio": t.folio_display,
        "fecha": t.fecha.isoformat(),
        "conceptos": [
            {"nombre": i.nombre_tratamiento or "Tratamiento",
             "monto": round(i.monto or 0.0, 2)}
            for i in t.ingresos
        ],
        "total": round(t.total or 0.0, 2),
        "exento_iva": True,
        "qr_url": qr_url,
        "facturable_hasta": facturable_hasta.isoformat(),
    })


@facturacion_bp.route("/tickets/<int:ticket_id>/timbrar", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def timbrar(ticket_id):
    t = Ticket.query.filter_by(
        id=ticket_id, tenant_id=g.tenant_id
    ).first_or_404()
    receptor = ReceptorSchema().load(request.get_json() or {})
    try:
        timbrar_ticket(t, receptor)
    except TimbradoError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(TicketSchema().dump(t))


@facturacion_bp.route("/tickets/<int:ticket_id>/cancelar", methods=["POST"])
@require_auth
@require_role("admin")
def cancelar(ticket_id):
    t = Ticket.query.filter_by(
        id=ticket_id, tenant_id=g.tenant_id
    ).first_or_404()
    data = CancelacionSchema().load(request.get_json() or {})
    try:
        cancelar_ticket(t, data["motivo"], data.get("uuid_sustitucion"))
    except TimbradoError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(TicketSchema().dump(t))
