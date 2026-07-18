import json
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, current_app, request, jsonify
from app.extensions import db
from app.superadmin.models import (
    Payment, Subscription, Plan,
    SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA, SUBSCRIPTION_VENCIDA,
)
from app.auth.models import Tenant, User, TENANT_STATUS_ACTIVE, TENANT_STATUS_SUSPENDED
from app.clip.service import get_invoice, get_subscription, ClipAPIError
from app.clip.billing import add_one_month

clip_bp = Blueprint("clip", __name__, url_prefix="/api/v1/clip")


@clip_bp.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "ok"}), 200

    raw_body = request.get_data()
    if not raw_body:
        return jsonify({"received": True}), 200

    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        current_app.logger.warning("Clip webhook: invalid JSON body=%r", raw_body[:500])
        return jsonify({"error": "Invalid JSON"}), 400

    current_app.logger.info("Clip webhook received: %s", data)

    # Detect event type. Clip recurring webhooks use different shapes depending
    # on the resource. We handle three shapes:
    #   1. v2/checkout (one-time):  {'resource': 'CHECKOUT', 'resource_status': ...}
    #   2. full subscription/invoice: {'resource': 'SUBSCRIPTION'|'INVOICE', ...}
    #   3. "thin" recurring notification: {'origin': 'subscription'|'invoice',
    #      'event_type': 'create'|..., 'id': <resource_id>}  -- only carries an id,
    #      so we fetch the full resource from the API before processing.
    resource = (data.get("resource") or "").upper()
    origin = (data.get("origin") or "").lower()
    status = (data.get("resource_status") or data.get("status") or "").upper()

    try:
        if resource == "CHECKOUT":
            _handle_checkout_event(data, status)
        elif resource == "SUBSCRIPTION":
            _handle_subscription_event(data, status)
        elif resource in ("INVOICE", "PAYMENT", "RECURRING_PAYMENT"):
            _handle_invoice_event(data, status)
        elif origin == "invoice":
            _handle_invoice_notification(data)
        elif origin == "subscription":
            _handle_subscription_notification(data)
        elif data.get("subscription_id") and data.get("invoice_id"):
            # Best-effort fallback for shape without `resource`
            _handle_invoice_event(data, status)
        elif data.get("subscription_id"):
            _handle_subscription_event(data, status)
        else:
            current_app.logger.info("Clip webhook: no recognized event shape, ignored")
    except Exception as e:
        current_app.logger.exception("Clip webhook handler crashed: %s", e)
        db.session.rollback()
        return jsonify({"received": True}), 200

    return jsonify({"received": True}), 200


def _handle_checkout_event(data, status):
    """Eventos de checkout normal (cobros variables y compatibilidad legacy)."""
    clip_id = data.get("payment_request_id") or data.get("id") or ""
    if not clip_id:
        return
    payment = Payment.query.filter_by(clip_payment_id=clip_id).first()
    if not payment:
        return

    if status in ("COMPLETED", "CHECKOUT_COMPLETED", "PAID"):
        payment.clip_status = "PAID"
        payment.paid_at = datetime.now(timezone.utc)
        if payment.subscription_id:
            sub = db.session.get(Subscription, payment.subscription_id)
            if sub:
                sub.estado = SUBSCRIPTION_ACTIVA
                sub.grace_expires_at = None
                if payment.billing_cycle_date:
                    next_cycle = add_one_month(payment.billing_cycle_date)
                    if not sub.proximo_cobro or sub.proximo_cobro <= payment.billing_cycle_date:
                        sub.proximo_cobro = next_cycle
                elif payment.periodo_fin:
                    sub.proximo_cobro = payment.periodo_fin + timedelta(days=1)
                plan = sub.plan
                if plan and plan.cupo_maximo is not None and not sub.counted_in_cupo:
                    plan.cupo_usados = (plan.cupo_usados or 0) + 1
                    sub.counted_in_cupo = True
        tenant = db.session.get(Tenant, payment.tenant_id)
        if tenant and tenant.status != TENANT_STATUS_ACTIVE:
            tenant.status = TENANT_STATUS_ACTIVE
            tenant.is_active = True
        db.session.commit()
    elif status in ("CANCELED", "CANCELLED", "EXPIRED"):
        payment.clip_status = "EXPIRED" if status == "EXPIRED" else "CANCELLED"
        db.session.commit()
    elif status == "PENDING":
        payment.clip_status = "PENDING"
        db.session.commit()


def _es_precio_addon_recepcionista(price_id):
    if not price_id:
        return False
    from app.auth.seats_service import get_addon_plan
    plan = get_addon_plan()
    return bool(plan and plan.clip_price_id and plan.clip_price_id == price_id)


