"""Actividad del paciente: timeline de la ficha y detalle de una visita.

Solo lectura. El timeline junta visitas, seguimientos y eventos en una lista;
los usuarios, ingresos y hermanos de visita se cargan en lote para que el
número de queries no crezca con la cantidad de visitas.

Los montos de dinero solo los ve quien tiene acceso a ingresos
(`usuario_ve_montos`): la recepcionista sin el bloque "ingresos" y el asistente
sin el recurso `edr.ingresos` ven la visita pero no cuánto costó.
"""
from collections import defaultdict
from datetime import timezone

from app.auth.models import User
from app.crm.models import PacienteVisita
from app.crm.services import CrmNotFound
from app.facturacion.iva import iva_de
from app.facturacion.timezone_helper import MEXICO_TIMEZONE
from app.middleware.permisos import NIVELES, normalizar_permisos
from app.middleware.permisos_recepcion import normalizar_permisos_recepcion


def usuario_ve_montos(usuario):
    """True si el usuario puede ver dinero de los ingresos (timeline y detalle)."""
    if usuario.is_superuser or usuario.role == "admin":
        return True
    if usuario.role == "recepcionista":
        apagados = normalizar_permisos_recepcion(usuario.permisos)["bloques_apagados"]
        return "ingresos" not in apagados
    if usuario.role == "asistente":
        return normalizar_permisos(usuario.permisos or {}).get("edr.ingresos") in NIVELES
    return False


def _total(lineas):
    """Σ (monto + IVA): la misma regla que `recalcular_total` del ticket."""
    return round(sum(
        (i.monto or 0.0) + iva_de(i.monto, i.tipo_servicio, i.factura) for i in lineas
    ), 2)


def _nombres_de_usuarios(ids):
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.name for u in User.query.filter(User.id.in_(ids)).all()}


def _grupos_de_ingresos(tenant_id, ingreso_ids):
    """{ingreso_ancla_id: [ingresos del grupo]} con dos queries en total."""
    from app.edr.models import Ingreso
    if not ingreso_ids:
        return {}
    anclas = Ingreso.query.filter(
        Ingreso.tenant_id == tenant_id, Ingreso.id.in_(ingreso_ids)
    ).all()
    uids = {a.visita_uid for a in anclas if a.visita_uid}
    por_uid = defaultdict(list)
    if uids:
        for h in Ingreso.query.filter(
            Ingreso.tenant_id == tenant_id, Ingreso.visita_uid.in_(uids)
        ).order_by(Ingreso.id).all():
            por_uid[h.visita_uid].append(h)
    # Sin visita_uid el grupo es el ingreso solo (igual que hermanos_de_visita).
    return {a.id: por_uid[a.visita_uid] if a.visita_uid else [a] for a in anclas}


def _iso(dt):
    return dt.isoformat() if dt else None


def _dia_local(dt):
    """Día calendario en hora de México de un created_at guardado como UTC naive."""
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(MEXICO_TIMEZONE).date().isoformat()


