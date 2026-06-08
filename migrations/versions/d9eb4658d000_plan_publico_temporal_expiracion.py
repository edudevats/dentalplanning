"""plan_publico_temporal_expiracion

Revision ID: d9eb4658d000
Revises: 47f8e0762a09
Create Date: 2026-05-15 14:18:46.223856

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9eb4658d000'
down_revision = '47f8e0762a09'
branch_labels = None
depends_on = None


def _has_column(table, column):
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info('{table}')"))
    return any(row[1] == column for row in result)


def upgrade():
    with op.batch_alter_table('plans', schema=None) as batch_op:
        if not _has_column('plans', 'publico'):
            batch_op.add_column(sa.Column('publico', sa.Boolean(), nullable=False, server_default='1'))
        if not _has_column('plans', 'es_temporal'):
            batch_op.add_column(sa.Column('es_temporal', sa.Boolean(), nullable=False, server_default='0'))
        if not _has_column('plans', 'dias_expiracion'):
            batch_op.add_column(sa.Column('dias_expiracion', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_column('dias_expiracion')
        batch_op.drop_column('es_temporal')
        batch_op.drop_column('publico')
