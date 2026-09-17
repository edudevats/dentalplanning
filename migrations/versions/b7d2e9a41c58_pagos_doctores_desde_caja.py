"""pagos a doctores desde la caja

Un pago a doctor hecho desde /corte-caja sale del cajón: el PagoDoctor tiene
que saberlo (sale_de_caja), saber de qué caja salió (sucursal_id) y quién lo
registró (created_by). El corte congela su suma en pagos_doctores_efectivo.

Los pagos existentes nacen con sale_de_caja = 0 y los cortes existentes con
pagos_doctores_efectivo = 0: ningún corte histórico cambia su esperado.

Revision ID: b7d2e9a41c58
Revises: e4c1a9d73b52
"""
import sqlalchemy as sa
from alembic import op

revision = "b7d2e9a41c58"
down_revision = "e4c1a9d73b52"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pagos_doctores", sa.Column(
        "sale_de_caja", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("pagos_doctores", sa.Column(
        "sucursal_id", sa.Integer(), nullable=True))
    op.add_column("pagos_doctores", sa.Column(
        "created_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_pagos_doctores_sucursal", "pagos_doctores",
                          "sucursales", ["sucursal_id"], ["id"])
    op.create_foreign_key("fk_pagos_doctores_created_by", "pagos_doctores",
                          "users", ["created_by"], ["id"])
    op.create_index("ix_pagos_doctores_tenant_fecha_caja", "pagos_doctores",
                    ["tenant_id", "fecha", "sale_de_caja"])
    op.add_column("cortes_caja", sa.Column(
        "pagos_doctores_efectivo", sa.Float(), nullable=False,
        server_default="0"))


def downgrade():
    op.drop_column("cortes_caja", "pagos_doctores_efectivo")
    op.drop_index("ix_pagos_doctores_tenant_fecha_caja",
                  table_name="pagos_doctores")
    op.drop_constraint("fk_pagos_doctores_created_by", "pagos_doctores",
                       type_="foreignkey")
    op.drop_constraint("fk_pagos_doctores_sucursal", "pagos_doctores",
                       type_="foreignkey")
    op.drop_column("pagos_doctores", "created_by")
    op.drop_column("pagos_doctores", "sucursal_id")
    op.drop_column("pagos_doctores", "sale_de_caja")
