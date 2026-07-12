"""CRM de pacientes: pacientes, visitas, seguimientos, eventos, config + ingresos.paciente_id.

Revision ID: b7c8d9e0f1a2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pacientes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("telefono", sa.String(30)),
        sa.Column("whatsapp", sa.String(30)),
        sa.Column("email", sa.String(255)),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("estatus_crm", sa.String(20), nullable=False, server_default="prospecto"),
        sa.Column("especialista_id", sa.Integer(), sa.ForeignKey("especialistas.id"), nullable=True),
        sa.Column("es_problematico", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notas_generales", sa.Text()),
        sa.Column("eliminado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_pacientes_tenant_id", "pacientes", ["tenant_id"])
    op.create_index("ix_pacientes_tenant_estatus", "pacientes", ["tenant_id", "estatus_crm"])

    op.create_table(
        "pacientes_visitas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("paciente_id", sa.Integer(), sa.ForeignKey("pacientes.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("motivo", sa.String(300)),
        sa.Column("ingreso_id", sa.Integer(), sa.ForeignKey("ingresos.id"), nullable=True, unique=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_pacientes_visitas_tenant_id", "pacientes_visitas", ["tenant_id"])
    op.create_index(
        "ix_visitas_tenant_paciente_fecha", "pacientes_visitas",
        ["tenant_id", "paciente_id", "fecha"],
    )

    op.create_table(
        "pacientes_seguimientos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("paciente_id", sa.Integer(), sa.ForeignKey("pacientes.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False, server_default="llamada"),
        sa.Column("fecha_programada", sa.Date(), nullable=False),
        sa.Column("notas", sa.Text()),
        sa.Column("completado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fecha_completado", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_pacientes_seguimientos_tenant_id", "pacientes_seguimientos", ["tenant_id"])

    op.create_table(
        "pacientes_eventos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("paciente_id", sa.Integer(), sa.ForeignKey("pacientes.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("detalle", sa.Text()),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_pacientes_eventos_tenant_id", "pacientes_eventos", ["tenant_id"])

    op.create_table(
        "crm_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, unique=True),
        sa.Column("meses_inactividad", sa.Integer(), nullable=False, server_default="4"),
    )

    with op.batch_alter_table("ingresos") as batch_op:
        batch_op.add_column(sa.Column("paciente_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ingresos_paciente_id", "pacientes", ["paciente_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("ingresos") as batch_op:
        batch_op.drop_constraint("fk_ingresos_paciente_id", type_="foreignkey")
        batch_op.drop_column("paciente_id")
    op.drop_table("crm_config")
    op.drop_table("pacientes_eventos")
    op.drop_table("pacientes_seguimientos")
    op.drop_table("pacientes_visitas")
    op.drop_table("pacientes")
