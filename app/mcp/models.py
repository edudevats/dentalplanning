from datetime import datetime, timezone

from app.extensions import db


class McpToken(db.Model):
    """Token personal con el que el admin conecta Claude a su clínica.

    Solo se guarda el SHA-256: el token en claro se muestra una vez al crearlo.
    `prefijo` (los primeros caracteres) sirve para reconocerlo en la lista.
    """
    __tablename__ = "mcp_tokens"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False, default="Claude")
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    prefijo = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OAuthCliente(db.Model):
    """Cliente registrado dinámicamente (RFC 7591), p. ej. Claude."""
    __tablename__ = "oauth_clientes"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(64), nullable=False, unique=True)
    client_name = db.Column(db.String(100), nullable=False)
    redirect_uris = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=_ahora)


class OAuthConcesion(db.Model):
    """Permiso que un admin dio a un cliente para leer los datos de su clínica."""
    __tablename__ = "oauth_concesiones"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("oauth_clientes.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_ahora)
    last_used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    cliente = db.relationship("OAuthCliente")


class OAuthCodigo(db.Model):
    """Código de autorización de un solo uso (solo se guarda su SHA-256)."""
    __tablename__ = "oauth_codigos"

    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(64), nullable=False, unique=True)
    concesion_id = db.Column(db.Integer, db.ForeignKey("oauth_concesiones.id"), nullable=False)
    redirect_uri = db.Column(db.String(500), nullable=False)
    code_challenge = db.Column(db.String(128), nullable=False)
    resource = db.Column(db.String(500), nullable=False)
    expira = db.Column(db.DateTime, nullable=False)
    usado_at = db.Column(db.DateTime, nullable=True)

    concesion = db.relationship("OAuthConcesion")


class OAuthToken(db.Model):
    """Token de acceso o de refresco (solo se guarda su SHA-256)."""
    __tablename__ = "oauth_tokens"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    tipo = db.Column(db.String(10), nullable=False)  # access | refresh
    concesion_id = db.Column(db.Integer, db.ForeignKey("oauth_concesiones.id"),
                             nullable=False, index=True)
    resource = db.Column(db.String(500), nullable=False)
    expira = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    reemplazado_por_id = db.Column(db.Integer, db.ForeignKey("oauth_tokens.id"), nullable=True)

    concesion = db.relationship("OAuthConcesion")


class McpConsulta(db.Model):
    """Una llamada a herramienta; se cuenta en BD para el límite por clínica."""
    __tablename__ = "mcp_consultas"
    __table_args__ = (
        db.Index("ix_mcp_consultas_tenant_created", "tenant_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    herramienta = db.Column(db.String(60), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_ahora)


class OAuthIntento(db.Model):
    """Intento fallido o sensible de OAuth, para limitar fuerza bruta."""
    __tablename__ = "oauth_intentos"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(300), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_ahora)
