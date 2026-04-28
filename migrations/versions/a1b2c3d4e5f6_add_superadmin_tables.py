"""add superadmin tables (tenant status, plans, subscriptions, payments, notes)

Revision ID: a1b2c3d4e5f6
Revises: 52380ddb57f3
Create Date: 2026-04-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '52380ddb57f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('contact_email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('approved_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rejected_reason', sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(
            'fk_tenants_approved_by_id_users', 'users', ['approved_by_id'], ['id'],
            use_alter=True,
        )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=50), nullable=False),
        sa.Column('precio_mensual', sa.Float(), nullable=False, server_default='0'),
        sa.Column('descripcion', sa.String(length=500), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre'),
    )

    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('inicio', sa.Date(), nullable=False),
        sa.Column('proximo_cobro', sa.Date(), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='activa'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )

    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('monto', sa.Float(), nullable=False),
        sa.Column('metodo', sa.String(length=20), nullable=False, server_default='transferencia'),
        sa.Column('periodo_inicio', sa.Date(), nullable=True),
        sa.Column('periodo_fin', sa.Date(), nullable=True),
        sa.Column('comentarios', sa.String(length=500), nullable=True),
        sa.Column('registrado_por_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['registrado_por_id'], ['users.id']),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'tenant_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('autor_id', sa.Integer(), nullable=False),
        sa.Column('texto', sa.String(length=2000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['autor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Cambiar el server_default a 'pending' para nuevos tenants después del backfill
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.alter_column(
            'status', existing_type=sa.String(length=20),
            server_default='pending', existing_nullable=False,
        )


def downgrade():
    op.drop_table('tenant_notes')
    op.drop_table('payments')
    op.drop_table('subscriptions')
    op.drop_table('plans')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_superuser')

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tenants_approved_by_id_users', type_='foreignkey')
        batch_op.drop_column('rejected_reason')
        batch_op.drop_column('approved_by_id')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('contact_email')
        batch_op.drop_column('status')
