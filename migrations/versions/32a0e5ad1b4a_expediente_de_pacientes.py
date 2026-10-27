"""expediente de pacientes

Número de expediente por paciente (letra + 6 dígitos o 7 dígitos) y su
configuración por clínica. crm_config.expediente_siguiente nace en 100 para
las clínicas existentes; pacientes.expediente nace NULL.

Revision ID: 32a0e5ad1b4a
Revises: 7c4e1a9b2d60
"""
import sqlalchemy as sa
from alembic import op

revision = "32a0e5ad1b4a"
down_revision = "7c4e1a9b2d60"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("crm_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("expediente_formato", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("expediente_letras", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("expediente_siguiente", sa.Integer(), server_default="100", nullable=False))

    with op.batch_alter_table("pacientes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("expediente", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("expediente_numero", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint("uq_pacientes_tenant_expediente", ["tenant_id", "expediente"])


def downgrade():
    with op.batch_alter_table("pacientes", schema=None) as batch_op:
        batch_op.drop_constraint("uq_pacientes_tenant_expediente", type_="unique")
        batch_op.drop_column("expediente_numero")
        batch_op.drop_column("expediente")

    with op.batch_alter_table("crm_config", schema=None) as batch_op:
        batch_op.drop_column("expediente_siguiente")
        batch_op.drop_column("expediente_letras")
        batch_op.drop_column("expediente_formato")
