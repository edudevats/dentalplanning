from datetime import date
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, or_
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.crm.models import (
    ESTATUS_CRM, Paciente, PacienteVisita, PacienteSeguimiento, PacienteEvento,
)
from app.crm.schemas import (
    PacienteSchema, VisitaSchema, SeguimientoSchema, NotaSchema, CrmConfigSchema,
)
from app.crm import services
from app.crm.services import CrmError, CrmNotFound

crm_bp = Blueprint("crm", __name__, url_prefix="/api/v1/crm")

LIMITE_BUSQUEDA = 20


@crm_bp.errorhandler(CrmNotFound)
def _crm_not_found(e):
    return jsonify({"error": str(e)}), 404


@crm_bp.errorhandler(CrmError)
def _crm_error(e):
    return jsonify({"error": str(e)}), 400


def _dump_paciente(p, ultima_visita=None, siguiente_seguimiento=None, corte=None):
    data = PacienteSchema().dump(p)
    data["especialista_nombre"] = p.especialista.nombre if p.especialista else None
    data["ultima_visita"] = ultima_visita.isoformat() if ultima_visita else None
    data["siguiente_seguimiento"] = (
        siguiente_seguimiento.isoformat() if siguiente_seguimiento else None
    )
    data["inactivo"] = bool(
        corte and p.estatus_crm in ("activo", "alta")
        and (ultima_visita is None or ultima_visita < corte)
    )
    return data


def _query_listado(tenant_id):
    """Query base: (Paciente, ultima_visita, siguiente_seguimiento) sin N+1."""
    ult = db.session.query(
        PacienteVisita.paciente_id.label("pid"),
        func.max(PacienteVisita.fecha).label("ultima_visita"),
    ).filter(PacienteVisita.tenant_id == tenant_id).group_by(
        PacienteVisita.paciente_id
    ).subquery()
    sig = db.session.query(
        PacienteSeguimiento.paciente_id.label("pid"),
        func.min(PacienteSeguimiento.fecha_programada).label("siguiente"),
    ).filter(
        PacienteSeguimiento.tenant_id == tenant_id,
        PacienteSeguimiento.completado.is_(False),
    ).group_by(PacienteSeguimiento.paciente_id).subquery()

    return db.session.query(
        Paciente, ult.c.ultima_visita, sig.c.siguiente
    ).outerjoin(ult, ult.c.pid == Paciente.id
    ).outerjoin(sig, sig.c.pid == Paciente.id
    ).filter(Paciente.tenant_id == tenant_id, Paciente.eliminado.is_(False))


def _dump_paciente_enriquecido(paciente_id):
    corte = services.fecha_corte_inactividad(g.tenant_id)
    fila = _query_listado(g.tenant_id).filter(Paciente.id == paciente_id).first()
    if not fila:
        raise CrmNotFound("Paciente no encontrado")
    p, ultima, siguiente = fila
    return _dump_paciente(p, ultima, siguiente, corte)


@crm_bp.route("/pacientes", methods=["GET"])
@require_auth
def listar_pacientes():
    corte = services.fecha_corte_inactividad(g.tenant_id)
    q = _query_listado(g.tenant_id)

    texto = (request.args.get("q") or "").strip()
    if texto:
        like = f"%{texto}%"
        q = q.filter(or_(Paciente.nombre.ilike(like), Paciente.telefono.ilike(like)))
    estatus = request.args.get("estatus")
    if estatus:
        q = q.filter(Paciente.estatus_crm == estatus)
    especialista_id = request.args.get("especialista_id", type=int)
    if especialista_id:
        q = q.filter(Paciente.especialista_id == especialista_id)

    filas = q.order_by(Paciente.nombre).all()

    solo_inactivos = request.args.get("inactivos") == "true"
    resultado = []
    for p, ultima, siguiente in filas:
        data = _dump_paciente(p, ultima, siguiente, corte)
        if solo_inactivos and not data["inactivo"]:
            continue
        resultado.append(data)

    return jsonify({"pacientes": resultado, "total": len(resultado)})


