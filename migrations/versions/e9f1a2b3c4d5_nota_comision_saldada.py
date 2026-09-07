"""Nota de por qué una comisión se saldó sin un PagoDoctor

El admin ya podía liquidar comisiones seleccionándolas en el recuadro de
pendientes, pero no sacar de ahí una que ya había pagado por fuera (típico
cuando el doctor negocia un monto mayor y se captura como un pago suelto).

`pago_comision_ingreso.pago_id` ya era nullable —así se marcaron las
liquidaciones históricas en la migración inicial—, así que sólo falta esta
columna para distinguir esas de las que el admin salda a mano, y por qué.

NULL en todo el histórico y en las liquidaciones normales: no hay relleno.

Revision ID: e9f1a2b3c4d5
Revises: d4c8a91f3b27
"""
import sqlalchemy as sa
from alembic import op

revision = "e9f1a2b3c4d5"
down_revision = "d4c8a91f3b27"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pago_comision_ingreso",
        sa.Column("nota", sa.String(200), nullable=True),
    )


def downgrade():
    op.drop_column("pago_comision_ingreso", "nota")
