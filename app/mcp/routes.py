"""Endpoint MCP (/mcp) y gestión de tokens (/api/v1/mcp/tokens).

El MCP habla JSON-RPC sobre "Streamable HTTP" en modo sin estado: cada POST
trae un mensaje y la respuesta es JSON (sin SSE). Solo expone herramientas de
lectura, así que no necesita sesiones, notificaciones del servidor ni streams.
"""
import json

from flask import Blueprint, current_app, g, jsonify, request

from app.extensions import db
from app.mcp import herramientas, limite, oauth, tokens
from app.mcp.consultas import ConsultaInvalida
from app.mcp.models import McpToken, OAuthConcesion
from app.middleware.tenant import require_auth, require_role

mcp_bp = Blueprint("mcp", __name__)

VERSIONES_PROTOCOLO = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCCIONES = (
    "Datos de una clínica dental en Dental Planning, solo lectura. Montos en pesos "
    "mexicanos; las ventas no incluyen IVA. Las fechas son de la zona horaria de "
    "Ciudad de México. De los pacientes solo se conoce el nombre."
)


def _error_auth(mensaje):
    respuesta = jsonify({"error": mensaje})
    respuesta.status_code = 401
    metadatos = f"{oauth.base_url()}/.well-known/oauth-protected-resource/mcp"
    respuesta.headers["WWW-Authenticate"] = (
        f'Bearer realm="dental-planning-mcp", resource_metadata="{metadatos}"')
    return respuesta


@mcp_bp.errorhandler(oauth.ConfiguracionFaltante)
def _sin_base_url(error):
    current_app.logger.error("MCP sin APP_BASE_URL válida: %s", error)
    return jsonify({"error": "server_error", "error_description": oauth.MSG_SIN_BASE_URL}), 503


def _resultado(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, codigo, mensaje):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensaje}}


def _texto(contenido, es_error=False):
    if isinstance(contenido, str):
        resultado = {"content": [{"type": "text", "text": contenido}]}
    else:
        resultado = {
            "content": [{"type": "text",
                         "text": json.dumps(contenido, ensure_ascii=False, default=str)}],
            "structuredContent": contenido,
        }
    resultado["isError"] = es_error
    return resultado


def _llamar_herramienta(id_, params):
    nombre = params.get("name")
    argumentos = params.get("arguments") or {}
    herramienta = herramientas.buscar(g.current_user.tenant, nombre)
    if herramienta is None:
        return _error(id_, -32602, f"Herramienta desconocida: {nombre}")
    if not isinstance(argumentos, dict):
        return _error(id_, -32602, "arguments debe ser un objeto")
    espera = limite.segundos_de_espera(g.tenant_id)
    if espera is not None:
        return _resultado(id_, _texto(
            "Llegaste al límite de consultas de tu clínica; intenta de nuevo en "
            f"{espera} {'segundo' if espera == 1 else 'segundos'}.",
            es_error=True,
        ))
    limite.registrar(g.tenant_id, g.current_user.id, nombre)
    current_app.logger.info(
        "mcp tool=%s tenant=%s user=%s", nombre, g.tenant_id, g.current_user.id,
    )
    try:
        datos = herramienta["_consulta"](g.tenant_id, argumentos)
    except (ConsultaInvalida, ValueError, TypeError) as error:
        db.session.rollback()
        return _resultado(id_, _texto(str(error), es_error=True))
    except Exception:  # noqa: BLE001 — Claude recibe un error legible, el log el detalle
        db.session.rollback()
        current_app.logger.exception("mcp tool=%s falló", nombre)
        return _resultado(id_, _texto("Error interno al consultar los datos", es_error=True))
    return _resultado(id_, _texto(datos))


def _despachar(mensaje):
    """Respuesta JSON-RPC de un mensaje, o None si era una notificación."""
    if not isinstance(mensaje, dict) or mensaje.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Solicitud JSON-RPC inválida")
    metodo = mensaje.get("method")
    id_ = mensaje.get("id")
    if "id" not in mensaje:
        return None  # notificación (initialized, cancelled...): no lleva respuesta
    params = mensaje.get("params") or {}

    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        version = pedida if pedida in VERSIONES_PROTOCOLO else VERSIONES_PROTOCOLO[0]
        return _resultado(id_, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "dental-planning", "title": "Dental Planning",
                           "version": "1.0.0"},
            "instructions": INSTRUCCIONES,
        })
    if metodo == "ping":
        return _resultado(id_, {})
    if metodo == "tools/list":
        return _resultado(id_, {"tools": [
            herramientas.definicion_publica(h)
            for h in herramientas.disponibles(g.current_user.tenant)
        ]})
    if metodo == "tools/call":
        return _llamar_herramienta(id_, params)
    return _error(id_, -32601, f"Método no soportado: {metodo}")


