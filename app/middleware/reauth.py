"""Revalidación de contraseña para operaciones destructivas.

Va SIEMPRE después de @require_auth y @require_role("admin"). Protege contra
la sesión abierta y desatendida: aunque el rol ya autorice la acción, se pide
de nuevo la contraseña del propio usuario.
"""
from functools import wraps

from flask import current_app, g, jsonify, request

from app.middleware.rate_limit import _RateLimiter

# Cuenta SOLO intentos fallidos, por usuario. Las operaciones legítimas
# repetidas (borrar varios pagos) no consumen cuota.
_reauth_failures = _RateLimiter()
MAX_FALLOS = 5
VENTANA_SEG = 300


def require_admin_password(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"error": "No autenticado"}), 401

        enabled = current_app.config.get("RATELIMIT_ENABLED", True)
        key = f"reauth:{user.id}"
        if enabled and _reauth_failures.remaining(key, MAX_FALLOS, VENTANA_SEG) <= 0:
            return jsonify({
                "error": "Demasiados intentos fallidos. Espera unos minutos.",
            }), 429

        body = request.get_json(silent=True) or {}
        password = (body.get("admin_password") or "").strip()
        if not password:
            return jsonify({
                "error": "Escribe la contraseña de administrador para continuar",
            }), 400
        if not user.check_password(password):
            if enabled:
                # Registra el fallo (append en el bucket del usuario).
                _reauth_failures.is_allowed(key, MAX_FALLOS, VENTANA_SEG)
            return jsonify({"error": "Contraseña incorrecta"}), 403
        return f(*args, **kwargs)
    return decorated