def timeline(p, ver_montos):
    """Lista de actividad del paciente, de la más reciente a la más antigua."""
    visitas = p.visitas.all()
    seguimientos = p.seguimientos.all()
    eventos = p.eventos.all()

    autores = _nombres_de_usuarios(
        [v.created_by for v in visitas]
        + [s.created_by for s in seguimientos]
        + [e.usuario_id for e in eventos]
    )
    grupos = _grupos_de_ingresos(
        p.tenant_id, [v.ingreso_id for v in visitas if v.ingreso_id]
    )

    items = []
    for v in visitas:
        grupo = grupos.get(v.ingreso_id) if v.ingreso_id else None
        cobrada = bool(grupo)
        items.append({
            "tipo": "visita", "id": v.id, "fecha": v.fecha.isoformat(),
            "fecha_hora": _iso(v.created_at),
            "detalle": v.motivo or "Visita", "autor": autores.get(v.created_by),
            "completado": None, "ingreso_id": v.ingreso_id,
            "tipo_seguimiento": None, "notas": None, "fecha_completado": None,
            "cobrada": cobrada,
            "total": _total(grupo) if cobrada and ver_montos else None,
        })
    for s in seguimientos:
        items.append({
            "tipo": "seguimiento", "id": s.id,
            "fecha": s.fecha_programada.isoformat(),
            "fecha_hora": _iso(s.created_at),
            "detalle": f"{s.tipo}: {s.notas or ''}".strip(": "),
            "autor": autores.get(s.created_by),
            "completado": s.completado, "ingreso_id": None,
            "tipo_seguimiento": s.tipo, "notas": s.notas,
            "fecha_completado": _iso(s.fecha_completado),
            "cobrada": None, "total": None,
        })
    for e in eventos:
        items.append({
            "tipo": e.tipo, "id": e.id,
            "fecha": _dia_local(e.created_at),
            "fecha_hora": _iso(e.created_at),
            "detalle": e.detalle, "autor": autores.get(e.usuario_id),
            "completado": None, "ingreso_id": None,
            "tipo_seguimiento": None, "notas": None, "fecha_completado": None,
            "cobrada": None, "total": None,
        })
    items.sort(key=lambda x: (x["fecha"] or "", x["id"]), reverse=True)
    return items


def detalle_visita(tenant_id, visita_id, ver_montos):
    """Detalle de una visita: motivo, líneas cobradas, ticket y totales.

    Una visita sin ingreso (registrada a mano, o cuyo ingreso ya no existe)
    responde `cobrada: False` y sin líneas, nunca falla.
    """
    from app.edr.models import Ingreso
    from app.edr.services import hermanos_de_visita

    v = PacienteVisita.query.filter_by(id=visita_id, tenant_id=tenant_id).first()
    if not v:
        raise CrmNotFound("Visita no encontrada")

    autor = _nombres_de_usuarios([v.created_by]).get(v.created_by)
    ancla = (
        Ingreso.query.filter_by(id=v.ingreso_id, tenant_id=tenant_id).first()
        if v.ingreso_id else None
    )
    grupo = hermanos_de_visita(ancla) if ancla else []

    ticket = None
    ticket_origen = next((i for i in grupo if i.ticket_id), None)
    if ticket_origen is not None:
        t = ticket_origen.ticket
        ticket = {
            "folio": t.folio_display,
            "sucursal": t.sucursal.nombre if t.sucursal else None,
        }

    lineas = []
    for i in grupo:
        lineas.append({
            "tratamiento": i.nombre_tratamiento
            or (i.tratamiento.nombre if i.tratamiento else None),
            "doctor": i.especialista.nombre if i.especialista else None,
            "descuento": (i.descuento_monto if (i.descuento_monto or 0) > 0 else None)
            if ver_montos else None,
            "monto": i.monto if ver_montos else None,
        })

    metodos = []
    comentarios = []
    for i in grupo:
        if i.metodo_pago and i.metodo_pago.nombre not in metodos:
            metodos.append(i.metodo_pago.nombre)
        c = (i.comentarios or "").strip()
        if c and c not in comentarios:
            comentarios.append(c)

    subtotal = iva = total = None
    if ver_montos and grupo:
        subtotal = round(sum(i.monto or 0.0 for i in grupo), 2)
        iva = round(sum(iva_de(i.monto, i.tipo_servicio, i.factura) for i in grupo), 2)
        total = round(subtotal + iva, 2)

    return {
        "id": v.id,
        "fecha": v.fecha.isoformat(),
        "motivo": v.motivo,
        "autor": autor,
        "cobrada": bool(grupo),
        "montos_visibles": bool(ver_montos),
        "ticket": ticket,
        "lineas": lineas,
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
        "metodos_pago": metodos,
        "factura": any(i.factura for i in grupo),
        "comentarios": comentarios,
        "ingreso_id": v.ingreso_id,
    }
