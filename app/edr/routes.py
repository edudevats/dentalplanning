from flask import Blueprint, request, jsonify, g
from marshmallow import ValidationError
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.edr.models import Ingreso, GastoOperativo, PagoDoctor, PagoComisionIngreso
from app.edr.schemas import (
    IngresoSchema,
    VisitaSchema,
    GastoOperativoSchema,
    PagoDoctorSchema,
    ComisionPagoSchema,
)
from app.facturacion.services import recalcular_total, FacturacionError
from app.facturacion.models import TICKET_SIN_TIMBRAR
from app.ajustes.models import Especialista
from app.configuracion.models import ConfigConsultorio
# parse_mes y ganancia_tratamiento viven en el núcleo contable unificado
from app.engine.accounting import parse_mes as _parse_mes, ganancia_tratamiento, filtro_mes
from app.crm.services import (
    crm_activo, sincronizar_visita_ingreso, eliminar_visita_ingreso, CrmError,
)

edr_bp = Blueprint("edr", __name__, url_prefix="/api/v1/edr")


def _enrich_ingreso(ingreso):
    data = IngresoSchema().dump(ingreso)
    data["especialista_nombre"] = ingreso.especialista.nombre if ingreso.especialista else None
    data["metodo_pago_nombre"] = ingreso.metodo_pago.nombre if ingreso.metodo_pago else None
    data["estrategia_nombre"] = ingreso.estrategia.nombre if ingreso.estrategia else None
    data["cupon_codigo"] = ingreso.cupon.codigo if ingreso.cupon else None
    tk = ingreso.ticket
    data["ticket_id"] = tk.id if tk else None
    data["ticket_folio"] = tk.folio if tk else None
    data["ticket_folio_display"] = tk.folio_display if tk else None
    return data


# ── INGRESOS ──

@edr_bp.route("/ingresos", methods=["GET"])
@require_auth
def listar_ingresos():
    year, month = _parse_mes(request.args.get("mes"))
    # eager-load las relaciones que _enrich_ingreso lee por fila
    ingresos = Ingreso.query.options(
        joinedload(Ingreso.especialista),
        joinedload(Ingreso.metodo_pago),
        joinedload(Ingreso.estrategia),
        joinedload(Ingreso.ticket),
        joinedload(Ingreso.cupon),
    ).filter(
        Ingreso.tenant_id == g.tenant_id,
        *filtro_mes(Ingreso.fecha, year, month),
    ).order_by(Ingreso.fecha).all()

    return jsonify([_enrich_ingreso(i) for i in ingresos])


