import json
from datetime import timedelta
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.clip.service import verify_webhook_signature
from app.superadmin.models import Payment, Subscription, SUBSCRIPTION_ACTIVA
from app.auth.models import Tenant, TENANT_STATUS_ACTIVE

clip_bp = Blueprint("clip", __name__, url_prefix="/api/v1/clip")


@clip_bp.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data()
    signature = request.headers.get("X-Clip-Signature", "")

    if not verify_webhook_signature(raw_body, signature):
        return jsonify({"error": "Invalid signature"}), 400

    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "Invalid JSON"}), 400

    event = data.get("event", "")
    clip_id = data.get("payment_request_id", "")

    if event == "payment.paid" and clip_id:
        payment = Payment.query.filter_by(clip_payment_id=clip_id).first()
        if payment:
            payment.clip_status = "PAID"
            if payment.subscription_id:
                sub = db.session.get(Subscription, payment.subscription_id)
                if sub:
                    sub.estado = SUBSCRIPTION_ACTIVA
                    sub.grace_expires_at = None
                    if payment.periodo_fin:
                        sub.proximo_cobro = payment.periodo_fin + timedelta(days=1)

            metadata = data.get("metadata") or {}
            if metadata.get("is_registration"):
                tenant = db.session.get(Tenant, payment.tenant_id)
                if tenant and tenant.status != TENANT_STATUS_ACTIVE:
                    tenant.status = TENANT_STATUS_ACTIVE
                    tenant.is_active = True

            db.session.commit()

    elif event == "payment.failed" and clip_id:
        payment = Payment.query.filter_by(clip_payment_id=clip_id).first()
        if payment:
            payment.clip_status = "FAILED"
            db.session.commit()

    return jsonify({"received": True}), 200
