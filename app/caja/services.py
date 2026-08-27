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


def _primer_turno_del_dia(tenant_id, sucursal_id, fecha):
    """La fila del turno más antiguo de ese día en esa sucursal, o None.

    Vive aparte porque `fondo_del_dia` y la herencia de `abrir_turno` tienen que
    leer la MISMA fila con el MISMO criterio. Copiada en dos lados, la invariante
    dependería de que nadie toque una sin tocar la otra; aquí no puede divergir.
    """
    return _turnos_del_dia(tenant_id, sucursal_id, fecha).first()


def _turnos_del_dia(tenant_id, sucursal_id, fecha):
    """Todos los turnos de ese día y sucursal, del más viejo al más nuevo.

    Por la herencia de `abrir_turno` todos cargan el mismo fondo, así que
    corregirlo tiene que tocarlos a todos: dejar las demás filas con el valor
    viejo guardaría un dato que contradice al que se lee.
    """
    return TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.fecha == fecha,
        _filtro_sucursal(TurnoCaja.sucursal_id, sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
    ).order_by(TurnoCaja.id)


def _parsear_fondo(valor):
    """El monto tecleado, vuelto un número que la caja acepta.

    Lo comparten abrir y corregir a propósito: si cada uno validara por su lado,
    el fondo podría entrar por una puerta con reglas que la otra no aplica.
    """
    try:
        monto = round(float(valor or 0), 2)
    except (TypeError, ValueError):
        raise CajaError("El fondo inicial no es un número válido",
                        codigo="fondo_invalido")
    if monto < 0:
        raise CajaError("El fondo inicial no puede ser negativo",
                        codigo="fondo_invalido")
    return monto


def _fondo_normalizado(turno):
    """El fondo de una fila, redondeado igual en todos lados."""
    return round(float(turno.fondo_inicial or 0), 2)


def _exigir_misma_sucursal(turno, sucursal_id):
    """Un turno que ya existe solo sirve si es de la sucursal que se está pidiendo.

    Devolverlo cuando no coincide pondría a la persona a capturar creyendo que
    está en otra sede: el bug exacto que el turno existe para cerrar. Vive aparte
    porque los dos caminos que pueden toparse con un turno ajeno —el tranquilo y
    el de la carrera contra el UNIQUE— tienen que exigir lo mismo; si divergen,
    la carrera queda con menos garantías que el camino tranquilo.
    """
    if turno.sucursal_id == sucursal_id:
        return
    nombre = turno.sucursal.nombre if turno.sucursal else "Sin sucursal"
    raise CajaError(
        f"Ya abriste caja hoy en {nombre}",
        codigo="turno_en_otra_sucursal",
    )


def fondo_del_dia(tenant_id, sucursal_id, fecha):
    """El fondo que declaró quien abrió primero ese día en esa sucursal.

    Hay UN cajón por sucursal: si dos personas abren el mismo día, el fondo no
    se suma. Manda el turno más antiguo, que es un valor único y consultable.
    """
    t = _primer_turno_del_dia(tenant_id, sucursal_id, fecha)
    return _fondo_normalizado(t) if t is not None else 0.0


def hay_turno_del_dia(tenant_id, sucursal_id, fecha):
    """Si alguien abrió el cajón ese día en esa sucursal.

    La pantalla la usa para decidir si ofrece corregir el fondo: sin turno no
    hay fondo declarado, y el botón llevaría a un 409 seguro.
    """
    return _primer_turno_del_dia(tenant_id, sucursal_id, fecha) is not None


def _tickets_del_dia(tenant_id, sucursal_id, fecha):
    """Los tickets de los ingresos de ese día y sucursal, sin repetir.

    Se llega a ellos por el ingreso y no por `Ticket.fecha`: la fecha del ticket
    es la del PRIMER ingreso que lo abrió, y lo que se está moviendo son los
    ingresos.
    """
    from app.facturacion.models import Ticket
    ids = [i.ticket_id for i in Ingreso.query.filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.fecha == fecha,
        Ingreso.sucursal_id == sucursal_id,
        Ingreso.ticket_id.isnot(None),
    ).all()]
    if not ids:
        return []
    # `tenant_id` de nuevo aquí: `Ticket.id` es autoincremental global, y sin
    # este filtro un `id` que calzara por casualidad con el de otro tenant
    # (imposible en la práctica, pero el resto del módulo no se fía de eso en
    # ningún otro lado) se colaría en la lista.
    return Ticket.query.filter(Ticket.id.in_(set(ids)),
                               Ticket.tenant_id == tenant_id).all()


