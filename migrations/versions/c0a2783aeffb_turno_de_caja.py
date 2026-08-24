"""turno de caja

Revision ID: c0a2783aeffb
Revises: a26b40b235c3
"""
import sqlalchemy as sa
from alembic import op

revision = 'c0a2783aeffb'
down_revision = 'a26b40b235c3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'turnos_caja',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('fondo_inicial', sa.Float(), nullable=False,
                  server_default='0'),
        sa.Column('abierto_at', sa.DateTime(), nullable=False),
        sa.Column('cerrado_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursales.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'usuario_id', 'fecha',
                            name='uq_turno_caja_tenant_usuario_fecha'),
    )
    op.create_index('ix_turnos_caja_tenant_fecha', 'turnos_caja',
                    ['tenant_id', 'fecha'])

    # Sin backfill: los cortes que ya existen no tenian fondo, y 0 lo describe.
    op.add_column('cortes_caja',
                  sa.Column('fondo_inicial', sa.Float(), nullable=False,
                            server_default='0'))


def downgrade():
    op.drop_column('cortes_caja', 'fondo_inicial')
    op.drop_index('ix_turnos_caja_tenant_fecha', table_name='turnos_caja')
    op.drop_table('turnos_caja')
