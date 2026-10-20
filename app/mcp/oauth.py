"""OAuth 2.1 del MCP: registro de clientes, códigos con PKCE y tokens con rotación.

Solo lógica: las rutas y la pantalla de consentimiento viven en otro módulo.
Solo se guardan hashes SHA-256 de códigos y tokens.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from flask import current_app, request

from app.extensions import db
from app.mcp import tokens
from app.mcp.models import (
    OAuthCliente, OAuthCodigo, OAuthConcesion, OAuthToken, _ahora,
)

SCOPE = "reportes:lectura"
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400
CODIGO_TTL = 600

PREFIJO_ACCESS = "dpoat_"
PREFIJO_REFRESH = "dport_"
_HOSTS_LOCALES = ("localhost", "127.0.0.1")
_MAX_REDIRECTS = 5


class OAuthError(Exception):
    def __init__(self, codigo, descripcion=""):
        super().__init__(f"{codigo}: {descripcion}")
        self.codigo = codigo
        self.descripcion = descripcion


class ConfiguracionFaltante(RuntimeError):
    """APP_BASE_URL falta o no es https fuera de desarrollo/pruebas."""


MSG_SIN_BASE_URL = "APP_BASE_URL no está configurada"


def base_url():
    """URL pública del servidor (issuer y resource).

    En producción sale solo de APP_BASE_URL y debe ser https: el Host de la
    petición lo controla quien la manda. Solo en DEBUG/TESTING se cae al host.
    """
    configurada = (current_app.config.get("APP_BASE_URL") or "").strip()
    if current_app.debug or current_app.testing:
        return (configurada or request.url_root).rstrip("/")
    if not configurada.startswith("https://"):
        raise ConfiguracionFaltante(MSG_SIN_BASE_URL)
    return configurada.rstrip("/")


def recurso():
    return base_url() + "/mcp"


# ---- registro de clientes ----

def _redirect_valido(uri):
    if not isinstance(uri, str) or not uri or "#" in uri or len(uri) > 500:
        return False
    try:
        p = urlparse(uri)
        p.port  # noqa: B018 - lanza ValueError si el puerto es inválido
    except ValueError:
        return False
    if not p.hostname or p.username or p.password or not p.path.startswith("/"):
        return False
    if p.scheme == "https":
        return True
    return p.scheme == "http" and p.hostname in _HOSTS_LOCALES


def registrar_cliente(metadata):
    metadata = metadata if isinstance(metadata, dict) else {}
    uris = metadata.get("redirect_uris")
    if (not isinstance(uris, list) or not 1 <= len(uris) <= _MAX_REDIRECTS
            or not all(_redirect_valido(u) for u in uris)):
        raise OAuthError("invalid_redirect_uri",
                         "redirect_uris debe tener de 1 a 5 URIs https o http://localhost")
    # RFC 7591 §3.2.1: el servidor puede ignorar el método pedido. Todo cliente
    # se registra como público (none) y así se le responde.
    nombre = metadata.get("client_name")
    nombre = nombre.strip() if isinstance(nombre, str) else ""
    cliente = OAuthCliente(
        client_id=secrets.token_urlsafe(24),
        client_name=(nombre or "Cliente MCP")[:100],
        redirect_uris=list(uris),
    )
    db.session.add(cliente)
    db.session.commit()
    return cliente


# ---- autorización ----

def validar_solicitud(params):
    cliente = OAuthCliente.query.filter_by(client_id=params.get("client_id") or "").first()
    if cliente is None:
        raise OAuthError("invalid_client", "Cliente desconocido")
    redirect_uri = params.get("redirect_uri") or ""
    if redirect_uri not in (cliente.redirect_uris or []):
        raise OAuthError("invalid_redirect_uri", "redirect_uri no registrada para este cliente")
    if params.get("response_type") != "code":
        raise OAuthError("invalid_request", "response_type debe ser code")
    challenge = params.get("code_challenge") or ""
    if not challenge or params.get("code_challenge_method") != "S256":
        raise OAuthError("invalid_request", "Se requiere PKCE con code_challenge_method=S256")
    resource = params.get("resource") or recurso()
    if resource != recurso():
        raise OAuthError("invalid_target", "resource no corresponde a este servidor")
    return {
        "cliente": cliente,
        "redirect_uri": redirect_uri,
        "state": params.get("state"),
        "code_challenge": challenge,
        "resource": resource,
    }


def emitir_codigo(user, solicitud):
    cliente = solicitud["cliente"]
    motivo = tokens.motivo_no_elegible(user)
    if motivo:
        raise OAuthError("access_denied", motivo)
    concesion = OAuthConcesion.query.filter_by(
        user_id=user.id, cliente_id=cliente.id, revoked_at=None).first()
    if concesion is None:
        concesion = OAuthConcesion(tenant_id=user.tenant_id, user_id=user.id,
                                   cliente_id=cliente.id)
        db.session.add(concesion)
        db.session.flush()
    claro = secrets.token_urlsafe(32)
    db.session.add(OAuthCodigo(
        code_hash=tokens._hash(claro),
        concesion_id=concesion.id,
        redirect_uri=solicitud["redirect_uri"],
        code_challenge=solicitud["code_challenge"],
        resource=solicitud["resource"],
        expira=_ahora() + timedelta(seconds=CODIGO_TTL),
    ))
    db.session.commit()
    return claro


def _pkce_ok(verifier, challenge):
    digest = hashlib.sha256((verifier or "").encode()).digest()
    esperado = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return hmac.compare_digest(esperado, challenge or "")


def _grant_invalido(descripcion="Código inválido o vencido"):
    return OAuthError("invalid_grant", descripcion)


def canjear_codigo(code, client_id, redirect_uri, code_verifier, resource):
    registro = OAuthCodigo.query.filter_by(code_hash=tokens._hash(code or "")).first()
    if registro is None or registro.expira <= _ahora():
        raise _grant_invalido()
    concesion = registro.concesion
    if concesion.cliente.client_id != client_id or registro.redirect_uri != redirect_uri:
        # Antes que el reuso: un código ajeno no debe poder revocar la concesión.
        raise _grant_invalido()
    if registro.usado_at is not None:
        # Código ya canjeado: RFC 6749 4.1.2 pide revocar lo emitido con él.
        revocar_concesion(concesion)
        raise _grant_invalido("Código ya utilizado")
    if not _pkce_ok(code_verifier, registro.code_challenge):
        # Un verifier equivocado quema el código: no se puede seguir probando.
        # También vence ya, para que un reintento caiga en "vencido" y no en
        # "reusado": quien solo robó el código no puede revocar la concesión.
        ahora = _ahora()
        OAuthCodigo.query.filter_by(id=registro.id, usado_at=None).update(
            {"usado_at": ahora, "expira": ahora}, synchronize_session=False)
        db.session.commit()
        raise _grant_invalido("code_verifier no coincide")
    if concesion.revoked_at is not None or tokens.motivo_no_elegible(concesion.user):
        raise _grant_invalido("La conexión fue revocada")
    if resource and resource != registro.resource:
        raise OAuthError("invalid_target", "resource no coincide con el de la autorización")
    # Reclamo atómico: solo un canje simultáneo del mismo código puede ganar.
    reclamado = OAuthCodigo.query.filter_by(id=registro.id, usado_at=None).update(
        {"usado_at": _ahora()}, synchronize_session=False)
    if reclamado != 1:
        db.session.rollback()
        revocar_concesion(db.session.get(OAuthConcesion, concesion.id))
        raise _grant_invalido("Código ya utilizado")
    par, _ = _emitir_par(concesion, registro.resource)
    db.session.commit()
    return par


# ---- tokens ----

def _emitir_par(concesion, resource):
    """Agrega el par a la sesión (sin commit) y devuelve (respuesta, fila_refresh)."""
    ahora = _ahora()
    access = PREFIJO_ACCESS + secrets.token_urlsafe(32)
    refresh = PREFIJO_REFRESH + secrets.token_urlsafe(32)
    t_access = OAuthToken(token_hash=tokens._hash(access), tipo="access",
                          concesion_id=concesion.id, resource=resource,
                          expira=ahora + timedelta(seconds=ACCESS_TTL))
    t_refresh = OAuthToken(token_hash=tokens._hash(refresh), tipo="refresh",
                           concesion_id=concesion.id, resource=resource,
                           expira=ahora + timedelta(seconds=REFRESH_TTL))
    db.session.add_all([t_access, t_refresh])
    db.session.flush()
    return ({"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_TTL,
             "refresh_token": refresh, "scope": SCOPE}, t_refresh)


def refrescar(refresh_token, client_id, resource):
    viejo = OAuthToken.query.filter_by(
        token_hash=tokens._hash(refresh_token or ""), tipo="refresh").first()
    if viejo is None or viejo.expira <= _ahora():
        raise _grant_invalido("Refresh token inválido o vencido")
    concesion = viejo.concesion
    if concesion.cliente.client_id != client_id:
        raise _grant_invalido("Refresh token inválido")
    if viejo.revoked_at is not None or viejo.reemplazado_por_id is not None:
        # Reuso de un refresh ya rotado: se asume robo y se cierra toda la concesión.
        revocar_concesion(concesion)
        raise _grant_invalido("Refresh token ya utilizado")
    if concesion.revoked_at is not None or tokens.motivo_no_elegible(concesion.user):
        raise _grant_invalido("La conexión fue revocada")
    if resource and resource != viejo.resource:
        raise OAuthError("invalid_target", "resource no coincide con el de la autorización")
    # Reclamo atómico del refresh viejo: si otro lo rotó antes, es un reuso.
    reclamado = OAuthToken.query.filter_by(
        id=viejo.id, revoked_at=None, reemplazado_por_id=None).update(
        {"revoked_at": _ahora()}, synchronize_session=False)
    if reclamado != 1:
        db.session.rollback()
        revocar_concesion(db.session.get(OAuthConcesion, concesion.id))
        raise _grant_invalido("Refresh token ya utilizado")
    respuesta, nuevo = _emitir_par(concesion, viejo.resource)
    OAuthToken.query.filter_by(id=viejo.id).update(
        {"reemplazado_por_id": nuevo.id}, synchronize_session=False)
    db.session.commit()
    return respuesta


def revocar_concesion(concesion):
    ahora = _ahora()
    concesion.revoked_at = concesion.revoked_at or ahora
    OAuthToken.query.filter_by(concesion_id=concesion.id, revoked_at=None).update(
        {"revoked_at": ahora})
    db.session.commit()


def revocar_token(token):
    """RFC 7009: un token desconocido no es error ni hace nada."""
    registro = OAuthToken.query.filter_by(token_hash=tokens._hash(token or "")).first()
    if registro is not None:
        revocar_concesion(registro.concesion)


def autenticar_access_token(claro):
    if not claro or not claro.startswith(PREFIJO_ACCESS):
        raise tokens.TokenInvalido("Token inválido")
    registro = OAuthToken.query.filter_by(token_hash=tokens._hash(claro), tipo="access").first()
    if (registro is None or registro.revoked_at is not None
            or registro.expira <= _ahora() or registro.resource != recurso()):
        raise tokens.TokenInvalido("Token inválido, vencido o revocado")
    concesion = registro.concesion
    if concesion.revoked_at is not None:
        raise tokens.TokenInvalido("Token inválido o revocado")
    user = concesion.user
    if user is None or user.tenant_id != concesion.tenant_id:
        raise tokens.TokenInvalido("Token inválido")
    motivo = tokens.motivo_no_elegible(user)
    if motivo:
        raise tokens.TokenInvalido(motivo)
    concesion.last_used_at = _ahora()
    db.session.commit()
    return user