def _no_es_de_sucursal(columna, sucursal_id):
    """El NULL-safe "esto no es de esa sucursal", tratando NULL como un valor.

    No se puede armar negando `_filtro_sucursal` con `db.not_(...)`: en SQL,
    `NOT(columna == valor)` cuando `columna` es NULL sigue dando NULL (no
    verdadero), así que `NOT()` sobre una igualdad se degrada otra vez a un
    `!=` de a pie y pierde las filas en NULL — el mismo bug que motivó esta
    función, reaparecido por la puerta de atrás. Por eso el sentido "no es
    esta sucursal" se construye derecho, no por negación.
    """
    if sucursal_id is None:
        return columna.isnot(None)
    return db.or_(columna.is_(None), columna != sucursal_id)


def _exigir_tickets_movibles(tenant_id, origen_id, destino_id, fecha):
    """Los tickets del día tienen que poder mudarse enteros y sin timbrar.

    Cuatro rechazos:

    - `ticket_timbrado`: un CFDI ya emitido lleva la sucursal dentro del
      comprobante. Cambiársela por debajo sería falsificarlo; hay que cancelarlo.
    - `ticket_en_error`: un ticket que quedó en error de timbrado pudo haber
      timbrado igual y solo perdido la respuesta (por eso `Ticket.cfdi_fecha` se
      conserva: el reintento regenera un CFDI byte-idéntico). Cambiarle sucursal
      y folio por debajo rompería esa regeneración, así que se bloquea igual que
      un timbrado, pero con su propio mensaje: aquí no hay nada que cancelar
      (`cfdi.cancelar_ticket` exige `estado in (timbrada, en_proceso_cancelacion)`,
      así que un ticket en error no se puede cancelar). Reintentar el timbrado
      SÍ es posible (`cfdi.timbrar_ticket` acepta `TICKET_ERROR`, y el portal del
      paciente lo trata como refacturable) y sí saca al ticket de `error`, pero
      eso no desbloquea la caja: si el reintento timbra, el ticket cae derecho
      en el candado de `ticket_timbrado` de aquí abajo. La única salida real es
      que el timbrado NUNCA se complete (CSD vencido, RFC del receptor
      rechazado, Finkok caído) y alguien lo saque de `error` a mano -hoy no hay
      ninguna acción en el producto para eso.
    - `ticket_cancelado`: cancelar un CFDI no borra que existió. El ticket
      sigue llevando la sucursal con la que se timbró en su momento, así que
      moverlo por debajo lo falsificaría igual que a uno vigente. Y aquí, igual
      que en `ticket_en_error`, no hay ninguna salida real en el producto: los
      tres caminos que un admin probaría para "recapturar en la otra sucursal"
      están cerrados -editar el ingreso y borrarlo y recapturarlo chocan los
      dos con el mismo candado de `app/edr/routes.py` (`estado != sin_timbrar`
      → 400), y `asignar_ticket` sabe reasignar un ingreso a otro ticket pero
      ninguna ruta lo invoca sobre un ingreso que YA tiene ticket (sus únicos
      llamadores son altas nuevas). Lo único ejecutable es escalarlo. Lo que le
      faltaría al producto para que hubiera una salida de verdad es una acción
      que desasigne los ingresos de un ticket no vigente (cancelado) para que
      puedan recapturarse o reasignarse limpios -análoga a la nota de `uuid IS
      NULL` de `ticket_en_error`.
    - `ticket_mixto`: `asignar_ticket` agrupa por folio, no por día, así que un
      ticket sin timbrar puede haber acumulado ingresos de otra fecha o de una
      TERCERA sucursal (ni el origen ni el destino de esta mudanza). Mover solo
      esa parte lo dejaría partido entre dos sucursales. Un ticket cuyos
      ingresos caen todos en el origen o el destino sí se puede mover completo
      -la mudanza lo termina de unificar, no lo parte- así que "ajeno" se define
      contra los DOS extremos del movimiento, no solo contra el origen.

    Devuelve la lista de tickets que sí se pueden mudar.
    """
    from app.facturacion.models import (
        TICKET_SIN_TIMBRAR, TICKET_ERROR, TICKET_CANCELADA,
    )

    tickets = _tickets_del_dia(tenant_id, origen_id, fecha)

    en_error = [t for t in tickets if t.estado == TICKET_ERROR]
    if en_error:
        folios = ", ".join(t.folio_display for t in en_error)
        raise CajaError(
            f"Los tickets {folios} quedaron en error de timbrado y pueden "
            "haberse emitido igual con la respuesta perdida, así que la caja "
            "no se puede mover mientras sigan en ese estado. Reintentar el "
            "timbrado no desbloquea la caja -si timbra, el ticket cae en el "
            "mismo candado que uno ya facturado-: si el timbrado de verdad no "
            "se puede completar (CSD vencido, RFC rechazado, Finkok caído), "
            "repórtalo a soporte técnico para resolverlo a mano.",
            codigo="ticket_en_error",
            datos={"folios": folios},
        )

    # `timbrados` va ANTES que `canceladas`: con un ticket de cada tipo el
    # mismo día, `ticket_timbrado` SÍ trae una acción ejecutable (cancelar la
    # factura), mientras que `ticket_cancelado` es, como `ticket_en_error`, un
    # callejón sin salida. Mostrar primero lo accionable importa -esconder el
    # camino que sí funciona detrás del que no tiene sería el mismo defecto
    # que esta ola vino a corregir, solo que en el orden en vez del texto.
    timbrados = [t for t in tickets
                if t.estado not in (TICKET_SIN_TIMBRAR, TICKET_CANCELADA)]
    if timbrados:
        folios = ", ".join(t.folio_display for t in timbrados)
        raise CajaError(
            f"No se puede mover la caja: ya se facturaron los tickets {folios}. "
            "Cancela esas facturas antes de cambiar la sucursal.",
            codigo="ticket_timbrado",
            datos={"folios": folios},
        )

    canceladas = [t for t in tickets if t.estado == TICKET_CANCELADA]
    if canceladas:
        folios = ", ".join(t.folio_display for t in canceladas)
        raise CajaError(
            f"Los tickets {folios} ya están cancelados, y cancelar no borra "
            "que existieron: siguen llevando la sucursal con la que se "
            "timbraron, así que moverlos la falsificaría igual que a uno "
            "vigente. Aquí no hay una salida en el producto -editar o "
            "recapturar esos cobros choca con el mismo candado que un ticket "
            "vigente, y no hay ninguna acción que los desligue de este ticket-"
            " así que repórtalo a soporte técnico para resolverlo a mano.",
            codigo="ticket_cancelado",
            datos={"folios": folios},
        )

    for t in tickets:
        # Ajeno = ni el origen ni el destino de ESTA mudanza, con NULL tratado
        # como valor en los dos lados (`_no_es_de_sucursal`). Cuando no hay
        # mudanza real (origen == destino) las dos condiciones son la misma y
        # el AND se reduce solo, sin caso especial.
        no_es_origen = _no_es_de_sucursal(Ingreso.sucursal_id, origen_id)
        no_es_destino = _no_es_de_sucursal(Ingreso.sucursal_id, destino_id)
        ajenos = Ingreso.query.filter(
            Ingreso.tenant_id == tenant_id,
            Ingreso.ticket_id == t.id,
            db.or_(Ingreso.fecha != fecha,
                   db.and_(no_es_origen, no_es_destino)),
        ).count()
        if ajenos:
            folio_display = t.folio_display
            raise CajaError(
                f"El ticket {folio_display} agrupa cobros de otro día o de una "
                "tercera sucursal, así que moverlo lo dejaría partido. Reasigna "
                "esos cobros a la fecha o sucursal que les corresponde, o "
                "cancela el ticket, y vuelve a intentar mover la caja.",
                codigo="ticket_mixto",
                datos={"folios": folio_display},
            )
    return tickets


