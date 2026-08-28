"""Agrupa los ingresos capturados juntos como una sola visita

Una visita con varios tratamientos son varias filas de `ingresos` —una por
tratamiento, para no mover el IVA por concepto ni los pagos a doctores— unidas
por este token.

Nullable y sin relleno: NULL significa "ingreso suelto", que es exactamente lo
que es todo el histórico y también la visita de un solo tratamiento.

Revision ID: b8e5c2f70a13
Revises: a7d3f19c2b40
"""
import sqlalchemy as sa
from alembic import op

revision = "b8e5c2f70a13"
down_revision = "a7d3f19c2b40"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ingresos", sa.Column("visita_uid", sa.String(32), nullable=True))
    op.create_index(
        "ix_ingresos_tenant_visita", "ingresos", ["tenant_id", "visita_uid"]
    )


def downgrade():
    op.drop_index("ix_ingresos_tenant_visita", table_name="ingresos")
    op.drop_column("ingresos", "visita_uid")
