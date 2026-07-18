"""Cobros mensuales variables de Dental Planning.

El plan, la cuota de facturación y los timbres se congelan en ``Payment`` al
momento del corte. Así, una cancelación posterior del CFDI no modifica el monto
ya generado y ejecutar el ciclo más de una vez no duplica el cobro.
"""
from datetime import date, datetime, time, timedelta, timezone

from flask import current_app

from app.auth.models import User
from app.extensions import db
from app.facturacion.models import ConfiguracionFiscal, Ticket
from app.facturacion.timezone_helper import MEXICO_TIMEZONE, get_today
from app.superadmin.models import (
    Payment,
    Subscription,
    SUBSCRIPTION_GRACIA,
)
from app.clip.service import ClipAPIError, create_checkout_link


def add_one_month(value):
    """Avanza una fecha un mes calendario conservando un día válido."""
    import calendar

    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(value.day, last_day))


def _money(value):
    return round(float(value or 0), 2)


def _base_url(explicit=None):
    return (
        explicit
        or current_app.config.get("APP_BASE_URL")
        or "http://www.dentalplanning.mx"
    ).rstrip("/")


def _grace_days():
    return int(current_app.config.get("BILLING_GRACE_DAYS", 3))


def _registered_by(tenant_id, preferred=None):
    if preferred:
        return preferred
    user = (
        User.query.filter_by(tenant_id=tenant_id, role="admin")
        .order_by(User.id.asc())
        .first()
        or User.query.filter_by(tenant_id=tenant_id).order_by(User.id.asc()).first()
    )
    if not user:
        raise ValueError("El tenant no tiene un usuario para registrar el cobro")
    return user.id


def _existing_charge(tenant_id, cycle_date):
    return Payment.query.filter_by(
        tenant_id=tenant_id, billing_cycle_date=cycle_date
    ).first()