def _mover_caja(tenant_id, origen_id, destino_id, fecha):
    """Muda el día entero de una sucursal a otra. No hace commit.

    El día entero y no solo el turno: mover únicamente el turno dejaría a la
    sucursal correcta en ceros y a la equivocada con el dinero, que es el
    problema que se vino a arreglar. "El día entero" incluye TODOS los
    `GastoOperativo` de esa fecha y sucursal, no solo los que salen de caja
    (`sale_de_caja=True`): el gasto pertenece a la sucursal igual que el
    ingreso, así que corregir la sucursal tiene que alcanzarlo también.
    """
    from app.facturacion.models import Sucursal
    from app.facturacion.services import siguiente_folio

    destino = Sucursal.query.filter_by(
        id=destino_id, tenant_id=tenant_id).first()
    if destino is None:
        # Sin esta guarda, los tres UPDATE masivos de abajo escriben
        # `sucursal_id = destino_id` de todos modos -la FK se satisface con
        # una fila de otro tenant o revienta con un id que no existe en
        # ninguno- y el día entero, dinero y folios, queda apuntando a una
        # sucursal que no es de esta clínica.
        raise CajaError(
            "La sucursal de destino no existe en esta clínica. "
            "Elige una sucursal válida de la lista.",
            codigo="sucursal_invalida",
        )

    tickets = _exigir_tickets_movibles(tenant_id, origen_id, destino_id, fecha)

    for modelo in (Ingreso, GastoOperativo, TurnoCaja):
        modelo.query.filter(
            modelo.tenant_id == tenant_id,
            modelo.fecha == fecha,
            modelo.sucursal_id == origen_id,
        ).update({"sucursal_id": destino_id}, synchronize_session=False)

    # Los tickets al final y de uno en uno: cada folio nuevo se calcula contra
    # el máximo del destino, así que el flush entre uno y otro es lo que evita
    # que dos tickets de la misma mudanza reciban el mismo número.
    #
    # El folio se calcula ANTES de tocar `t.sucursal_id`: la sesión hace
    # autoflush al lanzar la consulta de `siguiente_folio`, y si la sucursal ya
    # estuviera sucia en memoria ese autoflush la escribiría en la BD antes del
    # SELECT — el propio ticket, todavía con su folio viejo, se colaría en el
    # máximo del destino y el folio nuevo saldría inflado.
    for t in tickets:
        if t.sucursal_id == destino_id:
            # Ya vive en el destino (p. ej. `actualizar_ingreso` dejó divergir
            # la sucursal del ingreso de la de su ticket). Re-foliarlo sería
            # gastar un folio para no cambiar nada; el mismo principio que ya
            # exige `test_mover_a_la_misma_sucursal_es_un_no_op` para el
            # turno aplica aquí ticket por ticket.
            continue
        folio = siguiente_folio(tenant_id, destino_id)
        t.sucursal_id = destino_id
        t.serie = destino.serie or ""
        t.folio = folio
        db.session.flush()


