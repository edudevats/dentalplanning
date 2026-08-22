"""Cálculo y escritura del corte de caja.

Todo el trabajo del módulo vive aquí, como en `app/inventario/services.py`:
cerrar una caja toca varias tablas, valida candados y congela una foto de
totales. Las rutas solo traducen HTTP.
"""
from sqlalchemy.orm import joinedload

from app.ajustes.models import (
    MetodoPago, TIPO_EFECTIVO, TIPO_TARJETA, TIPOS_METODO,
)
from app.edr.models import GastoOperativo, Ingreso


class CajaError(Exception):
    """Error de negocio del corte. La ruta lo traduce a 4xx."""

    def __init__(self, mensaje, codigo=None, datos=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo
        self.datos = datos or {}


def _filtro_sucursal(columna, sucursal_id):
    """`sucursal_id = NULL` es un valor, no un comodín: es el corte "Sin sucursal"."""
    return columna.is_(None) if sucursal_id is None else columna == sucursal_id


def resumen_dia(tenant_id, sucursal_id, fecha):
    """Foto del día: totales por tipo de método, salidas de caja y detalle.

    Única fuente de verdad del corte — la usan la vista de recepción, la del
    admin y el propio cierre.
    """
    ingresos = Ingreso.query.options(
        joinedload(Ingreso.metodo_pago),
    ).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.fecha == fecha,
        _filtro_sucursal(Ingreso.sucursal_id, sucursal_id),
    ).order_by(Ingreso.id).all()

    totales = {tipo: 0.0 for tipo in TIPOS_METODO}
    comision_tarjeta = 0.0
    sin_clasificar = []
    detalle_ingresos = []

    for ing in ingresos:
        monto = float(ing.monto or 0)
        fila = {
            "id": ing.id,
            "paciente": ing.paciente,
            "concepto": ing.nombre_tratamiento,
            "monto": round(monto, 2),
            "metodo": ing.metodo_pago.nombre if ing.metodo_pago else None,
            "tipo": ing.metodo_pago.tipo if ing.metodo_pago else None,
        }
        detalle_ingresos.append(fila)

        if ing.metodo_pago is None:
            # Un ingreso sin método es efectivo que nadie está contando.
            sin_clasificar.append(fila)
            continue

        tipo = ing.metodo_pago.tipo if ing.metodo_pago.tipo in totales else "otro"
        totales[tipo] += monto
        if tipo == TIPO_TARJETA:
            comision_tarjeta += float(ing.comision_bancaria or 0)

    salidas = GastoOperativo.query.options(
        joinedload(GastoOperativo.metodo_pago),
    ).filter(
        GastoOperativo.tenant_id == tenant_id,
        GastoOperativo.fecha == fecha,
        GastoOperativo.sale_de_caja.is_(True),
        _filtro_sucursal(GastoOperativo.sucursal_id, sucursal_id),
    ).order_by(GastoOperativo.id).all()

    salidas_efectivo = sum(float(s.monto or 0) for s in salidas)
    detalle_salidas = [{
        "id": s.id,
        "concepto": s.concepto_nombre,
        "monto": round(float(s.monto or 0), 2),
        "created_by": s.created_by,
    } for s in salidas]

    totales = {k: round(v, 2) for k, v in totales.items()}
    total_dia = round(sum(totales.values()), 2)
    salidas_efectivo = round(salidas_efectivo, 2)
    comision_tarjeta = round(comision_tarjeta, 2)

    return {
        "totales": totales,
        "comision_tarjeta": comision_tarjeta,
        "neto_tarjeta": round(totales[TIPO_TARJETA] - comision_tarjeta, 2),
        "total_dia": total_dia,
        "salidas_efectivo": salidas_efectivo,
        "esperado_efectivo": round(totales[TIPO_EFECTIVO] - salidas_efectivo, 2),
        "sin_clasificar": sin_clasificar,
        "ingresos": detalle_ingresos,
        "salidas": detalle_salidas,
    }
