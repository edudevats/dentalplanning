"""toggle de cupones separado del de descuentos

Los consultorios pidieron poder encender cada funcion por su cuenta: hay
clinicas que dan descuentos de visita y nunca reparten cupones, y al reves.

`cupones_activo` hereda el valor de `descuentos_activo` a proposito: quien ya
tenia la seccion encendida la tenia encendida ENTERA, asi que separarla no le
puede apagar la mitad sin avisar. Los tenants que la tenian apagada siguen con
los dos apagados, que es el default de la columna.

Revision ID: e4c1a9d73b52
Revises: 9f2c7ad41b63
"""
import sqlalchemy as sa
from alembic import op

revision = "e4c1a9d73b52"
down_revision = "9f2c7ad41b63"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("config_consultorio", sa.Column(
        "cupones_activo", sa.Boolean(), nullable=False, server_default="0"))
    # Nadie pierde los cupones al desplegar: ver el docstring de arriba.
    op.execute("UPDATE config_consultorio SET cupones_activo = descuentos_activo")


def downgrade():
    op.drop_column("config_consultorio", "cupones_activo")
