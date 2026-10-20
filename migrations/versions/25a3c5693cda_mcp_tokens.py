"""mcp tokens

Tokens personales con los que el admin de una clínica conecta Claude (MCP) a
sus datos. Solo se guarda el SHA-256 del token.

Revision ID: 25a3c5693cda
Revises: a9e3c7d15b42
"""
import sqlalchemy as sa
from alembic import op

revision = "25a3c5693cda"
down_revision = "a9e3c7d15b42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("prefijo", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_mcp_tokens_token_hash"),
    )
    op.create_index("ix_mcp_tokens_tenant_id", "mcp_tokens", ["tenant_id"])


def downgrade():
    op.drop_index("ix_mcp_tokens_tenant_id", table_name="mcp_tokens")
    op.drop_table("mcp_tokens")
