"""Interruptor del campo "agregar a un ticket ya abierto" en /ingresos

La serie y la secuencia del folio ya las pone la sucursal (Ajustes >
Sucursales), asi que para casi todos los consultorios el campo de folio manual
de la pantalla de captura sobra. En vez de quitarselo a todos, queda tras un
interruptor por tenant: quien lo necesita lo prende, y el resto captura con la
pantalla limpia.

Nace apagado, tambien para los tenants que ya existen: es el default que hace
la captura mas simple, y prenderlo es un clic en Ajustes.

Es SOLO una preferencia de pantalla. La API sigue aceptando `ticket_folio`
este como este esta bandera, porque los abonos de un plan de cobranza lo usan
por dentro para caer en el ticket de su plan.

Revision ID: f3a8b1c60d92
Revises: e9f1a2b3c4d5
"""
import sqlalchemy as sa
from alembic import op

revision = "f3a8b1c60d92"
down_revision = "e9f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "configuracion_fiscal",
        sa.Column("folio_manual_activo", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade():
    op.drop_column("configuracion_fiscal", "folio_manual_activo")
