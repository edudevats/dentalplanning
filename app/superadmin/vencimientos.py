"""Vencimientos de mensualidades de tenants que pagan por transferencia.

Una sola definición de "cliente de paga por transferencia" (``query_transferencia``)
alimenta la página /admin/vencimientos, los recordatorios por correo y el
resumen diario, para que las tres vistas nunca discrepen.
"""
import re
from datetime import timedelta, timezone
from urllib.parse import quote

from flask import current_app

from app.auth.models import Tenant, SYSTEM_TENANT_SLUG, TENANT_STATUS_ACTIVE
from app.clip.billing import calculate_variable_breakdown
from app.superadmin.models import (
    Plan, Subscription, RecordatorioCobro,
    SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA, SUB_METODO_TRANSFERENCIA,
)
from app.superadmin.services import es_plan_de_pago

TIPO_PAGA = "paga"
TIPO_PRUEBA = "prueba"
TIPO_PRUEBA_VENCIDA = "prueba_vencida"
TIPO_SIN_PLAN = "sin_plan"
TIPOS_CLIENTE = (TIPO_PAGA, TIPO_PRUEBA, TIPO_PRUEBA_VENCIDA, TIPO_SIN_PLAN)


def tipo_cliente(sub, today):
    """Clasifica al tenant por su suscripción: paga, prueba o prueba vencida.

    Un plan gratuito no temporal cuenta como prueba: no paga, pero no vence.
    """
    if not sub or not sub.plan:
        return TIPO_SIN_PLAN
    if sub.plan.es_temporal:
        if sub.proximo_cobro and sub.proximo_cobro < today:
            return TIPO_PRUEBA_VENCIDA
        return TIPO_PRUEBA
    if es_plan_de_pago(sub.plan):
        return TIPO_PAGA
    return TIPO_PRUEBA


def query_transferencia():
    """Suscripciones de paga, por transferencia, vivas y con fecha de cobro."""
    return (
        Subscription.query
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .join(Plan, Plan.id == Subscription.plan_id)
        .filter(
            Tenant.slug != SYSTEM_TENANT_SLUG,
            Tenant.status == TENANT_STATUS_ACTIVE,
            Plan.precio_mensual > 0,
            Plan.es_temporal.is_(False),
            Plan.addon_tipo.is_(None),
            Subscription.metodo_pago == SUB_METODO_TRANSFERENCIA,
            Subscription.estado.in_([SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA]),
            Subscription.proximo_cobro.isnot(None),
        )
    )


def monto_esperado(sub):
    """Total del próximo corte (plan + facturación + timbres).

    Si el desglose falla por datos incompletos, cae al precio del plan: la
    alerta no debe romperse por un detalle de facturación.
    """
    try:
        return round(float(calculate_variable_breakdown(sub, sub.proximo_cobro)["total"]), 2)
    except Exception:  # noqa: BLE001 — degradar a precio de lista
        current_app.logger.warning("monto_esperado: desglose falló para sub %s", sub.id)
        return round(float(sub.plan.precio_mensual or 0), 2)


def normalizar_telefono(tel):
    """Deja sólo dígitos para wa.me; 10 dígitos (México) → antepone 52."""
    digitos = re.sub(r"\D", "", tel or "")
    if len(digitos) == 10:
        return "52" + digitos
    if len(digitos) < 10:
        return None
    return digitos


def texto_datos_bancarios():
    cfg = current_app.config
    partes = []
    if cfg.get("BILLING_BANCO"):
        partes.append(cfg["BILLING_BANCO"])
    if cfg.get("BILLING_CLABE"):
        partes.append(f"CLABE {cfg['BILLING_CLABE']}")
    if cfg.get("BILLING_BENEFICIARIO"):
        partes.append(cfg["BILLING_BENEFICIARIO"])
    return " · ".join(partes)


def _fmt_monto(monto):
    return f"${monto:,.2f}"


def _frase_fecha(sub, today):
    fecha = sub.proximo_cobro.strftime("%d/%m")
    return f"venció el {fecha}" if sub.proximo_cobro < today else f"vence el {fecha}"


def mensaje_whatsapp(sub, today):
    plan = sub.plan.nombre if sub.plan else ""
    msg = (
        f"Hola {sub.tenant.name}, te saludamos de Dental Planning. "
        f"Tu mensualidad del plan {plan} por {_fmt_monto(monto_esperado(sub))} "
        f"{_frase_fecha(sub, today)}."
    )
    bancarios = texto_datos_bancarios()
    if bancarios:
        msg += f" Puedes transferir a: {bancarios}. Envíanos tu comprobante por este medio."
    return msg + " ¡Gracias!"


def url_whatsapp(sub, today):
    tel = normalizar_telefono(sub.tenant.contact_phone if sub.tenant else None)
    if not tel:
        return None
    return f"https://wa.me/{tel}?text={quote(mensaje_whatsapp(sub, today))}"


def _iso_utc(dt):
    """created_at se guarda como UTC ingenuo; se serializa con offset explícito."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def ultimo_recordatorio(sub):
    r = (
        RecordatorioCobro.query.filter_by(subscription_id=sub.id)
        .order_by(RecordatorioCobro.created_at.desc(), RecordatorioCobro.id.desc())
        .first()
    )
    if not r:
        return None
    return {
        "tipo": r.tipo, "canal": r.canal, "origen": r.origen,
        "fecha": _iso_utc(r.created_at),
    }


def serializar_vencimiento(sub, today):
    t = sub.tenant
    return {
        "subscription_id": sub.id,
        "tenant_id": sub.tenant_id,
        "tenant_name": t.name if t else None,
        "plan": sub.plan.nombre if sub.plan else None,
        "monto": monto_esperado(sub),
        "proximo_cobro": sub.proximo_cobro.isoformat(),
        "dias": (sub.proximo_cobro - today).days,
        "contact_email": t.contact_email if t else None,
        "contact_phone": t.contact_phone if t else None,
        "ultimo_recordatorio": ultimo_recordatorio(sub),
    }


def agrupar_vencimientos(today):
    """Vencidos, próximos 7 días y días 8–30, ordenados por fecha de cobro."""
    subs = (
        query_transferencia()
        .filter(Subscription.proximo_cobro <= today + timedelta(days=30))
        .order_by(Subscription.proximo_cobro.asc(), Subscription.id.asc())
        .all()
    )
    grupos = {"vencidos": [], "semana": [], "mes": []}
    for sub in subs:
        fila = serializar_vencimiento(sub, today)
        if sub.proximo_cobro < today:
            grupos["vencidos"].append(fila)
        elif sub.proximo_cobro <= today + timedelta(days=7):
            grupos["semana"].append(fila)
        else:
            grupos["mes"].append(fila)
    urgentes = grupos["vencidos"] + grupos["semana"]
    grupos["resumen"] = {
        "por_cobrar": len(urgentes),
        "monto": round(sum(f["monto"] for f in urgentes), 2),
    }
    return grupos
