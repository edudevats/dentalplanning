"""finkok registro columnas en configuracion_fiscal

Revision ID: d6e7f8a9b0c1
Revises: c5b17d4862ff
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "c5b17d4862ff"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "configuracion_fiscal",
        sa.Column("finkok_registrado_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "configuracion_fiscal",
        sa.Column("finkok_rfc_registrado", sa.String(length=13), nullable=True),
    )


def downgrade():
    op.drop_column("configuracion_fiscal", "finkok_rfc_registrado")
    op.drop_column("configuracion_fiscal", "finkok_registrado_at")
