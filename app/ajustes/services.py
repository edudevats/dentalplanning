"""Lógica de descuentos y cupones.

Toda escritura de negocio pasa por aquí (patrón de inventario/services.py y
edr/services.py). Las funciones NO hacen commit; lo hace el llamador.
"""

from app.extensions import db
from app.ajustes.models import (
    Cupon, Descuento, DESCUENTOS_DEFAULT, CUPON_MONTO, CUPON_PORCENTAJE,
)
from app.configuracion.models import ConfigConsultorio


class DescuentosError(Exception):
    """Dato inválido en un descuento o un canje (el llamador lo traduce a HTTP)."""


def descuentos_activos(tenant_id):
    """True si el consultorio encendió los descuentos de visita."""
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    return bool(cfg and cfg.descuentos_activo)


def cupones_activos(tenant_id):
    """True si el consultorio encendió los cupones.

    Es un interruptor aparte del de descuentos: son dos funciones distintas y
    hay clínicas que solo usan una. El canje depende de ÉSTE, no del otro.
    """
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    return bool(cfg and cfg.cupones_activo)


def sembrar_descuentos(tenant_id):
    """Crea los porcentajes de fábrica. Idempotente: devuelve cuántos creó.

    Solo siembra cuando el tenant no tiene NINGUNO. Si ya capturó los suyos,
    no le caen encima los de fábrica; y si borró todos a propósito, volverá a
    recibirlos la próxima vez que encienda, que es preferible a dejarlo con la
    lista vacía sin explicación.
    """
    if Descuento.query.filter_by(tenant_id=tenant_id).count():
        return 0
    for pct in DESCUENTOS_DEFAULT:
        db.session.add(Descuento(
            tenant_id=tenant_id, nombre=f"{pct}%", porcentaje=float(pct),
        ))
    return len(DESCUENTOS_DEFAULT)


def _config_o_error(tenant_id):
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    if not cfg:
        raise DescuentosError("El consultorio no tiene configuración todavía")
    return cfg


def activar_descuentos(tenant_id, activo):
    """Mueve el toggle de descuentos. Al encender siembra; al apagar no borra.

    Apagar conserva el catálogo a propósito: es un interruptor de visibilidad,
    no un botón de borrado. Quien lo apague por error vuelve a encenderlo y
    encuentra sus descuentos intactos.

    No toca el toggle de cupones: son independientes.
    """
    cfg = _config_o_error(tenant_id)
    cfg.descuentos_activo = bool(activo)
    if cfg.descuentos_activo:
        sembrar_descuentos(tenant_id)
    return cfg.descuentos_activo


def activar_cupones(tenant_id, activo):
    """Mueve el toggle de cupones. No siembra nada y no borra nada.

    No hay cupones de fábrica que sembrar: los captura la clínica uno por uno,
    con su código y su tratamiento. Apagar conserva los que ya existen, igual
    que con los descuentos.
    """
    cfg = _config_o_error(tenant_id)
    cfg.cupones_activo = bool(activo)
    return cfg.cupones_activo


# ── Cupones ──

def normalizar_codigo(codigo):
    """Los códigos se comparan en mayúsculas y sin espacios sobrantes.

    En el mostrador el código se dicta o se lee de un papel, así que llega
    tecleado de cualquier forma. Se normaliza al guardar y al buscar, para que
    "blanq50" encuentre a BLANQ50.
    """
    return (codigo or "").strip().upper()


def usos_de(cupon):
    """Cuántas veces se ha canjeado, contando ingresos y conceptos.

    Se cuenta en vez de guardar un contador: un contador denormalizado puede
    desincronizarse, y contando, borrar el ingreso o la cotización libera el
    uso solo.
    """
    from app.cobranza.models import Cotizacion, CotizacionConcepto
    from app.edr.models import Ingreso

    en_ingresos = Ingreso.query.filter_by(
        tenant_id=cupon.tenant_id, cupon_id=cupon.id,
    ).count()
    # `rechazar_cotizacion`/`cancelar_cotizacion` (app/cobranza/services.py)
    # nunca borran los CotizacionConcepto, solo cambian el estatus. Una
    # cotización "rechazada" es un presupuesto que el paciente nunca aceptó
    # (nadie se trató, nada se cobró), así que no debe quemar el cupón — si
    # no, una promo de N usos se agotaría sola con presupuestos rechazados.
    # "cancelada" SÍ cuenta: es un plan que se aprobó y se cobró
    # parcialmente, así que el cupón sí se usó de verdad.
    en_conceptos = (
        CotizacionConcepto.query
        .join(Cotizacion, CotizacionConcepto.cotizacion_id == Cotizacion.id)
        .filter(
            CotizacionConcepto.tenant_id == cupon.tenant_id,
            CotizacionConcepto.cupon_id == cupon.id,
            Cotizacion.tenant_id == cupon.tenant_id,
            Cotizacion.estatus != "rechazada",
        )
        .count()
    )
    return en_ingresos + en_conceptos


