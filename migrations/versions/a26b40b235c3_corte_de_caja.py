"""corte de caja: tipo de metodo, metodo en gastos, cortes y eventos

Revision ID: a26b40b235c3
Revises: afb12a05e6da
Create Date: 2026-08-22

"""
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = 'a26b40b235c3'
down_revision = 'afb12a05e6da'
branch_labels = None
depends_on = None


# El orden importa: "Transferencia con tarjeta" es tarjeta, no transferencia —
# lo que decide es el instrumento con el que se cobró.
_PATRONES = (
    ("tarjeta", ("tarjeta", "tdc", "tdd", "terminal", "visa", "master",
                 "amex", "credito", "debito")),
    ("transferencia", ("transferencia", "spei", "deposito", "bancaria")),
    ("efectivo", ("efectivo", "cash")),
)


def clasificar_por_nombre(nombre):
    """Adivina el tipo de un método de pago por su nombre. Default: 'otro'.

    Ignora mayúsculas y acentos. Es una heurística de arranque: el admin
    corrige lo que falle desde Ajustes → Métodos de Pago.
    """
    if not nombre:
        return "otro"
    plano = unicodedata.normalize("NFKD", str(nombre))
    plano = "".join(c for c in plano if not unicodedata.combining(c)).lower()
    for tipo, patrones in _PATRONES:
        if any(p in plano for p in patrones):
            return tipo
    return "otro"


def upgrade():
    op.add_column('metodos_pago', sa.Column(
        'tipo', sa.String(length=20), nullable=False, server_default='otro'))

    op.add_column('gastos_operativos', sa.Column(
        'metodo_pago_id', sa.Integer(), nullable=True))
    op.add_column('gastos_operativos', sa.Column(
        'sucursal_id', sa.Integer(), nullable=True))
    op.add_column('gastos_operativos', sa.Column(
        'created_by', sa.Integer(), nullable=True))
    op.add_column('gastos_operativos', sa.Column(
        'sale_de_caja', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.create_foreign_key('fk_gastos_metodo_pago', 'gastos_operativos',
                          'metodos_pago', ['metodo_pago_id'], ['id'])
    op.create_foreign_key('fk_gastos_sucursal', 'gastos_operativos',
                          'sucursales', ['sucursal_id'], ['id'])
    op.create_foreign_key('fk_gastos_created_by', 'gastos_operativos',
                          'users', ['created_by'], ['id'])

    op.add_column('config_consultorio', sa.Column(
        'tolerancia_corte_caja', sa.Float(), nullable=False, server_default='0'))

    op.create_table(
        'cortes_caja',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('sucursal_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('total_efectivo', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_tarjeta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_transferencia', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_otro', sa.Float(), nullable=False, server_default='0'),
        sa.Column('comision_tarjeta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('salidas_efectivo', sa.Float(), nullable=False, server_default='0'),
        sa.Column('efectivo_contado', sa.Float(), nullable=False, server_default='0'),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.Column('cerrado_por', sa.Integer(), nullable=False),
        sa.Column('cerrado_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursales.id']),
        sa.ForeignKeyConstraint(['cerrado_por'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'sucursal_id', 'fecha',
                            name='uq_corte_caja_tenant_sucursal_fecha'),
    )
    op.create_index('ix_cortes_caja_tenant_fecha', 'cortes_caja',
                    ['tenant_id', 'fecha'])

    op.create_table(
        'cortes_caja_eventos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('corte_id', sa.Integer(), nullable=False),
        sa.Column('evento', sa.String(length=20), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('datos', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['corte_id'], ['cortes_caja.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cortes_caja_eventos_tenant_corte', 'cortes_caja_eventos',
                    ['tenant_id', 'corte_id'])

    _backfill()


def _backfill():
    """Clasifica los métodos existentes y liga las devoluciones a su método."""
    conn = op.get_bind()

    for mid, nombre in conn.execute(
        sa.text("SELECT id, nombre FROM metodos_pago")
    ).fetchall():
        conn.execute(
            sa.text("UPDATE metodos_pago SET tipo = :t WHERE id = :id"),
            {"t": clasificar_por_nombre(nombre), "id": mid},
        )

    # Las devoluciones ya guardan con qué se devolvió; su gasto ligado no.
    # Se copia el método y se marca la salida de caja cuando fue en efectivo.
    conn.execute(sa.text("""
        UPDATE gastos_operativos AS g
        SET metodo_pago_id = (
            SELECT d.metodo_pago_id FROM cobranza_devoluciones AS d
            WHERE d.gasto_id = g.id
        )
        WHERE EXISTS (SELECT 1 FROM cobranza_devoluciones AS d WHERE d.gasto_id = g.id)
    """))
    conn.execute(sa.text("""
        UPDATE gastos_operativos SET sale_de_caja = 1
        WHERE metodo_pago_id IN (
            SELECT id FROM metodos_pago WHERE tipo = 'efectivo'
        )
        AND id IN (SELECT gasto_id FROM cobranza_devoluciones WHERE gasto_id IS NOT NULL)
    """))


def downgrade():
    op.drop_index('ix_cortes_caja_eventos_tenant_corte',
                  table_name='cortes_caja_eventos')
    op.drop_table('cortes_caja_eventos')
    op.drop_index('ix_cortes_caja_tenant_fecha', table_name='cortes_caja')
    op.drop_table('cortes_caja')
    op.drop_column('config_consultorio', 'tolerancia_corte_caja')
    op.drop_constraint('fk_gastos_created_by', 'gastos_operativos',
                       type_='foreignkey')
    op.drop_constraint('fk_gastos_sucursal', 'gastos_operativos',
                       type_='foreignkey')
    op.drop_constraint('fk_gastos_metodo_pago', 'gastos_operativos',
                       type_='foreignkey')
    op.drop_column('gastos_operativos', 'sale_de_caja')
    op.drop_column('gastos_operativos', 'created_by')
    op.drop_column('gastos_operativos', 'sucursal_id')
    op.drop_column('gastos_operativos', 'metodo_pago_id')
    op.drop_column('metodos_pago', 'tipo')
