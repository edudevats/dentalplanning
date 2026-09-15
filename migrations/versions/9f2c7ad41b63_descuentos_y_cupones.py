"""descuentos y cupones por tenant

Revision ID: 9f2c7ad41b63
Revises: f3a8b1c60d92
"""
import sqlalchemy as sa
from alembic import op

revision = "9f2c7ad41b63"
down_revision = "f3a8b1c60d92"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "descuentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("porcentaje", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_descuento"),
    )
    op.create_index("ix_descuentos_tenant_id", "descuentos", ["tenant_id"])

    op.create_table(
        "cupones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False),
        sa.Column("tratamiento_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("vigencia_desde", sa.Date(), nullable=True),
        sa.Column("vigencia_hasta", sa.Date(), nullable=True),
        sa.Column("max_usos", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["tratamiento_id"], ["tratamientos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "codigo", name="uq_tenant_cupon"),
    )
    op.create_index("ix_cupones_tenant_id", "cupones", ["tenant_id"])
    op.create_index("ix_cupones_tenant_tratamiento", "cupones",
                    ["tenant_id", "tratamiento_id"])

    op.add_column("config_consultorio", sa.Column(
        "descuentos_activo", sa.Boolean(), nullable=False, server_default="0"))

    op.add_column("ingresos", sa.Column(
        "cupon_id", sa.Integer(), nullable=True))
    op.add_column("ingresos", sa.Column(
        "descuento_monto", sa.Float(), nullable=False, server_default="0"))
    op.create_foreign_key("fk_ingresos_cupon", "ingresos", "cupones",
                          ["cupon_id"], ["id"])

    op.add_column("cotizacion_conceptos", sa.Column(
        "cupon_id", sa.Integer(), nullable=True))
    op.add_column("cotizacion_conceptos", sa.Column(
        "descuento_monto", sa.Float(), nullable=False, server_default="0"))
    op.create_foreign_key("fk_cotizacion_conceptos_cupon",
                          "cotizacion_conceptos", "cupones",
                          ["cupon_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_cotizacion_conceptos_cupon",
                       "cotizacion_conceptos", type_="foreignkey")
    op.drop_column("cotizacion_conceptos", "descuento_monto")
    op.drop_column("cotizacion_conceptos", "cupon_id")

    op.drop_constraint("fk_ingresos_cupon", "ingresos", type_="foreignkey")
    op.drop_column("ingresos", "descuento_monto")
    op.drop_column("ingresos", "cupon_id")

    op.drop_column("config_consultorio", "descuentos_activo")

    op.drop_index("ix_cupones_tenant_tratamiento", table_name="cupones")
    op.drop_index("ix_cupones_tenant_id", table_name="cupones")
    op.drop_table("cupones")

    op.drop_index("ix_descuentos_tenant_id", table_name="descuentos")
    op.drop_table("descuentos")
