import json
from datetime import timedelta
from flask import Blueprint, current_app, request, jsonify
from app.extensions import db
from app.superadmin.models import Payment, Subscription, SUBSCRIPTION_ACTIVA
from app.auth.models import Tenant, TENANT_STATUS_ACTIVE

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

    resource = (data.get("resource") or "").upper()
    status = (data.get("resource_status") or "").upper()
    clip_id = data.get("payment_request_id") or ""

    if not clip_id:
        return jsonify({"received": True}), 200

    payment = Payment.query.filter_by(clip_payment_id=clip_id).first()
    if not payment:
        current_app.logger.info("Clip webhook: no Payment for clip_id=%s", clip_id)
        return jsonify({"received": True}), 200

    if resource == "CHECKOUT" and status == "COMPLETED":
        payment.clip_status = "PAID"
        if payment.subscription_id:
            sub = db.session.get(Subscription, payment.subscription_id)
            if sub:
                sub.estado = SUBSCRIPTION_ACTIVA
                sub.grace_expires_at = None
                if payment.periodo_fin:
                    sub.proximo_cobro = payment.periodo_fin + timedelta(days=1)

        tenant = db.session.get(Tenant, payment.tenant_id)
        if tenant and tenant.status != TENANT_STATUS_ACTIVE:
            tenant.status = TENANT_STATUS_ACTIVE
            tenant.is_active = True

        db.session.commit()

    elif resource == "CHECKOUT" and status in ("CANCELED", "EXPIRED"):
        payment.clip_status = status
        db.session.commit()

    elif resource == "CHECKOUT" and status == "PENDING":
        payment.clip_status = "PENDING"
        db.session.commit()

    return jsonify({"received": True}), 200
