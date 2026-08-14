"""drop configuracion_fiscal.naturaleza_juridica

El IVA dejó de depender de la razón social del tenant: ahora lo determina
únicamente el tipo de servicio del tratamiento (estético grava, clínico exento).

Revision ID: 0516f657c524
Revises: d6e7f8a9b0c1
"""
from alembic import op
import sqlalchemy as sa

revision = '0516f657c524'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('configuracion_fiscal', 'naturaleza_juridica')


def downgrade():
    op.add_column(
        'configuracion_fiscal',
        sa.Column('naturaleza_juridica', sa.String(length=20), nullable=True),
    )
