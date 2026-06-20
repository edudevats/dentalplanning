"""facturacion fase 5: columnas FIEL en configuracion_fiscal

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-20 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('configuracion_fiscal', sa.Column('fiel_cer', sa.LargeBinary(), nullable=True))
    op.add_column('configuracion_fiscal', sa.Column('fiel_key_cifrada', sa.LargeBinary(), nullable=True))
    op.add_column('configuracion_fiscal', sa.Column('fiel_password_cifrada', sa.LargeBinary(), nullable=True))
    op.add_column('configuracion_fiscal', sa.Column('fiel_no_certificado', sa.String(length=20), nullable=True))
    op.add_column('configuracion_fiscal', sa.Column('fiel_valido_desde', sa.DateTime(), nullable=True))
    op.add_column('configuracion_fiscal', sa.Column('fiel_valido_hasta', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('configuracion_fiscal', 'fiel_valido_hasta')
    op.drop_column('configuracion_fiscal', 'fiel_valido_desde')
    op.drop_column('configuracion_fiscal', 'fiel_no_certificado')
    op.drop_column('configuracion_fiscal', 'fiel_password_cifrada')
    op.drop_column('configuracion_fiscal', 'fiel_key_cifrada')
    op.drop_column('configuracion_fiscal', 'fiel_cer')
