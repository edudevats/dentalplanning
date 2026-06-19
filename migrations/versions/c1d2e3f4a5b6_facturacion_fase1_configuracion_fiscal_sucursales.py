"""facturacion fase 1: configuracion_fiscal y sucursales

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-06-19 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = 'c1d2e3f4a5b6'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'configuracion_fiscal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('rfc', sa.String(length=13), nullable=True),
        sa.Column('razon_social', sa.String(length=255), nullable=True),
        sa.Column('regimen_fiscal', sa.String(length=5), nullable=True),
        sa.Column('logo', sa.LargeBinary(), nullable=True),
        sa.Column('clave_prod_serv_default', sa.String(length=8), nullable=True),
        sa.Column('clave_unidad_default', sa.String(length=3), nullable=True),
        sa.Column('objeto_imp_default', sa.String(length=2), nullable=True),
        sa.Column('csd_cer', sa.LargeBinary(), nullable=True),
        sa.Column('csd_key_cifrada', sa.LargeBinary(), nullable=True),
        sa.Column('csd_password_cifrada', sa.LargeBinary(), nullable=True),
        sa.Column('csd_no_certificado', sa.String(length=20), nullable=True),
        sa.Column('csd_valido_desde', sa.DateTime(), nullable=True),
        sa.Column('csd_valido_hasta', sa.DateTime(), nullable=True),
        sa.Column('ventana_facturacion', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )

    op.create_table(
        'sucursales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('direccion', sa.String(length=400), nullable=True),
        sa.Column('codigo_postal', sa.String(length=5), nullable=True),
        sa.Column('telefono', sa.String(length=30), nullable=True),
        sa.Column('serie', sa.String(length=10), nullable=True),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sucursales_tenant', 'sucursales', ['tenant_id'])


def downgrade():
    op.drop_index('ix_sucursales_tenant', table_name='sucursales')
    op.drop_table('sucursales')
    op.drop_table('configuracion_fiscal')
