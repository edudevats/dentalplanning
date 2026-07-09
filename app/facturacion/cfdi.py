"""Orquestación de timbrado: arma conceptos del ticket, genera y timbra el CFDI con
el motor probado (CFDIGenerator + FacturacionService) y persiste/notifica.

El PAC y el CSD se mockean en los tests; el timbrado real requiere Finkok + CSD.
"""
import calendar
import logging
from datetime import date, datetime, timezone

from app.facturacion.timezone_helper import get_today

from flask import current_app

from app.extensions import db
from app.facturacion import crypto
from app.facturacion.models import (
    ConfiguracionFiscal, TICKET_SIN_TIMBRAR, TICKET_TIMBRADA, TICKET_ERROR,
    TICKET_CANCELADA, TICKET_EN_PROCESO_CANCELACION,
)
from app.facturacion.pac_service import FacturacionService

logger = logging.getLogger(__name__)


class TimbradoError(Exception):
    """Error de negocio al timbrar (ventana vencida, sin CSD, fallo del PAC, etc.)."""


def _ventana_vencida(ticket, hoy=None):
    from datetime import timedelta
    hoy = hoy or get_today()
    ultimo = calendar.monthrange(ticket.fecha.year, ticket.fecha.month)[1]
    limite = date(ticket.fecha.year, ticket.fecha.month, ultimo) + timedelta(days=3)
    return hoy > limite


def cargar_signer(cfg):
    """Carga el Signer del CSD descifrando key y contraseña (desde la BD)."""
    from satcfdi.models import Signer
    key = crypto.decrypt(cfg.csd_key_cifrada)
    password = crypto.decrypt(cfg.csd_password_cifrada).decode()
    return Signer.load(certificate=cfg.csd_cer, key=key, password=password)


def cargar_signer_fiel(cfg):
    """Carga el Signer de la FIEL (e.firma) descifrando key y contraseña."""
    from satcfdi.models import Signer
    key = crypto.decrypt(cfg.fiel_key_cifrada)
    password = crypto.decrypt(cfg.fiel_password_cifrada).decode()
    return Signer.load(certificate=cfg.fiel_cer, key=key, password=password)


def _conceptos_cfdi(ticket, cfg):
    """Conceptos del CFDI: cada uno con valor_unitario = monto (base) y Tasa/Exento."""
    from app.facturacion.iva import grava_iva, TASA_IVA
    naturaleza = cfg.naturaleza_juridica if cfg else None
    conceptos = []
    for ing in ticket.ingresos:
        c = {
            "clave_prod_serv": cfg.clave_prod_serv_default or "85121800",
            "clave_unidad": cfg.clave_unidad_default or "E48",
            "unidad": "Servicio",
            "cantidad": 1,
            "descripcion": ing.nombre_tratamiento or "Tratamiento dental",
            "valor_unitario": float(ing.monto or 0),
            "objeto_imp": "02",
        }
        if grava_iva(naturaleza, ing.tipo_servicio, ing.factura):
            c["tipo_factor"] = "Tasa"
            c["tasa_iva"] = TASA_IVA
        else:
            c["tipo_factor"] = "Exento"
        conceptos.append(c)
    return conceptos


def desglose_ticket(ticket):
    """Devuelve {subtotal, iva, total, conceptos:[{nombre, base, iva, importe}]}."""
    from app.facturacion.models import ConfiguracionFiscal
    from app.facturacion.iva import iva_de
    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=ticket.tenant_id).first()
    naturaleza = cfg.naturaleza_juridica if cfg else None
    conceptos, subtotal, iva_total = [], 0.0, 0.0
    for i in ticket.ingresos:
        base = round(i.monto or 0.0, 2)
        iva = iva_de(base, naturaleza, i.tipo_servicio, i.factura)
        subtotal += base
        iva_total += iva
        conceptos.append({
            "nombre": i.nombre_tratamiento or "Tratamiento",
            "base": base, "iva": round(iva, 2), "importe": round(base + iva, 2),
        })
    return {"subtotal": round(subtotal, 2), "iva": round(iva_total, 2),
            "total": round(subtotal + iva_total, 2), "conceptos": conceptos}


def _generar_cfdi(ticket, receptor, cfg, signer, fecha=None):
    """Devuelve (cfdi_obj, xml_str) usando el CFDIGenerator probado.

    `fecha` (aware) fija la emisión del comprobante; si es None el generador usa
    la hora actual. Se pasa para que los reintentos produzcan el mismo sello.
    """
    from app.facturacion.cfdi_generator import CFDIGenerator
    gen = CFDIGenerator(signer=signer)
    suc = ticket.sucursal
    return gen.crear_factura(
        serie=ticket.serie or None,
        folio=str(ticket.folio),
        fecha=fecha,
        forma_pago="01",
        metodo_pago="PUE",
        lugar_expedicion=(suc.codigo_postal if suc else ""),
        emisor_regimen=cfg.regimen_fiscal,
        receptor_rfc=receptor["rfc"],
        receptor_nombre=receptor["nombre"],
        receptor_uso_cfdi=receptor["uso_cfdi"],
        receptor_regimen=receptor["regimen_fiscal"],
        receptor_cp=receptor["cp"],
        conceptos=_conceptos_cfdi(ticket, cfg),
    )


