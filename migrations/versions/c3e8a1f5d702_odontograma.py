"""odontograma: estado de dientes y tratamientos asignados por diente

Revision ID: c3e8a1f5d702
Revises: e4c1a9d73b52
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e8a1f5d702"
down_revision = "e4c1a9d73b52"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dientes_estado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("paciente_id", sa.Integer(), sa.ForeignKey("pacientes.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("paciente_id", "numero", name="uq_dientes_estado_paciente_numero"),
    )
    op.create_index("ix_dientes_estado_tenant_id", "dientes_estado", ["tenant_id"])

    op.create_table(
        "dientes_tratamientos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("paciente_id", sa.Integer(), sa.ForeignKey("pacientes.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("caras", sa.String(20), nullable=True),
        sa.Column("estatus", sa.String(20), nullable=False),
        sa.Column("fecha_realizado", sa.Date(), nullable=True),
        sa.Column("especialista_id", sa.Integer(), sa.ForeignKey("especialistas.id"), nullable=True),
        sa.Column("tratamiento_id", sa.Integer(), sa.ForeignKey("tratamientos.id"), nullable=True),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("cotizacion_concepto_id", sa.Integer(),
                  sa.ForeignKey("cotizacion_conceptos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ingreso_id", sa.Integer(),
                  sa.ForeignKey("ingresos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origen_eliminado", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("cotizacion_concepto_id", "numero", name="uq_dientes_trat_concepto_numero"),
        sa.UniqueConstraint("ingreso_id", "numero", name="uq_dientes_trat_ingreso_numero"),
    )
    op.create_index("ix_dientes_tratamientos_tenant_id", "dientes_tratamientos", ["tenant_id"])
    op.create_index("ix_dientes_trat_tenant_paciente", "dientes_tratamientos",
                    ["tenant_id", "paciente_id"])


def downgrade():
    op.drop_index("ix_dientes_trat_tenant_paciente", table_name="dientes_tratamientos")
    op.drop_index("ix_dientes_tratamientos_tenant_id", table_name="dientes_tratamientos")
    op.drop_table("dientes_tratamientos")
    op.drop_index("ix_dientes_estado_tenant_id", table_name="dientes_estado")
    op.drop_table("dientes_estado")
