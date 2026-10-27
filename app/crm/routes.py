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
    AsignarSchema, CorregirAsignacionSchema, EstadoDienteSchema, RealizarSchema,
)
from app.crm import services, odontograma, expediente, actividad
from app.crm.services import CrmError, CrmNotFound, CrmForbidden

crm_bp = Blueprint("crm", __name__, url_prefix="/api/v1/crm")

LIMITE_BUSQUEDA = 20


@crm_bp.errorhandler(CrmNotFound)
def _crm_not_found(e):
    return jsonify({"error": str(e)}), 404


@crm_bp.errorhandler(CrmForbidden)
def _crm_forbidden(e):
    return jsonify({"error": str(e)}), 403


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


def _filtro_texto(texto):
    """Nombre, teléfono o expediente; "a245" también encuentra A000245."""
    like = f"%{texto}%"
    condiciones = [
        Paciente.nombre.ilike(like), Paciente.telefono.ilike(like),
        Paciente.expediente.ilike(like),
    ]
    codigo = expediente.codigo_de_busqueda(texto)
    if codigo:
        condiciones.append(Paciente.expediente == codigo)
    return or_(*condiciones)


@crm_bp.route("/pacientes", methods=["GET"])
@require_auth
def listar_pacientes():
    corte = services.fecha_corte_inactividad(g.tenant_id)
    q = _query_listado(g.tenant_id)

    texto = (request.args.get("q") or "").strip()
    if texto:
        q = q.filter(_filtro_texto(texto))
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
    """Búsqueda ligera para autocompletar: id/nombre/telefono/expediente, con límite.

    A diferencia de listar_pacientes, no calcula inactividad ni timeline, así
    que es barato aun con miles de pacientes. La ruta /pacientes/buscar no
    choca con /pacientes/<int:paciente_id> porque "buscar" no es entero.
    """
    texto = (request.args.get("q") or "").strip()
    if len(texto) < 2:
        return jsonify({"pacientes": [], "total": 0})
    filas = (
        Paciente.query
        .filter(
            Paciente.tenant_id == g.tenant_id,
            Paciente.eliminado.is_(False),
            _filtro_texto(texto),
        )
        .order_by(Paciente.nombre)
        .limit(LIMITE_BUSQUEDA)
        .all()
    )
    pacientes = [
        {"id": p.id, "nombre": p.nombre, "telefono": p.telefono,
         "expediente": p.expediente}
        for p in filas
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
    # Sin expediente cualquiera lo asigna; con uno, solo el admin lo cambia.
    data["expediente_editable"] = (
        p.expediente is None or expediente.es_admin(g.current_user)
    )

    data["timeline"] = actividad.timeline(p, actividad.usuario_ve_montos(g.current_user))
    return jsonify(data)


@crm_bp.route("/visitas/<int:visita_id>", methods=["GET"])
@require_auth
def detalle_visita(visita_id):
    """Detalle de una visita; los montos solo para quien ve ingresos."""
    return jsonify(actividad.detalle_visita(
        g.tenant_id, visita_id, actividad.usuario_ve_montos(g.current_user)
    ))


@crm_bp.route("/pacientes", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def crear_paciente():
    data = PacienteSchema().load(request.get_json() or {})
    p = services.crear_paciente(
        g.tenant_id, data, usuario_id=g.current_user.id, usuario=g.current_user
    )
    return jsonify(_dump_paciente(p)), 201


@crm_bp.route("/pacientes/<int:paciente_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def actualizar_paciente(paciente_id):
    data = PacienteSchema(partial=True).load(request.get_json() or {})
    services.actualizar_paciente(
        g.tenant_id, paciente_id, data, usuario_id=g.current_user.id,
        usuario=g.current_user,
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
    return jsonify({
        "meses_inactividad": cfg.meses_inactividad,
        "expediente": _dump_expediente_config(cfg),
        "es_admin": expediente.es_admin(g.current_user),
    })


def _dump_expediente_config(cfg):
    return {
        "formato": cfg.expediente_formato,
        "letras": expediente.letras_de(cfg),
        "siguiente": cfg.expediente_siguiente or expediente.CONTADOR_INICIAL,
    }


@crm_bp.route("/expediente/config", methods=["PUT"])
@require_auth
def actualizar_config_expediente():
    # Explícito: require_role deja pasar siempre al asistente.
    if not expediente.es_admin(g.current_user):
        return jsonify({"error": "Solo el administrador configura los expedientes"}), 403
    body = request.get_json() or {}
    cfg = expediente.configurar(g.tenant_id, body.get("formato"), body.get("letras"))
    db.session.commit()
    return jsonify(_dump_expediente_config(cfg))


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


# ── Odontograma ──────────────────────────────────────────────────────────────
# Todas devuelven el odontograma completo: el frontend repinta con una sola
# respuesta y no hay estado intermedio que reconciliar.

def _odontograma(paciente_id, status=200):
    return jsonify(odontograma.obtener_odontograma(g.tenant_id, paciente_id)), status


@crm_bp.route("/pacientes/<int:paciente_id>/odontograma", methods=["GET"])
@require_auth
def ver_odontograma(paciente_id):
    return _odontograma(paciente_id)


@crm_bp.route("/pacientes/<int:paciente_id>/odontograma/asignaciones", methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def asignar_odontograma(paciente_id):
    data = AsignarSchema().load(request.get_json() or {})
    odontograma.asignar(g.tenant_id, g.current_user.id, paciente_id,
                        data["origen_tipo"], data["origen_id"], data["dientes"])
    return _odontograma(paciente_id, 201)


@crm_bp.route("/pacientes/<int:paciente_id>/odontograma/asignaciones/<int:asignacion_id>/realizar",
              methods=["POST"])
@require_auth
@require_role("admin", "editor", "recepcionista")
def realizar_asignacion(paciente_id, asignacion_id):
    data = RealizarSchema().load(request.get_json() or {})
    odontograma.marcar_realizado(g.tenant_id, g.current_user.id, paciente_id,
                                 asignacion_id, data.get("fecha"))
    return _odontograma(paciente_id)


@crm_bp.route("/pacientes/<int:paciente_id>/odontograma/asignaciones/<int:asignacion_id>",
              methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def corregir_asignacion(paciente_id, asignacion_id):
    data = CorregirAsignacionSchema().load(request.get_json() or {})
    odontograma.corregir_asignacion(g.tenant_id, g.current_user.id, paciente_id,
                                    asignacion_id, data)
    return _odontograma(paciente_id)


@crm_bp.route("/pacientes/<int:paciente_id>/odontograma/asignaciones/<int:asignacion_id>",
              methods=["DELETE"])
@require_auth
@require_role("admin", "editor")
def desasignar(paciente_id, asignacion_id):
    odontograma.desasignar(g.tenant_id, g.current_user.id, paciente_id, asignacion_id)
    return _odontograma(paciente_id)


@crm_bp.route("/pacientes/<int:paciente_id>/odontograma/dientes/<int:numero>/estado",
              methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def cambiar_estado_diente(paciente_id, numero):
    data = EstadoDienteSchema().load(request.get_json() or {})
    odontograma.cambiar_estado_diente(g.tenant_id, g.current_user.id, paciente_id,
                                      numero, data["estado"], data.get("fecha"))
    return _odontograma(paciente_id)
