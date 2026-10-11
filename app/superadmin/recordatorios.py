"""Recordatorios de cobro por correo para tenants que pagan por transferencia.

Idempotente: un aviso automático por (suscripción, ciclo, tipo). Si la tarea
diaria no corre un día, la siguiente corrida envía lo pendiente. Nunca cambia
estados, cobra ni suspende.
"""
from datetime import timedelta
from html import escape

from flask import current_app

from app.auth.models import User
from app.email.service import send_email, EmailError
from app.extensions import db
from app.superadmin.models import (
    RecordatorioCobro, Subscription,
    RECORDATORIO_PREVIO, RECORDATORIO_VENCIDO, RECORDATORIO_RESUMEN,
    CANAL_EMAIL, ORIGEN_AUTO,
)
from app.superadmin.vencimientos import (
    query_transferencia, monto_esperado, texto_datos_bancarios, agrupar_vencimientos,
)

DIAS_PREVIO = 3
DIAS_VENCIDO = 2
ASUNTO_RESUMEN = "Dental Planning: resumen de cobros por transferencia"


def destinatarios_tenant(tenant):
    """Correo de contacto; si no hay, los admins activos del tenant."""
    if tenant.contact_email:
        return [tenant.contact_email]
    admins = (
        User.query.filter_by(tenant_id=tenant.id, role="admin", is_active=True)
        .order_by(User.id.asc()).all()
    )
    return [u.email for u in admins]


def tipo_pendiente(sub, today):
    cobro = sub.proximo_cobro
    if cobro - timedelta(days=DIAS_PREVIO) <= today < cobro:
        return RECORDATORIO_PREVIO
    if today >= cobro + timedelta(days=DIAS_VENCIDO):
        return RECORDATORIO_VENCIDO
    return None


def _ya_enviado(sub, tipo):
    return db.session.query(
        RecordatorioCobro.query.filter_by(
            subscription_id=sub.id, ciclo=sub.proximo_cobro,
            tipo=tipo, origen=ORIGEN_AUTO,
        ).exists()
    ).scalar()


def _contenido(sub, tipo):
    fecha = sub.proximo_cobro.strftime("%d/%m/%Y")
    monto = f"${monto_esperado(sub):,.2f}"
    plan = sub.plan.nombre if sub.plan else ""
    nombre = sub.tenant.name
    bancarios = texto_datos_bancarios()
    if tipo == RECORDATORIO_VENCIDO:
        asunto = "Tu pago de Dental Planning está pendiente"
        cuerpo = (f"Tu mensualidad del plan {plan} por {monto} venció el {fecha} "
                  "y aún no la tenemos registrada. Realiza tu pago para evitar "
                  "la suspensión del servicio.")
    else:
        asunto = f"Tu mensualidad de Dental Planning vence el {sub.proximo_cobro.strftime('%d/%m')}"
        cuerpo = f"Te recordamos que tu mensualidad del plan {plan} por {monto} vence el {fecha}."
    pie = "Si ya realizaste tu pago, ignora este mensaje. ¡Gracias!"
    texto = f"Hola {nombre},\n\n{cuerpo}\n"
    html = f"<p>Hola {escape(nombre)},</p><p>{escape(cuerpo)}</p>"
    if bancarios:
        texto += f"\nDatos para transferir: {bancarios}\n"
        html += f"<p><strong>Datos para transferir:</strong> {escape(bancarios)}</p>"
    texto += f"\n{pie}\n"
    html += f"<p>{escape(pie)}</p>"
    return asunto, html, texto


def _enviar(destino, asunto, html, texto):
    try:
        return bool(send_email(destino, asunto, html, texto))
    except EmailError as exc:
        current_app.logger.error("Recordatorio a %s falló: %s", destino, exc)
        return False


def enviar_recordatorio(sub, tipo, today, *, origen, enviado_por_id=None):
    """Envía el correo a cada destinatario; registra una fila por envío exitoso.

    No hace commit. Devuelve True si al menos un envío salió.
    """
    asunto, html, texto = _contenido(sub, tipo)
    alguno = False
    for destino in destinatarios_tenant(sub.tenant):
        if _enviar(destino, asunto, html, texto):
            db.session.add(RecordatorioCobro(
                tenant_id=sub.tenant_id, subscription_id=sub.id,
                ciclo=sub.proximo_cobro, tipo=tipo, canal=CANAL_EMAIL,
                origen=origen, destinatario=destino, enviado_por_id=enviado_por_id,
            ))
            alguno = True
    return alguno


def enviar_resumen(today):
    """Correo diario a los super-admin: vencidos y los que vencen en ≤3 días."""
    if db.session.query(
        RecordatorioCobro.query.filter_by(tipo=RECORDATORIO_RESUMEN, ciclo=today).exists()
    ).scalar():
        return False
    grupos = agrupar_vencimientos(today)
    proximos = [f for f in grupos["semana"] if f["dias"] <= DIAS_PREVIO]
    vencidos = grupos["vencidos"]
    if not vencidos and not proximos:
        return False

    def _lineas(filas, etiqueta):
        return [f"{f['tenant_name']} — ${f['monto']:,.2f} — {etiqueta(f)}" for f in filas]

    lineas = (
        ["Vencidos:"] + _lineas(vencidos, lambda f: f"{-f['dias']} días de atraso")
        + ["", "Vencen en los próximos 3 días:"]
        + _lineas(proximos, lambda f: f"cobro {f['proximo_cobro']}")
    )
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    if base:
        lineas += ["", f"Ver detalle: {base}/admin/vencimientos"]
    texto = "\n".join(lineas)
    html = "<br>".join(escape(l) for l in lineas)

    superadmins = User.query.filter_by(is_superuser=True, is_active=True).all()
    enviados = [u.email for u in superadmins if _enviar(u.email, ASUNTO_RESUMEN, html, texto)]
    if not enviados:
        return False
    db.session.add(RecordatorioCobro(
        ciclo=today, tipo=RECORDATORIO_RESUMEN, canal=CANAL_EMAIL,
        origen=ORIGEN_AUTO, destinatario=", ".join(enviados)[:255],
    ))
    return True


def enviar_recordatorios_pendientes(today, dry_run=False):
    resultado = {"enviados": [], "omitidos": [], "resumen_enviado": False}
    subs = (
        query_transferencia()
        .order_by(Subscription.proximo_cobro.asc(), Subscription.id.asc())
        .all()
    )
    for sub in subs:
        tipo = tipo_pendiente(sub, today)
        if not tipo or _ya_enviado(sub, tipo):
            continue
        nombre = sub.tenant.name
        if dry_run:
            resultado["enviados"].append(nombre)
            continue
        if enviar_recordatorio(sub, tipo, today, origen=ORIGEN_AUTO):
            resultado["enviados"].append(nombre)
        else:
            resultado["omitidos"].append(nombre)
        db.session.commit()
    if not dry_run:
        resultado["resumen_enviado"] = enviar_resumen(today)
        db.session.commit()
    return resultado
