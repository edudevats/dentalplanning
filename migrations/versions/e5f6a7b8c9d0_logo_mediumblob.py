"""Ampliar configuracion_fiscal.logo a MEDIUMBLOB (MySQL).

El tipo BLOB de MySQL trunca a 65535 bytes, lo que corta los logos grandes
(el PNG queda incompleto y solo se ve la parte superior). MEDIUMBLOB sube el
límite a 16MB. En SQLite es no-op (BLOB no tiene límite de tamaño).

Revision ID: e5f6a7b8c9d0
Revises: c2d3e4f5a6b7
Create Date: 2026-06-29
"""
from alembic import op
from sqlalchemy.dialects.mysql import MEDIUMBLOB, BLOB

revision = "e5f6a7b8c9d0"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.alter_column(
            "configuracion_fiscal", "logo",
            existing_type=BLOB(), type_=MEDIUMBLOB(), existing_nullable=True,
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.alter_column(
            "configuracion_fiscal", "logo",
            existing_type=MEDIUMBLOB(), type_=BLOB(), existing_nullable=True,
        )