def corregir_caja_del_dia(tenant_id, sucursal_id, fecha, *, fondo_inicial,
                          sucursal_destino_id=None):
    """Enmienda el fondo y —si hace falta— la sucursal del cajón de hoy.

    Existe porque la caja se abre a primera hora y con prisa: dejar el fondo en
    blanco y elegir la sucursal equivocada son los dos errores naturales, y sin
    esto la única salida era cerrar el día con una diferencia falsa o editar
    ingreso por ingreso.

    Las dos correcciones van juntas en una transacción a propósito: se hacen en
    el mismo momento y sobre el mismo día, y partirlas dejaría la puerta abierta
    a que una pase y la otra falle.

    Si el destino ya tenía su propio turno abierto por otra persona, los dos
    turnos se fusionan bajo el fondo nuevo: hay UN cajón por sucursal y por
    día, así que dos fondos abiertos a la vez en la misma sucursal no es un
    estado que tenga sentido conservar por separado.
    """
    monto = _parsear_fondo(fondo_inicial)

    if fecha != date.today():
        # El turno de ayer ya caducó y su fondo es historia: corregirlo movería
        # el esperado de un día que nadie va a volver a contar.
        raise CajaError("Solo puedes corregir la caja del día en curso",
                        codigo="fecha_no_editable")

    if corte_cerrado(tenant_id, sucursal_id, fecha):
        raise CajaError(
            f"La caja del {fecha.strftime('%d/%m/%Y')} ya fue cerrada. "
            "Reábrela para corregirla.",
            codigo="dia_cerrado",
        )

    turnos = _turnos_del_dia(tenant_id, sucursal_id, fecha).all()
    if not turnos:
        # Sin turno nadie abrió el cajón: no hay caja que enmendar. Declararla
        # aquí exigiría inventar un dueño para el turno.
        raise CajaError("Nadie ha abierto caja hoy en esta sucursal",
                        codigo="sin_turno_del_dia")

    mueve = (sucursal_destino_id is not None
             and sucursal_destino_id != sucursal_id)

    # De aquí en adelante el cuerpo muta filas de verdad. El docstring promete
    # una transacción -las dos correcciones pasan juntas o ninguna- y sin este
    # try/except esa promesa no está escrita en ningún lado: un fallo que no
    # sea `CajaError` (por ejemplo un `IntegrityError` contra
    # `uq_ticket_folio_sucursal` si dos mudanzas compiten por el mismo folio, o
    # una mudanza choca contra un `asignar_ticket` corriendo al mismo tiempo)
    # saldría dejando los tres UPDATE masivos ya aplicados y sin revertir.
    # El `IntegrityError` tiene además su propio `except`, más abajo: sin
    # traducirlo a `CajaError` la ruta (`app/caja/routes.py`) no lo atrapa -solo
    # captura `services.CajaError`- y el admin vería un 500 crudo en una
    # pantalla de dinero, en vez del 409 con instrucciones que sí puede seguir.
    try:
        if mueve:
            if corte_cerrado(tenant_id, sucursal_destino_id, fecha):
                raise CajaError(
                    "La caja de la sucursal a la que quieres mover ya fue "
                    f"cerrada el {fecha.strftime('%d/%m/%Y')}. Reábrela "
                    "primero.",
                    codigo="dia_cerrado",
                )
            _mover_caja(tenant_id, sucursal_id, sucursal_destino_id, fecha)
            # Hay que releer, pero no por lo que parece: el UPDATE masivo de
            # `_mover_caja` corrió con `synchronize_session=False`, así que
            # SQLAlchemy no le avisó a la sesión del cambio, pero eso no hace
            # que las instancias en memoria queden mal apuntadas -el
            # `commit()` de abajo, con `expire_on_commit=True`, las expira y
            # las recarga solas. Lo que esta relectura sí aporta es traer los
            # turnos que YA vivían en el destino (la fusión que describe el
            # docstring): sin ella `turnos` seguiría apuntando solo a los del
            # origen.
            turnos = _turnos_del_dia(tenant_id, sucursal_destino_id, fecha).all()

        for turno in turnos:
            turno.fondo_inicial = monto
        db.session.commit()
    except IntegrityError:
        # `uq_ticket_folio_sucursal`: dos mudanzas a la vez, o una mudanza
        # contra un `asignar_ticket` concurrente, calcularon el mismo folio
        # nuevo para el mismo destino. No es un dato inválido -el cliente mandó
        # algo bien formado- es una carrera; reintentar (ahora sin la otra
        # operación de por medio) sí funciona, así que se le dice eso al admin
        # en vez de dejarlo con un 500 sin explicación.
        db.session.rollback()
        raise CajaError(
            "Dos movimientos de caja chocaron por el mismo folio al mismo "
            "tiempo. Vuelve a intentar mover la caja.",
            codigo="folio_en_disputa",
        )
    except Exception:
        db.session.rollback()
        raise
    return turnos[0]


