"""rol asistente: permisos por usuario y rol del asiento

Revision ID: afb12a05e6da
Revises: 0516f657c524
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa


revision = 'afb12a05e6da'
down_revision = '0516f657c524'
branch_labels = None
depends_on = None


def upgrade():
    # MySQL no admite DEFAULT en columnas JSON: se crea nullable y el modelo
    # aporta el default. El código lee siempre `user.permisos or {}`.
    op.add_column('users', sa.Column('permisos', sa.JSON(), nullable=True))
    op.add_column(
        'asientos_recepcionista',
        sa.Column('rol', sa.String(length=20), nullable=False,
                  server_default='recepcionista'),
    )


def downgrade():
    op.drop_column('asientos_recepcionista', 'rol')
    op.drop_column('users', 'permisos')
