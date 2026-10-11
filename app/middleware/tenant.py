from functools import wraps
from flask import g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.extensions import db
from app.auth.models import (
    User, TENANT_STATUS_ACTIVE, TENANT_STATUS_PENDING,
    TENANT_STATUS_SUSPENDED, TENANT_STATUS_REJECTED,
)
from app.middleware.permisos import ROLE_ASISTENTE
from app.middleware.permisos_recepcion import (
    BASE_RECEPCION, BLOQUES, EXTRAS_RECEPCION, compilar,
    normalizar_permisos_recepcion,
)

# Base y bloques compilados una vez.
_BASE_COMPILADA = compilar(BASE_RECEPCION)
_BLOQUES_COMPILADOS = {clave: compilar(b["reglas"]) for clave, b in BLOQUES.items()}


def _coincide(reglas, method, path):
    return any(method == m and pattern.match(path) for m, pattern in reglas)


def check_recepcionista_access():
    """Recepcionista: base + bloques encendidos; si no, sus extras. Resto → 403.

    Los permisos se normalizan al leerlos: NULL o {} es "todo encendido", la
    recepcionista de siempre.
    """
    if not hasattr(g, "current_user"):
        return None
    if g.current_user.is_superuser:
        return None
    if g.current_user.role != "recepcionista":
        return None
    method, path = request.method, request.path
    permisos = normalizar_permisos_recepcion(g.current_user.permisos)

    if _coincide(_BASE_COMPILADA, method, path):
        return None
    apagados = set(permisos["bloques_apagados"])
    for clave, reglas in _BLOQUES_COMPILADOS.items():
        if clave not in apagados and _coincide(reglas, method, path):
            return None

    from app.middleware.permisos import autorizar_por_recurso
    blueprint = request.blueprints[0] if request.blueprints else None
    if autorizar_por_recurso(permisos["extras"], blueprint, method,
                             path.rstrip("/") or "/",
                             recursos_validos=EXTRAS_RECEPCION):
        # require_role no conoce los extras: esta marca le dice que la ruta ya
        # quedó autorizada por un permiso por usuario.
        g.acceso_por_extra = True
        return None
    return jsonify({"error": "No tienes acceso a esta sección"}), 403


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
            # Modo mentoría: un superadmin puede LEER datos de otra clínica con
            # ?as_tenant=<id> (o header X-As-Tenant). Restringido a GET como
            # señal de intención de lectura — OJO: no es garantía dura de "sin
            # escrituras" (algunos GET hacen lazy-create, p.ej.
            # /facturacion/configuracion crea la config si no existe).
            if request.method == "GET":
                override = (request.args.get("as_tenant")
                            or request.headers.get("X-As-Tenant", ""))
                if override and override.isascii() and override.isdigit():
                    g.tenant_id = int(override)
            return f(*args, **kwargs)
        if not user.is_active:
            return jsonify({"error": "Usuario deshabilitado"}), 403
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

        from app.middleware.modules import check_module_access
        blocked = check_module_access()
        if blocked is not None:
            return blocked

        from app.middleware.permisos import check_asistente_access
        blocked = check_asistente_access()
        if blocked is not None:
            return blocked

        blocked = check_recepcionista_access()
        if blocked is not None:
            return blocked

        return f(*args, **kwargs)
    decorated.__wrapped_por__ = getattr(f, "__wrapped_por__", ()) + ("require_auth",)
    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, "current_user"):
                return jsonify({"error": "No autenticado"}), 401
            # El asistente no se valida contra esta lista. Sus permisos son por
            # usuario y ya los resolvió check_asistente_access() dentro de
            # require_auth, que responde 403 si la ruta no le corresponde. Estas
            # listas de roles se escribieron antes de que el rol existiera, así
            # que no lo mencionan y lo bloquearían aunque el motor lo autorice.
            if g.current_user.role == ROLE_ASISTENTE:
                return f(*args, **kwargs)
            # Recepcionista que entró por un extra (recurso otorgado por el
            # admin en Ajustes → Usuarios): la autorización ya la resolvió
            # check_recepcionista_access. Las rutas de sus bloques no llevan
            # esta marca y siguen sujetas a la lista de roles.
            if getattr(g, "acceso_por_extra", False):
                return f(*args, **kwargs)
            if g.current_user.role not in roles:
                return jsonify({"error": "Permisos insuficientes"}), 403
            return f(*args, **kwargs)
        decorated.__wrapped_por__ = getattr(f, "__wrapped_por__", ()) + ("require_role",)
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
