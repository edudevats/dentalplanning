from datetime import timedelta

import click
from flask.cli import AppGroup

from app.auth.models import User
from app.extensions import db
from app.mcp import tokens
from app.mcp.models import (
    McpConsulta, OAuthCliente, OAuthCodigo, OAuthConcesion, OAuthIntento, OAuthToken, _ahora,
)

mcp_cli = AppGroup("mcp", help="Conexión de Claude (MCP)")


@mcp_cli.command("crear-token")
@click.option("--email", required=True, help="Email del admin de la clínica")
@click.option("--nombre", default="Claude", help="Etiqueta para reconocer el token")
def crear_token(email, nombre):
    """Genera un token MCP para un admin (se muestra una sola vez)."""
    user = User.query.filter(
        db.func.lower(User.email) == email.strip().lower()).first()
    if user is None:
        raise click.ClickException(f"No existe el usuario {email}")
    try:
        registro, claro = tokens.crear_token(user, nombre)
    except tokens.TokenInvalido as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Token #{registro.id} para {user.email} (tenant {user.tenant_id}):")
    click.echo(claro)


@mcp_cli.command("purgar")
def purgar():
    """Borra códigos, tokens, clientes, consultas e intentos OAuth ya inservibles."""
    ahora = _ahora()
    borradas = {}

    borradas["oauth_codigos"] = OAuthCodigo.query.filter(
        db.or_(OAuthCodigo.usado_at.isnot(None), OAuthCodigo.expira < ahora),
    ).delete(synchronize_session=False)

    vencidos = OAuthToken.query.filter(OAuthToken.expira < ahora - timedelta(days=30))
    ids = [t.id for t in vencidos.with_entities(OAuthToken.id)]
    if ids:
        # Un token no vencido no debe quedar apuntando a uno que se borra.
        OAuthToken.query.filter(OAuthToken.reemplazado_por_id.in_(ids)).update(
            {"reemplazado_por_id": None}, synchronize_session=False)
    borradas["oauth_tokens"] = vencidos.delete(synchronize_session=False)

    con_concesion = db.session.query(OAuthConcesion.cliente_id)
    borradas["oauth_clientes"] = OAuthCliente.query.filter(
        OAuthCliente.created_at < ahora - timedelta(days=7),
        ~OAuthCliente.id.in_(con_concesion),
    ).delete(synchronize_session=False)

    borradas["mcp_consultas"] = McpConsulta.query.filter(
        McpConsulta.created_at < ahora - timedelta(days=90),
    ).delete(synchronize_session=False)
    borradas["oauth_intentos"] = OAuthIntento.query.filter(
        OAuthIntento.created_at < ahora - timedelta(days=1),
    ).delete(synchronize_session=False)

    db.session.commit()
    for tabla, cuantas in borradas.items():
        click.echo(f"{tabla}: {cuantas}")
