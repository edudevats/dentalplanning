"""Cálculo y escritura del corte de caja.

Todo el trabajo del módulo vive aquí, como en `app/inventario/services.py`:
cerrar una caja toca varias tablas, valida candados y congela una foto de
totales. Las rutas solo traducen HTTP.
"""
from datetime import date, datetime, timezone

from sqlalchemy import func, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.ajustes.models import (
    MetodoPago, TIPO_EFECTIVO, TIPO_TARJETA, TIPOS_METODO,
)
from app.caja.models import (
    CorteCaja, CorteCajaEvento, TurnoCaja,
    EVENTO_CIERRE, EVENTO_RECIERRE, EVENTO_REAPERTURA,
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


def sucursal_separa_cajas(tenant_id):
    """¿La sucursal parte el día en varias cajas? Solo si de verdad hay varias.

    Con una sola sucursal —o ninguna— la clínica tiene UNA caja al día, pero sus
    ingresos NO se guardan todos igual: la pantalla de captura preselecciona la
    única sucursal que existe (`edr/ingresos.html`, openCreate), mientras que la
    página del corte solo aprende qué sucursal pedir a través de un selector que
    únicamente aparece con 2 o más. Resultado: los ingresos caían en un cubo y el
    corte pedía el otro, y la recepcionista veía ceros. Reproducido en
    `tests/test_caja_sucursal_unica.py`.

    Con 2 o más sucursales cada una sí tiene su caja y su corte, y mezclarlas
    sería el bug contrario.
    """
    from app.facturacion.models import Sucursal
    return Sucursal.query.filter_by(tenant_id=tenant_id).limit(2).count() >= 2


def turno_vigente(tenant_id, usuario_id):
    """El turno de HOY de esa persona, o None.

    Vigente = `fecha == hoy` y `cerrado_at IS NULL`. De esa definición sale
    gratis que el turno de ayer caduque solo: tiene otra fecha, así que deja de
    ser vigente sin que ningún proceso lo limpie.
    """
    return TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.usuario_id == usuario_id,
        TurnoCaja.fecha == date.today(),
        TurnoCaja.cerrado_at.is_(None),
    ).first()


def fondo_del_dia(tenant_id, sucursal_id, fecha):
    """El fondo que declaró quien abrió primero ese día en esa sucursal.

    Hay UN cajón por sucursal: si dos personas abren el mismo día, el fondo no
    se suma. Manda el turno más antiguo, que es un valor único y consultable.
    """
    t = TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.fecha == fecha,
        _filtro_sucursal(TurnoCaja.sucursal_id, sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
    ).order_by(TurnoCaja.id).first()
    return round(float(t.fondo_inicial or 0), 2) if t else 0.0


