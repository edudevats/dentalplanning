import calendar
import secrets
from datetime import date, datetime, timezone
from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.auth.models import Tenant
from app.configuracion.logo import logo_b64, logo_bytes
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
from app.facturacion import crypto, registro_clientes
from app.facturacion.csd import validar_csd, validar_fiel, CSDInvalido

facturacion_bp = Blueprint("facturacion", __name__, url_prefix="/api/v1/facturacion")


def _get_or_create_config():
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=g.tenant_id).first()
    if not cfg:
        cfg = ConfiguracionFiscal(tenant_id=g.tenant_id)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _config_payload(cfg):
    data = ConfiguracionFiscalSchema().dump(cfg)
    data["tarifas_facturacion"] = {
        "cuota_mensual": float(
            current_app.config.get("FACTURACION_MONTHLY_FEE", 100)
        ),
        "costo_por_timbre": float(
            current_app.config.get("FACTURACION_STAMP_FEE", 2)
        ),
    }
    return data


# ── CONFIGURACIÓN FISCAL ──

@facturacion_bp.route("/configuracion", methods=["GET"])
@require_auth
def obtener_configuracion():
    cfg = _get_or_create_config()
    return jsonify(_config_payload(cfg))


@facturacion_bp.route("/configuracion", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_configuracion():
    cfg = _get_or_create_config()
    data = ConfiguracionFiscalSchema(partial=True).load(request.get_json() or {})
    requested_active = data.pop("facturacion_activa", None)
    for k, v in data.items():
        setattr(cfg, k, v)
    if requested_active is not None and bool(requested_active) != bool(cfg.facturacion_activa):
        cfg.facturacion_activa = bool(requested_active)
        if cfg.facturacion_activa:
            cfg.facturacion_activada_at = datetime.now(timezone.utc)
            cfg.facturacion_cargo_pendiente = True
    db.session.commit()
    return jsonify(_config_payload(cfg))


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
    return jsonify(_config_payload(cfg))


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
    return jsonify(_config_payload(cfg))


def _rfc_ya_existe_en_finkok(message):
    m = (message or "").lower()
    return any(s in m for s in (
        "already", "exist", "ya existe", "ya registrado", "registered"))


@facturacion_bp.route("/configuracion/finkok/registrar", methods=["POST"])
@require_auth
@require_role("admin")
def registrar_finkok():
    cfg = _get_or_create_config()
    if not cfg.csd_configurado:
        return jsonify({"error": "Configura tu CSD primero"}), 400
    if not cfg.rfc:
        return jsonify({"error": "Configura el RFC del emisor primero"}), 400

    username = current_app.config.get("FINKOK_USERNAME", "")
    password = current_app.config.get("FINKOK_PASSWORD", "")
    if not username or not password:
        return jsonify({"error": "Credenciales de Finkok no configuradas"}), 500
    environment = current_app.config.get("FINKOK_ENVIRONMENT", "test")

    cer_bytes = cfg.csd_cer
    key_bytes = crypto.decrypt(cfg.csd_key_cifrada)
    passphrase = crypto.decrypt(cfg.csd_password_cifrada).decode()

    if cfg.finkok_rfc_registrado == cfg.rfc:
        res = registro_clientes.editar_cliente(
            cfg.rfc, cer_bytes, key_bytes, passphrase,
            username=username, password=password, environment=environment,
            status="A",
        )
    else:
        res = registro_clientes.agregar_cliente(
            cfg.rfc, cer_bytes, key_bytes, passphrase,
            username=username, password=password, environment=environment,
            type_user="O",
        )
        if not res["success"] and _rfc_ya_existe_en_finkok(res["message"]):
            # Ya estaba dado de alta: deja el estado listo para 'edit'.
            cfg.finkok_rfc_registrado = cfg.rfc
            db.session.commit()
            return jsonify({
                "success": False,
                "message": "El RFC ya estaba registrado en Finkok. "
                           "Usa 'Actualizar CSD en Finkok' para renovarlo.",
            })

    if res["success"]:
        cfg.finkok_registrado_at = datetime.now(timezone.utc)
        cfg.finkok_rfc_registrado = cfg.rfc
        db.session.commit()

    return jsonify({"success": res["success"], "message": res["message"]})


@facturacion_bp.route("/configuracion/finkok/estado", methods=["GET"])
@require_auth
@require_role("admin")
def estado_finkok():
    cfg = _get_or_create_config()
    if not cfg.rfc:
        return jsonify({"configurado": False, "message": "Sin RFC configurado"})

    username = current_app.config.get("FINKOK_USERNAME", "")
    password = current_app.config.get("FINKOK_PASSWORD", "")
    if not username or not password:
        return jsonify({"configurado": False,
                        "message": "Credenciales de Finkok no configuradas"})
    environment = current_app.config.get("FINKOK_ENVIRONMENT", "test")

    res = registro_clientes.consultar_cliente(
        cfg.rfc, username=username, password=password, environment=environment,
    )
    return jsonify({
        "configurado": True,
        "registrado_at": cfg.finkok_registrado_at.isoformat()
        if cfg.finkok_registrado_at else None,
        "success": res["success"],
        "status": res.get("status"),
        "counter": res.get("counter"),
        "credit": res.get("credit"),
        "message": res.get("message", ""),
    })


# El logo del consultorio vive en ConfigConsultorio y se sube/consulta desde
# /api/v1/config/logo. Aquí sólo se lee para el ticket y el PDF del CFDI.


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
    #
    # TurnoCaja, GastoOperativo y CorteCaja entraron a la lista junto con
    # Ticket e Ingreso: los tres tienen FK a `sucursales.id` desde antes, pero
    # el backfill de la sucursal obligatoria (turno-de-caja) fue lo que los
    # llenó de verdad. Antes, en un tenant de una sola sucursal, esas columnas
    # vivían en NULL y nunca estorbaban un borrado; ahora todos los turnos,
    # gastos y cortes apuntan a la sucursal, así que borrar una con turnos pero
    # sin ingresos violaría la FK y tiraría un 500 en vez de este 409.
    from app.caja.models import CorteCaja, TurnoCaja
    from app.edr.models import GastoOperativo, Ingreso
    referencias = (
        (Ticket, "ticket"), (Ingreso, "ingreso"), (TurnoCaja, "turno"),
        (GastoOperativo, "gasto"), (CorteCaja, "corte"),
    )
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

    tickets = Ticket.query.options(joinedload(Ticket.ingresos)).filter(
        Ticket.tenant_id == g.tenant_id,
        *filtro_mes(Ticket.fecha, year, month),
    ).all()

    iva_generado = iva_reclamado = iva_cancelado = 0.0
    for t in tickets:
        iva_t = sum(
            iva_de(i.monto or 0.0, i.tipo_servicio, i.factura)
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
        "logo": logo_b64(g.tenant_id),
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
        "logo": logo_b64(g.tenant_id),
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
        pdf = generar_pdf_de_xml(t.xml, logo=logo_bytes(g.tenant_id))
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

