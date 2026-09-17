"""Reglas de las comisiones de los doctores: qué está pendiente y cómo se liquida.

Vive fuera de `routes.py` porque ahora las liquidan dos puertas —el admin desde
/pagos-doctores y recepción desde /corte-caja— y las dos tienen que aplicar
exactamente las mismas reglas: neto por devoluciones, descuento del saldo
negativo del doctor, y que nada se pague dos veces.
"""
from sqlalchemy.orm import joinedload, selectinload

from app.ajustes.models import Especialista
from app.configuracion.models import ConfigConsultorio
from app.edr.models import Ingreso, PagoComisionIngreso, PagoDoctor
from app.extensions import db


class ComisionError(Exception):
    """Error de negocio al liquidar. Quien llama lo traduce a su HTTP."""

    def __init__(self, mensaje, codigo):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def ingresos_liquidados_ids(tenant_id):
    """Set de ingreso_id que ya tienen su comisión liquidada (tenant)."""
    filas = PagoComisionIngreso.query.filter_by(tenant_id=tenant_id).all()
    return {f.ingreso_id for f in filas}


def reversiones_no_pagadas_por_ingreso(tenant_id, *, bloquear=False):
    """{ingreso_id: comisión revertida NO pagada} (para restar de pendientes).

    `bloquear=True` hace la lectura con `SELECT ... FOR UPDATE` (ver
    `saldo_negativo_por_doctor` para el porqué).
    """
    from app.cobranza.models import ComisionReversion
    out = {}
    q = ComisionReversion.query.filter_by(
        tenant_id=tenant_id, pagada_al_revertir=False,
    )
    if bloquear:
        q = q.with_for_update()
    for r in q.all():
        out[r.ingreso_id] = round(out.get(r.ingreso_id, 0) + r.monto, 2)
    return out


def saldo_negativo_por_doctor(tenant_id, *, bloquear=False):
    """{especialista_id: saldo negativo} = reversiones ya pagadas − descuentos
    ya aplicados en PagoDoctor. Solo positivos (lo que el doctor aún debe).

    `bloquear=True` usa `SELECT ... FOR UPDATE` en vez de una lectura normal.
    En MySQL/InnoDB con REPEATABLE READ (el nivel por defecto, y el que usa
    producción) una lectura normal ve la foto de la transacción tomada en su
    primer SELECT —anterior al `with_for_update()` de `ConfigConsultorio` en
    `liquidar`— así que dos liquidaciones concurrentes del mismo doctor
    podrían no ver el descuento que la otra ya aplicó. `FOR UPDATE` en
    InnoDB siempre lee el último dato comprometido, así que tras tomar el
    candado de `ConfigConsultorio` esta lectura ya ve los cambios de quien
    liquidó justo antes. SQLite (los tests) ignora `FOR UPDATE`.
    """
    from app.cobranza.models import ComisionReversion
    deuda = {}
    revs_q = ComisionReversion.query.filter_by(
        tenant_id=tenant_id, pagada_al_revertir=True,
    )
    if bloquear:
        revs_q = revs_q.with_for_update()
    for r in revs_q.all():
        esp = r.ingreso.especialista_id if r.ingreso else None
        if esp is None:
            continue
        deuda[esp] = round(deuda.get(esp, 0) + r.monto, 2)
    aplicado = {}
    pagos_q = PagoDoctor.query.filter_by(tenant_id=tenant_id)
    if bloquear:
        pagos_q = pagos_q.with_for_update()
    for p in pagos_q.all():
        if p.descuento_saldo:
            aplicado[p.especialista_id] = round(
                aplicado.get(p.especialista_id, 0) + p.descuento_saldo, 2)
    return {
        esp: max(0.0, round(monto - aplicado.get(esp, 0), 2))
        for esp, monto in deuda.items()
    }


def despagar_reversiones(tenant_id, ingreso_id):
    """La comisión deja de estar pagada: sus reversiones tampoco lo están.

    Si una devolución revirtió una comisión YA pagada, el doctor arrastra un
    saldo negativo. Al deshacer ese pago nunca cobró, así que el saldo sobra.
    """
    from app.cobranza.models import ComisionReversion
    reversiones = ComisionReversion.query.filter_by(
        tenant_id=tenant_id, ingreso_id=ingreso_id, pagada_al_revertir=True,
    ).all()
    for rev in reversiones:
        rev.pagada_al_revertir = False


