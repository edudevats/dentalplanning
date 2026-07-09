import base64
import calendar
import secrets
from io import BytesIO
from datetime import date
from PIL import Image, UnidentifiedImageError
from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.auth.models import Tenant
from app.facturacion.models import (
    ConfiguracionFiscal, Sucursal, Ticket,
    TICKET_TIMBRADA, TICKET_CANCELADA,
)
from app.facturacion.schemas import (
    ConfiguracionFiscalSchema, SucursalSchema, TicketSchema, ReceptorSchema,
    CancelacionSchema,
)
from app.facturacion.cfdi import timbrar_ticket, cancelar_ticket, TimbradoError
from app.facturacion.iva import iva_de
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


# Procesamiento del logo al subir: normalizamos a un tamaño/formato controlado
# para que siempre quede chico (sin riesgo de truncado en BD) y se vea consistente.
LOGO_MAX_PX = 512          # lado mayor; suficiente para mostrarlo a 80-220px (incl. retina)
LOGO_MAX_UPLOAD = 8 * 1024 * 1024  # tope del archivo de entrada (8MB) antes de decodificar


def _procesar_logo(raw):
    """Valida que sea imagen, la reescala a LOGO_MAX_PX y la devuelve como PNG.
    Conserva la transparencia. Lanza ValueError si no es una imagen válida."""
    try:
        img = Image.open(BytesIO(raw))
        img.load()  # fuerza el decode real → valida que no esté corrupta
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("archivo no es una imagen válida")
    # Conserva canal alfa si lo tiene; si no, RGB plano
    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX), Image.LANCZOS)  # mantiene proporción
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _logo_b64(cfg):
    """Logo del consultorio como base64 (PNG) para enviarlo al agente de impresión.
    Devuelve None si no hay logo; el agente térmico lo pinta arriba del nombre."""
    if not cfg or not cfg.logo:
        return None
    return base64.b64encode(bytes(cfg.logo)).decode("ascii")


@facturacion_bp.route("/configuracion/logo", methods=["POST"])
@require_auth
@require_role("admin")
def subir_logo():
    logo = request.files.get("logo")
    if not logo:
        return jsonify({"error": "Se requiere el archivo del logo"}), 400
    raw = logo.read()
    if len(raw) > LOGO_MAX_UPLOAD:
        return jsonify({"error": "El logo no debe superar 8MB"}), 400
    try:
        procesado = _procesar_logo(raw)
    except ValueError:
        return jsonify({"error": "El archivo no es una imagen válida (usa PNG o JPG)"}), 400
    cfg = _get_or_create_config()
    cfg.logo = procesado
    db.session.commit()
    return jsonify({"message": "Logo actualizado"})


@facturacion_bp.route("/configuracion/logo", methods=["GET"])
@require_auth
@require_role("admin")
def ver_logo():
    """Devuelve el logo guardado (para la vista previa en Ajustes). 404 si no hay."""
    from flask import Response
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    if not cfg or not cfg.logo:
        return jsonify({"error": "Sin logo"}), 404
    data = bytes(cfg.logo)
    mime = "image/png" if data[:8].startswith(b"\x89PNG") else "application/octet-stream"
    resp = Response(data, mimetype=mime)
    resp.headers["Cache-Control"] = "no-store"  # siempre muestra el actual
    return resp


# ── AGENTE DE IMPRESIÓN (API key por tenant) ──

@facturacion_bp.route("/print-agent/key", methods=["GET"])
@require_auth
def obtener_print_agent_key():
    """Devuelve la API key del agente para este tenant (en claro). Cualquier
    usuario del tenant la necesita para imprimir; no la genera."""
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    if not cfg or not cfg.print_agent_key_cifrada:
        return jsonify({"configured": False, "api_key": None})
    api_key = crypto.decrypt(cfg.print_agent_key_cifrada).decode()
    return jsonify({"configured": True, "api_key": api_key})


@facturacion_bp.route("/print-agent/key/regenerate", methods=["POST"])
@require_auth
@require_role("admin")
def regenerar_print_agent_key():
    """Genera y guarda una nueva API key para el agente (solo admin)."""
    cfg = _get_or_create_config()
    nueva = secrets.token_urlsafe(32)
    cfg.print_agent_key_cifrada = crypto.encrypt(nueva)
    db.session.commit()
    return jsonify({"api_key": nueva})


# ── CATÁLOGOS SAT (autocompletado) ──

@facturacion_bp.route("/catalogos/<tipo>/buscar", methods=["GET"])
@require_auth
def buscar_catalogo(tipo):
    """Autocompletado de catálogos SAT (Régimen / ClaveProdServ / ClaveUnidad).

    tipo ∈ {regimenes, productos, unidades}. Devuelve [{code, description}].
    """
    from app.facturacion.catalogos import buscar, CATALOGS
    if tipo not in CATALOGS:
        return jsonify({"error": "Catálogo no válido"}), 404
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except (TypeError, ValueError):
        limit = 50
    return jsonify(buscar(tipo, request.args.get("q", ""), limit))


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
    # Bloquea el borrado si hay filas que referencian la sucursal (FK). Se filtra
    # por tenant_id además de sucursal_id para no contar datos de otros tenants.
    from app.edr.models import Ingreso
    referencias = ((Ticket, "ticket"), (Ingreso, "ingreso"))
    for modelo, nombre in referencias:
        n = modelo.query.filter_by(tenant_id=g.tenant_id, sucursal_id=suc.id).count()
        if n > 0:
            return jsonify({
                "error": f"No se puede eliminar: la sucursal tiene {n} {nombre}(s) asociado(s). "
                         "Puedes desactivarla en su lugar."
            }), 409
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