@edr_bp.route("/ingresos", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista")
def crear_ingreso():
    """Alta de UN ingreso. El alta de varios vive en /ingresos/visita.

    Se conserva tal cual porque cobranza lo usa para los pagos de un plan.
    """
    body = request.get_json() or {}
    ticket_folio = body.get("ticket_folio")
    data = IngresoSchema().load(body)

    linea = {k: data.pop(k, None) for k in
             ("tratamiento_id", "nombre_tratamiento", "monto", "comision_doctor",
              "cupon_codigo")}

    from app.caja import services as caja_services
    from app.edr.services import crear_ingresos_visita, EdrError
    try:
        ingresos, _, _ = crear_ingresos_visita(
            g.tenant_id, g.current_user, data, [linea], ticket_folio,
        )
    except caja_services.CajaError as exc:
        db.session.rollback()
        return jsonify({"error": exc.mensaje, "codigo": exc.codigo}), 409
    except (CrmError, EdrError) as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
    except FacturacionError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(_enrich_ingreso(ingresos[0])), 201


@edr_bp.route("/ingresos/visita", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista")
def crear_visita():
    """Alta de una visita: varios tratamientos en un solo movimiento.

    El paciente vino una vez, pagó una vez y se lleva un solo ticket; por
    dentro sigue siendo un ingreso por tratamiento, que es lo que necesitan el
    IVA por concepto y los pagos a doctores.
    """
    body = request.get_json() or {}
    data = VisitaSchema().load(body)
    lineas = data.pop("lineas")
    ticket_folio = body.get("ticket_folio")

    from app.caja import services as caja_services
    from app.edr.services import crear_ingresos_visita, EdrError
    try:
        ingresos, visita_uid, ticket = crear_ingresos_visita(
            g.tenant_id, g.current_user, data, lineas, ticket_folio,
        )
    except caja_services.CajaError as exc:
        db.session.rollback()
        return jsonify({"error": exc.mensaje, "codigo": exc.codigo}), 409
    except (CrmError, EdrError) as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
    except FacturacionError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify({
        "ingresos": [_enrich_ingreso(i) for i in ingresos],
        "visita_uid": visita_uid,
        "ticket_id": ticket.id if ticket else None,
        "ticket_folio_display": ticket.folio_display if ticket else None,
    }), 201


@edr_bp.route("/ingresos/<int:ingreso_id>", methods=["PUT"])
@require_auth
@require_role("admin", "recepcionista")
def actualizar_ingreso(ingreso_id):
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()

    # La regla vive en cobranza (import local para no cargar el módulo de más);
    # aquí sólo se consulta, así la dependencia apunta en una sola dirección.
    from app.cobranza.services import ingreso_bloqueado_para_edicion
    bloqueo = ingreso_bloqueado_para_edicion(ingreso)
    if bloqueo:
        return jsonify({"error": bloqueo}), 400

    if ingreso.ticket and ingreso.ticket.estado != TICKET_SIN_TIMBRAR:
        return jsonify({
            "error": "Este ingreso ya fue facturado (timbrado); no se puede modificar."
        }), 400

    schema = IngresoSchema(partial=True)
    data = schema.load(request.get_json() or {})

    # Import local: app.caja.services importa de app.edr.models, y un import a
    # nivel de módulo aquí crearía un ciclo.
    from app.caja import services as caja_services
    es_admin = g.current_user.role == "admin"
    destino_fecha = data.get("fecha", ingreso.fecha)
    # "sucursal_id" in data, no .get(): mover un ingreso a "sin sucursal" manda
    # None explícito, y .get() no distinguiría eso de "no lo mandaron".
    destino_sucursal = (data["sucursal_id"] if "sucursal_id" in data
                        else ingreso.sucursal_id)
    # Solo los dos pares REALES: donde el ingreso está y a dónde va. El
    # producto cartesiano de fechas x sucursales evaluaba combinaciones que
    # nunca existieron (p. ej. la fecha origen con la sucursal destino) y
    # bloqueaba ediciones legítimas citando un corte ajeno al movimiento.
    pares = {(ingreso.fecha, ingreso.sucursal_id),
             (destino_fecha, destino_sucursal)}
    try:
        for f, s in pares:
            caja_services.exigir_dia_abierto(g.tenant_id, s, f, es_admin=es_admin)
        # Editar también es capturar: el PUT mueve dinero de día y de sucursal,
        # así que el turno manda sobre el destino igual que sobre un alta. Va
        # después del día por el mismo motivo que en `crear_ingreso`: un día
        # cerrado se explica solo, y explicarlo como "sin turno" sería mandar a
        # la recepcionista a abrir una caja que ese día ya no admite.
        caja_services.exigir_turno_abierto(
            g.tenant_id, g.current_user, destino_fecha, destino_sucursal,
            es_admin=es_admin,
        )
    except caja_services.CajaError as exc:
        return jsonify({"error": exc.mensaje, "codigo": exc.codigo}), 409

    if data.get("paciente_id") and not crm_activo(g.tenant_id):
        data.pop("paciente_id")

    # El cupón sólo se revalida si CAMBIÓ. Si no, un ingreso viejo con un cupón
    # ya vencido o agotado sería imposible de corregir: bastaría querer
    # arreglarle los comentarios para quedar atorado.
    actual = ingreso.cupon.codigo if ingreso.cupon else ""
    if "cupon_codigo" in data:
        from app.ajustes.services import normalizar_codigo
        codigo = normalizar_codigo(data.pop("cupon_codigo"))
    else:
        codigo = actual

    # La exclusión mutua se valida SIEMPRE contra el resultado FINAL de este
    # PUT, cambie o no el código: antes este chequeo vivía dentro de
    # `if codigo != actual`, así que un PUT que sólo agregaba
    # `descuento_pct` a un ingreso que YA tenía cupón (sin tocar
    # `cupon_codigo`) se colaba y la fila terminaba con las dos cosas a la
    # vez. Esto es una pregunta distinta de "revalidar el cupón contra el
    # catálogo" (que sigue yendo sólo cuando el código cambió, más abajo).
    if codigo and data.get("descuento_pct", ingreso.descuento_pct):
        return jsonify({
            "error": "Una línea con cupón no puede llevar además "
                     "un descuento de visita"
        }), 400

    if codigo != actual:
        from app.ajustes.services import DescuentosError, aplicar_cupon, validar_cupon
        # `ingreso.monto` ya es el NETO si el ingreso traía cupón. El
        # precio de lista es lo que mandó el cliente (si mandó `monto`)
        # o, si no, se reconstruye sumando lo ya descontado -- para eso
        # existe `descuento_monto`. "monto" in data, no .get(): así no
        # se confunde "no lo mandaron" con "lo mandaron en 0".
        precio_lista = (
            data["monto"] if "monto" in data
            else ingreso.monto + ingreso.descuento_monto
        )
        if not codigo:
            ingreso.cupon_id = None
            ingreso.descuento_monto = 0
            data["monto"] = precio_lista
        else:
            try:
                cupon = validar_cupon(
                    g.tenant_id, codigo,
                    data.get("tratamiento_id", ingreso.tratamiento_id),
                    data.get("fecha", ingreso.fecha),
                    bloquear=True,
                )
                # `monto` llega como el precio ANTES del cupón, igual que
                # en el alta.
                neto, descuento = aplicar_cupon(precio_lista, cupon)
            except DescuentosError as e:
                return jsonify({"error": str(e)}), 400
            ingreso.cupon_id = cupon.id
            ingreso.descuento_monto = descuento
            data["monto"] = neto

    for key, value in data.items():
        setattr(ingreso, key, value)

    if crm_activo(g.tenant_id):
        try:
            sincronizar_visita_ingreso(ingreso)
        except CrmError as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    if ingreso.ticket:
        recalcular_total(ingreso.ticket)
    db.session.commit()
    return jsonify(_enrich_ingreso(ingreso))


@edr_bp.route("/ingresos/<int:ingreso_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_ingreso(ingreso_id):
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()

    # Borrarlo aquí dejaba `pago.ingreso_id` en NULL sin fallar: el plan seguía
    # creyendo que cobró y el ticket salía corto. `eliminar_pago` de cobranza sí
    # valida ticket asignado y comisión ya pagada.
    from app.cobranza.services import ingreso_bloqueado_para_edicion
    bloqueo = ingreso_bloqueado_para_edicion(ingreso)
    if bloqueo:
        return jsonify({"error": bloqueo}), 400

    ticket = ingreso.ticket
    if ticket and ticket.estado != TICKET_SIN_TIMBRAR:
        return jsonify({
            "error": "Este ingreso ya fue facturado; no se puede eliminar."
        }), 400

    PagoComisionIngreso.query.filter_by(
        ingreso_id=ingreso.id, tenant_id=g.tenant_id
    ).delete()

    eliminar_visita_ingreso(g.tenant_id, ingreso.id)

    db.session.delete(ingreso)
    db.session.flush()

    if ticket:
        restantes = Ingreso.query.filter_by(ticket_id=ticket.id).count()
        if restantes == 0:
            db.session.delete(ticket)
        else:
            recalcular_total(ticket)

    db.session.commit()
    return jsonify({"message": "Ingreso eliminado"})


# ── GASTOS OPERATIVOS ──

def _resolver_metodo(metodo_pago_id):
    """El método debe existir y ser del tenant. Devuelve el objeto o None."""
    from app.ajustes.models import MetodoPago
    if metodo_pago_id is None:
        return None
    return MetodoPago.query.filter_by(
        id=metodo_pago_id, tenant_id=g.tenant_id).first()


def _resolver_salida_caja(metodo, propuesto):
    """Qué baja el efectivo del cajón.

    No es un campo que el usuario llene a mano: si el método no es efectivo,
    es False sin excepción. Si lo es, True salvo que el admin lo desmarque —
    el caso "pagué en efectivo pero de la caja fuerte, no del cajón".
    """
    from app.ajustes.models import TIPO_EFECTIVO
    if metodo is None or metodo.tipo != TIPO_EFECTIVO:
        return False
    return True if propuesto is None else bool(propuesto)


def _enrich_gasto(gasto, schema=None):
    schema = schema or GastoOperativoSchema()
    data = schema.dump(gasto)
    data["metodo_pago_nombre"] = gasto.metodo_pago.nombre if gasto.metodo_pago else None
    data["metodo_pago_tipo"] = gasto.metodo_pago.tipo if gasto.metodo_pago else None
    return data


@edr_bp.route("/gastos", methods=["GET"])
@require_auth
def listar_gastos():
    year, month = _parse_mes(request.args.get("mes"))
    # eager-load el método para no hacer una consulta por fila en _enrich_gasto
    gastos = GastoOperativo.query.options(
        joinedload(GastoOperativo.metodo_pago),
    ).filter(
        GastoOperativo.tenant_id == g.tenant_id,
        *filtro_mes(GastoOperativo.fecha, year, month),
    ).order_by(GastoOperativo.fecha).all()

    schema = GastoOperativoSchema()
    return jsonify([_enrich_gasto(x, schema) for x in gastos])


@edr_bp.route("/gastos", methods=["POST"])
@require_auth
@require_role("admin")
def crear_gasto():
    schema = GastoOperativoSchema()
    try:
        data = schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Datos inválidos", "detalles": err.messages}), 400

    # Aquí NO hay `exigir_dia_abierto`, y no es descuido: la ruta es admin-only
    # y el admin está exento de ese candado. El del turno sí aplica, porque
    # `require_role` deja pasar al asistente antes de mirar la lista de roles
    # (app/middleware/tenant.py) y el menú le ofrece /gastos si tiene el permiso
    # `edr.gastos`. Un asistente no es admin, así que el turno lo alcanza.
    # Import local: app.caja.services importa de app.edr.models, y un import a
    # nivel de módulo aquí crearía un ciclo.
    from app.caja import services as caja_services
    try:
        caja_services.exigir_turno_abierto(
            g.tenant_id, g.current_user, data["fecha"],
            data.get("sucursal_id"),
            es_admin=g.current_user.role == "admin",
        )
    except caja_services.CajaError as exc:
        return jsonify({"error": exc.mensaje, "codigo": exc.codigo}), 409

    metodo = _resolver_metodo(data.get("metodo_pago_id"))
    if metodo is None:
        return jsonify({
            "error": "Datos inválidos",
            "detalles": {"metodo_pago_id": ["Método de pago no válido"]},
        }), 400
    data["sale_de_caja"] = _resolver_salida_caja(metodo, data.get("sale_de_caja"))
    gasto = GastoOperativo(tenant_id=g.tenant_id, created_by=g.current_user.id, **data)
    db.session.add(gasto)
    db.session.commit()
    return jsonify(_enrich_gasto(gasto)), 201


@edr_bp.route("/gastos/<int:gasto_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_gasto(gasto_id):
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=g.tenant_id
    ).first_or_404()
    schema = GastoOperativoSchema(partial=True)
    try:
        data = schema.load(request.get_json() or {})
    except ValidationError as err:
        return jsonify({"error": "Datos inválidos", "detalles": err.messages}), 400

    # Mismo razonamiento que en `crear_gasto`: admin-only para la lista de
    # roles, pero el asistente con permiso `edr.gastos` entra por un costado y
    # el turno es lo único que le pone fecha y sucursal.
    from app.caja import services as caja_services
    try:
        caja_services.exigir_turno_abierto(
            g.tenant_id, g.current_user,
            data.get("fecha", gasto.fecha),
            data.get("sucursal_id", gasto.sucursal_id),
            es_admin=g.current_user.role == "admin",
        )
    except caja_services.CajaError as exc:
        return jsonify({"error": exc.mensaje, "codigo": exc.codigo}), 409

    from app.ajustes.models import TIPO_EFECTIVO
    # El método ANTES de aplicar el PUT: hace falta para saber si el False
    # guardado fue una decisión del admin o solo la consecuencia de que el
    # método no era efectivo.
    metodo_previo = _resolver_metodo(gasto.metodo_pago_id)
    previo_era_efectivo = (metodo_previo is not None
                          and metodo_previo.tipo == TIPO_EFECTIVO)

    # El método puede haber cambiado en este PUT o venir del gasto existente.
    # Se valida ANTES de mutar `gasto` con el loop de abajo: si no, el setattr
    # deja un FK posiblemente ajeno a medio aplicar y puede disparar un
    # autoflush con ese valor inválido antes de que lo rechacemos.
    nuevo_metodo_id = data.get("metodo_pago_id", gasto.metodo_pago_id)
    metodo = _resolver_metodo(nuevo_metodo_id)
    if nuevo_metodo_id is not None and metodo is None:
        return jsonify({
            "error": "Datos inválidos",
            "detalles": {"metodo_pago_id": ["Método de pago no válido"]},
        }), 400

    for key, value in data.items():
        setattr(gasto, key, value)

    # Si el PUT no manda `sale_de_caja`, se PRESERVA el valor guardado SOLO si
    # el método anterior ya era de tipo efectivo -si no, ese False nunca fue
    # una decisión de nadie, era la consecuencia forzada del método anterior,
    # y al corregir el método el default debe volver a aplicar. Si sí manda
    # `sale_de_caja`, es una decisión de este PUT y tiene prioridad: preservar
    # el valor guardado en ese caso revertiría en silencio la decisión del
    # admin y a la recepcionista le aparecería un faltante que no es suyo.
    if "sale_de_caja" in data:
        propuesto = data["sale_de_caja"]
    elif previo_era_efectivo:
        propuesto = gasto.sale_de_caja
    else:
        propuesto = None
    gasto.sale_de_caja = _resolver_salida_caja(metodo, propuesto)
    db.session.commit()
    return jsonify(_enrich_gasto(gasto))


@edr_bp.route("/gastos/<int:gasto_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_gasto(gasto_id):
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=g.tenant_id
    ).first_or_404()

    from app.cobranza.models import Devolucion
    if Devolucion.query.filter_by(tenant_id=g.tenant_id, gasto_id=gasto.id).first():
        return jsonify({
            "error": "Este gasto es la devolución de un plan. Elimínala desde la cotización."
        }), 409

    db.session.delete(gasto)
    db.session.commit()
    return jsonify({"message": "Gasto eliminado"})


# ── PAGOS A DOCTORES ──

@edr_bp.route("/pagos-doctores", methods=["GET"])
@require_auth
def listar_pagos():
    year, month = _parse_mes(request.args.get("mes"))
    pagos = PagoDoctor.query.options(
        joinedload(PagoDoctor.especialista)
    ).filter(
        PagoDoctor.tenant_id == g.tenant_id,
        *filtro_mes(PagoDoctor.fecha, year, month),
    ).order_by(PagoDoctor.fecha).all()

    result = []
    for p in pagos:
        data = PagoDoctorSchema().dump(p)
        data["especialista_nombre"] = p.especialista.nombre if p.especialista else None
        result.append(data)
    return jsonify(result)


@edr_bp.route("/pagos-doctores", methods=["POST"])
@require_auth
@require_role("admin")
def crear_pago():
    schema = PagoDoctorSchema()
    data = schema.load(request.get_json() or {})
    pago = PagoDoctor(tenant_id=g.tenant_id, **data)
    db.session.add(pago)
    db.session.commit()
    return jsonify(schema.dump(pago)), 201


@edr_bp.route("/pagos-doctores/<int:pago_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_pago(pago_id):
    pago = PagoDoctor.query.filter_by(
        id=pago_id, tenant_id=g.tenant_id
    ).first_or_404()
    schema = PagoDoctorSchema(partial=True)
    data = schema.load(request.get_json() or {})
    for key, value in data.items():
        setattr(pago, key, value)
    db.session.commit()
    return jsonify(PagoDoctorSchema().dump(pago))


@edr_bp.route("/pagos-doctores/<int:pago_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_pago(pago_id):
    pago = PagoDoctor.query.filter_by(
        id=pago_id, tenant_id=g.tenant_id
    ).first_or_404()
    # Si el pago liquidó comisiones, soltar las ligas: esos ingresos vuelven a
    # quedar pendientes.
    PagoComisionIngreso.query.filter_by(
        pago_id=pago.id, tenant_id=g.tenant_id
    ).delete()
    db.session.delete(pago)
    db.session.commit()
    return jsonify({"message": "Pago eliminado"})


# ── COMISIONES PENDIENTES ──

def _ingresos_liquidados_ids(tenant_id):
    """Set de ingreso_id que ya tienen su comisión liquidada (tenant)."""
    filas = PagoComisionIngreso.query.filter_by(tenant_id=tenant_id).all()
    return {f.ingreso_id for f in filas}


def _reversiones_no_pagadas_por_ingreso(tenant_id):
    """{ingreso_id: comisión revertida NO pagada} (para restar de pendientes)."""
    from app.cobranza.models import ComisionReversion
    out = {}
    q = ComisionReversion.query.filter_by(
        tenant_id=tenant_id, pagada_al_revertir=False,
    ).all()
    for r in q:
        out[r.ingreso_id] = round(out.get(r.ingreso_id, 0) + r.monto, 2)
    return out


def _saldo_negativo_por_doctor(tenant_id):
    """{especialista_id: saldo negativo} = reversiones ya pagadas − descuentos
    ya aplicados en PagoDoctor. Solo positivos (lo que el doctor aún debe)."""
    from app.cobranza.models import ComisionReversion
    deuda = {}
    revs = ComisionReversion.query.filter_by(
        tenant_id=tenant_id, pagada_al_revertir=True,
    ).all()
    for r in revs:
        esp = r.ingreso.especialista_id if r.ingreso else None
        if esp is None:
            continue
        deuda[esp] = round(deuda.get(esp, 0) + r.monto, 2)
    aplicado = {}
    pagos = PagoDoctor.query.filter_by(tenant_id=tenant_id).all()
    for p in pagos:
        if p.descuento_saldo:
            aplicado[p.especialista_id] = round(
                aplicado.get(p.especialista_id, 0) + p.descuento_saldo, 2)
    return {
        esp: max(0.0, round(monto - aplicado.get(esp, 0), 2))
        for esp, monto in deuda.items()
    }


@edr_bp.route("/comisiones/pendientes", methods=["GET"])
@require_auth
def comisiones_pendientes():
    """Todas las comisiones sin liquidar (de cualquier mes), agrupadas por doctor.

    Una comisión está pendiente si su Ingreso tiene comision_doctor > 0 y no
    tiene fila en pago_comision_ingreso.
    """
    especialista_filtro = request.args.get("especialista_id", type=int)
    origen = (request.args.get("origen") or "todos").strip().lower()
    if origen not in ("todos", "contado", "plan"):
        return jsonify({
            "error": "origen debe ser todos, contado o plan"
        }), 400

    # Import local para conservar al EDR utilizable aunque el add-on de
    # cobranza no esté habilitado para el tenant.
    from app.cobranza.models import Cotizacion, Pago as PagoCobranza

    liquidados = _ingresos_liquidados_ids(g.tenant_id)
    reversiones_no_pagadas = _reversiones_no_pagadas_por_ingreso(g.tenant_id)
    saldos = _saldo_negativo_por_doctor(g.tenant_id)

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
        Ingreso.tenant_id == g.tenant_id,
        Ingreso.comision_doctor > 0,
        Ingreso.especialista_id.isnot(None),
    )
    if origen == "plan":
        q = q.filter(Ingreso.cobranza_pago.has())
    elif origen == "contado":
        q = q.filter(~Ingreso.cobranza_pago.has())
    if especialista_filtro:
        q = q.filter(Ingreso.especialista_id == especialista_filtro)
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
    # orígenes, y respetando el filtro de especialista si vino en la query.
    if origen == "todos":
        for esp_id, saldo in saldos.items():
            if especialista_filtro and esp_id != especialista_filtro:
                continue
            if saldo > 0 and esp_id not in por_doctor:
                esp = Especialista.query.filter_by(id=esp_id, tenant_id=g.tenant_id).first()
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

    return jsonify({
        "origen": origen,
        "total_pendiente": round(total_pendiente, 2),
        "doctores": doctores,
    })


@edr_bp.route("/comisiones/pagar", methods=["POST"])
@require_auth
@require_role("admin")
def pagar_comisiones():
    """Liquida las comisiones de los ingresos indicados en una sola fecha.

    Crea un PagoDoctor (tipo comisión) en la fecha elegida + filas puente que
    ligan ese pago a cada ingreso. Atómico: si algo no valida, no crea nada.
    """
    data = ComisionPagoSchema().load(request.get_json() or {})
    especialista_id = data["especialista_id"]
    fecha = data["fecha"]
    ingreso_ids = data["ingreso_ids"]

    # El especialista debe pertenecer al tenant.
    esp = Especialista.query.filter_by(
        id=especialista_id, tenant_id=g.tenant_id
    ).first()
    if not esp:
        return jsonify({"error": "Especialista no encontrado"}), 400

    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        Ingreso.id.in_(ingreso_ids),
    ).all()

    # Validar que todos existan, sean del doctor y tengan comisión.
    if len(ingresos) != len(set(ingreso_ids)):
        return jsonify({"error": "Algún ingreso no existe o no es de este consultorio"}), 400
    for i in ingresos:
        if i.especialista_id != especialista_id:
            return jsonify({"error": "Algún ingreso no pertenece al especialista indicado"}), 400
        if not (i.comision_doctor and i.comision_doctor > 0):
            return jsonify({"error": "Algún ingreso no tiene comisión por pagar"}), 400

    # Ninguno debe estar ya liquidado.
    ya_liquidados = _ingresos_liquidados_ids(g.tenant_id)
    if any(i.id in ya_liquidados for i in ingresos):
        return jsonify({"error": "Alguna comisión ya fue pagada"}), 400

    # Rechazar comisiones totalmente revertidas por una devolución (no se pagan)
    # y calcular de una sola vez el NETO por ingreso (bruto - reversión no
    # pagada), reutilizándolo para el total y para las filas puente: así el
    # doctor nunca cobra sobre dinero ya devuelto al paciente.
    reversiones = _reversiones_no_pagadas_por_ingreso(g.tenant_id)
    pendientes_por_ingreso = {}
    for i in ingresos:
        pend = round((i.comision_doctor or 0) - reversiones.get(i.id, 0), 2)
        if pend <= 0:
            return jsonify({
                "error": "Alguna comisión fue revertida por una devolución"
            }), 400
        pendientes_por_ingreso[i.id] = pend

    total = round(sum(pendientes_por_ingreso.values()), 2)

    # Descontar el saldo negativo del doctor (reversiones de comisión ya pagadas).
    saldo = _saldo_negativo_por_doctor(g.tenant_id).get(especialista_id, 0.0)
    descuento = round(min(saldo, total), 2)
    neto = round(total - descuento, 2)

    pago = PagoDoctor(
        tenant_id=g.tenant_id,
        fecha=fecha,
        especialista_id=especialista_id,
        concepto=f"Pago de {len(ingresos)} comisión(es)",
        tipo="comision",
        monto=neto,
        descuento_saldo=descuento,
    )
    db.session.add(pago)
    db.session.flush()  # obtener pago.id

    for i in ingresos:
        db.session.add(PagoComisionIngreso(
            tenant_id=g.tenant_id,
            pago_id=pago.id,
            ingreso_id=i.id,
            monto=pendientes_por_ingreso[i.id],
        ))

    db.session.commit()
    return jsonify(PagoDoctorSchema().dump(pago)), 201


def _comision_pendiente_o_error(ingreso_id):
    """(ingreso, pendiente_neto, None) si la comisión se puede tocar.

    Devuelve (None, 0.0, respuesta_de_error) si el ingreso no tiene comisión,
    si ya se liquidó o si una devolución ya la revirtió por completo.
    """
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()

    if not (ingreso.comision_doctor and ingreso.comision_doctor > 0):
        return None, 0.0, (jsonify({
            "error": "Este ingreso no tiene comisión."
        }), 400)
    if ingreso.id in _ingresos_liquidados_ids(g.tenant_id):
        return None, 0.0, (jsonify({
            "error": "Esa comisión ya fue pagada; no se puede modificar."
        }), 400)

    revertido = _reversiones_no_pagadas_por_ingreso(g.tenant_id).get(ingreso.id, 0)
    pendiente = round((ingreso.comision_doctor or 0) - revertido, 2)
    if pendiente <= 0:
        return None, 0.0, (jsonify({
            "error": "Esa comisión fue revertida por una devolución."
        }), 400)
    return ingreso, pendiente, None


@edr_bp.route("/comisiones/<int:ingreso_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def editar_comision(ingreso_id):
    """Ajusta a mano la comisión pendiente de un ingreso.

    Existe porque un doctor puede negociar una comisión mayor a la que calculó
    su porcentaje, y hasta ahora la única salida era capturar un pago suelto
    —que dejaba la comisión original marcada como pendiente para siempre.
    """
    ingreso, _, error = _comision_pendiente_o_error(ingreso_id)
    if error:
        return error

    try:
        monto = round(float((request.get_json() or {}).get("comision_doctor")), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "comision_doctor debe ser un número"}), 400
    if monto <= 0:
        return jsonify({
            "error": "La comisión debe ser mayor a cero. "
                     "Si no aplica, elimínala del recuadro."
        }), 400

    delta = round(monto - (ingreso.comision_doctor or 0), 2)
    ingreso.comision_doctor = monto

    # Un plan reparte su comisión total entre los abonos: si el total no sube
    # con el ajuste, los abonos que falten se recortan para cuadrar al total
    # viejo y el aumento se le quitaría al propio doctor más adelante.
    from app.cobranza.services import absorber_ajuste_de_comision
    absorber_ajuste_de_comision(ingreso, delta)

    db.session.commit()
    return jsonify({"ingreso_id": ingreso.id, "comision_doctor": monto})


@edr_bp.route("/comisiones/<int:ingreso_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def saldar_comision(ingreso_id):
    """Saca una comisión del recuadro de pendientes sin generar gasto.

    Para cuando ya se pagó por fuera (p. ej. el monto negociado, capturado como
    un pago suelto): ese gasto ya está registrado, así que duplicarlo aquí
    contaría la comisión dos veces. `Ingreso.comision_doctor` queda intacto —la
    ganancia neta del tratamiento no se mueve— y sólo se escribe la fila puente
    sin PagoDoctor, que es como el modelo ya representa una comisión liquidada
    fuera de un pago.
    """
    ingreso, pendiente, error = _comision_pendiente_o_error(ingreso_id)
    if error:
        return error

    nota = ((request.get_json(silent=True) or {}).get("nota") or "").strip()
    db.session.add(PagoComisionIngreso(
        tenant_id=g.tenant_id,
        pago_id=None,
        ingreso_id=ingreso.id,
        monto=pendiente,
        nota=nota[:200] or None,
    ))
    db.session.commit()
    return jsonify({"message": "Comisión marcada como saldada"})


# ── COMISIONES YA PAGADAS ──

def _concepto_automatico(concepto):
    """¿El concepto es el que genera /comisiones/pagar, o lo escribió alguien?"""
    concepto = (concepto or "").strip()
    return concepto.startswith("Pago de ") and concepto.endswith("comisión(es)")


def _reajustar_pago(pago):
    """Recalcula el PagoDoctor con las comisiones que le quedan ligadas.

    Devuelve True si se quedó sin ninguna y se eliminó. Así el gasto del mes
    siempre vale lo que el doctor realmente cobró, sin cuadres a mano.
    """
    restantes = PagoComisionIngreso.query.filter_by(
        pago_id=pago.id, tenant_id=g.tenant_id
    ).all()
    if not restantes:
        db.session.delete(pago)
        return True

    total = round(sum(liq.monto for liq in restantes), 2)
    # El descuento de saldo negativo no puede pasarse del total que queda.
    descuento = round(min(pago.descuento_saldo or 0.0, total), 2)
    pago.descuento_saldo = descuento
    pago.monto = round(total - descuento, 2)
    if _concepto_automatico(pago.concepto):
        pago.concepto = f"Pago de {len(restantes)} comisión(es)"
    return False


def _despagar_reversiones(ingreso_id):
    """La comisión deja de estar pagada: sus reversiones tampoco lo están.

    Si una devolución revirtió una comisión YA pagada, el doctor arrastra un
    saldo negativo. Al deshacer ese pago nunca cobró, así que el saldo sobra.
    """
    from app.cobranza.models import ComisionReversion
    reversiones = ComisionReversion.query.filter_by(
        tenant_id=g.tenant_id, ingreso_id=ingreso_id, pagada_al_revertir=True,
    ).all()
    for rev in reversiones:
        rev.pagada_al_revertir = False


@edr_bp.route("/comisiones/pagadas", methods=["GET"])
@require_auth
def comisiones_pagadas():
    """Comisiones liquidadas por un PagoDoctor con fecha en el mes pedido.

    Agrupadas por doctor, una fila por comisión: es el detalle de la tarjeta
    "Comisiones Pagadas". Las saldadas a mano (sin PagoDoctor) no entran: no
    fueron un pago y no hay gasto que deshacer.
    """
    year, month = _parse_mes(request.args.get("mes"))

    filas = PagoComisionIngreso.query.options(
        joinedload(PagoComisionIngreso.pago).joinedload(PagoDoctor.especialista),
        joinedload(PagoComisionIngreso.ingreso).selectinload(Ingreso.tratamiento),
    ).join(
        PagoDoctor, PagoComisionIngreso.pago_id == PagoDoctor.id
    ).filter(
        PagoComisionIngreso.tenant_id == g.tenant_id,
        *filtro_mes(PagoDoctor.fecha, year, month),
    ).order_by(PagoDoctor.fecha, PagoComisionIngreso.id).all()

    por_doctor = {}
    total_pagado = 0.0
    for liq in filas:
        pago, ingreso = liq.pago, liq.ingreso
        esp_id = pago.especialista_id
        grupo = por_doctor.setdefault(esp_id, {
            "especialista_id": esp_id,
            "especialista_nombre": pago.especialista.nombre if pago.especialista else "—",
            "total_pagado": 0.0,
            "comisiones": [],
        })
        monto = round(liq.monto, 2)
        grupo["comisiones"].append({
            "id": liq.id,
            "ingreso_id": liq.ingreso_id,
            "pago_id": pago.id,
            "fecha_pago": pago.fecha.isoformat(),
            "fecha_ingreso": ingreso.fecha.isoformat() if ingreso else None,
            "paciente": (ingreso.paciente if ingreso else None) or "Paciente",
            "nombre_tratamiento": (
                (ingreso.nombre_tratamiento if ingreso else None)
                or (ingreso.tratamiento.nombre if ingreso and ingreso.tratamiento else None)
                or "Tratamiento"
            ),
            "monto": monto,
            "concepto": pago.concepto,
        })
        grupo["total_pagado"] += monto
        total_pagado += monto

    doctores = sorted(por_doctor.values(), key=lambda d: d["especialista_nombre"])
    for d in doctores:
        d["total_pagado"] = round(d["total_pagado"], 2)

    return jsonify({
        "mes": f"{year}-{month:02d}",
        "total_pagado": round(total_pagado, 2),
        "doctores": doctores,
    })


@edr_bp.route("/comisiones/pagadas/<int:liquidacion_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def borrar_comision_pagada(liquidacion_id):
    """Deshace el pago de UNA comisión. `modo` decide a dónde va después:

    - `pendiente`: se borra la liga y la comisión regresa al recuadro de
      pendientes, lista para volver a pagarse.
    - `permanente`: la liga se queda sin PagoDoctor (como las saldadas a
      mano), así que sale del gasto y tampoco vuelve a pendientes.

    En los dos casos el PagoDoctor se reajusta —o se borra si era su única
    comisión— para que el gasto del mes no cuente dinero que nadie cobró.
    `Ingreso.comision_doctor` no se toca: la ganancia del tratamiento es otra
    cosa.
    """
    modo = (request.args.get("modo") or "").strip().lower()
    if modo not in ("pendiente", "permanente"):
        return jsonify({"error": "modo debe ser pendiente o permanente"}), 400

    liq = PagoComisionIngreso.query.filter_by(
        id=liquidacion_id, tenant_id=g.tenant_id
    ).first_or_404()
    if liq.pago_id is None:
        return jsonify({
            "error": "Esa comisión se saldó a mano, sin pago: no hay nada que "
                     "deshacer aquí."
        }), 400

    pago = liq.pago
    nota = ((request.get_json(silent=True) or {}).get("nota") or "").strip()

    _despagar_reversiones(liq.ingreso_id)
    if modo == "pendiente":
        db.session.delete(liq)
    else:
        liq.pago_id = None
        liq.nota = (nota or "Pago borrado desde comisiones pagadas")[:200]
    db.session.flush()

    pago_id = pago.id
    eliminado = _reajustar_pago(pago)
    db.session.commit()

    return jsonify({
        "message": (
            "La comisión regresó a pendientes"
            if modo == "pendiente" else "Comisión borrada"
        ),
        "pago_eliminado": eliminado,
        "pago_id": None if eliminado else pago_id,
    })


@edr_bp.route("/pagos-doctores/resumen", methods=["GET"])
@require_auth
def resumen_pagos_doctores():
    year, month = _parse_mes(request.args.get("mes"))
    
    # 1. Configuración del consultorio
    config = ConfigConsultorio.query.filter_by(tenant_id=g.tenant_id).first()
    costo_hora = config.costo_hora if config else 0.0

    # 2. Especialistas
    especialistas = Especialista.query.filter_by(tenant_id=g.tenant_id).all()

    # 3. Ingresos (Tratamientos realizados) del mes
    # selectinload del tratamiento (sus materiales ya cargan joined) para evitar
    # el N+1 al calcular costo/ganancia por cada ingreso.
    ingresos = Ingreso.query.options(
        selectinload(Ingreso.tratamiento)
    ).filter(
        Ingreso.tenant_id == g.tenant_id,
        *filtro_mes(Ingreso.fecha, year, month),
    ).all()

    # 4. Pagos a doctores del mes
    pagos = PagoDoctor.query.filter(
        PagoDoctor.tenant_id == g.tenant_id,
        *filtro_mes(PagoDoctor.fecha, year, month),
    ).all()

    # Ingresos ya liquidados (su comisión ya se pagó, cualquier mes).
    liquidados = _ingresos_liquidados_ids(g.tenant_id)

    resumen_doctores = []
    
    total_tratamientos = 0
    total_generado_comisiones = 0
    total_pagado_comisiones = 0
    total_pendiente_comisiones = 0
    total_pagado_salarios = 0
    total_generado = 0
    total_ganancia = 0

    for esp in especialistas:
        # Filtrar ingresos y pagos del especialista
        ingresos_esp = [i for i in ingresos if i.especialista_id == esp.id]
        pagos_esp = [p for p in pagos if p.especialista_id == esp.id]

        tratamientos_count = len(ingresos_esp)
        comision_pagada = sum(p.monto for p in pagos_esp if p.tipo == "comision")
        salario_pagado = sum(p.monto for p in pagos_esp if p.tipo == "salario")
        total_gen_esp = sum(i.monto for i in ingresos_esp)
        comision_generada = sum(i.comision_doctor or 0.0 for i in ingresos_esp)

        total_ganancia_esp = 0
        detalle_tratamientos = []

        for i in ingresos_esp:
            costo_consultorio = 0
            costo_materiales = 0
            if i.tratamiento:
                horas = i.tratamiento.horas_invertidas or 1.0
                costo_consultorio = horas * costo_hora
                
                # Calcular costo materiales
                for tm in i.tratamiento.materiales:
                    if tm.material:
                        costo_materiales += (tm.material.costo_unitario or 0.0) * (tm.cantidad or 0.0)
            
            comision_bancaria = i.comision_bancaria or 0.0
            comision_doctor = i.comision_doctor or 0.0

            # Misma fórmula de ganancia que el motor de precios (planeación)
            ganancia_neta_tx = ganancia_tratamiento(
                i.monto,
                costo_materiales=costo_materiales,
                comision_bancaria=comision_bancaria,
                comision_especialista=comision_doctor,
                costo_consultorio=costo_consultorio,
            )

            total_ganancia_esp += ganancia_neta_tx

            detalle_tratamientos.append({
                "fecha": i.fecha.isoformat(),
                "paciente": i.paciente or "Paciente",
                "nombre_tratamiento": i.nombre_tratamiento or (i.tratamiento.nombre if i.tratamiento else "Tratamiento"),
                "monto": round(i.monto, 2),
                "comision_doctor": round(comision_doctor, 2),
                "ganancia": round(ganancia_neta_tx, 2)
            })

        # Redondear valores
        comision_pagada = round(comision_pagada, 2)
        salario_pagado = round(salario_pagado, 2)
        total_gen_esp = round(total_gen_esp, 2)
        total_ganancia_esp = round(total_ganancia_esp, 2)
        comision_generada = round(comision_generada, 2)
        # Pendiente = comisión de ingresos de ESTE mes aún no liquidados
        # (por-ingreso, no aritmética generada-pagada del mes).
        comision_pendiente = round(sum(
            i.comision_doctor or 0.0
            for i in ingresos_esp
            if i.id not in liquidados
        ), 2)

        # Agregar al total general si el doctor tiene actividad o pagos en el mes
        if esp.is_active or tratamientos_count > 0 or comision_pagada > 0 or salario_pagado > 0:
            resumen_doctores.append({
                "especialista_id": esp.id,
                "especialista_nombre": esp.nombre,
                "tratamientos_count": tratamientos_count,
                "comision_generada": comision_generada,
                "comision_pagada": comision_pagada,
                "comision_pendiente": comision_pendiente,
                "salario_pagado": salario_pagado,
                "total_generado": total_gen_esp,
                "total_ganancia_generada": total_ganancia_esp,
                "detalle_tratamientos": detalle_tratamientos
            })

            total_tratamientos += tratamientos_count
            total_generado_comisiones += comision_generada
            total_pagado_comisiones += comision_pagada
            total_pendiente_comisiones += comision_pendiente
            total_pagado_salarios += salario_pagado
            total_generado += total_gen_esp
            total_ganancia += total_ganancia_esp

    return jsonify({
        "mes": f"{year}-{month:02d}",
        "resumen_doctores": resumen_doctores,
        "totales_mes": {
            "total_tratamientos": total_tratamientos,
            "total_generado_comisiones": round(total_generado_comisiones, 2),
            "total_pagado_comisiones": round(total_pagado_comisiones, 2),
            "total_pendiente_comisiones": round(total_pendiente_comisiones, 2),
            "total_pagado_salarios": round(total_pagado_salarios, 2),
            "total_generado": round(total_generado, 2),
            "total_ganancia": round(total_ganancia, 2)
        }
    })
