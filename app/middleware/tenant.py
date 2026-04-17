from functools import wraps
from flask import g, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.extensions import db
from app.auth.models import User


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 401
        if not user.tenant.is_active:
            return jsonify({"error": "Cuenta desactivada"}), 403
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