def abrir_turno(tenant_id, usuario_id, *, sucursal_id, fondo_inicial):
    """Abre la caja de esa persona para HOY.

    La fecha la pone el servidor, nunca el cliente: es justamente el dato que el
    candado va a imponerle a todo lo que capture.
    """
    hoy = date.today()

    if sucursal_separa_cajas(tenant_id):
        # Con dos o más sedes, decir dónde trabaja es el punto entero del turno:
        # si se deja adivinar, vuelve el bug que este diseño existe para cerrar.
        if sucursal_id is None:
            raise CajaError("Elige en qué sucursal vas a trabajar",
                            codigo="sucursal_requerida")
    else:
        sucursal_id = None

    vigente = turno_vigente(tenant_id, usuario_id)
    if vigente is not None:
        if vigente.sucursal_id == sucursal_id:
            return vigente          # idempotente: recargar no crea turnos
        nombre = vigente.sucursal.nombre if vigente.sucursal else "Sin sucursal"
        raise CajaError(
            f"Ya abriste caja hoy en {nombre}",
            codigo="turno_en_otra_sucursal",
        )

    if corte_cerrado(tenant_id, sucursal_id, hoy):
        raise CajaError(
            f"La caja del {hoy.strftime('%d/%m/%Y')} ya fue cerrada. "
            "Pide al administrador que la reabra.",
            codigo="dia_cerrado",
        )

    # El fondo es del día: quien abre después hereda el del primero. Se pregunta
    # por la EXISTENCIA de ese turno, no por su monto: un fondo de cero es un
    # dato válido ("hoy arranco sin cambio"), no la ausencia de dato, y
    # `fondo_del_dia` devuelve 0.0 en ambos casos sin poder distinguirlos.
    primero = TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.fecha == hoy,
        _filtro_sucursal(TurnoCaja.sucursal_id, sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
    ).order_by(TurnoCaja.id).first()
    # Mismo criterio ("manda el más antiguo") y misma normalización que
    # `fondo_del_dia`, para que los dos números no puedan separarse nunca.
    heredado = (round(float(primero.fondo_inicial or 0), 2)
                if primero is not None else None)

    try:
        monto = round(float(fondo_inicial or 0), 2)
    except (TypeError, ValueError):
        raise CajaError("El fondo inicial no es un número válido",
                        codigo="fondo_invalido")
    if monto < 0:
        raise CajaError("El fondo inicial no puede ser negativo",
                        codigo="fondo_invalido")

    turno = TurnoCaja(
        tenant_id=tenant_id, usuario_id=usuario_id, sucursal_id=sucursal_id,
        fecha=hoy, fondo_inicial=monto if heredado is None else heredado,
    )
    try:
        db.session.add(turno)
        db.session.commit()
    except IntegrityError:
        # Doble clic: dos llamadas a la vez pasaron la comprobación de arriba y
        # el UNIQUE frenó la fila duplicada. La carrera la ganó la otra, y el
        # turno existe igual: devolver el que quedó es la respuesta correcta, no
        # un 500 en la pantalla que se abre a primera hora todos los días.
        db.session.rollback()
        return turno_vigente(tenant_id, usuario_id)
    return turno


def _filtro_sucursal(columna, sucursal_id, *, separa=True):
    """`sucursal_id = NULL` es un valor, no un comodín: es el corte "Sin sucursal".

    Salvo cuando la sucursal no separa cajas: ahí el filtro desaparece y el día
    se cuenta completo, venga el movimiento con sucursal o sin ella.
    """
    if not separa:
        return true()
    return columna.is_(None) if sucursal_id is None else columna == sucursal_id


