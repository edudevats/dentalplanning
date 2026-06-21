"""Orquestación de timbrado: arma conceptos del ticket, genera y timbra el CFDI con
el motor probado (CFDIGenerator + FacturacionService) y persiste/notifica.

El PAC y el CSD se mockean en los tests; el timbrado real requiere Finkok + CSD.
"""
import calendar
import logging
from datetime import date, datetime, timezone

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
    hoy = hoy or date.today()
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


def _generar_cfdi(ticket, receptor, cfg, signer):
    """Devuelve (cfdi_obj, xml_str) usando el CFDIGenerator probado."""
    from app.facturacion.cfdi_generator import CFDIGenerator
    gen = CFDIGenerator(signer=signer)
    suc = ticket.sucursal
    return gen.crear_factura(
        serie=ticket.serie or None,
        folio=str(ticket.folio),
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
    return svc.timbrar_factura(cfdi_obj, accept="XML_PDF")


def generar_pdf(cfdi_obj):
    from satcfdi.render import pdf_bytes
    return pdf_bytes(cfdi_obj)


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
    if ticket.estado != TICKET_SIN_TIMBRAR:
        raise TimbradoError("El ticket ya fue timbrado o cancelado.")
    if _ventana_vencida(ticket):
        raise TimbradoError("La ventana de facturación de este ticket ya venció.")

    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=ticket.tenant_id).first()
    if not cfg or not cfg.csd_configurado:
        raise TimbradoError("El consultorio no tiene un CSD configurado.")
    if not cfg.regimen_fiscal:
        raise TimbradoError("Falta el régimen fiscal del emisor.")

    try:
        signer = cargar_signer(cfg)
        cfdi_obj, xml_str = _generar_cfdi(ticket, receptor, cfg, signer)
        result = _timbrar(cfdi_obj)
    except Exception as e:  # noqa: BLE001
        ticket.estado = TICKET_ERROR
        ticket.error_timbrado = str(e)[:500]
        db.session.commit()
        raise TimbradoError(f"Falló el timbrado: {e}")

    if not result.get("success"):
        ticket.estado = TICKET_ERROR
        ticket.error_timbrado = (result.get("message") or "Error de timbrado")[:500]
        db.session.commit()
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

    # PDF (de Finkok si vino; si no, weasyprint) + correo. No rompen el timbrado.
    try:
        pdf = result.get("pdf")
        if not pdf:
            pdf = generar_pdf(cfdi_obj)
        ticket.email_enviado = bool(enviar_factura_email(ticket, pdf, xml_timbrado))
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("Factura timbrada %s pero falló PDF/correo: %s", ticket.uuid, e)
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
        raise TimbradoError(f"Falló la cancelación: {e}")

    if not result.get("success"):
        raise TimbradoError(result.get("message") or "Error al cancelar")

    ticket.estado = TICKET_CANCELADA
    ticket.motivo_cancelacion = motivo
    ticket.uuid_sustitucion = uuid_sustitucion
    ticket.acuse_xml = result.get("acuse")
    ticket.fecha_cancelacion = datetime.now(timezone.utc)
    db.session.commit()
    return ticket
