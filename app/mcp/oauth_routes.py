"""Rutas OAuth 2.1 del MCP: metadatos, registro, pantalla de autorización y tokens.

La lógica vive en app/mcp/oauth.py; aquí solo HTTP. Los límites de intentos se
cuentan en la base (OAuthIntento) porque en producción hay varios workers.
"""
import calendar
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Blueprint, current_app, jsonify, redirect, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth.models import User
from app.extensions import db
from app.mcp import oauth
from app.mcp.models import OAuthIntento, _ahora

oauth_bp = Blueprint("oauth", __name__)

_CAMPOS_OCULTOS = ("client_id", "redirect_uri", "response_type", "state",
                   "code_challenge", "code_challenge_method", "resource", "scope")
_CAMPOS_CSRF = ("client_id", "redirect_uri", "code_challenge", "state", "resource")
_CSRF_SALT = "oauth-autorizar"
_CSRF_MAX_AGE = 600

_LIMITE_IP = (5, 60)
_LIMITE_EMAIL = (10, 900)
_LIMITE_REGISTRO = (10, 3600)

_RUTAS_CORS = ("/.well-known/", "/oauth/register", "/oauth/token", "/oauth/revoke")

_MSG_CREDENCIALES = "Correo o contraseña incorrectos"
_MSG_CAMBIAR = "Entra a Dental Planning y cambia tu contraseña primero"
_MSG_DEMASIADOS = "Demasiados intentos. Espera un momento e intenta de nuevo."

# Hash de relleno para que un correo desconocido tarde lo mismo que una
# contraseña incorrecta (no revelar qué correos existen).
_HASH_RELLENO = generate_password_hash("relleno-no-es-una-contraseña")


def ip_cliente():
    # PythonAnywhere manda la IP real en X-Real-IP; remote_addr es su balanceador.
    return request.headers.get("X-Real-IP") or request.remote_addr or ""


# ---- límites en BD ----

def _excedido(clave, limite):
    maximo, segundos = limite
    desde = _ahora() - timedelta(seconds=segundos)
    n = OAuthIntento.query.filter(OAuthIntento.clave == clave,
                                  OAuthIntento.created_at >= desde).count()
    return n >= maximo


def _registrar_intento(*claves):
    for clave in claves:
        db.session.add(OAuthIntento(clave=clave[:300]))
    db.session.commit()


# ---- CORS y cabeceras ----

@oauth_bp.after_request
def _cabeceras(resp):
    if request.path.startswith(_RUTAS_CORS):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type, MCP-Protocol-Version")
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    elif request.path == "/oauth/authorize":
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _preflight():
    return "", 204


@oauth_bp.before_request
def _exigir_base_url():
    # Todas las rutas (metadatos, registro, authorize, token, revoke) dependen
    # del issuer/resource públicos: sin APP_BASE_URL válida ninguna atiende.
    oauth.base_url()


@oauth_bp.errorhandler(oauth.ConfiguracionFaltante)
def _sin_base_url(error):
    # Fallar cerrado: sin APP_BASE_URL https no se anuncia ni emite nada.
    current_app.logger.error("OAuth MCP sin APP_BASE_URL válida: %s", error)
    if request.path == "/oauth/authorize":
        return _pagina(503, error=oauth.MSG_SIN_BASE_URL)
    return _error_json("server_error", oauth.MSG_SIN_BASE_URL, 503)


# ---- metadatos ----

def _metadatos_recurso():
    return {
        "resource": oauth.recurso(),
        "authorization_servers": [oauth.base_url()],
        "scopes_supported": [oauth.SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Dental Planning",
    }


@oauth_bp.route("/.well-known/oauth-protected-resource", methods=["GET", "OPTIONS"])
@oauth_bp.route("/.well-known/oauth-protected-resource/mcp", methods=["GET", "OPTIONS"])
def metadatos_recurso():
    if request.method == "OPTIONS":
        return _preflight()
    return jsonify(_metadatos_recurso())


@oauth_bp.route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
@oauth_bp.route("/.well-known/openid-configuration", methods=["GET", "OPTIONS"])
def metadatos_servidor():
    if request.method == "OPTIONS":
        return _preflight()
    base = oauth.base_url()
    return jsonify({
        "issuer": base,
        "authorization_endpoint": base + "/oauth/authorize",
        "token_endpoint": base + "/oauth/token",
        "registration_endpoint": base + "/oauth/register",
        "revocation_endpoint": base + "/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [oauth.SCOPE],
    })


# ---- registro ----

def _error_json(codigo, descripcion, status):
    return jsonify({"error": codigo, "error_description": descripcion}), status


@oauth_bp.route("/oauth/register", methods=["POST", "OPTIONS"])
def registrar():
    if request.method == "OPTIONS":
        return _preflight()
    clave = f"registro:{ip_cliente()}"
    if _excedido(clave, _LIMITE_REGISTRO):
        return _error_json("too_many_requests",
                           "Demasiados registros desde esta IP. Intenta más tarde.", 429)
    try:
        cliente = oauth.registrar_cliente(request.get_json(silent=True))
    except oauth.OAuthError as e:
        return _error_json(e.codigo, e.descripcion, 400)
    _registrar_intento(clave)
    return jsonify({
        "client_id": cliente.client_id,
        "client_name": cliente.client_name,
        "redirect_uris": cliente.redirect_uris,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_id_issued_at": calendar.timegm(cliente.created_at.utctimetuple()),
    }), 201


# ---- autorización ----

def _serializador():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_CSRF_SALT)


def _campos(fuente):
    return {k: fuente.get(k) or "" for k in _CAMPOS_OCULTOS}


