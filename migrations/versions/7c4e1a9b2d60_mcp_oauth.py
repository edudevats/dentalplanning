"""mcp oauth

Tablas de OAuth para conectar Claude por autorización (clientes, concesiones,
códigos, tokens, intentos) y el registro de consultas para el límite por clínica.

Revision ID: 7c4e1a9b2d60
Revises: 25a3c5693cda
"""
import sqlalchemy as sa
from alembic import op

revision = "7c4e1a9b2d60"
down_revision = "25a3c5693cda"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oauth_clientes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("client_name", sa.String(100), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("client_id", name="uq_oauth_clientes_client_id"),
    )
    op.create_table(
        "oauth_concesiones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("oauth_clientes.id"), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_oauth_concesiones_tenant_id", "oauth_concesiones", ["tenant_id"])
    op.create_table(
        "oauth_codigos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("concesion_id", sa.Integer(), sa.ForeignKey("oauth_concesiones.id"),
                  nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("expira", sa.DateTime(), nullable=False),
        sa.Column("usado_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code_hash", name="uq_oauth_codigos_code_hash"),
    )
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("concesion_id", sa.Integer(), sa.ForeignKey("oauth_concesiones.id"),
                  nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("expira", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("reemplazado_por_id", sa.Integer(), sa.ForeignKey("oauth_tokens.id"),
                  nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_oauth_tokens_token_hash"),
    )
    op.create_index("ix_oauth_tokens_concesion_id", "oauth_tokens", ["concesion_id"])
    op.create_table(
        "mcp_consultas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("herramienta", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_mcp_consultas_tenant_created", "mcp_consultas",
                    ["tenant_id", "created_at"])
    op.create_table(
        "oauth_intentos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_oauth_intentos_clave", "oauth_intentos", ["clave"])


def downgrade():
    # Los índices que respaldan una FK no se borran a mano: InnoDB los toma
    # como índice de la FK y DROP INDEX falla con 1553; drop_table los quita.
    op.drop_index("ix_oauth_intentos_clave", table_name="oauth_intentos")
    op.drop_table("oauth_intentos")
    op.drop_table("mcp_consultas")
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_codigos")
    op.drop_table("oauth_concesiones")
    op.drop_table("oauth_clientes")
