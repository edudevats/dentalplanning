"""plan programado en subscriptions

Revision ID: d3e4f5a6b7c8
Revises: c8d9e0f1a2b3
Create Date: 2026-07-19 00:00:00.000000

Downgrade de plan programado: el plan mas barato entra al terminar el periodo
ya pagado. ``plan_programado_desde`` guarda la fecha en que debe aplicarse
(el proximo_cobro vigente al momento de agendarlo).
"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e4f5a6b7c8'
down_revision = 'c8d9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.add_column(sa.Column('plan_programado_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('plan_programado_desde', sa.Date(), nullable=True))
        batch_op.create_foreign_key(
            'fk_subscriptions_plan_programado_id_plans',
            'plans', ['plan_programado_id'], ['id'],
        )


def downgrade():
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.drop_constraint('fk_subscriptions_plan_programado_id_plans', type_='foreignkey')
        batch_op.drop_column('plan_programado_desde')
        batch_op.drop_column('plan_programado_id')
