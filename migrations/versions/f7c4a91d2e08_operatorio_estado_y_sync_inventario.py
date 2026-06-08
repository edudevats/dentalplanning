"""operatorio estado y sync materiales -> inventario

Revision ID: f7c4a91d2e08
Revises: d5013ec1eadb
Create Date: 2026-06-03 00:00:00.000000

Cambios:
- operatorios.activo (Boolean) -> operatorios.estado (String(20)).
  True -> 'activo', False -> 'suspendido'.
- Materiales: en_inventario = True para todo Material existente. La
  politica es "auto-sync siempre"; legacy con en_inventario=False
  causaba desajuste entre /materiales y el dashboard de inventario.
- Backfill: cada Material con en_inventario=True (i.e. todos) recibe
  una fila StockUbicacion (cantidad=0) por cada Operatorio que no la
  tenga.
- Sincronizacion: ConfigConsultorio.numero_unidades = count(Operatorio)
  por tenant (cuando hay >= 1 operatorio).
"""
from alembic import op
import sqlalchemy as sa


revision = 'f7c4a91d2e08'
down_revision = 'd5013ec1eadb'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    with op.batch_alter_table("operatorios") as batch_op:
        batch_op.add_column(
            sa.Column(
                "estado",
                sa.String(length=20),
                nullable=False,
                server_default="activo",
            )
        )

    bind.execute(sa.text(
        "UPDATE operatorios SET estado = 'suspendido' WHERE activo = 0"
    ))
    bind.execute(sa.text(
        "UPDATE operatorios SET estado = 'activo' WHERE activo = 1"
    ))

    with op.batch_alter_table("operatorios") as batch_op:
        batch_op.drop_column("activo")

    bind.execute(sa.text(
        "UPDATE materiales SET en_inventario = 1 WHERE en_inventario = 0"
    ))

    bind.execute(sa.text("""
        INSERT INTO stock_ubicacion (tenant_id, material_id, operatorio_id, cantidad)
        SELECT m.tenant_id, m.id, o.id, 0
        FROM materiales m
        JOIN operatorios o ON o.tenant_id = m.tenant_id
        WHERE m.en_inventario = 1
          AND NOT EXISTS (
              SELECT 1 FROM stock_ubicacion s
              WHERE s.tenant_id = m.tenant_id
                AND s.material_id = m.id
                AND s.operatorio_id = o.id
          )
    """))

    bind.execute(sa.text("""
        UPDATE config_consultorio
        SET numero_unidades = (
            SELECT COUNT(*) FROM operatorios
            WHERE operatorios.tenant_id = config_consultorio.tenant_id
        )
        WHERE EXISTS (
            SELECT 1 FROM operatorios
            WHERE operatorios.tenant_id = config_consultorio.tenant_id
        )
    """))


def downgrade():
    bind = op.get_bind()

    with op.batch_alter_table("operatorios") as batch_op:
        batch_op.add_column(
            sa.Column(
                "activo",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )

    bind.execute(sa.text(
        "UPDATE operatorios SET activo = 0 WHERE estado != 'activo'"
    ))
    bind.execute(sa.text(
        "UPDATE operatorios SET activo = 1 WHERE estado = 'activo'"
    ))

    with op.batch_alter_table("operatorios") as batch_op:
        batch_op.drop_column("estado")
