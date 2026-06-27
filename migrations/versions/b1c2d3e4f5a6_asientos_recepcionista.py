"""asientos_recepcionista + plans.addon_tipo

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = 'a9b8c7d6e5f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('addon_tipo', sa.String(length=30), nullable=True))

    op.create_table(
        'asientos_recepcionista',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('solicitado_por_id', sa.Integer(), nullable=False),
        sa.Column('aprobado_por_id', sa.Integer(), nullable=True),
        sa.Column('aprobado_at', sa.DateTime(), nullable=True),
        sa.Column('rechazo_motivo', sa.String(length=500), nullable=True),
        sa.Column('monto', sa.Float(), nullable=True),
        sa.Column('pago_metodo', sa.String(length=20), nullable=True),
        sa.Column('clip_subscription_id', sa.String(length=100), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['solicitado_por_id'], ['users.id']),
        sa.ForeignKeyConstraint(['aprobado_por_id'], ['users.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asientos_recepcionista_tenant_id', 'asientos_recepcionista', ['tenant_id'])


def downgrade():
    op.drop_index('ix_asientos_recepcionista_tenant_id', table_name='asientos_recepcionista')
    op.drop_table('asientos_recepcionista')
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_column('addon_tipo')
