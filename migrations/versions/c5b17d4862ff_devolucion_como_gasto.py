"""devolucion como gasto: gasto_id, descuento_saldo, comision_reversiones

Revision ID: c5b17d4862ff
Revises: b2c1d3e4f5a6
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "c5b17d4862ff"
down_revision = "b2c1d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cobranza_devoluciones",
        sa.Column("gasto_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_cobranza_devoluciones_gasto", "cobranza_devoluciones",
        "gastos_operativos", ["gasto_id"], ["id"],
    )
    op.add_column(
        "pagos_doctores",
        sa.Column("descuento_saldo", sa.Float(), nullable=False,
                  server_default="0"),
    )
    op.create_table(
        "comision_reversiones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("devolucion_id", sa.Integer(), sa.ForeignKey("cobranza_devoluciones.id"), nullable=False),
        sa.Column("ingreso_id", sa.Integer(), sa.ForeignKey("ingresos.id"), nullable=False),
        sa.Column("monto", sa.Float(), nullable=False),
        sa.Column("pagada_al_revertir", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_comision_reversiones_tenant_ing", "comision_reversiones", ["tenant_id", "ingreso_id"])
    op.create_index("ix_comision_reversiones_tenant_id", "comision_reversiones", ["tenant_id"])


def downgrade():
    op.drop_index("ix_comision_reversiones_tenant_id", table_name="comision_reversiones")
    op.drop_index("ix_comision_reversiones_tenant_ing", table_name="comision_reversiones")
    op.drop_table("comision_reversiones")
    op.drop_column("pagos_doctores", "descuento_saldo")
    op.drop_constraint("fk_cobranza_devoluciones_gasto", "cobranza_devoluciones", type_="foreignkey")
    op.drop_column("cobranza_devoluciones", "gasto_id")