def tiene_referencias(cupon):
    """True si CUALQUIER fila apunta a este cupón, sin importar el estatus.

    Distinto de `usos_de()`: ese cuenta canjes VIGENTES (excluye cotizaciones
    "rechazada") para decidir si quedan usos disponibles. Esta pregunta es
    "¿algo referencia esta fila?", que es la que hay que responder antes de
    borrar -- `cotizacion_conceptos.cupon_id` sigue apuntando al cupón aunque
    la cotización se haya rechazado, y borrar el cupón con esa fila viva
    revienta la FK en MySQL (SQLite no la aplica, así que ahí no truena).
    """
    from app.cobranza.models import CotizacionConcepto
    from app.edr.models import Ingreso

    en_ingresos = Ingreso.query.filter_by(
        tenant_id=cupon.tenant_id, cupon_id=cupon.id,
    ).count()
    en_conceptos = CotizacionConcepto.query.filter_by(
        tenant_id=cupon.tenant_id, cupon_id=cupon.id,
    ).count()
    return bool(en_ingresos or en_conceptos)


def validar_cupon(tenant_id, codigo, tratamiento_id, fecha, *, bloquear=False,
                   usos_extra=0):
    """Devuelve el cupón canjeable, o levanta DescuentosError con el motivo.

    `bloquear=True` toma la fila del cupón con FOR UPDATE: sin eso, dos
    capturas simultáneas pueden leer el mismo conteo y quemar las dos el
    último uso. SQLite (tests) ignora el FOR UPDATE, que ahí no hace falta.

    `usos_extra` suma canjes del mismo cupón que todavía no están escritos en
    la base (p. ej. otras líneas de la MISMA visita, resueltas en la misma
    transacción antes del primer flush): sin esto, `usos_de()` los cuenta a
    todos como cero y dos líneas iguales queman dos usos de un cupón de uno
    solo.
    """
    # El canje depende del toggle de CUPONES, no del de descuentos: son dos
    # funciones independientes y una clínica que solo da descuentos de visita
    # no debe poder canjear.
    if not cupones_activos(tenant_id):
        raise DescuentosError(
            "La sección de cupones no está activada en Ajustes"
        )

    codigo = normalizar_codigo(codigo)
    if not codigo:
        raise DescuentosError("Captura el código del cupón")

    q = Cupon.query.filter_by(tenant_id=tenant_id, codigo=codigo)
    if bloquear:
        q = q.with_for_update()
    cupon = q.first()
    if not cupon:
        raise DescuentosError(f"El cupón {codigo} no existe")
    if not cupon.is_active:
        raise DescuentosError(f"El cupón {codigo} está desactivado")
    if not tratamiento_id or cupon.tratamiento_id != tratamiento_id:
        nombre = cupon.tratamiento.nombre if cupon.tratamiento else "otro tratamiento"
        raise DescuentosError(
            f"El cupón {codigo} no aplica a este tratamiento; es de {nombre}"
        )
    if fecha:
        if cupon.vigencia_desde and fecha < cupon.vigencia_desde:
            raise DescuentosError(
                f"El cupón {codigo} está fuera de vigencia para esa fecha"
            )
        if cupon.vigencia_hasta and fecha > cupon.vigencia_hasta:
            raise DescuentosError(
                f"El cupón {codigo} está fuera de vigencia para esa fecha"
            )
    if (cupon.max_usos is not None
            and usos_de(cupon) + usos_extra >= cupon.max_usos):
        raise DescuentosError(f"El cupón {codigo} ya está agotado")
    return cupon


def aplicar_cupon(precio, cupon):
    """(monto_final, descuento_monto) a partir del precio ANTES del cupón.

    El monto fijo nunca deja la línea en negativo: un cupón de $500 sobre un
    tratamiento de $300 la deja en $0, y `descuento_monto` guarda los $300 que
    realmente se descontaron, no los $500 nominales — de lo contrario el
    reporte de descuentos sumaría dinero que nadie dejó de cobrar.
    """
    precio = round(float(precio or 0.0), 2)
    if cupon.tipo == CUPON_PORCENTAJE:
        monto = round(precio * (1 - (cupon.valor or 0) / 100), 2)
    elif cupon.tipo == CUPON_MONTO:
        monto = round(max(0.0, precio - (cupon.valor or 0)), 2)
    else:
        raise DescuentosError(f"Tipo de cupón desconocido: {cupon.tipo}")
    monto = max(0.0, monto)
    return monto, round(precio - monto, 2)
