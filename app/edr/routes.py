from flask import Blueprint, request, jsonify, g
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.edr.models import Ingreso, GastoOperativo, PagoDoctor, PagoComisionIngreso
from app.edr.schemas import (
    IngresoSchema,
    GastoOperativoSchema,
    PagoDoctorSchema,
    ComisionPagoSchema,
)
from app.facturacion.services import asignar_ticket, recalcular_total, FacturacionError
from app.facturacion.models import TICKET_SIN_TIMBRAR
from app.ajustes.models import Especialista
from app.configuracion.models import ConfigConsultorio
from app.tratamientos.models import Tratamiento
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
    ).filter(
        Ingreso.tenant_id == g.tenant_id,
        *filtro_mes(Ingreso.fecha, year, month),
    ).order_by(Ingreso.fecha).all()

    return jsonify([_enrich_ingreso(i) for i in ingresos])


@edr_bp.route("/ingresos", methods=["POST"])
@require_auth
@require_role("admin", "recepcionista")
def crear_ingreso():
    body = request.get_json() or {}
    ticket_folio = body.get("ticket_folio")
    schema = IngresoSchema()
    data = schema.load(body)

    # Sin módulo CRM no se acepta paciente_id (evita FKs cross-tenant sin validar)
    if data.get("paciente_id") and not crm_activo(g.tenant_id):
        data["paciente_id"] = None

    tipo_servicio = "clinico"
    if data.get("tratamiento_id"):
        _tr = Tratamiento.query.filter_by(
            id=data["tratamiento_id"], tenant_id=g.tenant_id
        ).first()
        if _tr and _tr.tipo_servicio:
            tipo_servicio = _tr.tipo_servicio

    ingreso = Ingreso(tenant_id=g.tenant_id, tipo_servicio=tipo_servicio, **data)
    db.session.add(ingreso)
    db.session.flush()

    if crm_activo(g.tenant_id) and ingreso.paciente_id:
        try:
            sincronizar_visita_ingreso(ingreso)
        except CrmError as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    if ingreso.factura and data.get("sucursal_id"):
        try:
            asignar_ticket(ingreso, data["sucursal_id"], ticket_folio)
        except FacturacionError as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(_enrich_ingreso(ingreso)), 201


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
    if data.get("paciente_id") and not crm_activo(g.tenant_id):
        data.pop("paciente_id")
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

@edr_bp.route("/gastos", methods=["GET"])
@require_auth
def listar_gastos():
    year, month = _parse_mes(request.args.get("mes"))
    gastos = GastoOperativo.query.filter(
        GastoOperativo.tenant_id == g.tenant_id,
        *filtro_mes(GastoOperativo.fecha, year, month),
    ).order_by(GastoOperativo.fecha).all()

    return jsonify(GastoOperativoSchema(many=True).dump(gastos))


@edr_bp.route("/gastos", methods=["POST"])
@require_auth
@require_role("admin")
def crear_gasto():
    schema = GastoOperativoSchema()
    data = schema.load(request.get_json() or {})
    gasto = GastoOperativo(tenant_id=g.tenant_id, **data)
    db.session.add(gasto)
    db.session.commit()
    return jsonify(schema.dump(gasto)), 201


@edr_bp.route("/gastos/<int:gasto_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_gasto(gasto_id):
    gasto = GastoOperativo.query.filter_by(
        id=gasto_id, tenant_id=g.tenant_id
    ).first_or_404()
    schema = GastoOperativoSchema(partial=True)
    data = schema.load(request.get_json() or {})
    for key, value in data.items():
        setattr(gasto, key, value)
    db.session.commit()
    return jsonify(GastoOperativoSchema().dump(gasto))


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
