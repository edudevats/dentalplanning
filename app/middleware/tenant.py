import re
from functools import wraps
from flask import g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.extensions import db
from app.auth.models import (
    User, TENANT_STATUS_ACTIVE, TENANT_STATUS_PENDING,
    TENANT_STATUS_SUSPENDED, TENANT_STATUS_REJECTED,
)
from app.middleware.permisos import ROLE_ASISTENTE

# (método, regex de ruta) que el rol recepcionista puede llamar. Resto → 403.
_RECEP_RULES = [
    ("GET", r"/api/v1/auth/me"),
    ("PUT", r"/api/v1/auth/password"),
    ("GET", r"/api/v1/edr/ingresos"),
    ("POST", r"/api/v1/edr/ingresos"),
    ("PUT", r"/api/v1/edr/ingresos/\d+"),
    ("GET", r"/api/v1/facturacion/tickets"),
    ("GET", r"/api/v1/facturacion/tickets/resumen-iva"),
    ("GET", r"/api/v1/facturacion/tickets/\d+"),
    ("GET", r"/api/v1/facturacion/tickets/\d+/impresion"),
    ("POST", r"/api/v1/facturacion/tickets/\d+/timbrar"),
    ("POST", r"/api/v1/facturacion/tickets/\d+/cancelar"),
    ("GET", r"/api/v1/facturacion/ingresos/\d+/ticket-simple"),
    ("GET", r"/api/v1/facturacion/sucursales"),
    ("GET", r"/api/v1/facturacion/configuracion"),
    ("GET", r"/api/v1/facturacion/print-agent/key"),
    ("GET", r"/api/v1/ajustes/especialistas"),
    ("GET", r"/api/v1/ajustes/metodos-pago"),
    ("GET", r"/api/v1/ajustes/estrategias"),
    ("GET", r"/api/v1/tratamientos"),
    # CRM (todo excepto DELETE paciente y PUT config)
    ("GET", r"/api/v1/crm/pacientes"),
    ("POST", r"/api/v1/crm/pacientes"),
    ("GET", r"/api/v1/crm/pacientes/\d+"),
    ("PUT", r"/api/v1/crm/pacientes/\d+"),
    ("PUT", r"/api/v1/crm/pacientes/\d+/estatus"),
    ("POST", r"/api/v1/crm/pacientes/\d+/visitas"),
    ("POST", r"/api/v1/crm/pacientes/\d+/seguimientos"),
    ("POST", r"/api/v1/crm/seguimientos/\d+/completar"),
    ("POST", r"/api/v1/crm/pacientes/\d+/notas"),
    ("POST", r"/api/v1/crm/pacientes/importar/preview"),
    ("POST", r"/api/v1/crm/pacientes/importar/confirmar"),
    ("GET", r"/api/v1/crm/sugerencias-edr"),
    ("POST", r"/api/v1/crm/sugerencias-edr/vincular"),
    ("GET", r"/api/v1/crm/resumen"),
    ("GET", r"/api/v1/crm/config"),
    # Cobranza: recepcion puede consultar, capturar/enviar cotizaciones y
    # registrar cobros. Aprobar, cancelar, borrar y reintentar facturacion
    # permanecen fuera de la allowlist.
    ("GET", r"/api/v1/cobranza/cotizaciones"),
    ("POST", r"/api/v1/cobranza/cotizaciones"),
    ("GET", r"/api/v1/cobranza/cotizaciones/\d+"),
    ("PUT", r"/api/v1/cobranza/cotizaciones/\d+"),
    ("POST", r"/api/v1/cobranza/cotizaciones/\d+/enviar"),
    ("POST", r"/api/v1/cobranza/cotizaciones/\d+/pagos"),
    ("GET", r"/api/v1/cobranza/cotizaciones/\d+/estado-cuenta"),
    ("GET", r"/api/v1/cobranza/cotizaciones/\d+/estado-cuenta\.pdf"),
    ("GET", r"/api/v1/cobranza/cotizaciones/\d+/pdf"),
    ("GET", r"/api/v1/cobranza/resumen"),
    # Turno de caja: es lo PRIMERO que hace la recepcionista al llegar. Sin
    # estas dos reglas no puede abrir su caja y, como el candado exige turno
    # abierto, no puede capturar absolutamente nada.
    ("GET", r"/api/v1/caja/turno"),
    ("POST", r"/api/v1/caja/turno"),
    # Corte de caja: consulta el día, registra salidas chicas de efectivo y
    # cierra. El histórico y la reapertura son del admin y quedan FUERA.
    ("GET", r"/api/v1/caja/corte"),
    ("POST", r"/api/v1/caja/corte"),
    ("GET", r"/api/v1/caja/salidas"),
    ("POST", r"/api/v1/caja/salidas"),
    ("DELETE", r"/api/v1/caja/salidas/\d+"),
]
RECEPCIONISTA_ALLOWLIST = [(m, re.compile("^" + p + "/?$")) for m, p in _RECEP_RULES]


def check_recepcionista_access():
    """Si el usuario es recepcionista, solo permite método+ruta de la allowlist."""
    if not hasattr(g, "current_user"):
        return None
    if g.current_user.is_superuser:
        return None
    if g.current_user.role != "recepcionista":
        return None
    method, path = request.method, request.path
    for m, pattern in RECEPCIONISTA_ALLOWLIST:
        if method == m and pattern.match(path):
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