def _timbrar(cfdi_obj):
    """Timbra con Finkok (FacturacionService). Devuelve el dict de resultado."""
    from app.facturacion.pac_service import FacturacionService
    svc = FacturacionService(
        finkok_username=current_app.config.get("FINKOK_USERNAME", ""),
        finkok_password=current_app.config.get("FINKOK_PASSWORD", ""),
        environment=current_app.config.get("FINKOK_ENVIRONMENT", "TEST"),
    )
    # Finkok solo devuelve XML al timbrar (no soporta accept=PDF/XML_PDF).
    # El PDF se genera localmente a partir del XML timbrado (ver generar_pdf_de_xml).
    return svc.timbrar_factura(cfdi_obj, accept="XML")


def generar_pdf(cfdi_obj):
    from satcfdi.render import pdf_bytes
    return pdf_bytes(cfdi_obj)


def _logo_mime(logo_bytes):
    """Infiere el mime del logo a partir de sus magic bytes (no se guarda el tipo)."""
    if logo_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if logo_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if logo_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


def generar_pdf_de_xml(xml_str, logo=None):
    """Convierte el XML ya timbrado (con TFD/UUID/QR) a PDF con weasyprint.

    Replica el render del sistema de facturación funcional: satcfdi arma el HTML del
    comprobante y weasyprint lo convierte a PDF, inyectando el logo del consultorio.
    """
    import base64
    import weasyprint
    from satcfdi.cfdi import CFDI
    from satcfdi import render as cfdi_render
    from app.facturacion.xml_safety import assert_safe_xml

    xml_bytes = xml_str.encode("utf-8") if isinstance(xml_str, str) else xml_str
    assert_safe_xml(xml_bytes)
    cfdi = CFDI.from_string(xml_bytes)
    html = cfdi_render.html_str(cfdi)

    if logo:
        logo_b64 = base64.b64encode(logo).decode("ascii")
        logo_tag = (
            '<div style="text-align:center;padding:8px 0;">'
            f'<img src="data:{_logo_mime(logo)};base64,{logo_b64}" '
            'style="max-height:90px;max-width:280px;"/></div>'
        )
        if "<body>" in html:
            html = html.replace("<body>", "<body>" + logo_tag, 1)
        else:
            html = logo_tag + html

    return weasyprint.HTML(string=html).write_pdf(stylesheets=[cfdi_render.PDF_CSS])


def enviar_factura_email(ticket, pdf, xml_str):
    from app.email.service import send_email_with_attachments, render_factura_email
    html, text = render_factura_email(ticket)
    return send_email_with_attachments(
        ticket.email, f"Tu factura {ticket.uuid}", html,
        [(f"{ticket.uuid}.pdf", pdf, "application/pdf"),
         (f"{ticket.uuid}.xml", xml_str.encode("utf-8"), "application/xml")],
        text_body=text,
    )


