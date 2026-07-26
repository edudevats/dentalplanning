"""Cobranza: cotizaciones, conceptos, pagos programados y pagos.

Crea las cuatro tablas del módulo de cobranza y cotizaciones: la cotización
(presupuesto con su plan de pagos diferido), sus renglones de concepto, el
calendario de pagos programados y los abonos reales recibidos del paciente.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-25
"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cotizaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("folio", sa.String(length=20), nullable=False),
        sa.Column("paciente_id", sa.Integer(), sa.ForeignKey("pacientes.id"), nullable=False),
        sa.Column("especialista_id", sa.Integer(), sa.ForeignKey("especialistas.id"), nullable=True),
        sa.Column("sucursal_id", sa.Integer(), sa.ForeignKey("sucursales.id"), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("valida_hasta", sa.Date(), nullable=False),
        sa.Column("fecha_inicio_tratamiento", sa.Date(), nullable=True),
        sa.Column("estatus", sa.String(length=20), nullable=False, server_default="borrador"),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("descuento_tipo", sa.String(length=20), nullable=True),
        sa.Column("descuento_valor", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("frecuencia", sa.String(length=20), nullable=False, server_default="mensual"),
        sa.Column("num_parcialidades", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("monto_parcialidad", sa.Float(), nullable=True),
        sa.Column("anticipo", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fecha_primer_pago", sa.Date(), nullable=True),
        sa.Column("comision_doctor_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("requiere_factura", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("aprobada_por", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("aprobada_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "folio", name="uq_cotizacion_tenant_folio"),
    )
    op.create_index(
        op.f("ix_cotizaciones_tenant_id"), "cotizaciones", ["tenant_id"], unique=False,
    )
    op.create_index(
        "ix_cotizaciones_tenant_estatus", "cotizaciones", ["tenant_id", "estatus"], unique=False,
    )
    op.create_index(
        "ix_cotizaciones_tenant_paciente", "cotizaciones", ["tenant_id", "paciente_id"], unique=False,
    )

    op.create_table(
        "cotizacion_conceptos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), sa.ForeignKey("cotizaciones.id"), nullable=False),
        sa.Column("tratamiento_id", sa.Integer(), sa.ForeignKey("tratamientos.id"), nullable=True),
        sa.Column("descripcion", sa.String(length=300), nullable=False),
        sa.Column("cantidad", sa.Float(), nullable=False, server_default="1"),
        sa.Column("precio_unitario", sa.Float(), nullable=False, server_default="0"),
        sa.Column("importe", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tipo_servicio", sa.String(length=20), nullable=True, server_default="clinico"),
        sa.Column("comision_especialista_tipo", sa.String(length=20), nullable=True, server_default="porcentaje"),
        sa.Column("comision_especialista_valor", sa.Float(), nullable=False, server_default="0"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        op.f("ix_cotizacion_conceptos_tenant_id"), "cotizacion_conceptos", ["tenant_id"], unique=False,
    )

    op.create_table(
        "pagos_programados",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), sa.ForeignKey("cotizaciones.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=False),
        sa.Column("monto_programado", sa.Float(), nullable=False),
        sa.Column("monto_pagado", sa.Float(), nullable=False, server_default="0"),
        sa.Column("estatus", sa.String(length=20), nullable=False, server_default="pendiente"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_pagos_programados_tenant_id"), "pagos_programados", ["tenant_id"], unique=False,
    )
    op.create_index(
        "ix_programados_tenant_cot_num", "pagos_programados",
        ["tenant_id", "cotizacion_id", "numero"], unique=False,
    )

    op.create_table(
        "cobranza_pagos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("cotizacion_id", sa.Integer(), sa.ForeignKey("cotizaciones.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("monto", sa.Float(), nullable=False),
        sa.Column("metodo_pago_id", sa.Integer(), sa.ForeignKey("metodos_pago.id"), nullable=True),
        sa.Column("historico", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ingreso_id", sa.Integer(), sa.ForeignKey("ingresos.id"), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("ingreso_id", name="uq_cobranza_pagos_ingreso_id"),
    )
    op.create_index(
        op.f("ix_cobranza_pagos_tenant_id"), "cobranza_pagos", ["tenant_id"], unique=False,
    )
    op.create_index(
        "ix_cobranza_pagos_tenant_cot_fecha", "cobranza_pagos",
        ["tenant_id", "cotizacion_id", "fecha"], unique=False,
    )


def downgrade():
    op.drop_index("ix_cobranza_pagos_tenant_cot_fecha", table_name="cobranza_pagos")
    op.drop_index(op.f("ix_cobranza_pagos_tenant_id"), table_name="cobranza_pagos")
    op.drop_table("cobranza_pagos")

    op.drop_index("ix_programados_tenant_cot_num", table_name="pagos_programados")
    op.drop_index(op.f("ix_pagos_programados_tenant_id"), table_name="pagos_programados")
    op.drop_table("pagos_programados")

    op.drop_index(op.f("ix_cotizacion_conceptos_tenant_id"), table_name="cotizacion_conceptos")
    op.drop_table("cotizacion_conceptos")

    op.drop_index("ix_cotizaciones_tenant_paciente", table_name="cotizaciones")
    op.drop_index("ix_cotizaciones_tenant_estatus", table_name="cotizaciones")
    op.drop_index(op.f("ix_cotizaciones_tenant_id"), table_name="cotizaciones")
    op.drop_table("cotizaciones")
