"""Contraseña temporal enviada por correo al admin que olvidó la suya

Convive con `password_hash` en vez de reemplazarla: mientras la temporal está
vigente ambas abren sesión. Así pedir un reset con el correo de otro no deja
a nadie fuera de su cuenta.

Ambas columnas son nullable y sin relleno: NULL significa "no hay temporal
pendiente", que es el estado de todo el histórico.

Revision ID: d4c8a91f3b27
Revises: b8e5c2f70a13
"""
import sqlalchemy as sa
from alembic import op

revision = "d4c8a91f3b27"
down_revision = "b8e5c2f70a13"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("temp_password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("temp_password_expira", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("users", "temp_password_expira")
    op.drop_column("users", "temp_password_hash")
