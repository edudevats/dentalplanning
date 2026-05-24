import base64
import hmac
import hashlib
import requests
from flask import current_app


class ClipAPIError(Exception):
    pass


def _auth_headers():
    """Generates the authentication headers for Clip APIs.
    
    Supports:
    1. Basic Authentication (x-api-key and Authorization):
       Used when both CLIP_API_KEY and CLIP_SECRET_KEY are configured, or if CLIP_API_KEY is prefixed with 'Basic'.
    2. Bearer Authentication (Authorization):
       Used when only CLIP_API_KEY is configured.
    """
    api_key = current_app.config.get("CLIP_API_KEY", "")
    secret_key = current_app.config.get("CLIP_SECRET_KEY", "")
    
    headers = {}
    
    if api_key and secret_key:
        credentials = f"{api_key}:{secret_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        basic_val = f"Basic {encoded_credentials}"
        headers["x-api-key"] = basic_val
        headers["Authorization"] = basic_val
    elif api_key:
        if api_key.startswith("Basic "):
            headers["x-api-key"] = api_key
            headers["Authorization"] = api_key
        elif api_key.startswith("Bearer "):
            headers["Authorization"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
            
    return headers


def _base_url():
    return current_app.config["CLIP_BASE_URL"].rstrip("/")


def create_checkout_link(amount, description, webhook_url=None, redirection_url=None,
                         metadata=None, expires_at=None):
    url = f"{_base_url()}/v2/checkout"
    body = {
        "amount": amount,
        "currency": "MXN",
        "purchase_description": description[:250],
    }
    if webhook_url:
        body["webhook_url"] = webhook_url
    if redirection_url:
        body["redirection_url"] = redirection_url
    if metadata:
        body["metadata"] = metadata
    if expires_at:
        body["expires_at"] = expires_at

    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        headers.update(_auth_headers())

        current_app.logger.info("Clip request POST %s body=%s", url, body)

        resp = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=15,
        )
        current_app.logger.info("Clip response status=%s body=%s", resp.status_code, resp.text)
        if resp.status_code != 200 and resp.status_code != 201:
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        # If we have a response, include its text
        if hasattr(e, 'response') and e.response is not None:
            raise ClipAPIError(f"Clip API HTTP error {e.response.status_code}: {e.response.text}")
        raise ClipAPIError(f"Clip API request failed: {e}")
    except Exception as e:
        raise ClipAPIError(f"Clip API error: {e}")

    return resp.json()


def verify_webhook_signature(raw_body, signature):
    secret = current_app.config.get("CLIP_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