def _sucursales_del_tenant(tenant_id):
    """Las sucursales del tenant, de la más vieja a la más nueva.

    El orden importa: con exactamente una, `resolver_sucursal_del_turno` la
    impone, y "la única" tiene que resolver siempre a la misma fila.
    """
    from app.facturacion.models import Sucursal
    return Sucursal.query.filter_by(tenant_id=tenant_id).order_by(
        Sucursal.id).all()


def resolver_sucursal_del_turno(tenant_id, sucursal_id):
    """La sucursal con la que se abre la caja. Nunca a medias.

    «Sin sucursal» dejó de ser un estado en el que se pueda abrir caja: era el
    hueco por el que el ingreso nacía huérfano y el ticket no llegaba a
    crearse. La regla se resuelve por cuántas sucursales tiene el tenant:

    - una  → el servidor la IMPONE y se ignora lo que mande el cliente. Pedir lo
             que tiene una única respuesta posible es inventar una oportunidad
             de equivocarse, y es a primera hora y con prisa cuando se abre caja.
    - dos+ → es OBLIGATORIA. Decir dónde se trabaja es el punto entero del turno.
    - cero → None es el único valor posible: no se puede obligar a elegir de una
             lista vacía, y bloquear la caja de un tenant que todavía no
             configuró facturación sería un remedio peor que la enfermedad.

    OJO: esto NO es `sucursal_separa_cajas`. Aquella decide si el CORTE parte el
    día en varias cajas (y con una sola sucursal sigue diciendo que no, para que
    los movimientos viejos en NULL caigan en el mismo corte que los nuevos).
    Esta decide con qué sucursal NACE el movimiento. Son preguntas distintas y
    confundirlas fue exactamente el bug.
    """
    sucursales = _sucursales_del_tenant(tenant_id)
    if len(sucursales) == 1:
        return sucursales[0].id
    if not sucursales:
        return None
    if sucursal_id is None:
        raise CajaError("Elige en qué sucursal vas a trabajar",
                        codigo="sucursal_requerida")
    return sucursal_id


