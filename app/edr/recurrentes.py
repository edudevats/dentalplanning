"""Gastos recurrentes: convierte cada GastoRecurrente en GastoOperativo reales.

No hay cron: `generar_pendientes_seguro` se llama al inicio de cada lectura de
gastos (lista de /gastos y los reportes). Es idempotente, así que llamarla de
más no cuesta nada: `ultima_fecha_generada` dice hasta dónde ya se generó.
"""
from calendar import monthrange
from datetime import date

from flask import current_app

from app.extensions import db
from app.edr.models import GastoOperativo, GastoRecurrente


def fecha_del_mes(dia, year, month):
    """El `dia` de ese mes, o el último día si el mes es más corto."""
    return date(year, month, min(dia, monthrange(year, month)[1]))


def _mes_siguiente(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _mes_anterior(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def siguiente_fecha(rec):
    """La próxima fecha que le toca generar a `rec`.

    El día base es SIEMPRE `fecha_inicio.day`: un recurrente del 31 que cayó el
    30 de noviembre vuelve al 31 en diciembre.
    """
    if rec.ultima_fecha_generada is None:
        return rec.fecha_inicio
    y, m = _mes_siguiente(rec.ultima_fecha_generada.year,
                          rec.ultima_fecha_generada.month)
    return fecha_del_mes(rec.fecha_inicio.day, y, m)


def ultima_programada_antes_de(dia, hoy):
    """La última fecha de la secuencia mensual de `dia` estrictamente antes de hoy."""
    este_mes = fecha_del_mes(dia, hoy.year, hoy.month)
    if este_mes < hoy:
        return este_mes
    y, m = _mes_anterior(hoy.year, hoy.month)
    return fecha_del_mes(dia, y, m)


def reactivar(rec, hoy):
    """Mueve la marca para que la reactivación no rellene los meses de la pausa.

    Lo siguiente que se genera es la primera fecha en o después de hoy. El
    máximo con la marca guardada evita repetir un gasto que ya se generó hoy
    (pausar y reactivar el mismo día). Si el primer cargo aún no llega, no se
    toca nada. No hace commit.
    """
    previa = ultima_programada_antes_de(rec.fecha_inicio.day, hoy)
    if previa < rec.fecha_inicio:
        return
    if rec.ultima_fecha_generada is None or previa > rec.ultima_fecha_generada:
        rec.ultima_fecha_generada = previa


def generar_pendientes(tenant_id, hoy=None, commit=True):
    """Crea los gastos que ya tocaban y todavía no existen. Devuelve cuántos."""
    hoy = hoy or date.today()
    activos = GastoRecurrente.query.filter_by(tenant_id=tenant_id, activo=True).all()
    vencidos = [r.id for r in activos if siguiente_fecha(r) <= hoy]
    if not vencidos:
        return 0

    # Segunda lectura, ahora con candado: otra petición pudo generar entre la
    # primera lectura y esta. populate_existing refresca los objetos que ya
    # estaban en la sesión con lo que dice la BD bajo el candado.
    bloqueados = (
        GastoRecurrente.query
        .filter(
            GastoRecurrente.id.in_(vencidos),
            GastoRecurrente.tenant_id == tenant_id,
            GastoRecurrente.activo.is_(True),
        )
        .with_for_update()
        .populate_existing()
        .all()
    )
    creados = 0
    for rec in bloqueados:
        fecha = siguiente_fecha(rec)
        while fecha <= hoy:
            db.session.add(GastoOperativo(
                tenant_id=tenant_id,
                fecha=fecha,
                concepto_id=rec.concepto_id,
                concepto_nombre=rec.concepto_nombre,
                tipo=rec.tipo,
                monto=rec.monto,
                metodo_pago_id=rec.metodo_pago_id,
                sucursal_id=rec.sucursal_id,
                # Nadie sacó dinero del cajón ese día: el recurrente nunca
                # entra al corte de caja.
                sale_de_caja=False,
                created_by=rec.created_by,
                recurrente_id=rec.id,
            ))
            rec.ultima_fecha_generada = fecha
            creados += 1
            fecha = siguiente_fecha(rec)
    if commit:
        db.session.commit()
    return creados


def generar_pendientes_seguro(tenant_id):
    """Como `generar_pendientes`, pero un fallo nunca tumba la lectura que la llama."""
    try:
        return generar_pendientes(tenant_id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "No se pudieron generar los gastos recurrentes del tenant %s", tenant_id)
        return 0