@mcp_bp.route("/mcp", methods=["POST"])
def mcp():
    oauth.base_url()  # sin APP_BASE_URL https en producción: 503, antes de tocar tokens
    encabezado = request.headers.get("Authorization", "")
    if not encabezado.startswith("Bearer "):
        return _error_auth("Falta el token de Dental Planning")
    try:
        user = tokens.autenticar(encabezado[len("Bearer "):].strip())
    except tokens.TokenInvalido as error:
        return _error_auth(str(error))
    g.current_user = user
    g.tenant_id = user.tenant_id

    cuerpo = request.get_json(silent=True)
    if cuerpo is None:
        return jsonify(_error(None, -32700, "JSON inválido")), 400
    if isinstance(cuerpo, list):
        respuestas = [r for r in map(_despachar, cuerpo) if r is not None]
        return (jsonify(respuestas), 200) if respuestas else ("", 202)
    respuesta = _despachar(cuerpo)
    if respuesta is None:
        return "", 202
    return jsonify(respuesta)


@mcp_bp.route("/mcp", methods=["GET", "DELETE"])
def mcp_sin_stream():
    # Sin estado: no hay stream SSE que abrir ni sesión que cerrar.
    return jsonify({"error": "Método no permitido"}), 405


# ── Tokens (los gestiona el admin desde la app) ──

def _dump_token(t):
    return {
        "id": t.id,
        "nombre": t.nombre,
        "prefijo": t.prefijo,
        "usuario": t.user.email if t.user else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "revocado": t.revoked_at is not None,
    }


@mcp_bp.route("/api/v1/mcp/tokens", methods=["GET"])
@require_auth
@require_role("admin")
def listar_tokens():
    filas = McpToken.query.filter_by(tenant_id=g.tenant_id).order_by(
        McpToken.created_at.desc(), McpToken.id.desc(),
    ).all()
    return jsonify([_dump_token(t) for t in filas])


@mcp_bp.route("/api/v1/mcp/tokens", methods=["POST"])
@require_auth
@require_role("admin")
def crear_token():
    nombre = (request.get_json(silent=True) or {}).get("nombre") or "Claude"
    try:
        registro, claro = tokens.crear_token(g.current_user, nombre)
    except tokens.TokenInvalido as error:
        return jsonify({"error": str(error)}), 403
    return jsonify({**_dump_token(registro), "token": claro}), 201


@mcp_bp.route("/api/v1/mcp/tokens/<int:token_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def revocar_token(token_id):
    if not tokens.revocar(g.tenant_id, token_id):
        return jsonify({"error": "Token no encontrado"}), 404
    return jsonify({"ok": True})


# ── Conexiones OAuth (claude.ai / Claude Desktop) ──

def _dump_conexion(c):
    return {
        "id": c.id,
        "cliente": c.cliente.client_name if c.cliente else None,
        "usuario": c.user.email if c.user else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        "revocada": c.revoked_at is not None,
    }


@mcp_bp.route("/api/v1/mcp/conexiones", methods=["GET"])
@require_auth
@require_role("admin")
def listar_conexiones():
    filas = OAuthConcesion.query.filter_by(tenant_id=g.tenant_id).order_by(
        OAuthConcesion.created_at.desc(), OAuthConcesion.id.desc(),
    ).all()
    return jsonify([_dump_conexion(c) for c in filas])


@mcp_bp.route("/api/v1/mcp/conexiones/<int:conexion_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def revocar_conexion(conexion_id):
    concesion = OAuthConcesion.query.filter_by(
        id=conexion_id, tenant_id=g.tenant_id).first()
    if concesion is None:
        return jsonify({"error": "Conexión no encontrada"}), 404
    oauth.revocar_concesion(concesion)
    return jsonify({"ok": True})