def _checkout(*, sub, amount, cycle_date, due_date, description, base_url):
    base = _base_url(base_url)
    expires_at = datetime.combine(
        due_date + timedelta(days=1), time.min, tzinfo=MEXICO_TIMEZONE
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    result = create_checkout_link(
        amount=_money(amount),
        description=description,
        webhook_url=f"{base}/api/v1/clip/webhook",
        redirection_url={
            "success": f"{base}/dashboard",
            "error": f"{base}/dashboard",
            "default": f"{base}/dashboard",
        },
        metadata={
            "tenant_id": sub.tenant_id,
            "subscription_id": sub.id,
            "billing_cycle_date": cycle_date.isoformat(),
        },
        expires_at=expires_at,
    )
    clip_id = result.get("payment_request_id") or result.get("id") or ""
    clip_url = (
        result.get("payment_request_url")
        or result.get("payment_url")
        or result.get("url")
        or ""
    )
    if not clip_id or not clip_url:
        raise ClipAPIError("Clip no devolvió un identificador y link de pago válidos")
    return clip_id, clip_url


def calculate_variable_breakdown(sub, cycle_date):
    """Calcula el corte sin crear el link ni modificar la base de datos."""
    if not isinstance(sub, Subscription):
        raise TypeError("sub debe ser una Subscription")
    if not sub.plan:
        raise ValueError("La suscripción no tiene un plan")

    previous = (
        Payment.query.filter(
            Payment.tenant_id == sub.tenant_id,
            Payment.billing_cycle_date.isnot(None),
            Payment.billing_cycle_date < cycle_date,
        )
        .order_by(Payment.billing_cycle_date.desc(), Payment.id.desc())
        .first()
    )
    usage_start = previous.billing_cycle_date if previous else sub.inicio
    if not usage_start or usage_start > cycle_date:
        usage_start = cycle_date

    start_dt = datetime.combine(usage_start, time.min)
    cutoff_dt = datetime.combine(cycle_date, time.min)
    stamp_count = (
        Ticket.query.filter(
            Ticket.tenant_id == sub.tenant_id,
            Ticket.fecha_timbrado.isnot(None),
            Ticket.fecha_timbrado >= start_dt,
            Ticket.fecha_timbrado < cutoff_dt,
        ).count()
    )

    cfg = ConfiguracionFiscal.query.filter_by(tenant_id=sub.tenant_id).first()
    if (
        previous is None
        and cfg
        and cfg.facturacion_activada_at
        and cfg.facturacion_activada_at.date() > usage_start
    ):
        # En el primer corte del nuevo esquema no se cobran timbres histÃ³ricos
        # anteriores a la aceptaciÃ³n expresa del servicio.
        usage_start = min(cfg.facturacion_activada_at.date(), cycle_date)
        start_dt = datetime.combine(usage_start, time.min)
        stamp_count = (
            Ticket.query.filter(
                Ticket.tenant_id == sub.tenant_id,
                Ticket.fecha_timbrado.isnot(None),
                Ticket.fecha_timbrado >= start_dt,
                Ticket.fecha_timbrado < cutoff_dt,
            ).count()
        )
    monthly_fee = _money(current_app.config.get("FACTURACION_MONTHLY_FEE", 100))
    stamp_unit_price = _money(current_app.config.get("FACTURACION_STAMP_FEE", 2))
    charge_invoice_feature = bool(
        cfg
        and (
            cfg.facturacion_activa
            or cfg.facturacion_cargo_pendiente
            or stamp_count > 0
        )
    )

    plan_amount = _money(sub.plan.precio_mensual)
    invoice_base_fee = monthly_fee if charge_invoice_feature else 0.0
    stamp_amount = _money(stamp_count * stamp_unit_price)
    return {
        "usage_start": usage_start,
        "usage_end": cycle_date - timedelta(days=1),
        "plan_amount": plan_amount,
        "invoice_base_fee": invoice_base_fee,
        "stamp_count": stamp_count,
        "stamp_unit_price": stamp_unit_price,
        "stamp_amount": stamp_amount,
        "total": _money(plan_amount + invoice_base_fee + stamp_amount),
        "config": cfg,
    }


def create_initial_charge(sub, *, registered_by_id=None, base_url=None, today=None):
    """Genera el primer pago normal de un plan, sin cuota ni timbres."""
    today = today or get_today()
    existing = _existing_charge(sub.tenant_id, today)
    if existing:
        return existing, False
    if not sub.plan or sub.plan.precio_mensual <= 0:
        raise ValueError("El plan no requiere un cobro inicial")

    next_cycle = add_one_month(today)
    due_date = today + timedelta(days=_grace_days())
    amount = _money(sub.plan.precio_mensual)
    clip_id, clip_url = _checkout(
        sub=sub,
        amount=amount,
        cycle_date=today,
        due_date=due_date,
        description=f"Mensualidad {sub.plan.nombre}",
        base_url=base_url,
    )
    payment = Payment(
        tenant_id=sub.tenant_id,
        subscription_id=sub.id,
        fecha=today,
        monto=amount,
        metodo="clip",
        periodo_inicio=today,
        periodo_fin=next_cycle - timedelta(days=1),
        comentarios=f"Cobro inicial variable — {sub.plan.nombre}",
        registrado_por_id=_registered_by(sub.tenant_id, registered_by_id),
        clip_payment_id=clip_id,
        clip_status="PENDING",
        billing_cycle_date=today,
        due_date=due_date,
        plan_amount=amount,
        invoice_base_fee=0.0,
        stamp_count=0,
        stamp_unit_price=_money(current_app.config.get("FACTURACION_STAMP_FEE", 2)),
        stamp_amount=0.0,
        clip_payment_url=clip_url,
    )
    db.session.add(payment)
    sub.proximo_cobro = next_cycle
    sub.estado = SUBSCRIPTION_GRACIA
    sub.grace_expires_at = due_date
    sub.clip_checkout_id = clip_id
    return payment, True


def create_variable_charge(
    sub, *, cycle_date=None, registered_by_id=None, base_url=None, today=None
):
    """Cierra el periodo y crea un checkout por plan + facturación + timbres."""
    today = today or get_today()
    cycle_date = cycle_date or today
    existing = _existing_charge(sub.tenant_id, cycle_date)
    if existing:
        return existing, False
    if not sub.plan or sub.plan.es_temporal or sub.plan.precio_mensual <= 0:
        raise ValueError("La suscripción no genera un cobro mensual")

    breakdown = calculate_variable_breakdown(sub, cycle_date)
    # La gracia se cuenta desde el día real en que se genera el cobro, no desde
    # cycle_date: si el job corrió tarde (cycle_date quedó en el pasado), el
    # cliente conserva sus días completos y el mismo barrido de gracia no lo
    # suspende en la misma corrida.
    due_date = max(cycle_date, today) + timedelta(days=_grace_days())
    next_cycle = add_one_month(cycle_date)
    description = (
        f"Mensualidad {sub.plan.nombre}: plan ${breakdown['plan_amount']:.2f}, "
        f"facturación ${breakdown['invoice_base_fee']:.2f}, "
        f"{breakdown['stamp_count']} timbres"
    )
    clip_id, clip_url = _checkout(
        sub=sub,
        amount=breakdown["total"],
        cycle_date=cycle_date,
        due_date=due_date,
        description=description,
        base_url=base_url,
    )
    payment = Payment(
        tenant_id=sub.tenant_id,
        subscription_id=sub.id,
        fecha=cycle_date,
        monto=breakdown["total"],
        metodo="clip",
        periodo_inicio=cycle_date,
        periodo_fin=next_cycle - timedelta(days=1),
        comentarios=(
            f"Corte variable {cycle_date.isoformat()} — "
            f"{breakdown['stamp_count']} timbres"
        ),
        registrado_por_id=_registered_by(sub.tenant_id, registered_by_id),
        clip_payment_id=clip_id,
        clip_status="PENDING",
        billing_cycle_date=cycle_date,
        due_date=due_date,
        plan_amount=breakdown["plan_amount"],
        invoice_base_fee=breakdown["invoice_base_fee"],
        stamp_count=breakdown["stamp_count"],
        stamp_unit_price=breakdown["stamp_unit_price"],
        stamp_amount=breakdown["stamp_amount"],
        clip_payment_url=clip_url,
    )
    db.session.add(payment)
    sub.estado = SUBSCRIPTION_GRACIA
    sub.grace_expires_at = due_date
    sub.clip_checkout_id = clip_id
    if breakdown["config"]:
        breakdown["config"].facturacion_cargo_pendiente = False
    return payment, True


def serialize_charge(payment):
    due = payment.due_date
    today = get_today()
    days_remaining = max((due - today).days, 0) if due else 0
    overdue = bool(due and today > due)
    return {
        "tipo": "cobro_variable",
        "cobro_id": payment.id,
        "fecha_corte": (
            payment.billing_cycle_date.isoformat() if payment.billing_cycle_date else None
        ),
        "fecha_limite": due.isoformat() if due else None,
        "dias_restantes": days_remaining,
        "vencido": overdue,
        "monto": _money(payment.monto),
        "plan_monto": _money(payment.plan_amount),
        "facturacion_monto": _money(payment.invoice_base_fee),
        "timbres_cantidad": int(payment.stamp_count or 0),
        "timbre_precio": _money(payment.stamp_unit_price),
        "timbres_monto": _money(payment.stamp_amount),
        "payment_url": (
            payment.clip_payment_url
            if not overdue and payment.clip_status not in ("EXPIRED", "CANCELLED")
            else None
        ),
        "estado_pago": payment.clip_status,
    }
