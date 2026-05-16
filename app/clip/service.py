import hmac
import hashlib
import requests
from flask import current_app


class ClipAPIError(Exception):
    pass


def _api_key():
    return current_app.config["CLIP_API_KEY"]


def _base_url():
    return current_app.config["CLIP_BASE_URL"].rstrip("/")


def create_checkout_link(amount, description, webhook_url=None, redirect_url=None,
                         metadata=None, expires_at=None):
    url = f"{_base_url()}/v2/checkout"
    body = {
        "amount": amount,
        "currency": "MXN",
        "purchase_description": description[:250],
    }
    if webhook_url:
        body["webhook_url"] = webhook_url
    if redirect_url:
        body["redirection_url"] = {
            "success": redirect_url,
            "error": redirect_url,
            "default": redirect_url,
        }
    if metadata:
        body["metadata"] = metadata
    if expires_at:
        body["expires_at"] = expires_at

    try:
        resp = requests.post(
            url,
            json=body,
            headers={
                "Authorization": f"Basic {_api_key()}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        raise ClipAPIError(f"Clip API error: {e}")

    return resp.json()


def verify_webhook_signature(raw_body, signature):
    secret = current_app.config.get("CLIP_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
