"""gastos recurrentes

Plantillas de gastos mensuales (renta, internet...) que el sistema convierte
en GastoOperativo el día que toca. gastos_operativos.recurrente_id marca de
qué plantilla salió cada gasto; los gastos existentes nacen con NULL.

Revision ID: a9e3c7d15b42
Revises: 5f1c0e7a9d34
"""
import sqlalchemy as sa
from alembic import op

revision = "a9e3c7d15b42"
down_revision = "5f1c0e7a9d34"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gastos_recurrentes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("concepto_id", sa.Integer(), sa.ForeignKey("gastos_conceptos.id"), nullable=False),
        sa.Column("concepto_nombre", sa.String(200)),
        sa.Column("tipo", sa.String(20)),
        sa.Column("monto", sa.Float(), nullable=False),
        sa.Column("metodo_pago_id", sa.Integer(), sa.ForeignKey("metodos_pago.id"), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("ultima_fecha_generada", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_gastos_recurrentes_tenant_activo", "gastos_recurrentes",
                    ["tenant_id", "activo"])
    op.add_column("gastos_operativos", sa.Column(
        "recurrente_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_gastos_operativos_recurrente", "gastos_operativos",
                          "gastos_recurrentes", ["recurrente_id"], ["id"],
                          ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_gastos_operativos_recurrente", "gastos_operativos",
                       type_="foreignkey")
    op.drop_column("gastos_operativos", "recurrente_id")
    op.drop_table("gastos_recurrentes")
