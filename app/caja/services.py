"""Cálculo y escritura del corte de caja.

Todo el trabajo del módulo vive aquí, como en `app/inventario/services.py`:
cerrar una caja toca varias tablas, valida candados y congela una foto de
totales. Las rutas solo traducen HTTP.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.ajustes.models import (
    MetodoPago, TIPO_EFECTIVO, TIPO_TARJETA, TIPOS_METODO,
)
from app.caja.models import (
    CorteCaja, CorteCajaEvento, EVENTO_CIERRE, EVENTO_RECIERRE, EVENTO_REAPERTURA,
)
from app.configuracion.models import ConfigConsultorio
from app.edr.models import GastoOperativo, Ingreso
from app.extensions import db


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


def obtener_corte(tenant_id, sucursal_id, fecha):
    """La fila del corte, exista o no. `None` significa día abierto."""
    return CorteCaja.query.filter(
        CorteCaja.tenant_id == tenant_id,
        CorteCaja.fecha == fecha,
        _filtro_sucursal(CorteCaja.sucursal_id, sucursal_id),
    ).first()


def corte_cerrado(tenant_id, sucursal_id, fecha):
    """True si ese día está cerrado. Lo consultan los candados de captura."""
    corte = obtener_corte(tenant_id, sucursal_id, fecha)
    return bool(corte and corte.cerrado)


def tolerancia(tenant_id):
    """Diferencia en pesos que se acepta sin exigir comentario."""
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    return float(getattr(cfg, "tolerancia_corte_caja", 0) or 0)


def _snapshot(corte):
    """Los totales de la fila, para guardarlos en el evento antes de pisarlos."""
    return {
        "total_efectivo": corte.total_efectivo,
        "total_tarjeta": corte.total_tarjeta,
        "total_transferencia": corte.total_transferencia,
        "total_otro": corte.total_otro,
        "comision_tarjeta": corte.comision_tarjeta,
        "salidas_efectivo": corte.salidas_efectivo,
        "efectivo_contado": corte.efectivo_contado,
        "esperado_efectivo": corte.esperado_efectivo,
        "diferencia": corte.diferencia,
    }


def cerrar_corte(tenant_id, usuario_id, *, fecha, sucursal_id,
                 efectivo_contado, comentario=None):
    """Congela la foto del día y la firma. Recerrar reusa la misma fila."""
    try:
        contado = round(float(efectivo_contado), 2)
    except (TypeError, ValueError):
        raise CajaError("El efectivo contado no es un número válido",
                        codigo="contado_invalido")
    if contado < 0:
        raise CajaError("El efectivo contado no puede ser negativo",
                        codigo="contado_invalido")

    corte = obtener_corte(tenant_id, sucursal_id, fecha)
    if corte is not None and corte.cerrado:
        raise CajaError(
            f"La caja del {fecha.strftime('%d/%m/%Y')} ya fue cerrada",
            codigo="ya_cerrado",
        )

    resumen = resumen_dia(tenant_id, sucursal_id, fecha)

    # Un ingreso sin método es efectivo que nadie está contando: si el cierre
    # lo dejara pasar, el dinero se fugaría en silencio y el corte se
    # declararía cuadrado.
    if resumen["sin_clasificar"]:
        raise CajaError(
            "Hay ingresos sin método de pago. Asígnales uno antes de cerrar.",
            codigo="sin_clasificar",
            datos={"sin_clasificar": resumen["sin_clasificar"]},
        )

    diferencia = round(contado - resumen["esperado_efectivo"], 2)
    comentario = (comentario or "").strip() or None
    if abs(diferencia) > tolerancia(tenant_id) and not comentario:
        raise CajaError(
            "La diferencia excede la tolerancia: explica por qué antes de cerrar",
            codigo="comentario_requerido",
            datos={"diferencia": diferencia},
        )

    es_recierre = corte is not None
    if es_recierre:
        # Antes de pisar los totales, se guarda lo que la fila decía.
        db.session.add(CorteCajaEvento(
            tenant_id=tenant_id, corte_id=corte.id, evento=EVENTO_RECIERRE,
            usuario_id=usuario_id, datos=_snapshot(corte),
        ))
    else:
        corte = CorteCaja(tenant_id=tenant_id, sucursal_id=sucursal_id,
                          fecha=fecha)
        db.session.add(corte)

    corte.total_efectivo = resumen["totales"]["efectivo"]
    corte.total_tarjeta = resumen["totales"]["tarjeta"]
    corte.total_transferencia = resumen["totales"]["transferencia"]
    corte.total_otro = resumen["totales"]["otro"]
    corte.comision_tarjeta = resumen["comision_tarjeta"]
    corte.salidas_efectivo = resumen["salidas_efectivo"]
    corte.efectivo_contado = contado
    corte.comentario = comentario
    corte.cerrado_por = usuario_id
    corte.cerrado_at = datetime.now(timezone.utc)
    db.session.flush()

    if not es_recierre:
        db.session.add(CorteCajaEvento(
            tenant_id=tenant_id, corte_id=corte.id, evento=EVENTO_CIERRE,
            usuario_id=usuario_id, datos=_snapshot(corte),
        ))

    db.session.commit()
    return corte


def reabrir_corte(tenant_id, usuario_id, corte_id, motivo):
    """Devuelve el día a captura. Solo el admin llega aquí (lo filtra la ruta)."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise CajaError("Escribe el motivo de la reapertura",
                        codigo="motivo_requerido")

    corte = CorteCaja.query.filter_by(id=corte_id, tenant_id=tenant_id).first()
    if corte is None:
        raise CajaError("Corte no encontrado", codigo="no_encontrado")
    if not corte.cerrado:
        raise CajaError("Ese corte ya está abierto", codigo="ya_abierto")

    db.session.add(CorteCajaEvento(
        tenant_id=tenant_id, corte_id=corte.id, evento=EVENTO_REAPERTURA,
        usuario_id=usuario_id, motivo=motivo, datos=_snapshot(corte),
    ))
    db.session.commit()
    return corte
