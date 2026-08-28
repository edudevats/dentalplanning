"""Lógica de escritura del EDR: alta de ingresos, sueltos o como una visita.

Toda escritura de ingresos pasa por aquí (patrón como inventario/services.py).
Las funciones NO hacen commit; lo hace el llamador.
"""

import secrets

from app.extensions import db
from app.edr.models import Ingreso
from app.tratamientos.models import Tratamiento
from app.facturacion.services import asignar_ticket, recalcular_total


def hermanos_de_visita(ingreso):
    """Los ingresos capturados junto con éste, ordenados por id.

    Sin `visita_uid` el grupo es él solo: así la visita de un tratamiento y
    todo el histórico recorren exactamente el mismo camino que la de tres.
    Vive aquí (no en crm/services.py) porque agrupar `Ingreso` es un concepto
    del EDR; facturación (Tarea 6) también lo necesita y así no tiene que
    importarlo desde el CRM.
    """
    if not ingreso.visita_uid:
        return [ingreso]
    return Ingreso.query.filter_by(
        tenant_id=ingreso.tenant_id, visita_uid=ingreso.visita_uid
    ).order_by(Ingreso.id).all()


def repartir_proporcional(total, montos):
    """Reparte `total` entre `montos`, proporcional a cada uno.

    El residuo de centavos va a la última línea a propósito: redondear cada
    parte por su cuenta pierde o inventa centavos, y esta cifra alimenta el
    corte de caja. La suma de lo que devuelve es exactamente `round(total, 2)`.

    Con todos los montos en cero no hay proporción que aplicar (y dividir sería
    un ZeroDivisionError), así que el total entero cae en la última línea.
    """
    if not montos:
        return []
    total = round(float(total or 0.0), 2)
    suma = sum(montos)
    if not suma:
        return [0.0] * (len(montos) - 1) + [total]

    partes = [round(total * m / suma, 2) for m in montos[:-1]]
    partes.append(round(total - sum(partes), 2))
    return partes


# Las llaves de la visita que se copian tal cual en cada línea. Se duplican a
# propósito: así el dashboard, el EDR, los pagos a doctores y el corte de caja
# siguen leyendo una sola tabla, sin join ni caso especial para las visitas.
CAMPOS_COMUNES = (
    "fecha", "paciente", "paciente_id", "especialista_id", "metodo_pago_id",
    "descuento_pct", "factura", "sucursal_id", "estrategia_id", "comentarios",
)


def _tipo_servicio(tenant_id, tratamiento_id):
    """El tipo de servicio sale del tratamiento: de ahí depende el IVA.

    Se resuelve POR LÍNEA, no por visita: en la misma visita puede haber un
    tratamiento clínico y uno estético, y cada uno lleva su propio IVA.
    """
    if not tratamiento_id:
        return "clinico"
    tr = Tratamiento.query.filter_by(id=tratamiento_id, tenant_id=tenant_id).first()
    return (tr.tipo_servicio if tr and tr.tipo_servicio else "clinico")


def crear_ingresos_visita(tenant_id, usuario, comun, lineas, ticket_folio=None):
    """Da de alta la visita completa: un ingreso por tratamiento.

    Devuelve `(ingresos, visita_uid, ticket)`. NO hace commit: si algo falla más
    arriba, la visita entera se va, y nunca queda media visita capturada.

    Levanta CajaError, CrmError o FacturacionError; traducirlas a HTTP es del
    llamador.
    """
    # Imports locales: app.caja.services y app.crm.services importan de
    # app.edr.models, y a nivel de módulo esto sería un ciclo.
    from app.caja import services as caja_services
    from app.crm.services import crm_activo, sincronizar_visita_ingreso

    es_admin = usuario.role == "admin"
    fecha = comun.get("fecha")
    sucursal_id = comun.get("sucursal_id")

    # Los candados se evalúan UNA vez para la visita, no una por línea: es el
    # mismo día, la misma sucursal y el mismo turno para todas.
    #
    # El día va primero. Cerrar el corte cierra también los turnos de ese día,
    # así que quien captura sobre un día cerrado no tiene turno: preguntando
    # primero por el turno, la respuesta sería "abre tu caja" — y abrirla es
    # imposible, porque `abrir_turno` rechaza el día cerrado. El orden inverso
    # da el mensaje que sí lleva a algún lado.
    caja_services.exigir_dia_abierto(tenant_id, sucursal_id, fecha, es_admin=es_admin)
    caja_services.exigir_turno_abierto(
        tenant_id, usuario, fecha, sucursal_id, es_admin=es_admin,
    )

    comun = dict(comun)
    # Sin módulo CRM no se acepta paciente_id (evita FKs cross-tenant sin validar)
    if comun.get("paciente_id") and not crm_activo(tenant_id):
        comun["paciente_id"] = None

    # Sólo la visita de VARIOS tratamientos necesita token. Con uno solo la fila
    # queda igual que todo el histórico, sin nada que la distinga.
    visita_uid = secrets.token_hex(16) if len(lineas) > 1 else None

    montos = [float(l.get("monto") or 0.0) for l in lineas]
    comisiones = repartir_proporcional(comun.get("comision_bancaria") or 0.0, montos)

    ingresos = []
    for linea, monto, com_ban in zip(lineas, montos, comisiones):
        datos = {k: comun[k] for k in CAMPOS_COMUNES if k in comun}
        ingreso = Ingreso(
            tenant_id=tenant_id,
            visita_uid=visita_uid,
            tipo_servicio=_tipo_servicio(tenant_id, linea.get("tratamiento_id")),
            tratamiento_id=linea.get("tratamiento_id"),
            nombre_tratamiento=linea.get("nombre_tratamiento"),
            monto=monto,
            comision_doctor=linea.get("comision_doctor") or 0.0,
            comision_bancaria=com_ban,
            **datos,
        )
        db.session.add(ingreso)
        ingresos.append(ingreso)
    db.session.flush()

    # Una sola visita para el grupo: `sincronizar_visita_ingreso` ya resuelve
    # los hermanos, así que basta llamarla una vez.
    if crm_activo(tenant_id) and comun.get("paciente_id"):
        sincronizar_visita_ingreso(ingresos[0])

    ticket = None
    if comun.get("factura") and sucursal_id:
        # La primera línea abre (o encuentra) el ticket; las demás caen en ESE
        # folio. Una visita, una factura.
        ticket = asignar_ticket(ingresos[0], sucursal_id, ticket_folio)
        for extra in ingresos[1:]:
            asignar_ticket(extra, sucursal_id, ticket.folio)
        recalcular_total(ticket)

    return ingresos, visita_uid, ticket
