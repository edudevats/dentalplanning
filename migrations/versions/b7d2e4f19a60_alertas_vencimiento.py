"""alertas de vencimiento: metodo_pago, contact_phone y recordatorios_cobro

`metodo_pago` se rellena desde `clip_subscription_id`: quien tiene suscripción
recurrente de Clip paga por Clip; todos los demás pagan por transferencia, que
es como hoy se registran los pagos a mano.

Revision ID: b7d2e4f19a60
Revises: e4c1a9d73b52
"""
import sqlalchemy as sa
from alembic import op

revision = "b7d2e4f19a60"
down_revision = "e4c1a9d73b52"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subscriptions", sa.Column(
        "metodo_pago", sa.String(20), nullable=False, server_default="transferencia"))
    op.execute(
        "UPDATE subscriptions SET metodo_pago = 'clip' "
        "WHERE clip_subscription_id IS NOT NULL"
    )
    op.add_column("tenants", sa.Column("contact_phone", sa.String(30), nullable=True))
    op.create_table(
        "recordatorios_cobro",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("ciclo", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("canal", sa.String(20), nullable=False),
        sa.Column("origen", sa.String(20), nullable=False),
        sa.Column("destinatario", sa.String(255), nullable=True),
        sa.Column("enviado_por_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_recordatorios_cobro_tenant_id", "recordatorios_cobro", ["tenant_id"])
    op.create_index(
        "ix_recordatorio_sub_ciclo_tipo", "recordatorios_cobro",
        ["subscription_id", "ciclo", "tipo"],
    )


def downgrade():
    op.drop_table("recordatorios_cobro")
    op.drop_column("tenants", "contact_phone")
    op.drop_column("subscriptions", "metodo_pago")
