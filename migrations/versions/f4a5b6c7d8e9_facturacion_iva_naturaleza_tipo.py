"""facturacion: naturaleza_juridica + tipo_servicio (IVA)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-20 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('configuracion_fiscal', sa.Column('naturaleza_juridica', sa.String(length=20), nullable=True))
    op.add_column('tratamientos', sa.Column('tipo_servicio', sa.String(length=20), nullable=True, server_default='clinico'))
    op.add_column('ingresos', sa.Column('tipo_servicio', sa.String(length=20), nullable=True, server_default='clinico'))


def downgrade():
    op.drop_column('ingresos', 'tipo_servicio')
    op.drop_column('tratamientos', 'tipo_servicio')
    op.drop_column('configuracion_fiscal', 'naturaleza_juridica')