def pendientes(tenant_id, *, especialista_id=None, origen="todos"):
    """Todas las comisiones sin liquidar (de cualquier mes), agrupadas por doctor.

    Una comisión está pendiente si su Ingreso tiene comision_doctor > 0 y no
    tiene fila en pago_comision_ingreso. `origen` ya viene validado
    ("todos" | "contado" | "plan").
    """
    # Import local para conservar al EDR utilizable aunque el add-on de
    # cobranza no esté habilitado para el tenant.
    from app.cobranza.models import Cotizacion, Pago as PagoCobranza

    liquidados = ingresos_liquidados_ids(tenant_id)
    reversiones_no_pagadas = reversiones_no_pagadas_por_ingreso(tenant_id)
    saldos = saldo_negativo_por_doctor(tenant_id)

    q = Ingreso.query.options(
        joinedload(Ingreso.especialista),
        selectinload(Ingreso.tratamiento),
        selectinload(Ingreso.cobranza_pago).joinedload(
            PagoCobranza.cotizacion
        ).joinedload(Cotizacion.paciente),
        selectinload(Ingreso.cobranza_pago).joinedload(
            PagoCobranza.cotizacion
        ).selectinload(Cotizacion.pagos),
    ).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.comision_doctor > 0,
        Ingreso.especialista_id.isnot(None),
    )
    if origen == "plan":
        q = q.filter(Ingreso.cobranza_pago.has())
    elif origen == "contado":
        q = q.filter(~Ingreso.cobranza_pago.has())
    if especialista_id:
        q = q.filter(Ingreso.especialista_id == especialista_id)
    ingresos = q.order_by(Ingreso.fecha).all()

    por_doctor = {}
    total_pendiente = 0.0
    for i in ingresos:
        if i.id in liquidados:
            continue
        grupo = por_doctor.setdefault(i.especialista_id, {
            "especialista_id": i.especialista_id,
            "especialista_nombre": i.especialista.nombre if i.especialista else "—",
            "total_pendiente": 0.0,
            "saldo_negativo": round(saldos.get(i.especialista_id, 0), 2),
            "comisiones": [],
            "cotizaciones": [],
            "_cotizaciones": {},
        })
        comision = round(i.comision_doctor or 0.0, 2)
        comision -= reversiones_no_pagadas.get(i.id, 0)
        comision = round(comision, 2)
        if comision <= 0:
            continue  # comisión totalmente revertida: no es pendiente
        pago_plan = i.cobranza_pago
        cotizacion = pago_plan.cotizacion if pago_plan else None
        detalle = {
            "ingreso_id": i.id,
            "fecha": i.fecha.isoformat(),
            "paciente": i.paciente or "Paciente",
            "nombre_tratamiento": i.nombre_tratamiento
                or (i.tratamiento.nombre if i.tratamiento else "Tratamiento"),
            "monto": round(i.monto, 2),
            "comision_doctor": comision,
            "origen": "plan" if cotizacion else "contado",
            "cotizacion_id": cotizacion.id if cotizacion else None,
            "cotizacion_folio": cotizacion.folio if cotizacion else None,
        }
        grupo["comisiones"].append(detalle)
        if cotizacion:
            agrupada = grupo["_cotizaciones"].setdefault(cotizacion.id, {
                "cotizacion_id": cotizacion.id,
                "folio": cotizacion.folio,
                "paciente": (
                    cotizacion.paciente.nombre
                    if cotizacion.paciente else (i.paciente or "Paciente")
                ),
                "abonos_totales": sum(
                    1 for pago in cotizacion.pagos if pago.ingreso_id
                ),
                "abonos_pendientes_comision": 0,
                "total_pendiente": 0.0,
                "abonos": [],
            })
            agrupada["abonos"].append(detalle)
            agrupada["abonos_pendientes_comision"] += 1
            agrupada["total_pendiente"] += comision
        grupo["total_pendiente"] += comision
        total_pendiente += comision

    # Los saldos negativos no son específicos de un origen (contado/plan), así
    # que solo se inyectan doctores "solo saldo" cuando se piden todos los
    # orígenes, y respetando el filtro de especialista si vino.
    if origen == "todos":
        for esp_id, saldo in saldos.items():
            if especialista_id and esp_id != especialista_id:
                continue
            if saldo > 0 and esp_id not in por_doctor:
                esp = Especialista.query.filter_by(id=esp_id, tenant_id=tenant_id).first()
                por_doctor[esp_id] = {
                    "especialista_id": esp_id,
                    "especialista_nombre": esp.nombre if esp else "—",
                    "total_pendiente": 0.0,
                    "saldo_negativo": round(saldo, 2),
                    "comisiones": [],
                    "cotizaciones": [],
                    "_cotizaciones": {},
                }

    doctores = sorted(por_doctor.values(), key=lambda d: d["especialista_nombre"])
    for d in doctores:
        d["total_pendiente"] = round(d["total_pendiente"], 2)
        d["cotizaciones"] = sorted(
            d.pop("_cotizaciones").values(),
            key=lambda cotizacion: cotizacion["folio"],
        )
        for cotizacion in d["cotizaciones"]:
            cotizacion["total_pendiente"] = round(
                cotizacion["total_pendiente"], 2,
            )
        if origen == "plan":
            # El arreglo plano se conserva por compatibilidad con la UI de
            # liquidación, pero en modo plan respeta la jerarquía por folio.
            d["comisiones"] = [
                abono
                for cotizacion in d["cotizaciones"]
                for abono in cotizacion["abonos"]
            ]

    return {
        "origen": origen,
        "total_pendiente": round(total_pendiente, 2),
        "doctores": doctores,
    }