@facturacion_bp.route("/tickets/resumen-iva", methods=["GET"])
@require_auth
def resumen_iva_tickets():
    """IVA del mes agregado por estado de ticket (para las cajitas de /facturas).

    Filtra por mes del ticket (Ticket.fecha), igual que el listado. El IVA por
    ticket usa el mismo iva_de() por concepto (0 si el ingreso no es facturable).
    """
    year, month = parse_mes(request.args.get("mes"))
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    naturaleza = cfg.naturaleza_juridica if cfg else None

    tickets = Ticket.query.options(joinedload(Ticket.ingresos)).filter(
        Ticket.tenant_id == g.tenant_id,
        *filtro_mes(Ticket.fecha, year, month),
    ).all()

    iva_generado = iva_reclamado = iva_cancelado = 0.0
    for t in tickets:
        iva_t = sum(
            iva_de(i.monto or 0.0, naturaleza, i.tipo_servicio, i.factura)
            for i in t.ingresos
        )
        if t.estado == TICKET_CANCELADA:
            iva_cancelado += iva_t
        else:
            iva_generado += iva_t
            if t.estado == TICKET_TIMBRADA:
                iva_reclamado += iva_t

    return jsonify({
        "iva_generado": round(iva_generado, 2),
        "iva_reclamado": round(iva_reclamado, 2),
        "iva_pendiente": round(iva_generado - iva_reclamado, 2),
        "iva_cancelado": round(iva_cancelado, 2),
    })


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

    from app.facturacion.cfdi import desglose_ticket
    from datetime import timedelta
    d = desglose_ticket(t)
    ultimo = calendar.monthrange(t.fecha.year, t.fecha.month)[1]
    facturable_hasta = date(t.fecha.year, t.fecha.month, ultimo) + timedelta(days=3)

    return jsonify({
        "logo": _logo_b64(cfg),
        "empresa": (cfg.razon_social if cfg and cfg.razon_social else (tenant.name if tenant else "")),
        "rfc": cfg.rfc if cfg else None,
        "regimen": cfg.regimen_fiscal if cfg else None,
        "sucursal": suc.nombre if suc else None,
        "direccion": suc.direccion if suc else None,
        "codigo_postal": suc.codigo_postal if suc else None,
        "telefono": suc.telefono if suc else None,
        "folio": t.folio_display,
        "fecha": t.fecha.isoformat(),
        "conceptos": [{"nombre": c["nombre"], "base": c["base"],
                       "iva": c["iva"], "monto": c["importe"]} for c in d["conceptos"]],
        "subtotal": d["subtotal"],
        "iva": d["iva"],
        "total": d["total"],
        "exento_iva": d["iva"] == 0,
        "qr_url": qr_url,
        "facturable_hasta": facturable_hasta.isoformat(),
    })


@facturacion_bp.route("/ingresos/<int:ingreso_id>/ticket-simple", methods=["GET"])
@require_auth
def ticket_simple(ingreso_id):
    from app.edr.models import Ingreso
    ing = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    tenant = db.session.get(Tenant, g.tenant_id)
    empresa = (cfg.razon_social if cfg and cfg.razon_social
               else (tenant.name if tenant else ""))
    suc = None
    if ing.sucursal_id:
        suc = Sucursal.query.filter_by(
            id=ing.sucursal_id, tenant_id=g.tenant_id
        ).first()
    return jsonify({
        "facturable": False,
        "logo": _logo_b64(cfg),
        "empresa": empresa,
        "sucursal": suc.nombre if suc else None,
        "direccion": suc.direccion if suc else None,
        "telefono": suc.telefono if suc else None,
        "fecha": ing.fecha.isoformat(),
        "conceptos": [{"nombre": ing.nombre_tratamiento or "Servicio",
                       "monto": round(ing.monto or 0.0, 2)}],
        "total": round(ing.monto or 0.0, 2),
    })


@facturacion_bp.route("/tickets/<int:ticket_id>/timbrar", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista")
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
@require_role("admin", "recepcionista")
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


@facturacion_bp.route("/tickets/<int:ticket_id>/reenviar", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista")
def reenviar(ticket_id):
    t = Ticket.query.filter_by(
        id=ticket_id, tenant_id=g.tenant_id
    ).first_or_404()
    
    if t.estado != TICKET_TIMBRADA:
        return jsonify({"error": "Solo se pueden reenviar facturas timbradas."}), 400

    data = request.get_json() or {}
    dest_email = (data.get("email") or t.email or "").strip()

    if not dest_email:
        return jsonify({"error": "Debe proporcionar una dirección de correo."}), 400

    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    if not cfg:
        return jsonify({"error": "Configuración fiscal no encontrada."}), 400

    # El correo del ticket solo se sobreescribe si el envío tiene éxito: si el
    # usuario escribió un email con typo y el envío falla, no queremos perder la
    # dirección buena. Lo asignamos en memoria y confirmamos con commit al final.
    t.email = dest_email
    try:
        from app.facturacion.cfdi import generar_pdf_de_xml, enviar_factura_email
        pdf = generar_pdf_de_xml(t.xml, logo=cfg.logo)
        t.email_enviado = bool(enviar_factura_email(t, pdf, t.xml))
    except Exception as e:
        db.session.rollback()  # descarta el cambio de email
        current_app.logger.exception("Error al reenviar factura del ticket %s", ticket_id)
        return jsonify({"error": f"Error al reenviar factura: {str(e)}"}), 500

    if not t.email_enviado:
        db.session.rollback()  # descarta el cambio de email
        current_app.logger.error(
            "Reenvío de factura del ticket %s: el correo no se envió (SMTP)", ticket_id)
        return jsonify({"error": "No se pudo enviar el correo. Verifique la configuración de SMTP."}), 500

    db.session.commit()
    return jsonify(TicketSchema().dump(t))