@crm_bp.route("/pacientes/buscar", methods=["GET"])
@require_auth
def buscar_pacientes():
    """Búsqueda ligera para autocompletar: solo id/nombre/telefono, con límite.

    A diferencia de listar_pacientes, no calcula inactividad ni timeline, así
    que es barato aun con miles de pacientes. La ruta /pacientes/buscar no
    choca con /pacientes/<int:paciente_id> porque "buscar" no es entero.
    """
    texto = (request.args.get("q") or "").strip()
    if len(texto) < 2:
        return jsonify({"pacientes": [], "total": 0})
    like = f"%{texto}%"
    filas = (
        Paciente.query
        .filter(
            Paciente.tenant_id == g.tenant_id,
            Paciente.eliminado.is_(False),
            or_(Paciente.nombre.ilike(like), Paciente.telefono.ilike(like)),
        )
        .order_by(Paciente.nombre)
        .limit(LIMITE_BUSQUEDA)
        .all()
    )
    pacientes = [
        {"id": p.id, "nombre": p.nombre, "telefono": p.telefono} for p in filas
    ]
    return jsonify({"pacientes": pacientes, "total": len(pacientes)})


@crm_bp.route("/pacientes/<int:paciente_id>", methods=["GET"])
@require_auth
def ficha_paciente(paciente_id):
    corte = services.fecha_corte_inactividad(g.tenant_id)
    fila = _query_listado(g.tenant_id).filter(Paciente.id == paciente_id).first()
    if not fila:
        return jsonify({"error": "Paciente no encontrado"}), 404
    p, ultima, siguiente = fila
    data = _dump_paciente(p, ultima, siguiente, corte)

    timeline = []
    for v in p.visitas.all():
        timeline.append({
            "tipo": "visita", "id": v.id, "fecha": v.fecha.isoformat(),
            "detalle": v.motivo or "Visita", "completado": None,
            "ingreso_id": v.ingreso_id,
        })
    for s in p.seguimientos.all():
        timeline.append({
            "tipo": "seguimiento", "id": s.id,
            "fecha": s.fecha_programada.isoformat(),
            "detalle": f"{s.tipo}: {s.notas or ''}".strip(": "),
            "completado": s.completado, "ingreso_id": None,
        })
    for e in p.eventos.all():
        timeline.append({
            "tipo": e.tipo, "id": e.id,
            "fecha": e.created_at.date().isoformat() if e.created_at else None,
            "detalle": e.detalle, "completado": None, "ingreso_id": None,
        })
    timeline.sort(key=lambda x: (x["fecha"] or "", x["id"]), reverse=True)
    data["timeline"] = timeline
    return jsonify(data)


