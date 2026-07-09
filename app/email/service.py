import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from flask import current_app


class EmailError(Exception):
    pass


def _smtp_server(cfg):
    """Abre y devuelve una conexión SMTP ya autenticada (SSL directo o STARTTLS,
    según config). El llamador es responsable de garantizar que SMTP_HOST existe
    y de cerrar el server (usar `with`)."""
    host = cfg.get("SMTP_HOST", "")
    port = cfg.get("SMTP_PORT", 587)
    user = cfg.get("SMTP_USER", "")
    password = cfg.get("SMTP_PASS", "")
    use_tls = cfg.get("SMTP_USE_TLS", True)
    use_ssl = cfg.get("SMTP_USE_SSL", False) or port == 465

    if use_ssl:
        server = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
    if user and password:
        server.login(user, password)
    return server


def send_email(to_address, subject, html_body, text_body=None):
    """Send an email via SMTP. Returns True on success, raises EmailError on failure."""
    cfg = current_app.config
    if not cfg.get("SMTP_HOST", ""):
        current_app.logger.warning("Email skipped (SMTP_HOST not configured): to=%s subject=%s",
                                   to_address, subject)
        return False

    from_addr = cfg.get("SMTP_FROM") or "no-reply@dentalplanning.mx"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with _smtp_server(cfg) as server:
            server.sendmail(from_addr, [to_address], msg.as_string())
        current_app.logger.info("Email sent to=%s subject=%s", to_address, subject)
        return True
    except Exception as e:
        current_app.logger.error("Email send failed to=%s subject=%s err=%s",
                                 to_address, subject, e)
        raise EmailError(str(e))


def send_email_with_attachments(to_address, subject, html_body, attachments,
                                text_body=None):
    """Envía un correo con adjuntos. `attachments` = lista de (filename, bytes, mimetype).
    Retorna True si se envió, False si SMTP no está configurado; lanza EmailError si falla.
    """
    cfg = current_app.config
    if not cfg.get("SMTP_HOST", ""):
        current_app.logger.warning(
            "Email (con adjuntos) omitido (SMTP_HOST no configurado): to=%s subject=%s",
            to_address, subject)
        return False

    from_addr = cfg.get("SMTP_FROM") or "no-reply@dentalplanning.mx"
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address

    alt = MIMEMultipart("alternative")
    if text_body:
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    for filename, content, mimetype in attachments:
        subtype = mimetype.split("/", 1)[-1] if "/" in mimetype else mimetype
        part = MIMEApplication(content, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    try:
        with _smtp_server(cfg) as server:
            server.sendmail(from_addr, [to_address], msg.as_string())
        current_app.logger.info("Email con adjuntos enviado to=%s subject=%s",
                                to_address, subject)
        return True
    except Exception as e:
        current_app.logger.error("Email con adjuntos falló to=%s err=%s", to_address, e)
        raise EmailError(str(e))


def render_factura_email(ticket):
    """HTML + texto del correo de entrega de la factura."""
    uuid = getattr(ticket, "uuid", "") or ""
    folio = getattr(ticket, "folio_display", "") or ""
    total = getattr(ticket, "total", 0) or 0
    nombre = getattr(ticket, "receptor_nombre", "") or "Cliente"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#1a73e8;">Tu factura está lista</h2>
  <p>Hola <strong>{nombre}</strong>,</p>
  <p>Adjuntamos tu factura (CFDI) en PDF y XML.</p>
  <p style="background:#f5f5f5;padding:15px;border-radius:6px;">
    <strong>Folio:</strong> {folio}<br>
    <strong>UUID:</strong> {uuid}<br>
    <strong>Total:</strong> ${total:,.2f} MXN
  </p>
  <p style="color:#999;font-size:12px;">— Dental Planning</p>
</body></html>"""
    text = (f"Tu factura está lista\n\nHola {nombre},\n\n"
            f"Folio: {folio}\nUUID: {uuid}\nTotal: ${total:,.2f} MXN\n\n"
            "Adjuntamos PDF y XML.\n— Dental Planning")
    return html, text


def render_billing_reminder(tenant_name, plan_name, monto, fecha_cobro, payment_url, is_retry=False):
    title = "Cobro de hoy" if is_retry else "Recordatorio: cobro mañana"
    intro = (
        "Tu suscripción vence <strong>HOY</strong>. Para no perder acceso, paga ahora:"
        if is_retry else
        f"Te recordamos que tu suscripción se renovará el <strong>{fecha_cobro}</strong>. "
        "Puedes adelantar el pago aquí:"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#1a73e8;">{title}</h2>
  <p>Hola <strong>{tenant_name}</strong>,</p>
  <p>{intro}</p>
  <p style="background:#f5f5f5;padding:15px;border-radius:6px;">
    <strong>Plan:</strong> {plan_name}<br>
    <strong>Monto:</strong> ${monto:.2f} MXN
  </p>
  <p style="text-align:center;margin:30px 0;">
    <a href="{payment_url}" style="background:#1a73e8;color:#fff;padding:14px 32px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">
      Pagar ahora
    </a>
  </p>
  <p style="color:#777;font-size:13px;">Si ya pagaste, ignora este correo. Para soporte responde a este email.</p>
  <p style="color:#999;font-size:12px;">— Dental Planning</p>
</body></html>"""

    text = (
        f"{title}\n\nHola {tenant_name},\n\n"
        f"Plan: {plan_name}\nMonto: ${monto:.2f} MXN\n"
        f"Fecha: {fecha_cobro}\n\nPaga aquí: {payment_url}\n\n"
        "Si ya pagaste, ignora este correo.\n— Dental Planning"
    )
    return html, text
