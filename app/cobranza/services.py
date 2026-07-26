"""Capa de servicios de cobranza: TODAS las escrituras pasan por aquí.

Las rutas validan con Marshmallow y delegan; nunca tocan db.session.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.ajustes.models import Especialista, MetodoPago
from app.cobranza.calculo import (
    MAX_PARCIALIDADES,
    TOLERANCIA,
    PlanInvalido,
    calcular_plan,
)
from app.cobranza.models import (
    Cotizacion,
    CotizacionConcepto,
    Pago,
    PagoProgramado,
)
from app.crm.models import Paciente
from app.tratamientos.models import Tratamiento

VIGENCIA_DIAS_DEFAULT = 30


class CobranzaError(Exception):
    """Error de negocio; las routes lo devuelven como 400."""


class CobranzaNotFound(CobranzaError):
    """Recurso no encontrado; las routes lo devuelven como 404."""


def _hoy():
    from app.facturacion.timezone_helper import get_today
    return get_today()


def obtener_cotizacion(tenant_id, cotizacion_id):
    cot = Cotizacion.query.filter_by(id=cotizacion_id, tenant_id=tenant_id).first()
    if not cot:
        raise CobranzaNotFound("Cotización no encontrada")
    return cot


def siguiente_folio(tenant_id):
    """COT-{año}-{consecutivo} por tenant y por año."""
    anio = _hoy().year
    prefijo = f"COT-{anio}-"
    ultimo = Cotizacion.query.filter(
        Cotizacion.tenant_id == tenant_id,
        Cotizacion.folio.like(f"{prefijo}%"),
    ).order_by(Cotizacion.folio.desc()).first()
    consecutivo = 1
    if ultimo:
        try:
            consecutivo = int(ultimo.folio.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            consecutivo = Cotizacion.query.filter(
                Cotizacion.tenant_id == tenant_id,
                Cotizacion.folio.like(f"{prefijo}%"),
            ).count() + 1
    return f"{prefijo}{consecutivo:04d}"


def calcular_totales(conceptos, descuento_tipo, descuento_valor):
    """(subtotal, total) a partir de los renglones y el descuento."""
    subtotal = round(sum(
        (c.get("cantidad") or 1) * (c.get("precio_unitario") or 0) for c in conceptos
    ), 2)
    descuento = 0.0
    if descuento_tipo == "porcentaje":
        descuento = round(subtotal * (descuento_valor or 0) / 100, 2)
    elif descuento_tipo == "monto":
        descuento = round(descuento_valor or 0, 2)
    if descuento < 0:
        raise CobranzaError("El descuento no puede ser negativo")
    if descuento > subtotal + TOLERANCIA:
        raise CobranzaError("El descuento no puede ser mayor al subtotal")
    return subtotal, round(subtotal - descuento, 2)


def _validar_paciente(tenant_id, paciente_id):
    p = Paciente.query.filter_by(
        id=paciente_id, tenant_id=tenant_id, eliminado=False,
    ).first()
    if not p:
        raise CobranzaError("Paciente no encontrado")
    return p


def _validar_especialista(tenant_id, especialista_id):
    if especialista_id is None:
        return
    if not Especialista.query.filter_by(id=especialista_id, tenant_id=tenant_id).first():
        raise CobranzaError("Especialista no encontrado")


def _validar_sucursal(tenant_id, sucursal_id, *, activa=False):
    if sucursal_id is None:
        return None
    from app.facturacion.models import Sucursal
    q = Sucursal.query.filter_by(id=sucursal_id, tenant_id=tenant_id)
    if activa:
        q = q.filter_by(activa=True)
    sucursal = q.first()
    if not sucursal:
        raise CobranzaError("Sucursal no encontrada")
    return sucursal


def _sucursal_activa_default(tenant_id):
    from app.facturacion.models import Sucursal
    return Sucursal.query.filter_by(
        tenant_id=tenant_id, activa=True,
    ).order_by(Sucursal.id).first()


def _construir_conceptos(tenant_id, cotizacion, conceptos_data):
    """Crea los renglones. Un renglón de catálogo copia precio, tipo de servicio
    y comisión como snapshot; uno libre lleva lo que capturó el doctor.
    """
    if not conceptos_data:
        raise CobranzaError("La cotización necesita al menos un concepto")

    for orden, item in enumerate(conceptos_data):
        cantidad = item.get("cantidad") or 1
        precio = item.get("precio_unitario") or 0
        tratamiento = None
        if item.get("tratamiento_id"):
            tratamiento = Tratamiento.query.filter_by(
                id=item["tratamiento_id"], tenant_id=tenant_id,
            ).first()
            if not tratamiento:
                raise CobranzaError("Tratamiento no encontrado")

        descripcion = (item.get("descripcion") or "").strip()
        if not descripcion:
            descripcion = tratamiento.nombre if tratamiento else ""
        if not descripcion:
            raise CobranzaError("Cada concepto necesita una descripción")

        db.session.add(CotizacionConcepto(
            tenant_id=tenant_id,
            cotizacion_id=cotizacion.id,
            tratamiento_id=tratamiento.id if tratamiento else None,
            descripcion=descripcion[:300],
            cantidad=cantidad,
            precio_unitario=precio,
            importe=round(cantidad * precio, 2),
            tipo_servicio=(
                tratamiento.tipo_servicio if tratamiento
                else (item.get("tipo_servicio") or "clinico")
            ),
            comision_especialista_tipo=(
                tratamiento.comision_especialista_tipo if tratamiento
                else (item.get("comision_especialista_tipo") or "porcentaje")
            ),
            comision_especialista_valor=(
                tratamiento.comision_especialista_valor if tratamiento
                else (item.get("comision_especialista_valor") or 0)
            ),
            orden=orden,
        ))


def _aplicar_datos(tenant_id, cot, data):
    """Campos comunes entre crear y actualizar. No hace commit."""
    _validar_paciente(tenant_id, data["paciente_id"])
    _validar_especialista(tenant_id, data.get("especialista_id"))
    _validar_sucursal(tenant_id, data.get("sucursal_id"))

    subtotal, total = calcular_totales(
        data.get("conceptos") or [],
        data.get("descuento_tipo"),
        data.get("descuento_valor") or 0,
    )

    cot.paciente_id = data["paciente_id"]
    cot.especialista_id = data.get("especialista_id")
    cot.sucursal_id = data.get("sucursal_id")
    cot.valida_hasta = data.get("valida_hasta") or (
        _hoy() + timedelta(days=VIGENCIA_DIAS_DEFAULT)
    )
    cot.fecha_inicio_tratamiento = data.get("fecha_inicio_tratamiento")
    cot.descuento_tipo = data.get("descuento_tipo")
    cot.descuento_valor = data.get("descuento_valor") or 0
    cot.subtotal = subtotal
    cot.total = total
    cot.frecuencia = data.get("frecuencia") or "mensual"
    cot.num_parcialidades = data.get("num_parcialidades") or 1
    cot.monto_parcialidad = data.get("monto_parcialidad")
    cot.anticipo = data.get("anticipo") or 0
    cot.fecha_primer_pago = data.get("fecha_primer_pago")
    cot.requiere_factura = bool(data.get("requiere_factura"))
    cot.notas = data.get("notas")

    if cot.anticipo > cot.total + TOLERANCIA:
        raise CobranzaError("El anticipo no puede ser mayor al total")


def _calendario_como_dicts(cot):
    return [
        {
            "numero": p.numero,
            "fecha_vencimiento": p.fecha_vencimiento,
            "monto_programado": p.monto_programado,
        }
        for p in sorted(cot.programados, key=lambda p: p.numero)
    ]


def validar_calendario(cot, calendario):
    """Valida un calendario propuesto/editado antes de persistir o aprobar.

    El doctor puede cambiar fechas y montos, pero no crear huecos, duplicar
    números ni cambiar el total económico de la cotización.
    """
    if not calendario:
        raise CobranzaError("El calendario necesita al menos un pago")
    if len(calendario) > MAX_PARCIALIDADES + 1:
        raise CobranzaError(
            f"El calendario admite como máximo {MAX_PARCIALIDADES} parcialidades"
        )

    normalizado = []
    for item in calendario:
        try:
            numero = int(item["numero"])
            fecha = item["fecha_vencimiento"]
            monto = round(float(
                item.get("monto_programado", item.get("monto", 0))
            ), 2)
        except (KeyError, TypeError, ValueError):
            raise CobranzaError("El calendario contiene un pago inválido")
        if numero < 0:
            raise CobranzaError("El número de pago no puede ser negativo")
        if not fecha:
            raise CobranzaError("Cada pago del calendario necesita una fecha")
        if monto <= 0:
            raise CobranzaError("Cada pago del calendario debe ser mayor a cero")
        normalizado.append({
            "numero": numero,
            "fecha_vencimiento": fecha,
            "monto_programado": monto,
        })

    normalizado.sort(key=lambda item: item["numero"])
    numeros = [item["numero"] for item in normalizado]
    if len(numeros) != len(set(numeros)):
        raise CobranzaError("El calendario contiene números de pago repetidos")

    tiene_anticipo = cot.anticipo > TOLERANCIA
    parciales = [n for n in numeros if n >= 1]
    esperados = list(range(1, len(parciales) + 1))
    if parciales != esperados:
        raise CobranzaError("Las parcialidades deben numerarse consecutivamente desde 1")
    if tiene_anticipo != (0 in numeros):
        raise CobranzaError(
            "El calendario debe incluir el anticipo indicado en la cotización"
            if tiene_anticipo else
            "El calendario no debe incluir anticipo cuando su monto es cero"
        )
    if tiene_anticipo:
        fila_anticipo = next(item for item in normalizado if item["numero"] == 0)
        if abs(fila_anticipo["monto_programado"] - cot.anticipo) > TOLERANCIA:
            raise CobranzaError(
                "El monto del anticipo en el calendario no coincide con la cotización"
            )
    if not parciales and cot.total - cot.anticipo > TOLERANCIA:
        raise CobranzaError("El calendario necesita al menos una parcialidad")

    total_calendario = round(
        sum(item["monto_programado"] for item in normalizado), 2,
    )
    if abs(total_calendario - cot.total) > TOLERANCIA:
        raise CobranzaError(
            f"El calendario suma ${total_calendario:,.2f} y debe sumar "
            f"${cot.total:,.2f}"
        )
    return normalizado


def reemplazar_calendario(cot, calendario):
    """Sustituye el calendario propuesto. No hace commit."""
    normalizado = validar_calendario(cot, calendario)
    for programado in list(cot.programados):
        db.session.delete(programado)
    db.session.flush()
    for item in normalizado:
        db.session.add(PagoProgramado(
            tenant_id=cot.tenant_id,
            cotizacion_id=cot.id,
            numero=item["numero"],
            fecha_vencimiento=item["fecha_vencimiento"],
            monto_programado=item["monto_programado"],
        ))
    cot.num_parcialidades = sum(
        1 for item in normalizado if item["numero"] >= 1
    )
    db.session.flush()
    return normalizado


def _es_conflicto_folio(error):
    detalle = str(getattr(error, "orig", error)).lower()
    return (
        "uq_cotizacion_tenant_folio" in detalle
        or (
            "cotizaciones.tenant_id" in detalle
            and "cotizaciones.folio" in detalle
        )
    )


def _crear_cotizacion_intento(tenant_id, user_id, data):
    cot = Cotizacion(
        tenant_id=tenant_id,
        folio=siguiente_folio(tenant_id),
        fecha=_hoy(),
        estatus="borrador",
        created_by=user_id,
        # _aplicar_datos los sobreescribe; se ponen para satisfacer NOT NULL
        # antes del flush que necesitamos para tener cot.id.
        paciente_id=data["paciente_id"],
        valida_hasta=data.get("valida_hasta") or (
            _hoy() + timedelta(days=VIGENCIA_DIAS_DEFAULT)
        ),
    )
    _aplicar_datos(tenant_id, cot, data)
    db.session.add(cot)
    db.session.flush()
    _construir_conceptos(tenant_id, cot, data.get("conceptos") or [])
    db.session.flush()
    if data.get("calendario") is not None:
        reemplazar_calendario(cot, data["calendario"])
    db.session.commit()
    return cot


def crear_cotizacion(tenant_id, user_id, data):
    # MAX(folio)+1 está protegido por la restricción única. Si dos solicitudes
    # compiten, la perdedora recalcula el consecutivo en una transacción limpia.
    for intento in range(3):
        try:
            return _crear_cotizacion_intento(tenant_id, user_id, data)
        except IntegrityError as error:
            db.session.rollback()
            if not _es_conflicto_folio(error) or intento == 2:
                raise
        except Exception:
            db.session.rollback()
            raise
    raise CobranzaError("No se pudo asignar un folio a la cotización")


def actualizar_cotizacion(tenant_id, cotizacion_id, data):
    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    if cot.estatus not in ("borrador", "enviada"):
        raise CobranzaError(
            "Sólo se puede editar una cotización en borrador o enviada"
        )
    try:
        _aplicar_datos(tenant_id, cot, data)
        for concepto in list(cot.conceptos):
            db.session.delete(concepto)
        db.session.flush()
        _construir_conceptos(tenant_id, cot, data.get("conceptos") or [])
        db.session.flush()
        if data.get("calendario") is not None:
            reemplazar_calendario(cot, data["calendario"])
        else:
            # Un PUT reemplaza toda la propuesta. No conservamos un calendario
            # viejo si cambiaron total, anticipo o frecuencia.
            for programado in list(cot.programados):
                db.session.delete(programado)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    db.session.refresh(cot)
    return cot


def eliminar_cotizacion(tenant_id, cotizacion_id):
    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    if cot.estatus != "borrador":
        raise CobranzaError("Sólo se puede eliminar una cotización en borrador")
    db.session.delete(cot)
    db.session.commit()


def comision_doctor_total(cot):
    """Comisión del especialista sobre la cotización completa.

    El descuento se prorratea entre los conceptos antes de aplicar el
    porcentaje; las comisiones de monto fijo se multiplican por la cantidad.
    """
    suma_conceptos = round(sum(c.importe for c in cot.conceptos), 2)
    factor = (cot.total / suma_conceptos) if suma_conceptos else 0

    comision = 0.0
    for c in cot.conceptos:
        valor = c.comision_especialista_valor or 0
        if c.comision_especialista_tipo == "porcentaje":
            comision += c.importe * factor * valor / 100
        else:
            comision += valor * (c.cantidad or 1)
    return round(comision, 2)


def esta_vencida(cot, hoy=None):
    """Una cotización sin aprobar cuya vigencia ya pasó. Derivado, no almacenado."""
    if cot.estatus not in ("borrador", "enviada"):
        return False
    return bool(cot.valida_hasta and cot.valida_hasta < (hoy or _hoy()))


def aprobar_cotizacion(tenant_id, user_id, cotizacion_id, sucursal_id=None):
    """Congela la comisión y genera el calendario. A partir de aquí no se edita."""
    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    if cot.estatus not in ("borrador", "enviada"):
        raise CobranzaError("Sólo se puede aprobar una cotización en borrador o enviada")
    if not cot.conceptos:
        raise CobranzaError("La cotización necesita al menos un concepto")
    if not cot.fecha_primer_pago:
        raise CobranzaError("Captura la fecha del primer pago antes de aprobar")

    if sucursal_id is not None:
        _validar_sucursal(tenant_id, sucursal_id, activa=True)
        cot.sucursal_id = sucursal_id
    elif cot.sucursal_id is not None:
        _validar_sucursal(tenant_id, cot.sucursal_id, activa=True)
    else:
        sucursal_default = _sucursal_activa_default(tenant_id)
        if sucursal_default:
            cot.sucursal_id = sucursal_default.id

    hoy = _hoy()
    if not cot.fecha_inicio_tratamiento:
        cot.fecha_inicio_tratamiento = hoy

    if cot.programados:
        filas = validar_calendario(cot, _calendario_como_dicts(cot))
    else:
        try:
            calculadas = calcular_plan(
                total=cot.total,
                anticipo=cot.anticipo,
                frecuencia=cot.frecuencia,
                fecha_primer_pago=cot.fecha_primer_pago,
                # El vencimiento del anticipo nuevo es la fecha de aprobación.
                # Los pagos históricos conservan su propia fecha real.
                fecha_anticipo=hoy,
                num_parcialidades=(
                    cot.num_parcialidades if cot.monto_parcialidad is None else None
                ),
                monto_parcialidad=cot.monto_parcialidad,
            )
            filas = [
                {
                    "numero": fila["numero"],
                    "fecha_vencimiento": fila["fecha_vencimiento"],
                    "monto_programado": fila["monto"],
                }
                for fila in calculadas
            ]
            filas = validar_calendario(cot, filas)
        except PlanInvalido as e:
            raise CobranzaError(str(e))

    try:
        if not cot.programados:
            reemplazar_calendario(cot, filas)
        else:
            for programado in cot.programados:
                programado.monto_pagado = 0
                programado.estatus = "pendiente"

        # El número de parcialidades queda fijo aunque se haya capturado por monto.
        cot.num_parcialidades = sum(1 for f in filas if f["numero"] >= 1)
        cot.comision_doctor_total = comision_doctor_total(cot)
        cot.estatus = "aprobada"
        cot.aprobada_por = user_id
        cot.aprobada_at = datetime.now(timezone.utc)

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    db.session.refresh(cot)
    return cot


def rechazar_cotizacion(tenant_id, cotizacion_id):
    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    if cot.estatus not in ("borrador", "enviada"):
        raise CobranzaError("Sólo se puede rechazar una cotización sin aprobar")
    cot.estatus = "rechazada"
    db.session.commit()
    return cot


def marcar_cotizacion_enviada(tenant_id, cotizacion_id):
    """Registra el envío sin permitir revivir una cotización cerrada."""
    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    if cot.estatus not in ("borrador", "enviada"):
        raise CobranzaError(
            "Sólo se puede enviar una cotización en borrador o ya enviada"
        )
    if cot.estatus == "borrador":
        cot.estatus = "enviada"
        db.session.commit()
    return cot


def cancelar_cotizacion(tenant_id, cotizacion_id):
    """Cierra el plan. Los abonos ya cobrados y sus ingresos quedan intactos:
    ese dinero entró de verdad.
    """
    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    if cot.estatus != "aprobada":
        raise CobranzaError("Sólo se puede cancelar un plan aprobado y abierto")
    for prog in cot.programados:
        if prog.estatus != "pagado":
            prog.estatus = "cancelado"
    cot.estatus = "cancelada"
    db.session.commit()
    return cot


# ── Pagos y cascada ──────────────────────────────────────────────────────────

def total_pagado(cot):
    return round(sum(p.monto for p in cot.pagos), 2)


def saldo(cot):
    return round(cot.total - total_pagado(cot), 2)


def parcialidades_pagadas(cot):
    """Cuántas parcialidades están cubiertas; el anticipo no cuenta."""
    return sum(
        1 for p in cot.programados
        if p.numero >= 1 and p.estatus == "pagado"
    )


def _cotizacion_para_pago(tenant_id, cotizacion_id):
    """Carga y bloquea el plan mientras se recalcula su saldo.

    SQLite ignora FOR UPDATE en tests; las bases de producción serializan dos
    cobros concurrentes y evitan que ambos gasten el mismo saldo.
    """
    cot = Cotizacion.query.filter_by(
        id=cotizacion_id, tenant_id=tenant_id,
    ).with_for_update().first()
    if not cot:
        raise CobranzaNotFound("Cotización no encontrada")
    return cot


def _validar_metodo_pago(tenant_id, metodo_pago_id):
    if metodo_pago_id is None:
        return None
    metodo = MetodoPago.query.filter_by(
        id=metodo_pago_id, tenant_id=tenant_id,
    ).first()
    if not metodo:
        raise CobranzaError("Método de pago no encontrado")
    return metodo


def _recalcular_cascada(cot):
    """Reparte todos los pagos del plan sobre el calendario. Idempotente."""
    from app.cobranza.calculo import aplicar_cascada, Sobrepago

    programados = sorted(cot.programados, key=lambda p: p.numero)
    pagos = sorted(cot.pagos, key=lambda p: (p.fecha, p.id or 0))
    try:
        return aplicar_cascada(programados, pagos)
    except Sobrepago as error:
        raise CobranzaError(str(error))


def _etiqueta_abono(cot, pago, asignaciones):
    """Etiqueta legible del abono en el EDR.

    Un mismo abono puede cubrir el anticipo y una o varias parcialidades; la
    etiqueta lo dice todo en vez de quedarse sólo con el anticipo.
    """
    numeros = [
        programado.numero
        for pago_asignado, programado, _monto in asignaciones
        if pago_asignado is pago
    ]
    parciales = [numero for numero in numeros if numero >= 1]
    if not parciales:
        return f"{cot.folio} · Anticipo"

    primero = min(parciales)
    ultimo = max(parciales)
    if primero == ultimo:
        detalle = f"Abono {primero}/{cot.num_parcialidades}"
    else:
        detalle = f"Abono {primero}–{ultimo}/{cot.num_parcialidades}"
    if 0 in numeros:
        detalle = f"Anticipo + {detalle}"
    return f"{cot.folio} · {detalle}"


def _comision_doctor_del_pago(cot, pago):
    """Prorrateo acumulado que absorbe centavos sin exceder la comisión total."""
    if not cot.total:
        return 0.0
    pagos_normales = [p for p in cot.pagos if not p.historico]
    monto_acumulado = round(sum(p.monto for p in pagos_normales), 2)
    objetivo_acumulado = round(
        (cot.comision_doctor_total or 0) * (monto_acumulado / cot.total), 2,
    )
    ya_generada = round(sum(
        (p.ingreso.comision_doctor or 0)
        for p in pagos_normales
        if p is not pago and p.ingreso is not None
    ), 2)
    return max(0.0, round(objetivo_acumulado - ya_generada, 2))


def _crear_ingreso(cot, pago, asignaciones, metodo):
    """Registra el abono en el EDR dentro de la transacción del pago."""
    from app.crm.services import sincronizar_visita_ingreso
    from app.edr.models import Ingreso

    comision_bancaria = round(
        pago.monto * ((metodo.comision_pct or 0) if metodo else 0) / 100, 2,
    )
    principal = max(cot.conceptos, key=lambda c: c.importe, default=None)

    ingreso = Ingreso(
        tenant_id=cot.tenant_id,
        fecha=pago.fecha,
        tratamiento_id=None,
        nombre_tratamiento=_etiqueta_abono(cot, pago, asignaciones),
        paciente=cot.paciente.nombre if cot.paciente else "Paciente",
        paciente_id=cot.paciente_id,
        especialista_id=cot.especialista_id,
        metodo_pago_id=pago.metodo_pago_id,
        monto=pago.monto,
        comision_bancaria=comision_bancaria,
        comision_doctor=_comision_doctor_del_pago(cot, pago),
        tipo_servicio=principal.tipo_servicio if principal else "clinico",
        # Todavía no se factura: el ingreso nace sin factura y `agrupar_en_ticket`
        # lo marca al agruparlo. OJO: `factura` NO es el candado del plan (ése lo
        # aplica `ingreso_bloqueado_para_factura`), es la llave del cálculo de
        # IVA en app/facturacion/iva.py.
        factura=False,
        comentarios=f"Plan de pagos {cot.folio}",
    )
    db.session.add(ingreso)
    db.session.flush()
    sincronizar_visita_ingreso(ingreso)
    return ingreso


def _marcar_liquidada(cot):
    """Cierra el saldo; ticket y correo se procesan después del commit."""
    cot.estatus = "liquidada"
    cot.facturacion_error = None
    cot.facturacion_actualizada_at = datetime.now(timezone.utc)
    cot.facturacion_estado = (
        "pendiente" if cot.requiere_factura else "no_requerida"
    )


def registrar_pago(tenant_id, user_id, cotizacion_id, data):
    """Registra un abono de forma atómica e idempotente.

    El pago, la cascada y el Ingreso se confirman primero. Si liquida el plan,
    ticket y correo se intentan después; sus fallos nunca revierten dinero.
    """
    clave = (data.get("idempotency_key") or "").strip() or None
    if clave and len(clave) > 64:
        raise CobranzaError("La clave de idempotencia es demasiado larga")

    try:
        cot = _cotizacion_para_pago(tenant_id, cotizacion_id)
        if clave:
            existente = Pago.query.filter_by(
                tenant_id=tenant_id,
                cotizacion_id=cotizacion_id,
                idempotency_key=clave,
            ).first()
            if existente:
                # Cierra la transacción antes de salir: `_cotizacion_para_pago`
                # dejó un SELECT ... FOR UPDATE que en MySQL sostendría el lock
                # de la fila hasta el teardown del request.
                db.session.rollback()
                existente._idempotent_replay = True
                return existente

        if cot.estatus != "aprobada":
            raise CobranzaError(
                "Sólo se pueden registrar pagos en una cotización aprobada"
            )

        monto = round(float(data.get("monto") or 0), 2)
        if monto <= 0:
            raise CobranzaError("El monto del pago debe ser mayor a cero")
        metodo = _validar_metodo_pago(tenant_id, data.get("metodo_pago_id"))

        # Se asocia por la relación, no por la FK: un flush no agrega la fila a
        # una colección `cot.pagos` que ya estuviera materializada, y todo lo que
        # sigue (cascada, comisión, saldo) lee de ahí.
        pago = Pago(
            tenant_id=tenant_id,
            cotizacion=cot,
            fecha=data["fecha"],
            monto=monto,
            metodo_pago_id=metodo.id if metodo else None,
            historico=bool(data.get("historico")),
            idempotency_key=clave,
            notas=data.get("notas"),
            created_by=user_id,
        )
        db.session.add(pago)
        db.session.flush()

        asignaciones = _recalcular_cascada(cot)
        if not pago.historico:
            pago.ingreso = _crear_ingreso(cot, pago, asignaciones, metodo)
        if saldo(cot) <= TOLERANCIA:
            _marcar_liquidada(cot)
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        # Dos reintentos idénticos pueden competir antes de ver la fila del otro.
        if clave:
            existente = Pago.query.filter_by(
                tenant_id=tenant_id,
                cotizacion_id=cotizacion_id,
                idempotency_key=clave,
            ).first()
            if existente:
                existente._idempotent_replay = True
                return existente
        raise error
    except Exception:
        db.session.rollback()
        raise

    pago._idempotent_replay = False
    if cot.estatus == "liquidada" and cot.requiere_factura:
        # Esta función captura y persiste sus propios errores.
        procesar_facturacion_liquidacion(tenant_id, cot.id)
        db.session.refresh(pago)
    return pago


def eliminar_pago(tenant_id, pago_id):
    """Borra un abono no liquidado, su Ingreso y recalcula el calendario."""
    from app.crm.services import eliminar_visita_ingreso
    from app.edr.models import Ingreso, PagoComisionIngreso

    try:
        pago = Pago.query.filter_by(
            id=pago_id, tenant_id=tenant_id,
        ).with_for_update().first()
        if not pago:
            raise CobranzaNotFound("Pago no encontrado")
        cot = _cotizacion_para_pago(tenant_id, pago.cotizacion_id)
        if cot.estatus == "liquidada":
            raise CobranzaError(
                "No se puede eliminar un pago de un plan liquidado"
            )

        ingreso = db.session.get(Ingreso, pago.ingreso_id) if pago.ingreso_id else None
        if ingreso is not None and ingreso.ticket_id:
            raise CobranzaError("Ese abono ya está en un ticket de facturación")
        if ingreso is not None and PagoComisionIngreso.query.filter_by(
            tenant_id=tenant_id, ingreso_id=ingreso.id,
        ).first():
            raise CobranzaError(
                "La comisión de ese abono ya fue pagada; revierte primero "
                "el pago al doctor"
            )

        db.session.delete(pago)
        if ingreso is not None:
            eliminar_visita_ingreso(tenant_id, ingreso.id)
            db.session.delete(ingreso)
        db.session.flush()
        db.session.refresh(cot)
        _recalcular_cascada(cot)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


# ── Facturación posterior a la liquidación ───────────────────────────────────

def ingreso_bloqueado_para_factura(ingreso):
    """Mensaje de bloqueo para un abono cuyo plan todavía está abierto."""
    pago = getattr(ingreso, "cobranza_pago", None)
    if pago is None:
        return None
    if pago.cotizacion.estatus in ("liquidada", "cancelada"):
        return None
    return (
        "Este abono pertenece a un plan de pagos que aún no está liquidado. "
        "Podrás facturarlo cuando el tratamiento esté pagado por completo."
    )


def ingreso_bloqueado_para_edicion(ingreso):
    """Mensaje de bloqueo si el ingreso es el abono de un plan de pagos.

    El monto vive en `Pago` y la comisión se prorratea sobre el plan completo:
    editar o borrar el `Ingreso` por su cuenta los deja descuadrados y le pagaría
    al doctor una comisión inventada. El EDR consulta esta regla; el alta, la
    edición y la baja de un abono pasan siempre por cobranza.
    """
    pago = getattr(ingreso, "cobranza_pago", None)
    if pago is None:
        return None
    return (
        f"Este ingreso es el abono de un plan de pagos ({pago.cotizacion.folio}). "
        "Modifícalo o elimínalo desde la cotización, en Cobranza."
    )


def agrupar_en_ticket(cot):
    """Crea o reutiliza un único ticket para los ingresos no históricos.

    Es idempotente: reintentar devuelve el ticket existente y sólo adjunta los
    ingresos que falten.
    """
    from app.edr.models import Ingreso
    from app.facturacion.models import TICKET_SIN_TIMBRAR, Ticket
    from app.facturacion.services import asignar_ticket

    # Un plan cancelado también se factura: sus abonos son dinero que el paciente
    # pagó de verdad y tiene derecho a su comprobante.
    if cot.estatus not in ("liquidada", "cancelada"):
        raise CobranzaError(
            "El plan debe estar liquidado o cancelado antes de crear el ticket"
        )
    sucursal = _validar_sucursal(cot.tenant_id, cot.sucursal_id, activa=True)
    if not sucursal:
        raise CobranzaError("Selecciona una sucursal activa para poder facturar")

    ingresos = [
        db.session.get(Ingreso, pago.ingreso_id)
        for pago in sorted(cot.pagos, key=lambda p: (p.fecha, p.id or 0))
        if pago.ingreso_id
    ]
    ingresos = [
        ingreso for ingreso in ingresos
        if ingreso is not None and ingreso.tenant_id == cot.tenant_id
    ]
    if not ingresos:
        return None

    ticket_ids = {ingreso.ticket_id for ingreso in ingresos if ingreso.ticket_id}
    if len(ticket_ids) > 1:
        raise CobranzaError(
            "Los abonos del plan están repartidos entre varios tickets; "
            "requieren revisión administrativa"
        )

    # Agrupar en un ticket ES facturar, así que los ingresos se marcan antes de
    # asignarlos: `recalcular_total` (dentro de `asignar_ticket`) lee `factura`
    # para decidir si el concepto grava IVA, y con el flag apagado el CFDI se
    # timbraría en ceros.
    for ingreso in ingresos:
        ingreso.factura = True
    db.session.flush()

    ticket = None
    if ticket_ids:
        ticket = Ticket.query.filter_by(
            id=next(iter(ticket_ids)),
            tenant_id=cot.tenant_id,
            sucursal_id=cot.sucursal_id,
        ).first()
        if not ticket:
            raise CobranzaError("El ticket existente no pertenece a esta cotización")
        faltantes = [ingreso for ingreso in ingresos if not ingreso.ticket_id]
        if faltantes and ticket.estado != TICKET_SIN_TIMBRAR:
            raise CobranzaError(
                "El ticket ya fue timbrado y no admite abonos faltantes"
            )
    else:
        ticket = asignar_ticket(ingresos[0], cot.sucursal_id)
        faltantes = ingresos[1:]

    for ingreso in faltantes:
        asignar_ticket(
            ingreso, cot.sucursal_id, ticket_folio=ticket.folio,
        )
    return ticket


def _aviso_abonos_historicos(cot):
    """Mensaje si el ticket no cubre todo lo cobrado por haber pagos históricos.

    Un pago histórico se capturó como ya cobrado antes de adoptar el módulo, así
    que no generó `Ingreso` y no puede entrar al ticket. Facturar sólo una parte
    de lo cobrado no es un éxito limpio: el paciente recibe el link y se
    encuentra con menos de lo que pagó.
    """
    cubierto = round(sum(p.monto for p in cot.pagos if p.ingreso_id), 2)
    cobrado = total_pagado(cot)
    faltante = round(cobrado - cubierto, 2)
    if faltante <= TOLERANCIA:
        return None
    return (
        f"Sólo se facturaron los abonos registrados en el sistema: "
        f"${cubierto:,.2f} de ${cobrado:,.2f} cobrados. Los ${faltante:,.2f} "
        "restantes son pagos históricos, capturados como ya cobrados antes de "
        "usar el módulo de cobranza, y no generan un ingreso facturable."
    )


def _guardar_estado_facturacion(cot, estado, error=None):
    cot.facturacion_estado = estado
    cot.facturacion_error = str(error)[:2000] if error else None
    cot.facturacion_actualizada_at = datetime.now(timezone.utc)
    db.session.commit()


def procesar_facturacion_liquidacion(tenant_id, cotizacion_id):
    """Intenta ticket y correo sin poner en riesgo el pago ya confirmado."""
    from flask import current_app

    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    # Un plan cancelado ya no cobrará más, pero lo cobrado sí se factura.
    if cot.estatus not in ("liquidada", "cancelada"):
        raise CobranzaError("El plan todavía no está liquidado")
    if not cot.requiere_factura:
        _guardar_estado_facturacion(cot, "no_requerida")
        return {"estado": cot.facturacion_estado, "ticket_id": None}

    # Si ya se cerró, un retry es una lectura idempotente.
    if cot.facturacion_estado in ("completada", "parcial_historicos"):
        ticket_ids = {
            pago.ingreso.ticket_id
            for pago in cot.pagos
            if pago.ingreso is not None and pago.ingreso.ticket_id
        }
        resultado = {
            "estado": cot.facturacion_estado,
            "ticket_id": next(iter(ticket_ids), None),
        }
        if cot.facturacion_error:
            resultado["error"] = cot.facturacion_error
        return resultado

    try:
        ticket = agrupar_en_ticket(cot)
        if ticket is None:
            _guardar_estado_facturacion(
                cot,
                "sin_ingresos",
                "El plan sólo contiene pagos históricos; no hay ingresos "
                "nuevos que agrupar en un ticket.",
            )
            return {
                "estado": cot.facturacion_estado,
                "error": cot.facturacion_error,
                "ticket_id": None,
            }
        _guardar_estado_facturacion(cot, "ticket_creado")
    except Exception as error:
        db.session.rollback()
        cot = obtener_cotizacion(tenant_id, cotizacion_id)
        _guardar_estado_facturacion(cot, "error_ticket", error)
        current_app.logger.exception(
            "No se pudo crear el ticket del plan %s", cot.folio,
        )
        return {
            "estado": cot.facturacion_estado,
            "error": cot.facturacion_error,
            "ticket_id": None,
        }

    # El ticket ya está confirmado. SMTP ocurre fuera de esa transacción.
    try:
        from app.cobranza.correo import enviar_link_facturacion
        enviado = enviar_link_facturacion(cot, ticket)
        if not enviado:
            raise CobranzaError("SMTP no está configurado")
    except Exception as error:
        db.session.rollback()
        cot = obtener_cotizacion(tenant_id, cotizacion_id)
        _guardar_estado_facturacion(cot, "error_correo", error)
        current_app.logger.exception(
            "No se pudo avisar la liquidación del plan %s", cot.folio,
        )
        return {
            "estado": cot.facturacion_estado,
            "error": cot.facturacion_error,
            "ticket_id": ticket.id,
        }

    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    # El correo salió, pero si el ticket dejó fuera abonos históricos el paciente
    # sólo podrá facturar una parte: se distingue del éxito limpio.
    aviso = _aviso_abonos_historicos(cot)
    if aviso:
        _guardar_estado_facturacion(cot, "parcial_historicos", aviso)
        return {
            "estado": cot.facturacion_estado,
            "error": cot.facturacion_error,
            "ticket_id": ticket.id,
        }
    _guardar_estado_facturacion(cot, "completada")
    return {"estado": "completada", "ticket_id": ticket.id}


# ── Estado de cuenta y tablero ────────────────────────────────────────────────

def _abonos_por_bloque(cot):
    asignaciones = _recalcular_cascada(cot)
    reparto = {}
    for pago, programado, monto in asignaciones:
        acumulado = reparto.setdefault(
            pago.id, {"anticipo": 0.0, "parcialidades": 0.0},
        )
        clave = "anticipo" if programado.numero == 0 else "parcialidades"
        acumulado[clave] += monto

    anticipo, parcialidades = [], []
    for pago in sorted(cot.pagos, key=lambda p: (p.fecha, p.id or 0)):
        acumulado = reparto.get(
            pago.id, {"anticipo": 0.0, "parcialidades": 0.0},
        )
        fila = {
            "fecha": pago.fecha,
            "monto": pago.monto,
            "metodo": pago.metodo_pago.nombre if pago.metodo_pago else None,
            "historico": pago.historico,
        }
        if acumulado["anticipo"] >= acumulado["parcialidades"]:
            anticipo.append(fila)
        else:
            parcialidades.append(fila)
    return anticipo, parcialidades


def datos_estado_cuenta(tenant_id, cotizacion_id):
    from app.cobranza.estado_cuenta import construir_texto

    cot = obtener_cotizacion(tenant_id, cotizacion_id)
    abonos_anticipo, abonos_parcialidades = _abonos_por_bloque(cot)
    pagado = total_pagado(cot)
    pendiente = saldo(cot)
    fecha_inicio = cot.fecha_inicio_tratamiento or cot.fecha
    pagadas = parcialidades_pagadas(cot)
    texto = construir_texto(
        paciente=cot.paciente.nombre if cot.paciente else "su paciente",
        fecha_inicio=fecha_inicio,
        total=cot.total,
        anticipo=cot.anticipo,
        frecuencia=cot.frecuencia,
        num_parcialidades=cot.num_parcialidades,
        parcialidades_pagadas=pagadas,
        abonos_anticipo=abonos_anticipo,
        abonos_parcialidades=abonos_parcialidades,
        pagado=pagado,
        saldo=pendiente,
    )
    return {
        "texto": texto,
        "folio": cot.folio,
        "paciente": cot.paciente.nombre if cot.paciente else "",
        "fecha_inicio": fecha_inicio,
        "total": cot.total,
        "anticipo": cot.anticipo,
        "pagado": pagado,
        "saldo": pendiente,
        "frecuencia": cot.frecuencia,
        "num_parcialidades": cot.num_parcialidades,
        "parcialidades_pagadas": pagadas,
        "abonos_anticipo": abonos_anticipo,
        "abonos_parcialidades": abonos_parcialidades,
    }


def ultima_fecha_pago(cot):
    return max((p.fecha for p in cot.pagos), default=None)


def sin_pagos_recientes(cot, hoy=None):
    from app.cobranza.calculo import DIAS_ALERTA_SIN_PAGO, dias_sin_pago

    if cot.estatus != "aprobada" or saldo(cot) <= TOLERANCIA:
        return False
    referencia = (
        ultima_fecha_pago(cot)
        or cot.fecha_inicio_tratamiento
        or cot.fecha
    )
    dias = dias_sin_pago(referencia, hoy or _hoy())
    return dias is not None and dias > DIAS_ALERTA_SIN_PAGO


def resumen_cobranza(tenant_id):
    hoy = _hoy()
    activas = Cotizacion.query.filter_by(
        tenant_id=tenant_id, estatus="aprobada",
    ).all()
    por_cobrar = 0.0
    alertadas = 0
    saldo_alertado = 0.0
    for cot in activas:
        pendiente = saldo(cot)
        por_cobrar += pendiente
        if sin_pagos_recientes(cot, hoy=hoy):
            alertadas += 1
            saldo_alertado += pendiente

    inicio_mes = hoy.replace(day=1)
    cobrado_mes = round(sum(
        pago.monto
        for pago in Pago.query.filter(
            Pago.tenant_id == tenant_id,
            Pago.fecha >= inicio_mes,
            Pago.fecha <= hoy,
            Pago.historico.is_(False),
        ).all()
    ), 2)
    return {
        "por_cobrar": round(por_cobrar, 2),
        "sin_pagos_recientes": alertadas,
        "saldo_sin_pagos_recientes": round(saldo_alertado, 2),
        "cobrado_mes": cobrado_mes,
        "planes_activos": len(activas),
    }