def _handle_subscription_event(data, status):
    """Subscription lifecycle: created, active, inactive."""
    clip_sub_id = data.get("subscription_id") or data.get("id") or ""
    price_id = data.get("price_id") or ""
    customer = data.get("customer") or {}
    email = (customer.get("email") or "").lower()

    if not clip_sub_id:
        return

    if _es_precio_addon_recepcionista(price_id):
        from app.auth.seats_service import activar_por_clip
        if status == "ACTIVE" and email:
            user = User.query.filter(db.func.lower(User.email) == email).first()
            if user:
                activar_por_clip(user.tenant_id, clip_sub_id)
        elif status in ("INACTIVE", "CANCELLED", "CANCELED"):
            from app.superadmin.models import AsientoRecepcionista, ASIENTO_CANCELADA
            a = AsientoRecepcionista.query.filter_by(clip_subscription_id=clip_sub_id).first()
            if a and a.estado != ASIENTO_CANCELADA:
                from app.auth.seats_service import cancelar_asiento
                cancelar_asiento(a)
        return  # no tratar como suscripción principal

    # Match by clip_subscription_id first, then by customer email + plan
    sub = Subscription.query.filter_by(clip_subscription_id=clip_sub_id).first()
    if not sub and email:
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user:
            sub = Subscription.query.filter_by(tenant_id=user.tenant_id).first()
            if sub:
                sub.clip_subscription_id = clip_sub_id

    if not sub:
        current_app.logger.info("Clip webhook: subscription %s with email %s not matched",
                                clip_sub_id, email)
        return

    if status == "ACTIVE":
        sub.estado = SUBSCRIPTION_ACTIVA
        sub.grace_expires_at = None
        tenant = db.session.get(Tenant, sub.tenant_id)
        if tenant and tenant.status != TENANT_STATUS_ACTIVE:
            tenant.status = TENANT_STATUS_ACTIVE
            tenant.is_active = True
    elif status in ("INACTIVE", "CANCELLED", "CANCELED"):
        sub.estado = SUBSCRIPTION_VENCIDA
        tenant = db.session.get(Tenant, sub.tenant_id)
        if tenant:
            tenant.status = TENANT_STATUS_SUSPENDED
            tenant.is_active = False
    db.session.commit()


def _handle_invoice_event(data, status):
    """Invoice (per-period charge) events. status: paid, scheduled, overdue, failed."""
    invoice_id = data.get("invoice_id") or data.get("id") or ""
    clip_sub_id = data.get("subscription_id") or ""
    amount = data.get("amount") or 0
    due_date_str = data.get("due_date") or ""
    paid_at_str = data.get("paid_at") or ""
    payment_request_id = data.get("payment_request_id") or ""

    sub = None
    if clip_sub_id:
        sub = Subscription.query.filter_by(clip_subscription_id=clip_sub_id).first()
    if not sub:
        current_app.logger.info("Clip webhook: invoice %s for sub %s not matched",
                                invoice_id, clip_sub_id)
        return

    payment = Payment.query.filter_by(clip_payment_id=invoice_id).first()
    if not payment:
        user = User.query.filter_by(tenant_id=sub.tenant_id, role="admin").first()
        registrado_por = user.id if user else None
        if not registrado_por:
            any_user = User.query.filter_by(tenant_id=sub.tenant_id).first()
            registrado_por = any_user.id if any_user else 1

        periodo_inicio = _parse_iso_date(due_date_str) or date.today()
        payment = Payment(
            tenant_id=sub.tenant_id,
            subscription_id=sub.id,
            fecha=date.today(),
            monto=float(amount or sub.plan.precio_mensual),
            metodo="clip",
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_inicio + timedelta(days=30),
            comentarios=f"Invoice {invoice_id}",
            registrado_por_id=registrado_por,
            clip_payment_id=invoice_id,
            clip_status="PENDING",
        )
        db.session.add(payment)

    norm_status = status.upper()
    if norm_status == "PAID":
        payment.clip_status = "PAID"
        if paid_at_str:
            paid_date = _parse_iso_date(paid_at_str)
            if paid_date:
                payment.fecha = paid_date
        sub.estado = SUBSCRIPTION_ACTIVA
        sub.grace_expires_at = None
        if payment.periodo_fin:
            sub.proximo_cobro = payment.periodo_fin + timedelta(days=1)
        tenant = db.session.get(Tenant, sub.tenant_id)
        if tenant and tenant.status != TENANT_STATUS_ACTIVE:
            tenant.status = TENANT_STATUS_ACTIVE
            tenant.is_active = True

        # Promotional cupo: count this subscription once (on first PAID invoice)
        plan = sub.plan
        if (plan and plan.cupo_maximo is not None and not sub.counted_in_cupo):
            plan.cupo_usados = (plan.cupo_usados or 0) + 1
            sub.counted_in_cupo = True
            current_app.logger.info(
                "Promo plan %s: cupo_usados=%s/%s after subscription %s",
                plan.nombre, plan.cupo_usados, plan.cupo_maximo, sub.id,
            )

    elif norm_status in ("OVERDUE", "FAILED"):
        payment.clip_status = "FAILED" if norm_status == "FAILED" else "OVERDUE"
        sub.estado = SUBSCRIPTION_GRACIA
        grace_days = current_app.config.get("BILLING_GRACE_DAYS", 3)
        sub.grace_expires_at = date.today() + timedelta(days=grace_days)

    elif norm_status == "SCHEDULED":
        payment.clip_status = "PENDING"

    elif norm_status in ("CANCELLED", "CANCELED"):
        payment.clip_status = "CANCELLED"

    if payment_request_id and not sub.clip_checkout_id:
        sub.clip_checkout_id = payment_request_id

    db.session.commit()


