"""fase2: last_login, is_active en users + admin_audit_log

Revision ID: d1e2f3a4b5c6
Revises: f4a5b6c7d8e9
Create Date: 2026-06-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_login', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')))

    op.create_table(
        'admin_audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('target_type', sa.String(length=20), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('summary', sa.String(length=500), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('admin_audit_log', schema=None) as batch_op:
        batch_op.create_index('ix_admin_audit_log_created_at', ['created_at'], unique=False)
        batch_op.create_index('ix_admin_audit_log_tenant_created', ['tenant_id', 'created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('admin_audit_log', schema=None) as batch_op:
        batch_op.drop_index('ix_admin_audit_log_tenant_created')
        batch_op.drop_index('ix_admin_audit_log_created_at')
    op.drop_table('admin_audit_log')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('last_login')