def timbrar_ticket(ticket, receptor):
    """Genera, timbra (Finkok), guarda el CFDI y envía el correo.

    Lanza TimbradoError ante reglas de negocio o fallo del PAC (deja estado='error').
    """
    # 'error' es re-intentable, pero OJO con las facturas duplicadas: si un intento
    # previo timbró y solo se perdió la respuesta (timeout), reintentar NO debe
    # emitir un segundo CFDI. Fijamos la fecha del comprobante en el primer intento
    # y la reutilizamos, para que el reintento genere un XML byte-idéntico (mismo
    # sello) que Finkok deduplica en lugar de asignar un UUID nuevo.
    if ticket.estado not in (TICKET_SIN_TIMBRAR, TICKET_ERROR):
        raise TimbradoError("El ticket ya fue timbrado o cancelado.")
    if _ventana_vencida(ticket):
        raise TimbradoError("La ventana de facturación de este ticket ya venció.")

    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=ticket.tenant_id).first()
    if not cfg or not cfg.csd_configurado:
        raise TimbradoError("El consultorio no tiene un CSD configurado.")
    if not cfg.regimen_fiscal:
        raise TimbradoError("Falta el régimen fiscal del emisor.")

    # Bloquea la fecha de emisión la primera vez (aware UTC, con la tolerancia de
    # 5 min del SAT) y persístela antes de timbrar para que sobreviva a un crash.
    if ticket.cfdi_fecha is None:
        from datetime import timedelta
        ticket.cfdi_fecha = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.session.commit()
    fecha_cfdi = ticket.cfdi_fecha
    if fecha_cfdi.tzinfo is None:  # la BD la devuelve naive → es UTC
        fecha_cfdi = fecha_cfdi.replace(tzinfo=timezone.utc)

    try:
        signer = cargar_signer(cfg)
        cfdi_obj, xml_str = _generar_cfdi(ticket, receptor, cfg, signer, fecha=fecha_cfdi)
        result = _timbrar(cfdi_obj)
    except Exception as e:  # noqa: BLE001
        logger.exception("Falló el timbrado del ticket %s", ticket.id)
        ticket.estado = TICKET_ERROR
        ticket.error_timbrado = str(e)[:500]
        db.session.commit()
        raise TimbradoError(f"Falló el timbrado: {e}")

    if not result.get("success"):
        ticket.estado = TICKET_ERROR
        ticket.error_timbrado = (result.get("message") or "Error de timbrado")[:500]
        db.session.commit()
        logger.error("PAC rechazó el timbrado del ticket %s: %s",
                     ticket.id, ticket.error_timbrado)
        raise TimbradoError(ticket.error_timbrado)

    xml_timbrado = result.get("xml") or xml_str
    if isinstance(xml_timbrado, (bytes, bytearray)):
        xml_timbrado = xml_timbrado.decode("utf-8")

    ticket.estado = TICKET_TIMBRADA
    ticket.uuid = result["uuid"]
    ticket.fecha_timbrado = datetime.now(timezone.utc)
    ticket.xml = xml_timbrado
    ticket.receptor_rfc = receptor["rfc"]
    ticket.receptor_nombre = receptor["nombre"]
    ticket.uso_cfdi = receptor["uso_cfdi"]
    ticket.regimen_receptor = receptor["regimen_fiscal"]
    ticket.cp_receptor = receptor["cp"]
    ticket.email = receptor["email"]
    ticket.forma_pago = "01"
    ticket.metodo_pago = "PUE"
    ticket.error_timbrado = None
    db.session.commit()

    # PDF a partir del XML timbrado (incluye UUID/sello SAT/QR) + correo.
    # No rompen el timbrado: si fallan, la factura ya quedó timbrada.
    try:
        pdf = result.get("pdf") or generar_pdf_de_xml(xml_timbrado, logo=cfg.logo)
        ticket.email_enviado = bool(enviar_factura_email(ticket, pdf, xml_timbrado))
        db.session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Factura timbrada %s pero falló PDF/correo", ticket.uuid)
        ticket.email_enviado = False
        db.session.commit()

    return ticket


def cancelar_ticket(ticket, motivo, uuid_sustitucion=None):
    """Cancela el CFDI timbrado ante Finkok con la FIEL del consultorio.

    Lanza TimbradoError ante reglas de negocio o fallo del PAC.
    """
    if ticket.estado not in (TICKET_TIMBRADA, TICKET_EN_PROCESO_CANCELACION):
        raise TimbradoError("Solo se puede cancelar una factura timbrada.")
    if not (ticket.xml and ticket.uuid):
        raise TimbradoError("La factura no tiene XML/UUID para cancelar.")
    if motivo == "01" and not uuid_sustitucion:
        raise TimbradoError("El motivo 01 requiere el UUID de la factura que sustituye.")

    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=ticket.tenant_id).first()
    if not cfg or not cfg.fiel_configurada:
        raise TimbradoError("Sube la e.firma (FIEL) del consultorio para poder cancelar.")

    try:
        fiel = cargar_signer_fiel(cfg)
        svc = FacturacionService(
            finkok_username=current_app.config.get("FINKOK_USERNAME", ""),
            finkok_password=current_app.config.get("FINKOK_PASSWORD", ""),
            environment=current_app.config.get("FINKOK_ENVIRONMENT", "TEST"),
            signer=fiel,
        )
        result = svc.cancelar_factura(ticket.xml, motivo, uuid_sustitucion)
    except Exception as e:  # noqa: BLE001
        logger.exception("Falló la cancelación del ticket %s (uuid=%s)",
                         ticket.id, ticket.uuid)
        raise TimbradoError(f"Falló la cancelación: {e}")

    if not result.get("success"):
        logger.error("PAC rechazó la cancelación del ticket %s (uuid=%s): %s",
                     ticket.id, ticket.uuid, result.get("message"))
        raise TimbradoError(result.get("message") or "Error al cancelar")

    ticket.estado = TICKET_CANCELADA
    ticket.motivo_cancelacion = motivo
    ticket.uuid_sustitucion = uuid_sustitucion
    ticket.acuse_xml = result.get("acuse")
    ticket.fecha_cancelacion = datetime.now(timezone.utc)
    db.session.commit()
    return ticket
