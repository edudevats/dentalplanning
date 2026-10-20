"""Alta, validación y revocación de los tokens personales del MCP."""
import hashlib
import secrets
from datetime import datetime, timezone

from app.auth.models import TENANT_STATUS_ACTIVE
from app.extensions import db
from app.mcp.models import McpToken
from app.superadmin.models import SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA

PREFIJO_TOKEN = "dpmcp_"


class TokenInvalido(Exception):
    """El token no existe, se revocó o su dueño ya no puede usar el MCP."""


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def clinica_de_pago(tenant):
    """El MCP viene incluido en las suscripciones de pago, no en free ni trial.

    La gracia cuenta como de pago: es el margen para regularizar un cobro.
    """
    if tenant is None or tenant.status != TENANT_STATUS_ACTIVE:
        return False
    sub = tenant.subscription
    if not sub or not sub.plan:
        return False
    if sub.estado not in (SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA):
        return False
    return sub.plan.precio_mensual > 0 and not sub.plan.es_temporal


def motivo_no_elegible(user):
    """None si el usuario puede usar el MCP; si no, el porqué en una frase."""
    if user is None or not user.is_active:
        return "Usuario deshabilitado"
    if user.is_superuser or user.role != "admin":
        return "Solo el administrador de la clínica puede conectar Claude"
    if not clinica_de_pago(user.tenant):
        return "La conexión con Claude está incluida solo en los planes de pago"
    return None


def crear_token(user, nombre="Claude"):
    """Devuelve (registro, token_en_claro). El token en claro no se vuelve a ver."""
    motivo = motivo_no_elegible(user)
    if motivo:
        raise TokenInvalido(motivo)
    claro = PREFIJO_TOKEN + secrets.token_urlsafe(32)
    registro = McpToken(
        tenant_id=user.tenant_id,
        user_id=user.id,
        nombre=(nombre or "Claude").strip()[:100] or "Claude",
        token_hash=_hash(claro),
        prefijo=claro[:12],
    )
    db.session.add(registro)
    db.session.commit()
    return registro, claro


def autenticar(claro):
    """Usuario dueño del token. Revalida en cada llamada: si la clínica deja de
    pagar o el admin cambia de rol, el token deja de servir sin revocarlo.

    Acepta los tokens personales (dpmcp_) y los access tokens OAuth (dpoat_)."""
    if claro and claro.startswith("dpoat_"):
        from app.mcp import oauth  # import diferido: oauth importa este módulo
        return oauth.autenticar_access_token(claro)
    if not claro or not claro.startswith(PREFIJO_TOKEN):
        raise TokenInvalido("Token inválido")
    registro = McpToken.query.filter_by(token_hash=_hash(claro)).first()
    if registro is None or registro.revoked_at is not None:
        raise TokenInvalido("Token inválido o revocado")
    user = registro.user
    if user is None or user.tenant_id != registro.tenant_id:
        raise TokenInvalido("Token inválido")
    motivo = motivo_no_elegible(user)
    if motivo:
        raise TokenInvalido(motivo)
    registro.last_used_at = datetime.now(timezone.utc)
    db.session.commit()
    return user


def revocar(tenant_id, token_id):
    registro = McpToken.query.filter_by(id=token_id, tenant_id=tenant_id).first()
    if registro is None:
        return False
    if registro.revoked_at is None:
        registro.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    return True
