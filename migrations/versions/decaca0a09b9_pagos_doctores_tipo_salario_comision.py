"""pagos_doctores: tipo fijo/variable -> salario/comision

Revision ID: decaca0a09b9
Revises: cb654436345d
Create Date: 2026-05-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'decaca0a09b9'
down_revision = 'b00181d2d215'
branch_labels = None
depends_on = None


def upgrade():
    # Migrate existing tipo values
    op.execute("UPDATE pagos_doctores SET tipo = 'salario'  WHERE tipo = 'fijo'")
    op.execute("UPDATE pagos_doctores SET tipo = 'comision' WHERE tipo = 'variable'")


def downgrade():
    op.execute("UPDATE pagos_doctores SET tipo = 'fijo'      WHERE tipo = 'salario'")
    op.execute("UPDATE pagos_doctores SET tipo = 'variable'  WHERE tipo = 'comision'")
