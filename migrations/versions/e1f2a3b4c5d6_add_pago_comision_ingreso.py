"""add pago_comision_ingreso + marcar comisiones existentes como pagadas

Revision ID: e1f2a3b4c5d6
Revises: c4e1f2a3b6d7
Create Date: 2026-06-11

Crea la tabla puente que liga un PagoDoctor (tipo comisión) con los ingresos
cuya comisión liquida.

Estrategia de datos existentes (decisión del usuario): "borrón y cuenta nueva".
Los registros históricos de PagoDoctor tipo comisión eran pagos en bloque que NO
se pueden mapear 1:1 a cada ingreso, así que se marcan TODAS las comisiones
existentes hasta el momento de la migración como ya liquidadas (fila puente con
pago_id NULL = liquidación histórica, sin PagoDoctor asociado). Así la cajita de
pendientes arranca en $0 y solo las comisiones nuevas se rastrean de aquí en
adelante.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'e1f2a3b4c5d6'
down_revision = 'c4e1f2a3b6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pago_comision_ingreso',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('pago_id', sa.Integer, sa.ForeignKey('pagos_doctores.id'), nullable=True),
        sa.Column('ingreso_id', sa.Integer, sa.ForeignKey('ingresos.id'), nullable=False),
        sa.Column('monto', sa.Float, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )

    # Borrón y cuenta nueva: marcar como liquidadas TODAS las comisiones ya
    # existentes (pago_id NULL = histórico). Una sola sentencia, eficiente en
    # SQLite y MySQL.
    op.execute(
        "INSERT INTO pago_comision_ingreso (tenant_id, ingreso_id, monto) "
        "SELECT tenant_id, id, comision_doctor FROM ingresos "
        "WHERE comision_doctor > 0"
    )


def downgrade():
    op.drop_table('pago_comision_ingreso')
