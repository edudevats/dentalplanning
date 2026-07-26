from functools import wraps
from flask import g, jsonify, request
from app.extensions import db
from app.auth.models import Tenant

BLUEPRINT_MODULE_MAP = {
    "inventario": ("inventario",),
    "finanzas_personales": ("finanzas_personales",),
    "crm": ("crm",),
    # Cobranza depends on CRM patients and visits.
    "cobranza": ("cobranza", "crm"),
}


def check_module_access():
    if not hasattr(g, "current_user") or not hasattr(g, "tenant_id"):
        return None
    if g.current_user.is_superuser:
        return None

    bp = request.blueprints[0] if request.blueprints else None
    module_slugs = BLUEPRINT_MODULE_MAP.get(bp)
    if not module_slugs:
        return None

    tenant = db.session.get(Tenant, g.tenant_id)
    if not tenant:
        return None

    missing = [
        module_slug for module_slug in module_slugs
        if module_slug not in tenant.allowed_modules
    ]
    if missing:
        return jsonify({
            "error": (
                "Tu plan no incluye los módulos necesarios: "
                + ", ".join(missing)
                + ". Contacta al administrador para actualizar tu plan."
            )
        }), 403

    return None


def require_module(module_slug):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, "current_user"):
                return jsonify({"error": "No autenticado"}), 401
            if g.current_user.is_superuser:
                return f(*args, **kwargs)

            tenant = db.session.get(Tenant, g.tenant_id)
            if not tenant:
                return jsonify({"error": "Tenant no encontrado"}), 404

            if module_slug not in tenant.allowed_modules:
                return jsonify({
                    "error": "Tu plan no incluye este módulo. Contacta al administrador para actualizar tu plan."
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator
