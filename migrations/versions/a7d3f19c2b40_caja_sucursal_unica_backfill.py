"""Rellena la sucursal de los movimientos que nacieron en NULL

Con una sola sucursal, `abrir_turno` guardaba el turno con `sucursal_id = NULL`,
y de ahí el hueco pasaba al ingreso y al gasto: la pantalla de captura toma la
sucursal del turno. Las dos consecuencias que se vieron en producción:

- el ticket nunca llegaba a crearse, porque `edr/routes.py::crear_ingreso` lo
  salta cuando `sucursal_id` viene nulo;
- y el recibo simple salía sin sucursal, dirección ni teléfono, porque
  `facturacion/routes.py::ticket_simple` los deja en None sin `sucursal_id`.

El código ya no produce el hueco (`resolver_sucursal_del_turno`); esto repara lo
que quedó. Solo en tenants con EXACTAMENTE una sucursal: con dos o más un NULL
es ambiguo y adivinar sería un bug peor.

`cortes_caja` NO se toca: la fila firmada del cierre se guarda sin sucursal a
propósito (ver `cerrar_corte`), y `obtener_corte` la encuentra así.

Revision ID: a7d3f19c2b40
Revises: c0a2783aeffb
"""
import sqlalchemy as sa
from alembic import op

revision = "a7d3f19c2b40"
down_revision = "c0a2783aeffb"
branch_labels = None
depends_on = None

# Las tres tablas por las que el hueco se propagó. El orden no importa: cada
# UPDATE es independiente.
TABLAS = ("ingresos", "gastos_operativos", "turnos_caja")


def _tenants_de_sucursal_unica(conn):
    """{tenant_id: sucursal_id} de los tenants con EXACTAMENTE una sucursal.

    Se resuelve en SQL, y no importando el criterio de `app.caja.services`, a
    propósito: una migración tiene que seguir significando lo mismo dentro de
    diez versiones del código, y para eso no puede depender de él.

    El `HAVING COUNT(*) = 1` es la regla entera: con dos o más sucursales un
    NULL es ambiguo por definición, y rellenarlo sería adivinar a qué sede fue
    el dinero.
    """
    filas = conn.execute(sa.text(
        "SELECT tenant_id, MIN(id) AS sucursal_id "
        "FROM sucursales GROUP BY tenant_id HAVING COUNT(*) = 1"
    )).fetchall()
    return {f[0]: f[1] for f in filas}


def upgrade():
    conn = op.get_bind()
    for tenant_id, sucursal_id in _tenants_de_sucursal_unica(conn).items():
        for tabla in TABLAS:
            conn.execute(
                sa.text(
                    f"UPDATE {tabla} SET sucursal_id = :suc "
                    "WHERE tenant_id = :ten AND sucursal_id IS NULL"
                ),
                {"suc": sucursal_id, "ten": tenant_id},
            )


def downgrade():
    """No hay vuelta atrás, y no debe haberla.

    Revertir exigiría saber cuáles de esas filas tenían sucursal antes del
    relleno y cuáles no, y ese dato no se guardó en ningún lado. Devolverlas
    TODAS a NULL le borraría la sucursal a movimientos legítimos.
    """
    pass
