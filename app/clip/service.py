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

        auth_header = headers.get("Authorization", "")
        auth_type = auth_header.split(" ")[0] if auth_header else "NONE"
        auth_len = len(auth_header)
        current_app.logger.info("Clip auth type=%s header_len=%s has_x_api_key=%s",
                                auth_type, auth_len, "x-api-key" in headers)
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


def create_price(name, description, amount, webhook_url, success_url, error_url, default_url,
                 anchor_on_first_payment=True, billing_day=None, grace_period_days=2,
                 interval="month", frequency=1, repeat=0, additional_information=None):
    """POST /prices — Create a recurring price (subscription plan) in Clip.

    Returns the Clip price object with `id` and `recurring.subscription_link`.
    """
    url = f"{_base_url()}/prices"
    body = {
        "name": name[:256],
        "description": description[:256],
        "amount": float(amount),
        "recurring": {
            "interval": interval,
            "frequency": frequency,
            "repeat": repeat,
            "billing_day": [] if anchor_on_first_payment else (billing_day or [1]),
            "anchor_billing_on_first_payment": bool(anchor_on_first_payment),
            "grace_period_days": grace_period_days,
        },
        "webhook_url": webhook_url,
        "redirect_urls": {
            "success": success_url,
            "error": error_url,
            "default": default_url,
        },
    }
    if additional_information:
        body["additional_information"] = additional_information[:4]

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    headers.update(_auth_headers())

    try:
        current_app.logger.info("Clip POST %s body=%s", url, body)
        resp = requests.post(url, json=body, headers=headers, timeout=20)
        current_app.logger.info("Clip price create status=%s body=%s",
                                resp.status_code, resp.text[:500])
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def get_price(price_id):
    """GET /prices/{id} — get a Clip price by ID."""
    url = f"{_base_url()}/prices/{price_id}"
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            return None
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def list_prices():
    """GET /prices — list all Clip prices."""
    url = f"{_base_url()}/prices"
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def get_subscription(subscription_id):
    """GET /subscriptions/{id} — get a Clip subscription with its invoices."""
    url = f"{_base_url()}/subscriptions/{subscription_id}"
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            return None
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def cancel_subscription(subscription_id):
    """PUT /subscriptions/{id} status=inactive. Irreversible per Clip docs."""
    url = f"{_base_url()}/subscriptions/{subscription_id}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    headers.update(_auth_headers())
    try:
        resp = requests.put(url, json={"status": "inactive"}, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def get_invoice(invoice_id):
    """GET /invoices/{id} — get a Clip invoice."""
    url = f"{_base_url()}/invoices/{invoice_id}"
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            return None
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def get_checkout_status(payment_request_id):
    """GET /v2/checkout/{id} — returns the current status of a checkout link.

    Useful to verify if a customer actually paid (status CHECKOUT_COMPLETED)
    when the webhook was missed for any reason.
    """
    if not payment_request_id:
        raise ClipAPIError("payment_request_id is required")

    url = f"{_base_url()}/v2/checkout/{payment_request_id}"
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())

    try:
        current_app.logger.info("Clip GET %s", url)
        resp = requests.get(url, headers=headers, timeout=15)
        current_app.logger.info("Clip checkout status=%s body=%s",
                                resp.status_code, resp.text[:500])
        if resp.status_code == 404:
            return None
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def list_payments(from_dt, to_dt, size=100):
    """GET /payments?from=X&to=Y — list all transactions in a date range.

    Args:
        from_dt: datetime or ISO8601 string
        to_dt: datetime or ISO8601 string
        size: page size (default 100)
    """
    if hasattr(from_dt, "isoformat"):
        from_str = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        from_str = str(from_dt)
    if hasattr(to_dt, "isoformat"):
        to_str = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        to_str = str(to_dt)

    url = f"{_base_url()}/payments"
    params = {"from": from_str, "to": to_str, "size": size}
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())

    try:
        current_app.logger.info("Clip GET %s params=%s", url, params)
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        current_app.logger.info("Clip payments list status=%s", resp.status_code)
        if resp.status_code not in (200, 201):
            raise ClipAPIError(f"Clip API error status {resp.status_code}: {resp.text}")
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise ClipAPIError(f"Clip API request failed: {e}")


def verify_webhook_signature(raw_body, signature):
    secret = current_app.config.get("CLIP_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
