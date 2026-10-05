"""Odontograma por paciente: dentición, estado de dientes y asignación de
tratamientos a dientes.

Toda escritura del odontograma pasa por aquí (patrón inventario/CRM). Los
"pendientes por asignar" NO se guardan: se calculan en cada lectura como
unidades del origen menos asignaciones existentes, así no hay contador que se
desincronice ni forma de duplicar.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.crm.models import DienteEstado, DienteTratamiento
from app.crm.services import CrmError, CrmNotFound, _paciente
from app.extensions import db

PERMANENTES = tuple(q * 10 + n for q in (1, 2, 3, 4) for n in range(1, 9))
TEMPORALES = tuple(q * 10 + n for q in (5, 6, 7, 8) for n in range(1, 6))
TODOS = frozenset(PERMANENTES) | frozenset(TEMPORALES)

CARAS = ("O", "M", "D", "V", "L")
ESTADOS_DIENTE = ("presente", "ausente", "extraido", "exfoliado", "no_erupcionado")
ESTATUS_ASIGNACION = ("planeado", "realizado")


class OdontogramaError(CrmError):
    """Error de negocio del odontograma; las routes lo devuelven como 400."""


def edad(fecha_nacimiento, hoy=None):
    if not fecha_nacimiento:
        return None
    hoy = hoy or date.today()
    antes_del_cumple = (hoy.month, hoy.day) < (
        fecha_nacimiento.month, fecha_nacimiento.day,
    )
    return hoy.year - fecha_nacimiento.year - int(antes_del_cumple)


def denticion_por_edad(fecha_nacimiento, hoy=None):
    """Sin fecha se asume adulto; la UI avisa para que la capturen."""
    anios = edad(fecha_nacimiento, hoy)
    if anios is None:
        return "permanente"
    if anios < 6:
        return "temporal"
    if anios <= 12:
        return "mixta"
    return "permanente"


def dientes_visibles(denticion):
    if denticion == "temporal":
        return TEMPORALES
    if denticion == "mixta":
        return TEMPORALES + PERMANENTES
    return PERMANENTES


def estado_por_defecto(numero, denticion):
    """Estado de un diente visible que no tiene fila en DienteEstado."""
    if numero in TEMPORALES:
        return "presente"
    return "no_erupcionado" if denticion == "mixta" else "presente"


def sucesor_permanente(numero):
    """El permanente que sale cuando se cae un temporal (85 -> 45)."""
    if numero not in TEMPORALES:
        return None
    return (numero // 10 - 4) * 10 + numero % 10


def normalizar_caras(caras):
    if not caras:
        return None
    elegidas = set()
    for cara in caras:
        letra = str(cara).strip().upper()
        if letra not in CARAS:
            raise OdontogramaError(f"Cara inválida: {cara}")
        elegidas.add(letra)
    return ",".join(c for c in CARAS if c in elegidas)


def caras_lista(caras):
    return caras.split(",") if caras else []


ESTATUS_COT_FUENTE = ("aprobada", "liquidada")


def _unidades_concepto(concepto):
    return max(1, int(concepto.cantidad or 1))


def _conceptos_fuente(tenant_id, paciente_id):
    from app.cobranza.models import Cotizacion, CotizacionConcepto
    return (
        CotizacionConcepto.query
        .join(Cotizacion, CotizacionConcepto.cotizacion_id == Cotizacion.id)
        .filter(
            CotizacionConcepto.tenant_id == tenant_id,
            Cotizacion.tenant_id == tenant_id,
            Cotizacion.paciente_id == paciente_id,
            Cotizacion.estatus.in_(ESTATUS_COT_FUENTE),
        )
        .order_by(Cotizacion.fecha, CotizacionConcepto.orden, CotizacionConcepto.id)
        .all()
    )


def _ids_ingresos_abono(tenant_id):
    """Ingresos que son abonos de un plan: dinero, no tratamientos."""
    from app.cobranza.models import Pago
    return db.session.query(Pago.ingreso_id).filter(
        Pago.tenant_id == tenant_id, Pago.ingreso_id.isnot(None),
    )


def _ingresos_fuente(tenant_id, paciente_id):
    from app.edr.models import Ingreso
    return (
        Ingreso.query
        .filter(
            Ingreso.tenant_id == tenant_id,
            Ingreso.paciente_id == paciente_id,
            Ingreso.tratamiento_id.isnot(None),
            ~Ingreso.id.in_(_ids_ingresos_abono(tenant_id)),
        )
        .order_by(Ingreso.fecha, Ingreso.id)
        .all()
    )


def _asignadas_por(columna, ids):
    if not ids:
        return {}
    filas = (
        db.session.query(columna, func.count(DienteTratamiento.id))
        .filter(columna.in_(ids))
        .group_by(columna)
        .all()
    )
    return dict(filas)


def pendientes(tenant_id, paciente_id):
    conceptos = _conceptos_fuente(tenant_id, paciente_id)
    ingresos = _ingresos_fuente(tenant_id, paciente_id)
    por_concepto = _asignadas_por(
        DienteTratamiento.cotizacion_concepto_id, [c.id for c in conceptos],
    )
    por_ingreso = _asignadas_por(DienteTratamiento.ingreso_id, [i.id for i in ingresos])

    salida = []
    for c in conceptos:
        unidades = _unidades_concepto(c)
        asignadas = por_concepto.get(c.id, 0)
        if asignadas < unidades:
            salida.append({
                "origen_tipo": "concepto", "origen_id": c.id,
                "descripcion": c.descripcion, "origen": c.cotizacion.folio,
                "fecha": c.cotizacion.fecha.isoformat(),
                "unidades": unidades, "asignadas": asignadas,
            })
    for i in ingresos:
        asignadas = por_ingreso.get(i.id, 0)
        if asignadas < 1:
            salida.append({
                "origen_tipo": "ingreso", "origen_id": i.id,
                "descripcion": i.nombre_tratamiento or "Tratamiento",
                "origen": "Ingreso", "fecha": i.fecha.isoformat(),
                "unidades": 1, "asignadas": asignadas,
            })
    return salida


def _estados(tenant_id, paciente_id):
    filas = DienteEstado.query.filter_by(tenant_id=tenant_id, paciente_id=paciente_id).all()
    return {e.numero: e for e in filas}


def estado_efectivo(numero, denticion, estados):
    fila = estados.get(numero)
    return fila.estado if fila else estado_por_defecto(numero, denticion)


def dump_asignacion(t):
    if t.cotizacion_concepto_id:
        origen_tipo = "concepto"
        origen = t.concepto.cotizacion.folio if t.concepto else None
    elif t.ingreso_id:
        origen_tipo, origen = "ingreso", "Ingreso"
    else:
        origen_tipo, origen = None, None
    return {
        "id": t.id,
        "numero": t.numero,
        "caras": caras_lista(t.caras),
        "estatus": t.estatus,
        "fecha_realizado": t.fecha_realizado.isoformat() if t.fecha_realizado else None,
        "descripcion": t.descripcion,
        "especialista_nombre": t.especialista.nombre if t.especialista else None,
        "origen_tipo": origen_tipo,
        "origen": origen,
        "origen_eliminado": bool(t.origen_eliminado),
    }


def obtener_odontograma(tenant_id, paciente_id, hoy=None):
    p = _paciente(tenant_id, paciente_id)
    denticion = denticion_por_edad(p.fecha_nacimiento, hoy)
    estados = _estados(tenant_id, p.id)

    por_diente = {}
    asignaciones = (
        DienteTratamiento.query
        .filter_by(tenant_id=tenant_id, paciente_id=p.id)
        .order_by(DienteTratamiento.created_at, DienteTratamiento.id)
        .all()
    )
    for t in asignaciones:
        por_diente.setdefault(t.numero, []).append(dump_asignacion(t))

    return {
        "paciente": {
            "id": p.id,
            "nombre": p.nombre,
            "edad": edad(p.fecha_nacimiento, hoy),
            "denticion": denticion,
            "sin_fecha_nacimiento": p.fecha_nacimiento is None,
        },
        "dientes": [
            {
                "numero": n,
                "temporal": n in TEMPORALES,
                "estado": estado_efectivo(n, denticion, estados),
                "tratamientos": por_diente.get(n, []),
            }
            for n in dientes_visibles(denticion)
        ],
        "pendientes": pendientes(tenant_id, p.id),
    }


def _validar_asignable(numero, denticion, estados):
    if numero not in TODOS:
        raise OdontogramaError(f"Número de diente inválido: {numero}")
    if numero not in dientes_visibles(denticion):
        raise OdontogramaError(
            f"El diente {numero} no corresponde a la dentición del paciente"
        )
    estado = estado_efectivo(numero, denticion, estados)
    if estado != "presente":
        raise OdontogramaError(f"El diente {numero} está {estado.replace('_', ' ')}")


def _cargar_origen(tenant_id, paciente_id, origen_tipo, origen_id):
    """Devuelve (origen, unidades, columna) con la fila del origen bloqueada.

    El FOR UPDATE sobre el origen serializa dos asignaciones simultáneas de la
    misma línea: la segunda espera a que la primera confirme. Ojo: en InnoDB
    REPEATABLE READ las lecturas simples ven el snapshot viejo, por eso el
    conteo de asignaciones existentes en `asignar` también es lectura con
    bloqueo (FOR UPDATE lee lo último confirmado).
    """
    if origen_tipo == "concepto":
        from app.cobranza.models import CotizacionConcepto
        c = (CotizacionConcepto.query
             .filter_by(id=origen_id, tenant_id=tenant_id)
             .with_for_update().first())
        if not c or c.cotizacion.paciente_id != paciente_id:
            raise CrmNotFound("Tratamiento no encontrado para este paciente")
        if c.cotizacion.estatus not in ESTATUS_COT_FUENTE:
            raise OdontogramaError(
                "Solo se asignan tratamientos de cotizaciones aprobadas o liquidadas"
            )
        return c, _unidades_concepto(c), DienteTratamiento.cotizacion_concepto_id
    if origen_tipo == "ingreso":
        from app.cobranza.models import Pago
        from app.edr.models import Ingreso
        i = (Ingreso.query
             .filter_by(id=origen_id, tenant_id=tenant_id)
             .with_for_update().first())
        if not i or i.paciente_id != paciente_id:
            raise CrmNotFound("Tratamiento no encontrado para este paciente")
        if Pago.query.filter_by(tenant_id=tenant_id, ingreso_id=i.id).first():
            raise OdontogramaError("Este ingreso es un abono de plan, no un tratamiento")
        if i.tratamiento_id is None:
            raise OdontogramaError("Este ingreso no tiene un tratamiento del catálogo")
        return i, 1, DienteTratamiento.ingreso_id
    raise OdontogramaError("Origen inválido")


def _nueva_asignacion(tenant_id, user_id, paciente_id, origen_tipo, origen, numero, caras):
    comun = dict(tenant_id=tenant_id, paciente_id=paciente_id, numero=numero,
                 caras=caras, usuario_id=user_id, tratamiento_id=origen.tratamiento_id)
    if origen_tipo == "concepto":
        return DienteTratamiento(
            **comun, estatus="planeado", descripcion=origen.descripcion,
            especialista_id=origen.cotizacion.especialista_id,
            cotizacion_concepto_id=origen.id,
        )
    return DienteTratamiento(
        **comun, estatus="realizado", fecha_realizado=origen.fecha,
        descripcion=origen.nombre_tratamiento or "Tratamiento",
        especialista_id=origen.especialista_id, ingreso_id=origen.id,
    )


def _columna_origen(t):
    if t.cotizacion_concepto_id:
        return DienteTratamiento.cotizacion_concepto_id, t.cotizacion_concepto_id
    if t.ingreso_id:
        return DienteTratamiento.ingreso_id, t.ingreso_id
    return None, None


def asignar(tenant_id, user_id, paciente_id, origen_tipo, origen_id, dientes, hoy=None):
    try:
        p = _paciente(tenant_id, paciente_id)
        origen, unidades, columna = _cargar_origen(tenant_id, p.id, origen_tipo, origen_id)
        if not dientes:
            raise OdontogramaError("Elige al menos un diente")
        numeros = [d["numero"] for d in dientes]
        if len(set(numeros)) != len(numeros):
            raise OdontogramaError("Un diente aparece repetido")

        # Lectura con bloqueo: ve las filas que otra transacción ya confirmó
        # (una lectura simple usaría el snapshot previo al lock del origen).
        existentes = (DienteTratamiento.query.filter(columna == origen.id)
                      .with_for_update().all())
        restantes = unidades - len(existentes)
        if len(dientes) > restantes:
            raise OdontogramaError(f"Solo quedan {restantes} por asignar de este tratamiento"
                                   if restantes != 1 else
                                   "Solo queda 1 por asignar de este tratamiento")
        ocupados = {t.numero for t in existentes}

        denticion = denticion_por_edad(p.fecha_nacimiento, hoy)
        estados = _estados(tenant_id, p.id)
        nuevas = []
        for d in dientes:
            numero = d["numero"]
            _validar_asignable(numero, denticion, estados)
            if numero in ocupados:
                raise OdontogramaError(f"El diente {numero} ya tiene asignado este tratamiento")
            nuevas.append(_nueva_asignacion(
                tenant_id, user_id, p.id, origen_tipo, origen, numero,
                normalizar_caras(d.get("caras")),
            ))
        db.session.add_all(nuevas)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise OdontogramaError(
            "Otro usuario acaba de asignar este tratamiento; recarga e intenta de nuevo"
        )
    except Exception:
        db.session.rollback()
        raise
    return nuevas


def _asignacion(tenant_id, paciente_id, asignacion_id):
    t = DienteTratamiento.query.filter_by(
        id=asignacion_id, tenant_id=tenant_id, paciente_id=paciente_id,
    ).first()
    if not t:
        raise CrmNotFound("Asignación no encontrada")
    return t


def _commit():
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise OdontogramaError(
            "Otro usuario acaba de modificar este diente; recarga e intenta de nuevo"
        )
    except Exception:
        db.session.rollback()
        raise


def marcar_realizado(tenant_id, user_id, paciente_id, asignacion_id, fecha=None):
    t = _asignacion(tenant_id, paciente_id, asignacion_id)
    if t.estatus != "planeado":
        raise OdontogramaError("Este tratamiento ya está realizado")
    t.estatus = "realizado"
    t.fecha_realizado = fecha or date.today()
    _commit()
    return t


def corregir_asignacion(tenant_id, user_id, paciente_id, asignacion_id, data, hoy=None):
    t = _asignacion(tenant_id, paciente_id, asignacion_id)
    if "numero" in data and data["numero"] != t.numero:
        p = _paciente(tenant_id, paciente_id)
        numero = data["numero"]
        _validar_asignable(numero, denticion_por_edad(p.fecha_nacimiento, hoy),
                           _estados(tenant_id, p.id))
        columna, valor = _columna_origen(t)
        if columna is not None and DienteTratamiento.query.filter(
            columna == valor, DienteTratamiento.numero == numero,
        ).first():
            raise OdontogramaError(f"El diente {numero} ya tiene asignado este tratamiento")
        t.numero = numero
    if "caras" in data:
        t.caras = normalizar_caras(data["caras"])
    if "fecha_realizado" in data:
        if t.estatus != "realizado":
            raise OdontogramaError("Solo un tratamiento realizado lleva fecha")
        if data["fecha_realizado"] is None:
            raise OdontogramaError("La fecha es obligatoria")
        t.fecha_realizado = data["fecha_realizado"]
    _commit()
    return t


def desasignar(tenant_id, user_id, paciente_id, asignacion_id):
    t = _asignacion(tenant_id, paciente_id, asignacion_id)
    db.session.delete(t)
    _commit()


def _upsert_estado(tenant_id, user_id, paciente_id, numero, estado, fecha):
    fila = DienteEstado.query.filter_by(
        tenant_id=tenant_id, paciente_id=paciente_id, numero=numero,
    ).first()
    if fila is None:
        fila = DienteEstado(tenant_id=tenant_id, paciente_id=paciente_id, numero=numero)
        db.session.add(fila)
    fila.estado = estado
    fila.fecha = fecha
    fila.usuario_id = user_id


def cambiar_estado_diente(tenant_id, user_id, paciente_id, numero, estado,
                          fecha=None, hoy=None):
    p = _paciente(tenant_id, paciente_id)
    if estado not in ESTADOS_DIENTE:
        raise OdontogramaError(f"Estado inválido: {estado}")
    if numero not in TODOS:
        raise OdontogramaError(f"Número de diente inválido: {numero}")
    if numero not in dientes_visibles(denticion_por_edad(p.fecha_nacimiento, hoy)):
        raise OdontogramaError(
            f"El diente {numero} no corresponde a la dentición del paciente"
        )
    _upsert_estado(tenant_id, user_id, p.id, numero, estado, fecha)
    sucesor = sucesor_permanente(numero) if estado == "exfoliado" else None
    if sucesor:
        _upsert_estado(tenant_id, user_id, p.id, sucesor, "presente", fecha)
    _commit()


# --- Ganchos para cobranza y EDR. No hacen commit: corren dentro de la
# transacción de quien borra/cancela el origen. ---

def _de_conceptos(tenant_id, cotizacion):
    ids = [c.id for c in cotizacion.conceptos]
    if not ids:
        return []
    return DienteTratamiento.query.filter(
        DienteTratamiento.tenant_id == tenant_id,
        DienteTratamiento.cotizacion_concepto_id.in_(ids),
    ).all()


def al_eliminar_origen_cotizacion(tenant_id, cotizacion):
    """Lo planeado se va con la cotización; lo realizado ya pasó en la boca y
    se conserva con su snapshot, marcado como origen eliminado."""
    for t in _de_conceptos(tenant_id, cotizacion):
        if t.estatus == "planeado":
            db.session.delete(t)
        else:
            t.cotizacion_concepto_id = None
            t.origen_eliminado = True
    db.session.flush()


def al_cancelar_cotizacion(tenant_id, cotizacion):
    """Un plan cancelado ya no se hará: fuera lo planeado. Lo realizado sigue
    ligado porque el concepto sigue existiendo."""
    for t in _de_conceptos(tenant_id, cotizacion):
        if t.estatus == "planeado":
            db.session.delete(t)
    db.session.flush()


def al_eliminar_ingreso(tenant_id, ingreso_id):
    for t in DienteTratamiento.query.filter_by(tenant_id=tenant_id, ingreso_id=ingreso_id).all():
        if t.estatus == "planeado":
            db.session.delete(t)
        else:
            t.ingreso_id = None
            t.origen_eliminado = True
    db.session.flush()


def ingreso_tiene_asignaciones(tenant_id, ingreso_id):
    return DienteTratamiento.query.filter_by(
        tenant_id=tenant_id, ingreso_id=ingreso_id,
    ).first() is not None
