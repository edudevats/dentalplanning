"""cobro variable de facturacion

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("configuracion_fiscal") as batch_op:
        batch_op.add_column(
            sa.Column(
                "facturacion_activa",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("facturacion_activada_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "facturacion_cargo_pendiente",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("billing_cycle_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("due_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("plan_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("invoice_base_fee", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("stamp_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("stamp_unit_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("stamp_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("clip_payment_url", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("paid_at", sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_payment_tenant_billing_cycle",
            ["tenant_id", "billing_cycle_date"],
        )


def downgrade():
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint(
            "uq_payment_tenant_billing_cycle", type_="unique"
        )
        batch_op.drop_column("paid_at")
        batch_op.drop_column("clip_payment_url")
        batch_op.drop_column("stamp_amount")
        batch_op.drop_column("stamp_unit_price")
        batch_op.drop_column("stamp_count")
        batch_op.drop_column("invoice_base_fee")
        batch_op.drop_column("plan_amount")
        batch_op.drop_column("due_date")
        batch_op.drop_column("billing_cycle_date")

    with op.batch_alter_table("configuracion_fiscal") as batch_op:
        batch_op.drop_column("facturacion_cargo_pendiente")
        batch_op.drop_column("facturacion_activada_at")
        batch_op.drop_column("facturacion_activa")
