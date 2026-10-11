"""union de heads: pagos a doctores desde caja + odontograma

Revision ID: 2a1d8c34e805
Revises: b7d2e9a41c58, c3e8a1f5d702

Ya existe en produccion (se creo en el servidor al desplegar el odontograma);
se trae al repo con el mismo ID para que el historial coincida.
"""

revision = "2a1d8c34e805"
down_revision = ("b7d2e9a41c58", "c3e8a1f5d702")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
