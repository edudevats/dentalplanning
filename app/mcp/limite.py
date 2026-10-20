"""Límite de consultas por clínica, contado en la BD (hay varios workers)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.mcp.models import McpConsulta

LIMITE_POR_MINUTO = 60
LIMITE_POR_DIA = 2000

_VENTANAS = ((60, LIMITE_POR_MINUTO), (86400, LIMITE_POR_DIA))


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def segundos_de_espera(tenant_id):
    """Segundos que debe esperar la clínica, o None si puede consultar."""
    ahora = _ahora()
    espera = None
    for segundos, maximo in _VENTANAS:
        desde = ahora - timedelta(seconds=segundos)
        cuenta, mas_antigua = db.session.query(
            func.count(McpConsulta.id), func.min(McpConsulta.created_at),
        ).filter(
            McpConsulta.tenant_id == tenant_id, McpConsulta.created_at >= desde,
        ).one()
        if cuenta >= maximo:
            n = max(1, segundos - int((ahora - mas_antigua).total_seconds()))
            espera = n if espera is None else max(espera, n)
    return espera


def registrar(tenant_id, user_id, herramienta):
    db.session.add(McpConsulta(
        tenant_id=tenant_id, user_id=user_id, herramienta=herramienta[:60],
    ))
    db.session.commit()
