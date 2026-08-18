"""Revalidación de contraseña para operaciones destructivas.

Va SIEMPRE después de @require_auth y @require_role("admin"). Protege contra
la sesión abierta y desatendida: aunque el rol ya autorice la acción, se pide
de nuevo la contraseña del propio usuario.

Ya NO delega el control de rol en @require_role("admin"): desde que ese
decorador deja pasar al rol asistente (sus permisos son por usuario, resueltos
en require_auth), require_admin_password valida el rol explícitamente. De lo
contrario, un asistente con el recurso en `editar` llegaría a estas rutas
destructivas usando su propia contraseña —el segundo factor quedaría
neutralizado, no reforzado.
"""
from functools import wraps

from flask import current_app, g, jsonify, request

from app.middleware.permisos import ROLE_ASISTENTE
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

        # El asistente no pasa este candado. require_admin_password solo verifica
        # la contraseña DEL PROPIO usuario en sesión —que el asistente obviamente
        # tiene—; el control de rol lo delegaba en require_role, que el rol
        # asistente ya no respeta. Sin este chequeo, el segundo factor de las
        # rutas destructivas de cobranza quedaría neutralizado.
        if user.role == ROLE_ASISTENTE:
            return jsonify({
                "error": "Esta operación está reservada al administrador"
            }), 403

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
