"""Mover el logo de configuracion_fiscal a config_consultorio.

El logo es un dato de la clínica, no de sus datos fiscales: lo usan el ticket
impreso, el PDF del CFDI, el portal de autofacturación y las cotizaciones. Se
copia el contenido existente antes de soltar la columna vieja.

Revision ID: b2c3d4e5f6a7
Revises: d3e4f5a6b7c8
Create Date: 2026-07-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import MEDIUMBLOB

revision = "b2c3d4e5f6a7"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


# MySQL mapea LargeBinary a BLOB (máx 64KB) y truncaría los logos grandes;
# MEDIUMBLOB sube el límite a 16MB. El variant es no-op en otros dialectos.
TIPO_LOGO = sa.LargeBinary().with_variant(MEDIUMBLOB(), "mysql")


def upgrade():
    op.add_column("config_consultorio", sa.Column("logo", TIPO_LOGO, nullable=True))

    # Copia el logo de cada tenant que ya tenga uno. Se hace por tenant_id
    # porque ambas tablas son 1-a-1 con el tenant.
    op.execute(sa.text("""
        UPDATE config_consultorio
           SET logo = (
               SELECT cf.logo FROM configuracion_fiscal cf
                WHERE cf.tenant_id = config_consultorio.tenant_id
           )
         WHERE EXISTS (
               SELECT 1 FROM configuracion_fiscal cf
                WHERE cf.tenant_id = config_consultorio.tenant_id
                  AND cf.logo IS NOT NULL
         )
    """))

    op.drop_column("configuracion_fiscal", "logo")


def downgrade():
    op.add_column("configuracion_fiscal", sa.Column("logo", TIPO_LOGO, nullable=True))
    op.execute(sa.text("""
        UPDATE configuracion_fiscal
           SET logo = (
               SELECT cc.logo FROM config_consultorio cc
                WHERE cc.tenant_id = configuracion_fiscal.tenant_id
           )
         WHERE EXISTS (
               SELECT 1 FROM config_consultorio cc
                WHERE cc.tenant_id = configuracion_fiscal.tenant_id
                  AND cc.logo IS NOT NULL
         )
    """))
    op.drop_column("config_consultorio", "logo")
