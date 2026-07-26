"""Cobranza: estado reintentable e idempotencia de pagos.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-26
"""
import sqlalchemy as sa
from alembic import op


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cotizaciones", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "facturacion_estado", sa.String(length=30),
            nullable=False, server_default="no_requerida",
        ))
        batch_op.add_column(sa.Column("facturacion_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column(
            "facturacion_actualizada_at", sa.DateTime(), nullable=True,
        ))

    with op.batch_alter_table("cobranza_pagos", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "idempotency_key", sa.String(length=64), nullable=True,
        ))
        batch_op.create_unique_constraint(
            "uq_cobranza_pago_idempotency",
            ["tenant_id", "cotizacion_id", "idempotency_key"],
        )

    # El calendario no puede tener dos renglones con el mismo número.
    op.drop_index(
        "ix_programados_tenant_cot_num", table_name="pagos_programados",
    )
    with op.batch_alter_table("pagos_programados", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_programados_tenant_cot_num",
            ["tenant_id", "cotizacion_id", "numero"],
        )


def downgrade():
    with op.batch_alter_table("pagos_programados", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_programados_tenant_cot_num", type_="unique",
        )
    op.create_index(
        "ix_programados_tenant_cot_num",
        "pagos_programados",
        ["tenant_id", "cotizacion_id", "numero"],
        unique=False,
    )

    with op.batch_alter_table("cobranza_pagos", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_cobranza_pago_idempotency", type_="unique",
        )
        batch_op.drop_column("idempotency_key")

    with op.batch_alter_table("cotizaciones", schema=None) as batch_op:
        batch_op.drop_column("facturacion_actualizada_at")
        batch_op.drop_column("facturacion_error")
        batch_op.drop_column("facturacion_estado")
