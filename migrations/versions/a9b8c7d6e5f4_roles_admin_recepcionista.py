"""roles a admin/recepcionista (migra editor/viewer -> recepcionista)

Revision ID: a9b8c7d6e5f4
Revises: d1e2f3a4b5c6
Create Date: 2026-06-26 00:00:00.000000

OPERACIÓN (prod): antes de aplicar, verificar que ningún tenant tenga usuarios no-admin
inesperados — pasarán a 'recepcionista' con acceso completo a Facturas (timbrar/cancelar).
"""
from alembic import op


revision = 'a9b8c7d6e5f4'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    # Migra cualquier rol no-admin (editor/viewer) a recepcionista.
    # is_superuser no se ve afectado por su rol (bypass en require_auth).
    op.execute("UPDATE users SET role = 'recepcionista' WHERE role NOT IN ('admin')")


def downgrade():
    # Irreversible a nivel de datos: no se conserva el rol original.
    pass
