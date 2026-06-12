"""add pago_comision_ingreso + auto-link FIFO de comisiones existentes

Revision ID: e1f2a3b4c5d6
Revises: c4e1f2a3b6d7
Create Date: 2026-06-11

Crea la tabla puente que liga un PagoDoctor (tipo comisión) con los ingresos
cuya comisión liquida. Además, para no romper datos previos a la función,
auto-liga los pagos de comisión ya existentes a los ingresos pendientes más
antiguos de cada doctor (FIFO), de modo que lo ya pagado no aparezca pendiente
ni se pueda pagar de nuevo.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'e1f2a3b4c5d6'
down_revision = 'c4e1f2a3b6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pago_comision_ingreso',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('tenant_id', sa.Integer, sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('pago_id', sa.Integer, sa.ForeignKey('pagos_doctores.id'), nullable=False),
        sa.Column('ingreso_id', sa.Integer, sa.ForeignKey('ingresos.id'), nullable=False),
        sa.Column('monto', sa.Float, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )

    conn = op.get_bind()

    pares = conn.execute(sa.text(
        "SELECT DISTINCT tenant_id, especialista_id FROM pagos_doctores "
        "WHERE tipo = 'comision' AND especialista_id IS NOT NULL"
    )).fetchall()

    for tenant_id, especialista_id in pares:
        pagos = conn.execute(sa.text(
            "SELECT id, monto FROM pagos_doctores "
            "WHERE tenant_id = :t AND especialista_id = :e AND tipo = 'comision' "
            "ORDER BY fecha, id"
        ), {"t": tenant_id, "e": especialista_id}).fetchall()

        ingresos = conn.execute(sa.text(
            "SELECT id, comision_doctor FROM ingresos "
            "WHERE tenant_id = :t AND especialista_id = :e AND comision_doctor > 0 "
            "ORDER BY fecha, id"
        ), {"t": tenant_id, "e": especialista_id}).fetchall()

        pago_iter = iter(pagos)
        try:
            cur = next(pago_iter)
        except StopIteration:
            continue
        credito = cur.monto or 0.0
        cur_id = cur.id
        agotado = False

        for ing in ingresos:
            com = ing.comision_doctor or 0.0
            # Avanzar al siguiente pago mientras el actual no tenga crédito.
            while credito <= 0 and not agotado:
                try:
                    cur = next(pago_iter)
                    credito = cur.monto or 0.0
                    cur_id = cur.id
                except StopIteration:
                    agotado = True
            if agotado:
                break
            conn.execute(sa.text(
                "INSERT INTO pago_comision_ingreso "
                "(tenant_id, pago_id, ingreso_id, monto) "
                "VALUES (:t, :p, :i, :m)"
            ), {"t": tenant_id, "p": cur_id, "i": ing.id, "m": com})
            credito -= com


def downgrade():
    op.drop_table('pago_comision_ingreso')
