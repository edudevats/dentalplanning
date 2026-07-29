"""Correos del módulo de cobranza."""
from html import escape
from urllib.parse import quote

from flask import current_app

from app.email.service import send_email, send_email_with_attachments


def _email_paciente(cot):
    email = (cot.paciente.email or "").strip() if cot.paciente else ""
    if not email:
        from app.cobranza.services import CobranzaError
        raise CobranzaError(
            "El paciente no tiene correo registrado. Agrégalo en su ficha del CRM."
        )
    return email


def enviar_cotizacion(cot):
    """Manda la cotización en PDF al correo del paciente."""
    from app.cobranza.pdf import nombre_archivo, pdf_cotizacion

    destino = _email_paciente(cot)
    filename = nombre_archivo(cot)
    nombre = escape(cot.paciente.nombre)
    folio = escape(cot.folio)
    total = f"${cot.total:,.2f}"
    vigencia = cot.valida_hasta.strftime("%d/%m/%Y")
    html = (
        f"<p>Hola {nombre},</p>"
        f"<p>Adjuntamos la cotización <strong>{folio}</strong> de tu "
        f"tratamiento, por un total de <strong>{total}</strong>.</p>"
        f"<p>La cotización es válida hasta el <strong>{vigencia}</strong>.</p>"
        "<p>Cualquier duda, quedamos a tus órdenes.</p>"
    )
    texto = (
        f"Hola {cot.paciente.nombre}, adjuntamos la cotización {cot.folio} "
        f"por un total de {total}. Válida hasta {vigencia}."
    )
    return send_email_with_attachments(
        destino,
        f"Cotización {cot.folio}",
        html,
        [(filename, pdf_cotizacion(cot), "application/pdf")],
        text_body=texto,
    )


def enviar_estado_cuenta(cot, datos):
    """Manda el estado de cuenta en el correo y como PDF adjunto."""
    from app.cobranza.pdf import nombre_archivo, pdf_estado_cuenta

    destino = _email_paciente(cot)
    filename = nombre_archivo(cot, "Estado-de-cuenta")
    nombre = escape(cot.paciente.nombre)
    folio = escape(cot.folio)
    texto_estado = datos["texto"]
    estado_html = escape(texto_estado).replace("\n", "<br>")
    html = (
        f"<p>Hola {nombre},</p>"
        f"<p>Te compartimos el estado de cuenta de tu tratamiento "
        f"<strong>{folio}</strong>.</p>"
        f'<div style="padding:16px;background:#f8fafc;border-radius:8px;'
        f'line-height:1.5">{estado_html}</div>'
        "<p>También encontrarás el documento completo en PDF adjunto.</p>"
        "<p>Cualquier duda, quedamos a tus órdenes.</p>"
    )
    return send_email_with_attachments(
        destino,
        f"Estado de cuenta {cot.folio}",
        html,
        [(filename, pdf_estado_cuenta(cot, datos), "application/pdf")],
        text_body=texto_estado,
    )


def enviar_link_facturacion(cot, ticket):
    """Manda el enlace funcional del portal una vez confirmado el ticket."""
    if ticket is None:
        return False
    from app.auth.models import Tenant
    from app.cobranza.services import CobranzaError
    from app.extensions import db

    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    if not base:
        raise CobranzaError(
            "APP_BASE_URL no está configurado; no se puede generar un enlace público"
        )

    destino = _email_paciente(cot)
    tenant = db.session.get(Tenant, cot.tenant_id)
    if not tenant:
        raise CobranzaError("Consultorio no encontrado")
    url = (
        f"{base}/portal/{quote(tenant.slug, safe='')}"
        f"?t={quote(ticket.token or '', safe='')}"
    )
    nombre = escape(cot.paciente.nombre)
    url_html = escape(url, quote=True)
    html = (
        f"<p>Hola {nombre},</p>"
        "<p>¡Tu tratamiento quedó pagado por completo! Si necesitas factura, "
        "puedes generarla tú mismo desde este enlace:</p>"
        f'<p><a href="{url_html}">{url_html}</a></p>'
        "<p>Sólo necesitarás tus datos fiscales.</p>"
    )
    texto = (
        f"Hola {cot.paciente.nombre}, tu tratamiento quedó pagado por completo. "
        f"Si necesitas factura, genérala aquí: {url}"
    )
    return send_email(
        destino,
        "Tu factura está lista para generarse",
        html,
        texto,
    )