def _csrf_para(campos):
    return _serializador().dumps({k: campos[k] for k in _CAMPOS_CSRF})


def _csrf_valido(token, campos):
    if not token:
        return False
    try:
        datos = _serializador().loads(token, max_age=_CSRF_MAX_AGE)
    except BadSignature:  # incluye SignatureExpired
        return False
    return datos == {k: campos[k] for k in _CAMPOS_CSRF}


_HOSTS_CLAUDE = ("claude.ai", "claude.com")
_HOSTS_LOCALES = ("localhost", "127.0.0.1")


def _host_de_claude(host):
    """El nombre del cliente lo elige quien lo registra; el host de regreso no."""
    host = (host or "").lower()
    return (host in _HOSTS_CLAUDE + _HOSTS_LOCALES
            or any(host.endswith("." + h) for h in _HOSTS_CLAUDE))


def _pagina(status, error=None, solicitud=None, campos=None, email=""):
    """Sin `solicitud` solo muestra el error: no hay formulario ni redirección."""
    contexto = {"public_page": True, "error": error, "email": email}
    if solicitud is not None:
        host = urlsplit(solicitud["redirect_uri"]).hostname or ""
        contexto.update(cliente_nombre=solicitud["cliente"].client_name,
                        campos=campos, csrf=_csrf_para(campos),
                        redirect_host=host, host_de_claude=_host_de_claude(host))
    return render_template("oauth/autorizar.html", **contexto), status


def _redirigir(uri, **params):
    partes = urlsplit(uri)
    query = parse_qsl(partes.query, keep_blank_values=True)
    query += [(k, v) for k, v in params.items() if v]
    return redirect(urlunsplit(partes._replace(query=urlencode(query))), code=302)


def _validar(campos):
    try:
        return oauth.validar_solicitud(campos), None
    except oauth.OAuthError as e:
        return None, e.descripcion or "Solicitud de autorización inválida"


@oauth_bp.route("/oauth/authorize", methods=["GET"])
def autorizar_get():
    campos = _campos(request.args)
    solicitud, error = _validar(campos)
    if solicitud is None:
        return _pagina(400, error=error)
    return _pagina(200, solicitud=solicitud, campos=campos)


@oauth_bp.route("/oauth/authorize", methods=["POST"])
def autorizar_post():
    campos = _campos(request.form)
    solicitud, error = _validar(campos)
    if solicitud is None:
        return _pagina(400, error=error)
    if not _csrf_valido(request.form.get("csrf"), campos):
        return _pagina(400, error="La solicitud venció o fue alterada. "
                                  "Vuelve a iniciar la conexión desde Claude.")

    accion = request.form.get("accion")
    if accion == "cancelar":
        return _redirigir(solicitud["redirect_uri"], error="access_denied",
                          state=campos["state"])
    if accion != "permitir":
        return _pagina(400, error="Acción desconocida")

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    clave_ip = f"auth-ip:{ip_cliente()}"
    clave_email = f"auth-email:{email.lower()}"
    if _excedido(clave_ip, _LIMITE_IP) or _excedido(clave_email, _LIMITE_EMAIL):
        return _pagina(429, error=_MSG_DEMASIADOS, solicitud=solicitud,
                       campos=campos, email=email)

    user = (User.query.filter(db.func.lower(User.email) == email.lower()).first()
            if email else None)
    if user is None:
        check_password_hash(_HASH_RELLENO, password)
        valida = False
    else:
        valida = user.check_password(password)

    if not valida:
        if user is not None and user.check_temp_password(password):
            return _pagina(403, error=_MSG_CAMBIAR, solicitud=solicitud,
                           campos=campos, email=email)
        _registrar_intento(clave_ip, clave_email)
        return _pagina(401, error=_MSG_CREDENCIALES, solicitud=solicitud,
                       campos=campos, email=email)
    if user.must_change_password:
        return _pagina(403, error=_MSG_CAMBIAR, solicitud=solicitud,
                       campos=campos, email=email)

    try:
        codigo = oauth.emitir_codigo(user, solicitud)
    except oauth.OAuthError as e:
        return _pagina(403, error=e.descripcion, solicitud=solicitud,
                       campos=campos, email=email)
    return _redirigir(solicitud["redirect_uri"], code=codigo, state=campos["state"])


# ---- tokens ----

def _sin_cache(resp, status=200):
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp


@oauth_bp.route("/oauth/token", methods=["POST", "OPTIONS"])
def token():
    if request.method == "OPTIONS":
        return _preflight()
    f = request.form
    grant = f.get("grant_type")
    try:
        if grant == "authorization_code":
            datos = oauth.canjear_codigo(f.get("code"), f.get("client_id"),
                                         f.get("redirect_uri"), f.get("code_verifier"),
                                         f.get("resource"))
        elif grant == "refresh_token":
            datos = oauth.refrescar(f.get("refresh_token"), f.get("client_id"),
                                    f.get("resource"))
        else:
            return _sin_cache(jsonify({
                "error": "unsupported_grant_type",
                "error_description": "grant_type debe ser authorization_code o refresh_token",
            }), 400)
    except oauth.OAuthError as e:
        status = 401 if e.codigo == "invalid_client" else 400
        return _sin_cache(jsonify({"error": e.codigo,
                                   "error_description": e.descripcion}), status)
    return _sin_cache(jsonify(datos))


@oauth_bp.route("/oauth/revoke", methods=["POST", "OPTIONS"])
def revocar():
    if request.method == "OPTIONS":
        return _preflight()
    oauth.revocar_token(request.form.get("token"))
    return "", 200
