"""Cobranza: tablas de devoluciones y auditoría.

Revision ID: b2c1d3e4f5a6
Revises: d4e5f6a7b8c9
Create Date: 2026-07-28
"""
import sqlalchemy as sa
from alembic import op


revision = "b2c1d3e4f5a6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cobranza_devoluciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("monto", sa.Float(), nullable=False),
        sa.Column("metodo_pago_id", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("ingreso_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["cotizacion_id"], ["cotizaciones.id"]),
        sa.ForeignKeyConstraint(["metodo_pago_id"], ["metodos_pago.id"]),
        sa.ForeignKeyConstraint(["ingreso_id"], ["ingresos.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingreso_id"),
    )
    with op.batch_alter_table("cobranza_devoluciones", schema=None) as batch_op:
        batch_op.create_index("ix_cobranza_devoluciones_tenant_id", ["tenant_id"])
        batch_op.create_index(
            "ix_cobranza_devoluciones_tenant_cot", ["tenant_id", "cotizacion_id"],
        )

    op.create_table(
        "cobranza_auditoria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("accion", sa.String(length=40), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), nullable=True),
        sa.Column("cotizacion_folio", sa.String(length=20), nullable=False),
        sa.Column("paciente", sa.String(length=200), nullable=True),
        sa.Column("monto", sa.Float(), nullable=True),
        sa.Column("detalle", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cobranza_auditoria", schema=None) as batch_op:
        batch_op.create_index("ix_cobranza_auditoria_tenant_id", ["tenant_id"])
        batch_op.create_index(
            "ix_cobranza_auditoria_tenant_fecha", ["tenant_id", "created_at"],
        )


def downgrade():
    op.drop_table("cobranza_auditoria")
    op.drop_table("cobranza_devoluciones")