def resumen_dia(tenant_id, sucursal_id, fecha):
    """Foto del día: totales por tipo de método, salidas de caja y detalle.

    Única fuente de verdad del corte — la usan la vista de recepción, la del
    admin y el propio cierre.
    """
    separa = sucursal_separa_cajas(tenant_id)
    ingresos = Ingreso.query.options(
        joinedload(Ingreso.metodo_pago),
    ).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.fecha == fecha,
        _filtro_sucursal(Ingreso.sucursal_id, sucursal_id, separa=separa),
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
        _filtro_sucursal(GastoOperativo.sucursal_id, sucursal_id, separa=separa),
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
        _filtro_sucursal(CorteCaja.sucursal_id, sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
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


# Los seis totales que el cierre congela en la fila. Si cualquiera de ellos ya
# no coincide con el recálculo vivo, la foto firmada dejó de describir el día.
TOTALES_CONGELADOS = (
    "total_efectivo", "total_tarjeta", "total_transferencia", "total_otro",
    "comision_tarjeta", "salidas_efectivo",
)


def totales_desde_resumen(resumen):
    """Traduce la salida de `resumen_dia` a los nombres de columna del corte.

    Las mismas claves que escribe `cerrar_corte` al congelar la foto.
    """
    return {
        "total_efectivo": resumen["totales"]["efectivo"],
        "total_tarjeta": resumen["totales"]["tarjeta"],
        "total_transferencia": resumen["totales"]["transferencia"],
        "total_otro": resumen["totales"]["otro"],
        "comision_tarjeta": resumen["comision_tarjeta"],
        "salidas_efectivo": resumen["salidas_efectivo"],
    }


def hay_movimientos_posteriores(corte, vivos):
    """True si la foto firmada difiere del recálculo en CUALQUIER total.

    No basta con vigilar el efectivo: un ingreso de tarjeta o de transferencia
    capturado sobre un día ya cerrado no mueve `esperado_efectivo`, pero sí
    cambia `total_tarjeta`, `comision_tarjeta` y el total del día, y el corte
    seguiría anunciándose como "Cerrado" a secas.
    """
    return any(
        round(float(vivos.get(campo) or 0), 2)
        != round(float(getattr(corte, campo) or 0), 2)
        for campo in TOTALES_CONGELADOS
    )


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

    # Candado por tenant antes del check-then-insert. Con `sucursal_id = NULL`
    # —el default de casi todo tenant— el índice UNIQUE no dispara (en SQL,
    # NULL no colisiona con NULL), así que dos cierres simultáneos crearían dos
    # filas del mismo día y el histórico, que agrupa por (fecha, sucursal_id),
    # perdería una de las dos. Bloquear la fila de config serializa los cierres
    # del tenant en InnoDB sin tocar el esquema. OJO: en SQLite (los tests)
    # `with_for_update()` es un no-op silencioso, y si el tenant no tuviera
    # ConfigConsultorio no habría fila que bloquear; en ambos casos degrada al
    # comportamiento anterior, nunca a algo peor.
    ConfigConsultorio.query.filter_by(
        tenant_id=tenant_id).with_for_update().first()

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
        # Con la sucursal colapsada, la fila firmada se guarda SIN sucursal:
        # así hay un único corte canónico por día y `obtener_corte` lo encuentra
        # venga la petición con sucursal o sin ella.
        corte = CorteCaja(
            tenant_id=tenant_id, fecha=fecha,
            sucursal_id=sucursal_id if sucursal_separa_cajas(tenant_id) else None,
        )
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


CONCEPTO_ENMASCARADO = "Salida autorizada por administración"


def metodo_efectivo(tenant_id):
    """El método de tipo efectivo del tenant. Estable: el de menor id."""
    metodo = MetodoPago.query.filter_by(
        tenant_id=tenant_id, tipo=TIPO_EFECTIVO,
    ).order_by(MetodoPago.id).first()
    if metodo is None:
        raise CajaError(
            "No hay ningún método de pago marcado como efectivo. "
            "Márcalo en Ajustes → Métodos de Pago.",
            codigo="sin_metodo_efectivo",
        )
    return metodo


def registrar_salida(tenant_id, usuario_id, *, fecha, concepto_nombre, monto,
                     sucursal_id):
    """Salida chica de efectivo del cajón. Es un GastoOperativo normal."""
    concepto = (concepto_nombre or "").strip()
    if not concepto:
        raise CajaError("Escribe de qué fue la salida", codigo="concepto_requerido")
    try:
        importe = round(float(monto), 2)
    except (TypeError, ValueError):
        raise CajaError("El monto no es un número válido", codigo="monto_invalido")
    if importe <= 0:
        raise CajaError("El monto debe ser mayor a cero", codigo="monto_invalido")

    metodo = metodo_efectivo(tenant_id)
    gasto = GastoOperativo(
        tenant_id=tenant_id, fecha=fecha, concepto_nombre=concepto,
        tipo="variable", monto=importe, metodo_pago_id=metodo.id,
        sucursal_id=sucursal_id, created_by=usuario_id, sale_de_caja=True,
    )
    db.session.add(gasto)
    db.session.commit()
    return gasto


def listar_salidas(tenant_id, sucursal_id, fecha, *, enmascarar_para=None):
    """Salidas de caja del día.

    `enmascarar_para` es el id de la recepcionista: ve TODAS las salidas —si no,
    su lista no cuadraría con la tarjeta "Gastos del día", que las suma todas—
    pero el concepto de las que no registró ella se sustituye, porque podría ser
    sensible.
    """
    salidas = GastoOperativo.query.filter(
        GastoOperativo.tenant_id == tenant_id,
        GastoOperativo.fecha == fecha,
        GastoOperativo.sale_de_caja.is_(True),
        _filtro_sucursal(GastoOperativo.sucursal_id, sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
    ).order_by(GastoOperativo.id).all()

    filas = []
    for s in salidas:
        propia = enmascarar_para is None or s.created_by == enmascarar_para
        filas.append({
            "id": s.id,
            "concepto": s.concepto_nombre if propia else CONCEPTO_ENMASCARADO,
            "monto": round(float(s.monto or 0), 2),
            "propia": propia,
        })
    return filas


def eliminar_salida(tenant_id, gasto_id, *, solo_de_usuario=None):
    """Borra una salida. `solo_de_usuario` limita a las propias (recepción)."""
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=tenant_id, sale_de_caja=True,
    ).first()
    if gasto is None:
        raise CajaError("Salida no encontrada", codigo="no_encontrado")
    if solo_de_usuario is not None and gasto.created_by != solo_de_usuario:
        raise CajaError("Esa salida no es tuya", codigo="ajena")
    db.session.delete(gasto)
    db.session.commit()


def historico(tenant_id, desde, hasta, solo_sucursal=None):
    """Una fila por (fecha, sucursal) con movimientos en el rango.

    Incluye los días SIN cerrar, que son justamente la señal que el admin
    necesita. Usa dos agregados sobre todo el rango en vez de un resumen_dia
    por día: con un mes de rango, lo segundo serían decenas de consultas.

    OJO con `solo_sucursal`: aquí `None` significa "todas las sucursales", al
    revés que el `sucursal_id=None` de `resumen_dia`, que es el corte concreto
    "Sin sucursal". Por eso el parámetro se llama distinto — el admin quiere ver
    el mes completo de toda la clínica por default.
    """
    separa = sucursal_separa_cajas(tenant_id)
    filtro_suc_ing = (
        [] if solo_sucursal is None
        else [Ingreso.sucursal_id == solo_sucursal]
    )
    filtro_suc_gas = (
        [] if solo_sucursal is None
        else [GastoOperativo.sucursal_id == solo_sucursal]
    )

    # (fecha, sucursal, tipo) -> monto, comisión
    # OJO: se agrupa por la expresión completa de coalesce, no por el alias
    # "tipo" — SQLite no siempre resuelve un GROUP BY por el label.
    tipo_expr = func.coalesce(MetodoPago.tipo, "sin_clasificar")
    ingresos = db.session.query(
        Ingreso.fecha, Ingreso.sucursal_id,
        tipo_expr.label("tipo"),
        func.sum(Ingreso.monto), func.sum(Ingreso.comision_bancaria),
    ).outerjoin(MetodoPago, Ingreso.metodo_pago_id == MetodoPago.id).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.fecha >= desde, Ingreso.fecha <= hasta,
        *filtro_suc_ing,
    ).group_by(Ingreso.fecha, Ingreso.sucursal_id, tipo_expr).all()

    salidas = db.session.query(
        GastoOperativo.fecha, GastoOperativo.sucursal_id,
        func.sum(GastoOperativo.monto),
    ).filter(
        GastoOperativo.tenant_id == tenant_id,
        GastoOperativo.fecha >= desde, GastoOperativo.fecha <= hasta,
        GastoOperativo.sale_de_caja.is_(True),
        *filtro_suc_gas,
    ).group_by(GastoOperativo.fecha, GastoOperativo.sucursal_id).all()

    dias = {}

    def _dia(fecha, suc_id):
        # Con la sucursal colapsada, todo el día es UNA fila: agrupar por
        # (fecha, sucursal) partía un mismo día en dos —una "Sin sucursal" y
        # otra con ella— y el admin veía dos cajas donde solo hubo una.
        if not separa:
            suc_id = None
        clave = (fecha, suc_id)
        if clave not in dias:
            dias[clave] = {
                "fecha": fecha, "sucursal_id": suc_id,
                "total_efectivo": 0.0, "total_tarjeta": 0.0,
                "total_transferencia": 0.0, "total_otro": 0.0,
                "comision_tarjeta": 0.0, "salidas_efectivo": 0.0,
                "sin_clasificar_monto": 0.0,
            }
        return dias[clave]

    for fecha, suc_id, tipo, monto, comision in ingresos:
        d = _dia(fecha, suc_id)
        if tipo == "sin_clasificar":
            d["sin_clasificar_monto"] += float(monto or 0)
            continue
        llave = f"total_{tipo}" if tipo in TIPOS_METODO else "total_otro"
        d[llave] += float(monto or 0)
        if tipo == TIPO_TARJETA:
            d["comision_tarjeta"] += float(comision or 0)

    for fecha, suc_id, monto in salidas:
        _dia(fecha, suc_id)["salidas_efectivo"] += float(monto or 0)

    cortes = {
        (c.fecha, c.sucursal_id if separa else None): c
        for c in CorteCaja.query.filter(
            CorteCaja.tenant_id == tenant_id,
            CorteCaja.fecha >= desde, CorteCaja.fecha <= hasta,
        ).all()
        if solo_sucursal is None or c.sucursal_id == solo_sucursal
    }

    # Un corte cerrado sin movimientos ese día también es una fila del reporte:
    # un día flojo cerrado en cero tiene que poder distinguirse de un día que
    # nadie cerró, que es la señal más valiosa del histórico.
    for fecha_corte, suc_corte in cortes:
        _dia(fecha_corte, suc_corte)

    filas = []
    for clave, d in dias.items():
        for k in ("total_efectivo", "total_tarjeta", "total_transferencia",
                  "total_otro", "comision_tarjeta", "salidas_efectivo",
                  "sin_clasificar_monto"):
            d[k] = round(d[k], 2)

        vivo_esperado = round(d["total_efectivo"] - d["salidas_efectivo"], 2)
        corte = cortes.get(clave)

        if corte is None or not corte.cerrado:
            d.update({
                "corte_id": corte.id if corte else None,
                "estado": "sin_cerrar",
                "total_dia": round(
                    d["total_efectivo"] + d["total_tarjeta"]
                    + d["total_transferencia"] + d["total_otro"], 2),
                "esperado_efectivo": vivo_esperado,
                "efectivo_contado": None,
                "diferencia": None,
                "cerrado_por": None,
                "cerrado_at": None,
                "comentario": None,
                "movimientos_posteriores": False,
                "delta_efectivo": 0.0,
            })
        else:
            # La fila muestra la foto FIRMADA; el delta compara contra lo vivo.
            # OJO: la marca se calcula ANTES del update, que pisa los totales
            # vivos de `d` con los congelados y borraría la comparación.
            movidos = hay_movimientos_posteriores(corte, d)
            delta = round(vivo_esperado - corte.esperado_efectivo, 2)
            d.update({
                "corte_id": corte.id,
                "estado": "cerrado",
                "total_efectivo": corte.total_efectivo,
                "total_tarjeta": corte.total_tarjeta,
                "total_transferencia": corte.total_transferencia,
                "total_otro": corte.total_otro,
                "comision_tarjeta": corte.comision_tarjeta,
                "salidas_efectivo": corte.salidas_efectivo,
                "total_dia": corte.total_dia,
                "esperado_efectivo": corte.esperado_efectivo,
                "efectivo_contado": corte.efectivo_contado,
                "diferencia": corte.diferencia,
                "cerrado_por": corte.usuario.name if corte.usuario else None,
                "cerrado_at": corte.cerrado_at,
                "comentario": corte.comentario,
                "movimientos_posteriores": movidos,
                "delta_efectivo": delta,
            })
        filas.append(d)

    filas.sort(key=lambda f: (f["fecha"], f["sucursal_id"] or 0), reverse=True)
    return filas


def exigir_dia_abierto(tenant_id, sucursal_id, fecha, *, es_admin=False):
    """Frena la captura sobre un día ya cerrado.

    El admin sí pasa: puede corregir un día cerrado, y el histórico lo marca
    como "con movimientos posteriores" comparando la foto contra lo vivo.
    """
    if es_admin:
        return
    if corte_cerrado(tenant_id, sucursal_id, fecha):
        raise CajaError(
            f"La caja del {fecha.strftime('%d/%m/%Y')} ya fue cerrada. "
            "Pide al administrador que la reabra.",
            codigo="dia_cerrado",
        )