@crm_bp.route("/pacientes", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def crear_paciente():
    data = PacienteSchema().load(request.get_json() or {})
    p = services.crear_paciente(g.tenant_id, data, usuario_id=g.current_user.id)
    return jsonify(_dump_paciente(p)), 201


@crm_bp.route("/pacientes/<int:paciente_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def actualizar_paciente(paciente_id):
    data = PacienteSchema(partial=True).load(request.get_json() or {})
    services.actualizar_paciente(
        g.tenant_id, paciente_id, data, usuario_id=g.current_user.id
    )
    return jsonify(_dump_paciente_enriquecido(paciente_id))


@crm_bp.route("/pacientes/<int:paciente_id>", methods=["DELETE"])
@require_auth
@require_role("admin", "editor")
def eliminar_paciente(paciente_id):
    services.eliminar_paciente(g.tenant_id, paciente_id)
    return jsonify({"message": "Paciente eliminado"})


@crm_bp.route("/pacientes/<int:paciente_id>/estatus", methods=["PUT"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def cambiar_estatus(paciente_id):
    nuevo = (request.get_json() or {}).get("estatus_crm")
    if nuevo not in ESTATUS_CRM:
        return jsonify({"error": "Estatus inválido"}), 400
    services.cambiar_estatus(
        g.tenant_id, paciente_id, nuevo, usuario_id=g.current_user.id
    )
    return jsonify(_dump_paciente_enriquecido(paciente_id))


@crm_bp.route("/pacientes/<int:paciente_id>/visitas", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def agregar_visita(paciente_id):
    data = VisitaSchema().load(request.get_json() or {})
    v = services.agregar_visita(
        g.tenant_id, paciente_id, data["fecha"],
        motivo=data.get("motivo"), usuario_id=g.current_user.id,
    )
    return jsonify(VisitaSchema().dump(v)), 201


@crm_bp.route("/pacientes/<int:paciente_id>/seguimientos", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def agregar_seguimiento(paciente_id):
    data = SeguimientoSchema().load(request.get_json() or {})
    s = services.agregar_seguimiento(
        g.tenant_id, paciente_id, data["tipo"], data["fecha_programada"],
        notas=data.get("notas"), usuario_id=g.current_user.id,
    )
    return jsonify(SeguimientoSchema().dump(s)), 201


@crm_bp.route("/seguimientos/<int:seguimiento_id>/completar", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def completar_seguimiento(seguimiento_id):
    s = services.completar_seguimiento(g.tenant_id, seguimiento_id)
    return jsonify(SeguimientoSchema().dump(s))


@crm_bp.route("/pacientes/<int:paciente_id>/notas", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def agregar_nota(paciente_id):
    data = NotaSchema().load(request.get_json() or {})
    e = services.agregar_nota(
        g.tenant_id, paciente_id, data["texto"], usuario_id=g.current_user.id
    )
    return jsonify({"id": e.id, "tipo": "nota", "detalle": e.detalle}), 201


@crm_bp.route("/resumen", methods=["GET"])
@require_auth
def resumen():
    corte = services.fecha_corte_inactividad(g.tenant_id)
    por_estatus = {e: 0 for e in ESTATUS_CRM}
    filas = db.session.query(
        Paciente.estatus_crm, func.count(Paciente.id)
    ).filter(
        Paciente.tenant_id == g.tenant_id, Paciente.eliminado.is_(False)
    ).group_by(Paciente.estatus_crm).all()
    for estatus, n in filas:
        por_estatus[estatus] = n

    inactivos = 0
    for p, ultima, _sig in _query_listado(g.tenant_id).all():
        if p.estatus_crm in ("activo", "alta") and (ultima is None or ultima < corte):
            inactivos += 1

    hoy = date.today()
    base_seg = PacienteSeguimiento.query.join(
        Paciente, Paciente.id == PacienteSeguimiento.paciente_id
    ).filter(
        PacienteSeguimiento.tenant_id == g.tenant_id,
        PacienteSeguimiento.completado.is_(False),
        Paciente.eliminado.is_(False),
    )
    seguimientos_hoy = base_seg.filter(
        PacienteSeguimiento.fecha_programada == hoy
    ).count()
    seguimientos_vencidos = base_seg.filter(
        PacienteSeguimiento.fecha_programada < hoy
    ).count()

    return jsonify({
        "por_estatus": por_estatus,
        "inactivos": inactivos,
        "seguimientos_hoy": seguimientos_hoy,
        "seguimientos_vencidos": seguimientos_vencidos,
    })


@crm_bp.route("/config", methods=["GET"])
@require_auth
def obtener_config():
    cfg = services.get_config(g.tenant_id)
    return jsonify({"meses_inactividad": cfg.meses_inactividad})


@crm_bp.route("/config", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_config():
    data = CrmConfigSchema().load(request.get_json() or {})
    cfg = services.get_config(g.tenant_id)
    cfg.meses_inactividad = data["meses_inactividad"]
    db.session.commit()
    return jsonify({"meses_inactividad": cfg.meses_inactividad})


@crm_bp.route("/pacientes/importar/preview", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def importar_preview():
    archivo = request.files.get("archivo")
    if not archivo:
        return jsonify({"error": "Falta el archivo"}), 400
    filas = services.parsear_archivo_pacientes(archivo)
    return jsonify(services.preview_importacion(g.tenant_id, filas))


@crm_bp.route("/pacientes/importar/confirmar", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def importar_confirmar():
    filas = (request.get_json() or {}).get("filas") or []
    creados = services.importar_pacientes(
        g.tenant_id, filas, usuario_id=g.current_user.id
    )
    return jsonify({"creados": creados}), 201


@crm_bp.route("/sugerencias-edr", methods=["GET"])
@require_auth
def sugerencias_edr():
    return jsonify({"sugerencias": services.sugerencias_edr(g.tenant_id)})


@crm_bp.route("/sugerencias-edr/vincular", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def vincular_sugerencia():
    nombre = (request.get_json() or {}).get("nombre")
    resultado = services.vincular_paciente_edr(
        g.tenant_id, nombre, usuario_id=g.current_user.id
    )
    return jsonify(resultado)
