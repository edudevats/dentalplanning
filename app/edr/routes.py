from flask import Blueprint, request, jsonify, g
from sqlalchemy import extract
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.edr.models import Ingreso, GastoOperativo, PagoDoctor
from app.edr.schemas import IngresoSchema, GastoOperativoSchema, PagoDoctorSchema
from app.ajustes.models import Especialista
from app.configuracion.models import ConfigConsultorio
from app.tratamientos.models import Tratamiento
# parse_mes y ganancia_tratamiento viven en el núcleo contable unificado
from app.engine.accounting import parse_mes as _parse_mes, ganancia_tratamiento

edr_bp = Blueprint("edr", __name__, url_prefix="/api/v1/edr")


def _enrich_ingreso(ingreso):
    data = IngresoSchema().dump(ingreso)
    data["especialista_nombre"] = ingreso.especialista.nombre if ingreso.especialista else None
    data["metodo_pago_nombre"] = ingreso.metodo_pago.nombre if ingreso.metodo_pago else None
    data["estrategia_nombre"] = ingreso.estrategia.nombre if ingreso.estrategia else None
    return data


# ── INGRESOS ──

@edr_bp.route("/ingresos", methods=["GET"])
@require_auth
def listar_ingresos():
    year, month = _parse_mes(request.args.get("mes"))
    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).order_by(Ingreso.fecha).all()

    return jsonify([_enrich_ingreso(i) for i in ingresos])


@edr_bp.route("/ingresos", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_ingreso():
    schema = IngresoSchema()
    data = schema.load(request.get_json() or {})

    # Las comisiones las define el usuario. El frontend las pre-llena con los
    # datos del tratamiento al seleccionarlo, pero quedan editables: el backend
    # respeta lo que llega y NO las sobrescribe.
    ingreso = Ingreso(tenant_id=g.tenant_id, **data)
    db.session.add(ingreso)
    db.session.commit()
    return jsonify(_enrich_ingreso(ingreso)), 201


@edr_bp.route("/ingresos/<int:ingreso_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_ingreso(ingreso_id):
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()

    schema = IngresoSchema(partial=True)
    data = schema.load(request.get_json() or {})
    # Passthrough: se respetan las comisiones que captura el usuario
    for key, value in data.items():
        setattr(ingreso, key, value)
    db.session.commit()
    return jsonify(_enrich_ingreso(ingreso))


@edr_bp.route("/ingresos/<int:ingreso_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_ingreso(ingreso_id):
    ingreso = Ingreso.query.filter_by(
        id=ingreso_id, tenant_id=g.tenant_id
    ).first_or_404()
    db.session.delete(ingreso)
    db.session.commit()
    return jsonify({"message": "Ingreso eliminado"})


# ── GASTOS OPERATIVOS ──

@edr_bp.route("/gastos", methods=["GET"])
@require_auth
def listar_gastos():
    year, month = _parse_mes(request.args.get("mes"))
    gastos = GastoOperativo.query.filter(
        GastoOperativo.tenant_id == g.tenant_id,
        extract("year", GastoOperativo.fecha) == year,
        extract("month", GastoOperativo.fecha) == month,
    ).order_by(GastoOperativo.fecha).all()

    return jsonify(GastoOperativoSchema(many=True).dump(gastos))


@edr_bp.route("/gastos", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_gasto():
    schema = GastoOperativoSchema()
    data = schema.load(request.get_json() or {})
    gasto = GastoOperativo(tenant_id=g.tenant_id, **data)
    db.session.add(gasto)
    db.session.commit()
    return jsonify(schema.dump(gasto)), 201


@edr_bp.route("/gastos/<int:gasto_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
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
    db.session.delete(gasto)
    db.session.commit()
    return jsonify({"message": "Gasto eliminado"})


# ── PAGOS A DOCTORES ──

@edr_bp.route("/pagos-doctores", methods=["GET"])
@require_auth
def listar_pagos():
    year, month = _parse_mes(request.args.get("mes"))
    pagos = PagoDoctor.query.filter(
        PagoDoctor.tenant_id == g.tenant_id,
        extract("year", PagoDoctor.fecha) == year,
        extract("month", PagoDoctor.fecha) == month,
    ).order_by(PagoDoctor.fecha).all()

    result = []
    for p in pagos:
        data = PagoDoctorSchema().dump(p)
        data["especialista_nombre"] = p.especialista.nombre if p.especialista else None
        result.append(data)
    return jsonify(result)


@edr_bp.route("/pagos-doctores", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_pago():
    schema = PagoDoctorSchema()
    data = schema.load(request.get_json() or {})
    pago = PagoDoctor(tenant_id=g.tenant_id, **data)
    db.session.add(pago)
    db.session.commit()
    return jsonify(schema.dump(pago)), 201


@edr_bp.route("/pagos-doctores/<int:pago_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
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
    db.session.delete(pago)
    db.session.commit()
    return jsonify({"message": "Pago eliminado"})


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
    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == g.tenant_id,
        extract("year", Ingreso.fecha) == year,
        extract("month", Ingreso.fecha) == month,
    ).all()

    # 4. Pagos a doctores del mes
    pagos = PagoDoctor.query.filter(
        PagoDoctor.tenant_id == g.tenant_id,
        extract("year", PagoDoctor.fecha) == year,
        extract("month", PagoDoctor.fecha) == month,
    ).all()

    resumen_doctores = []
    
    total_tratamientos = 0
    total_generado_comisiones = 0
    total_pagado_comisiones = 0
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
        comision_pendiente = round(comision_generada - comision_pagada, 2)

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
            "total_pendiente_comisiones": round(total_generado_comisiones - total_pagado_comisiones, 2),
            "total_pagado_salarios": round(total_pagado_salarios, 2),
            "total_generado": round(total_generado, 2),
            "total_ganancia": round(total_ganancia, 2)
        }
    })
