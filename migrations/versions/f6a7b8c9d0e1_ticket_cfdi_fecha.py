"""Agregar tickets.cfdi_fecha (fecha de emisión fijada por ticket).

Se usa para hacer idempotente el reintento de timbrado: al reintentar un ticket
en 'error' se reutiliza esta fecha y se regenera un comprobante byte-idéntico
(mismo sello), de modo que Finkok lo deduplique si el intento previo sí timbró
pero se perdió la respuesta — evita CFDIs duplicados ante el SAT.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("cfdi_fecha", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("tickets", "cfdi_fecha")
