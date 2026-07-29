"""facturacion fase 2: tabla tickets + FKs en ingresos

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-19 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.Integer(), nullable=False),
        sa.Column('serie', sa.String(length=10), nullable=True),
        sa.Column('folio', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('total', sa.Float(), nullable=True),
        sa.Column('token', sa.String(length=64), nullable=True),
        sa.Column('estado', sa.String(length=30), nullable=False),
        sa.Column('receptor_rfc', sa.String(length=13), nullable=True),
        sa.Column('receptor_nombre', sa.String(length=255), nullable=True),
        sa.Column('uso_cfdi', sa.String(length=5), nullable=True),
        sa.Column('regimen_receptor', sa.String(length=5), nullable=True),
        sa.Column('cp_receptor', sa.String(length=5), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('uuid', sa.String(length=36), nullable=True),
        sa.Column('fecha_timbrado', sa.DateTime(), nullable=True),
        sa.Column('xml', sa.Text(), nullable=True),
        sa.Column('forma_pago', sa.String(length=5), nullable=True),
        sa.Column('metodo_pago', sa.String(length=5), nullable=True),
        sa.Column('motivo_cancelacion', sa.String(length=2), nullable=True),
        sa.Column('uuid_sustitucion', sa.String(length=36), nullable=True),
        sa.Column('acuse_xml', sa.Text(), nullable=True),
        sa.Column('fecha_cancelacion', sa.DateTime(), nullable=True),
        sa.Column('error_timbrado', sa.Text(), nullable=True),
        sa.Column('email_enviado', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursales.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'sucursal_id', 'folio',
                            name='uq_ticket_folio_sucursal'),
    )
    op.create_index('ix_tickets_tenant_estado', 'tickets',
                    ['tenant_id', 'estado'])
    # SQLite no permite ALTER TABLE ... ADD CONSTRAINT. El modo batch recrea
    # la tabla preservando sus datos y también funciona en los demás motores.
    with op.batch_alter_table('ingresos', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('ticket_id', sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('sucursal_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_ingresos_ticket', 'tickets', ['ticket_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_ingresos_sucursal', 'sucursales', ['sucursal_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('ingresos', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_ingresos_sucursal', type_='foreignkey'
        )
        batch_op.drop_constraint(
            'fk_ingresos_ticket', type_='foreignkey'
        )
        batch_op.drop_column('sucursal_id')
        batch_op.drop_column('ticket_id')
    op.drop_index('ix_tickets_tenant_estado', table_name='tickets')
    op.drop_table('tickets')