def liquidar(tenant_id, *, especialista_id, fecha, ingreso_ids,
             sale_de_caja=False, sucursal_id=None, created_by=None):
    """Liquida las comisiones de los ingresos indicados en una sola fecha.

    Crea un PagoDoctor (tipo comisión) + las filas puente a cada ingreso. NO
    hace commit: el llamador decide, y si algo no valida no se escribió nada.
    """
    if not ingreso_ids:
        raise ComisionError("Elige al menos una comisión", "sin_seleccion")

    # Serializa las liquidaciones del tenant antes del check-then-insert: sin
    # esto, dos personas (admin y recepción) podrían pagar la misma comisión a
    # la vez. Mismo candado que `caja.services.cerrar_corte`; en SQLite (los
    # tests) es un no-op.
    #
    # Ese candado por sí solo no basta en MySQL: bajo REPEATABLE READ (el
    # nivel por defecto de InnoDB, el que usa producción) esta transacción ya
    # tomó su foto en un SELECT anterior (require_auth, la validación de
    # sucursal/turno, etc.), así que una lectura normal de "qué ya se pagó"
    # seguiría viendo datos viejos aunque este `with_for_update()` bloquee.
    # Por eso, de aquí en adelante las lecturas que deciden si algo ya se
    # pagó usan `FOR UPDATE`, que en InnoDB siempre trae el último dato
    # comprometido. SQLite (los tests) ignora `FOR UPDATE`, así que esto no
    # se puede probar por concurrencia real ahí — solo que se llama con
    # `bloquear=True`.
    ConfigConsultorio.query.filter_by(
        tenant_id=tenant_id).with_for_update().first()

    esp = Especialista.query.filter_by(
        id=especialista_id, tenant_id=tenant_id
    ).first()
    if not esp:
        raise ComisionError("Especialista no encontrado", "doctor_invalido")

    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.id.in_(ingreso_ids),
    ).all()
    if len(ingresos) != len(set(ingreso_ids)):
        raise ComisionError(
            "Algún ingreso no existe o no es de este consultorio", "ingreso_invalido")
    for i in ingresos:
        if i.especialista_id != especialista_id:
            raise ComisionError(
                "Algún ingreso no pertenece al especialista indicado", "ingreso_invalido")
        if not (i.comision_doctor and i.comision_doctor > 0):
            raise ComisionError(
                "Algún ingreso no tiene comisión por pagar", "sin_comision")

    # Lectura bloqueante y acotada a los ingresos pedidos (no todo el tenant,
    # como `ingresos_liquidados_ids`): con `FOR UPDATE` es la que decide si
    # alguno ya se pagó, para que un pago concurrente que acaba de comprometer
    # su fila no se nos escape por la foto vieja de la transacción.
    ya_liquidados_q = PagoComisionIngreso.query.filter(
        PagoComisionIngreso.tenant_id == tenant_id,
        PagoComisionIngreso.ingreso_id.in_([i.id for i in ingresos]),
    ).with_for_update()
    ya_liquidados = {f.ingreso_id for f in ya_liquidados_q.all()}
    if any(i.id in ya_liquidados for i in ingresos):
        raise ComisionError("Alguna comisión ya fue pagada", "ya_pagada")

    # Neto por ingreso (bruto − reversión no pagada): el doctor nunca cobra
    # sobre dinero ya devuelto al paciente.
    reversiones = reversiones_no_pagadas_por_ingreso(tenant_id, bloquear=True)
    pendientes_por_ingreso = {}
    for i in ingresos:
        pend = round((i.comision_doctor or 0) - reversiones.get(i.id, 0), 2)
        if pend <= 0:
            raise ComisionError(
                "Alguna comisión fue revertida por una devolución", "revertida")
        pendientes_por_ingreso[i.id] = pend

    total = round(sum(pendientes_por_ingreso.values()), 2)
    saldo = saldo_negativo_por_doctor(tenant_id, bloquear=True).get(especialista_id, 0.0)
    descuento = round(min(saldo, total), 2)
    neto = round(total - descuento, 2)

    pago = PagoDoctor(
        tenant_id=tenant_id,
        fecha=fecha,
        especialista_id=especialista_id,
        concepto=f"Pago de {len(ingresos)} comisión(es)",
        tipo="comision",
        monto=neto,
        descuento_saldo=descuento,
        sale_de_caja=sale_de_caja,
        sucursal_id=sucursal_id,
        created_by=created_by,
    )
    db.session.add(pago)
    db.session.flush()  # obtener pago.id

    for i in ingresos:
        db.session.add(PagoComisionIngreso(
            tenant_id=tenant_id,
            pago_id=pago.id,
            ingreso_id=i.id,
            monto=pendientes_por_ingreso[i.id],
        ))
    return pago