def _handle_invoice_notification(data):
    """Thin recurring webhook: {'origin': 'invoice', 'event_type': ..., 'id': <invoice_id>}.

    Clip sends only the invoice id for recurring events, so we fetch the full
    invoice from the API and route it through the normal invoice handler.
    """
    invoice_id = data.get("id") or data.get("invoice_id") or ""
    if not invoice_id:
        return
    try:
        detail = get_invoice(invoice_id)
    except ClipAPIError as e:
        current_app.logger.warning("Clip webhook: could not fetch invoice %s: %s", invoice_id, e)
        return
    if not detail:
        current_app.logger.info("Clip webhook: invoice %s not found when fetched", invoice_id)
        return
    current_app.logger.info("Clip webhook: fetched invoice %s detail=%s", invoice_id, detail)
    norm, status = _normalize_invoice(detail, invoice_id)
    _handle_invoice_event(norm, status)


def _handle_subscription_notification(data):
    """Thin recurring webhook: {'origin': 'subscription', 'event_type': ..., 'id': <sub_id>}.

    Fetches the full subscription from the API and routes it through the normal
    subscription handler.
    """
    sub_id = data.get("id") or data.get("subscription_id") or ""
    if not sub_id:
        return
    try:
        detail = get_subscription(sub_id)
    except ClipAPIError as e:
        current_app.logger.warning("Clip webhook: could not fetch subscription %s: %s", sub_id, e)
        return
    if not detail:
        current_app.logger.info("Clip webhook: subscription %s not found when fetched", sub_id)
        return
    current_app.logger.info("Clip webhook: fetched subscription %s detail=%s", sub_id, detail)
    norm, status = _normalize_subscription(detail, sub_id)
    _handle_subscription_event(norm, status)


def _normalize_invoice(detail, invoice_id):
    """Map a fetched Clip invoice object to the dict shape _handle_invoice_event expects.

    Field names vary across Clip API versions, so we look up several candidates.
    Returns (normalized_dict, status_str).
    """
    sub = detail.get("subscription")
    sub_id = detail.get("subscription_id") or ""
    if not sub_id and isinstance(sub, dict):
        sub_id = sub.get("id") or ""
    norm = {
        "invoice_id": detail.get("id") or invoice_id,
        "subscription_id": sub_id,
        "amount": detail.get("amount") or detail.get("total") or 0,
        "due_date": detail.get("due_date") or "",
        "paid_at": detail.get("paid_at") or detail.get("payment_date") or "",
        "payment_request_id": detail.get("payment_request_id") or "",
    }
    status = (detail.get("status") or detail.get("payment_status")
              or detail.get("resource_status") or "").upper()
    return norm, status


def _normalize_subscription(detail, sub_id):
    """Map a fetched Clip subscription object to the dict shape
    _handle_subscription_event expects. Returns (normalized_dict, status_str).
    """
    customer = detail.get("customer")
    norm = {
        "subscription_id": detail.get("id") or sub_id,
        "price_id": detail.get("price_id") or "",
        "customer": customer if isinstance(customer, dict) else {},
    }
    status = (detail.get("status") or detail.get("resource_status") or "").upper()
    return norm, status


def _parse_iso_date(s):
    """Best-effort parse of an ISO 8601 timestamp into a date."""
    if not s:
        return None
    try:
        from datetime import datetime
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None