def abrir_turno(tenant_id, usuario_id, *, sucursal_id, fondo_inicial):
    """Abre la caja de esa persona para HOY.

    La fecha la pone el servidor, nunca el cliente: es justamente el dato que el
    candado va a imponerle a todo lo que capture.
    """
    hoy = date.today()

    sucursal_id = resolver_sucursal_del_turno(tenant_id, sucursal_id)

    vigente = turno_vigente(tenant_id, usuario_id)
    if vigente is not None:
        _exigir_misma_sucursal(vigente, sucursal_id)
        return vigente              # idempotente: recargar no crea turnos

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
    primero = _primer_turno_del_dia(tenant_id, sucursal_id, hoy)
    heredado = _fondo_normalizado(primero) if primero is not None else None

    monto = _parsear_fondo(fondo_inicial)

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
        # un 500 en la pantalla que se abre a primera hora todos los días. Pero
        # se devuelve DESPUÉS de exigirle lo mismo que al camino tranquilo: la
        # carrera no puede tener menos garantías por haber llegado tarde.
        db.session.rollback()
        # Sin el filtro de `cerrado_at`: lo que hay que recuperar es la fila que
        # protege el UNIQUE (tenant, usuario, fecha), esté cerrada o no. Con
        # `turno_vigente` un turno ya cerrado se vería como "no hay nada" y el
        # servicio devolvería None a un llamador que espera un TurnoCaja.
        existente = TurnoCaja.query.filter(
            TurnoCaja.tenant_id == tenant_id,
            TurnoCaja.usuario_id == usuario_id,
            TurnoCaja.fecha == hoy,
        ).first()
        if existente is None:
            # El UNIQUE que reventó no era el del turno. No hay nada que
            # devolver, y callarlo dejaría pasar un None río abajo.
            raise CajaError("No se pudo abrir la caja. Vuelve a intentarlo.",
                            codigo="turno_no_disponible")
        _exigir_misma_sucursal(existente, sucursal_id)
        if existente.cerrado_at is not None:
            raise CajaError(
                "Ya cerraste tu turno de hoy. "
                "Pide al administrador que reabra la caja.",
                codigo="turno_cerrado",
            )
        return existente
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

    # El fondo va DENTRO del esperado porque ella cuenta todo el cajón, fondo
    # incluido: es lo natural, cuenta lo que ve. Restarlo del conteo la obligaría
    # a hacer aritmética antes de teclear, que es justo donde se cometen errores.
    fondo = fondo_del_dia(tenant_id, sucursal_id, fecha)
    esperado = round(fondo + totales[TIPO_EFECTIVO] - salidas_efectivo, 2)

    return {
        "totales": totales,
        "comision_tarjeta": comision_tarjeta,
        "neto_tarjeta": round(totales[TIPO_TARJETA] - comision_tarjeta, 2),
        "total_dia": total_dia,
        "salidas_efectivo": salidas_efectivo,
        "fondo_inicial": fondo,
        "esperado_efectivo": esperado,
        # Lo que sale del cajón al terminar: el fondo se queda para mañana.
        "a_entregar": round(esperado - fondo, 2),
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


# Los totales que el cierre congela en la fila. Si cualquiera de ellos ya no
# coincide con el recálculo vivo, la foto firmada dejó de describir el día. El
# fondo está aquí porque también entra en el esperado: cambiarlo después del
# cierre mueve el dinero que la foto dice que debía haber.
TOTALES_CONGELADOS = (
    "total_efectivo", "total_tarjeta", "total_transferencia", "total_otro",
    "comision_tarjeta", "salidas_efectivo", "fondo_inicial",
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
        "fondo_inicial": resumen["fondo_inicial"],
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
    # Parte de la foto firmada, igual que los seis totales.
    corte.fondo_inicial = resumen["fondo_inicial"]
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

    # El día se cierra para todos los que lo trabajaron.
    TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.fecha == fecha,
        _filtro_sucursal(TurnoCaja.sucursal_id, sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
    ).update({"cerrado_at": datetime.now(timezone.utc)},
             synchronize_session=False)

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

    # Devolverle la vigencia al turno: si no, quien trabajó ese día no puede
    # volver a capturar, y el UNIQUE por (tenant, usuario, fecha) le impide
    # abrir uno nuevo.
    TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.fecha == corte.fecha,
        _filtro_sucursal(TurnoCaja.sucursal_id, corte.sucursal_id,
                         separa=sucursal_separa_cajas(tenant_id)),
    ).update({"cerrado_at": None}, synchronize_session=False)

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

    # Una sola consulta para todo el rango, no una por día: es la misma razón
    # por la que este reporte no llama a resumen_dia. `setdefault` conserva el
    # primero, y como vienen ordenados por id, ese es el turno más antiguo:
    # el mismo criterio que usa `fondo_del_dia`.
    filtro_suc_turno = (
        [] if solo_sucursal is None
        else [TurnoCaja.sucursal_id == solo_sucursal]
    )
    fondos = {}
    for t in TurnoCaja.query.filter(
        TurnoCaja.tenant_id == tenant_id,
        TurnoCaja.fecha >= desde, TurnoCaja.fecha <= hasta,
        *filtro_suc_turno,
    ).order_by(TurnoCaja.id).all():
        fondos.setdefault(
            (t.fecha, t.sucursal_id if separa else None),
            _fondo_normalizado(t),
        )

    # Un día con fondo declarado y sin un solo movimiento también es una fila.
    # Antes del fondo ese día era genuinamente cero y omitirlo estaba bien; ahora
    # hay dinero real en el cajón, y "qué días nadie cerró" es justamente la
    # señal más valiosa de este reporte. Espejo del bucle que siembra `dias`
    # desde `cortes`, unas líneas más abajo.
    for fecha_fondo, suc_fondo in fondos:
        _dia(fecha_fondo, suc_fondo)

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

        # El fondo entra en el esperado también aquí. Sin esto, el delta contra
        # la foto firmada saldría exactamente igual a menos el fondo, y el
        # histórico anunciaría "movimientos posteriores" en un día que nadie
        # tocó. Va antes de `hay_movimientos_posteriores`, que compara esta
        # misma clave contra la congelada.
        d["fondo_inicial"] = fondos.get(clave, 0.0)
        vivo_esperado = round(d["fondo_inicial"] + d["total_efectivo"]
                              - d["salidas_efectivo"], 2)
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
                "fondo_inicial": corte.fondo_inicial,
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


def exigir_turno_abierto(tenant_id, usuario, fecha, sucursal_id, *,
                         es_admin=False):
    """Frena la captura de quien no abrió su caja.

    Es el guardián que le da un dueño a la sucursal y a la fecha. Sin él, cada
    pantalla vuelve a adivinarlas por su cuenta, que fue exactamente el origen
    del bug en el que la recepcionista veía ceros todo el día.

    El admin pasa, igual que en `exigir_dia_abierto`: alguien tiene que poder
    corregir un movimiento mal fechado, y el histórico ya marca esos días como
    "con movimientos posteriores".
    """
    if es_admin:
        return

    turno = turno_vigente(tenant_id, usuario.id)
    if turno is None:
        raise CajaError(
            "Abre tu caja para empezar a capturar",
            codigo="sin_turno",
        )

    if fecha != date.today():
        raise CajaError(
            "Solo puedes capturar movimientos de hoy",
            codigo="fecha_fuera_de_turno",
        )

    if sucursal_separa_cajas(tenant_id) and sucursal_id != turno.sucursal_id:
        nombre = turno.sucursal.nombre if turno.sucursal else "Sin sucursal"
        raise CajaError(
            f"Hoy estás trabajando en {nombre}",
            codigo="sucursal_fuera_de_turno",
        )
