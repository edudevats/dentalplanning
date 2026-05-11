from functools import wraps
from flask import g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.extensions import db
from app.auth.models import (
    User, TENANT_STATUS_ACTIVE, TENANT_STATUS_PENDING,
    TENANT_STATUS_SUSPENDED, TENANT_STATUS_REJECTED,
)


_STATUS_MESSAGES = {
    TENANT_STATUS_PENDING: "Cuenta pendiente de aprobación",
    TENANT_STATUS_SUSPENDED: "Cuenta suspendida",
    TENANT_STATUS_REJECTED: "Cuenta rechazada",
}


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 401
        # Super-admin bypassa el chequeo de tenant
        if user.is_superuser:
            g.current_user = user
            g.tenant_id = user.tenant_id
            return f(*args, **kwargs)
        if user.tenant.status != TENANT_STATUS_ACTIVE:
            msg = _STATUS_MESSAGES.get(user.tenant.status, "Cuenta no activa")
            return jsonify({"error": msg}), 403
        # Force password change if flagged (allow only /auth/password)
        if user.must_change_password and request.path != "/api/v1/auth/password":
            return jsonify({
                "error": "Debes cambiar tu contraseña temporal",
                "must_change_password": True,
            }), 403
        g.current_user = user
        g.tenant_id = user.tenant_id
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, "current_user"):
                return jsonify({"error": "No autenticado"}), 401
            if g.current_user.role not in roles:
                return jsonify({"error": "Permisos insuficientes"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_superuser(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if not user or not user.is_superuser:
            return jsonify({"error": "Acceso restringido"}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated
