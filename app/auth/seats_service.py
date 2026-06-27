from datetime import datetime, timezone
from app.extensions import db
from app.auth.models import User
from app.superadmin.models import (
    Plan, AsientoRecepcionista, ADDON_TIPO_RECEPCIONISTA,
    ASIENTO_PENDIENTE, ASIENTO_APROBADA, ASIENTO_ACTIVA,
    ASIENTO_RECHAZADA, ASIENTO_CANCELADA,
)
from app.clip.service import cancel_subscription, ClipAPIError


class SeatError(Exception):
    """Error de negocio en la gestión de asientos (mapear a 409/400 en las rutas)."""


def get_addon_plan():
    return Plan.query.filter_by(
        addon_tipo=ADDON_TIPO_RECEPCIONISTA, activo=True
    ).first()


def capacidad_recepcionistas(tenant_id):
    activos = AsientoRecepcionista.query.filter_by(
        tenant_id=tenant_id, estado=ASIENTO_ACTIVA
    ).count()
    return 1 + activos


def recepcionistas_actuales(tenant_id):
    return User.query.filter_by(
        tenant_id=tenant_id, role="recepcionista", is_active=True
    ).count()


def puede_crear_recepcionista(tenant_id):
    return recepcionistas_actuales(tenant_id) < capacidad_recepcionistas(tenant_id)


def asiento_libre_activo(tenant_id):
    return AsientoRecepcionista.query.filter_by(
        tenant_id=tenant_id, estado=ASIENTO_ACTIVA, usuario_id=None
    ).first()


def tiene_asiento_abierto(tenant_id):
    return AsientoRecepcionista.query.filter(
        AsientoRecepcionista.tenant_id == tenant_id,
        AsientoRecepcionista.estado.in_([ASIENTO_PENDIENTE, ASIENTO_APROBADA]),
    ).first() is not None


def solicitar_asiento(tenant_id, user_id):
    if puede_crear_recepcionista(tenant_id):
        raise SeatError("Aún tienes cupo para crear un recepcionista")
    if tiene_asiento_abierto(tenant_id):
        raise SeatError("Ya tienes una solicitud de asiento en curso")
    a = AsientoRecepcionista(
        tenant_id=tenant_id, estado=ASIENTO_PENDIENTE, solicitado_por_id=user_id
    )
    db.session.add(a)
    db.session.commit()
    return a


def aprobar_asiento(asiento, super_admin_id):
    if asiento.estado != ASIENTO_PENDIENTE:
        raise SeatError("El asiento no está pendiente")
    plan = get_addon_plan()
    if not plan or not plan.precio_mensual:
        raise SeatError("No hay plan de recepcionista adicional configurado")
    asiento.estado = ASIENTO_APROBADA
    asiento.monto = plan.precio_mensual
    asiento.aprobado_por_id = super_admin_id
    asiento.aprobado_at = datetime.now(timezone.utc)
    db.session.commit()
    return asiento


def rechazar_asiento(asiento, motivo):
    if asiento.estado != ASIENTO_PENDIENTE:
        raise SeatError("El asiento no está pendiente")
    asiento.estado = ASIENTO_RECHAZADA
    asiento.rechazo_motivo = motivo
    db.session.commit()
    return asiento


def activar_asiento(asiento, pago_metodo, clip_subscription_id=None):
    if asiento.estado != ASIENTO_APROBADA:
        raise SeatError("El asiento no está aprobado")
    asiento.estado = ASIENTO_ACTIVA
    asiento.pago_metodo = pago_metodo
    if clip_subscription_id:
        asiento.clip_subscription_id = clip_subscription_id
    db.session.commit()
    return asiento


def activar_por_clip(tenant_id, clip_subscription_id):
    a = AsientoRecepcionista.query.filter_by(
        tenant_id=tenant_id, estado=ASIENTO_APROBADA, clip_subscription_id=None
    ).order_by(AsientoRecepcionista.created_at).first()
    if not a:
        return False
    activar_asiento(a, "clip", clip_subscription_id)
    return True


def cancelar_asiento(asiento):
    if asiento.estado == ASIENTO_CANCELADA:
        return asiento
    if asiento.clip_subscription_id:
        try:
            cancel_subscription(asiento.clip_subscription_id)
        except ClipAPIError:
            pass  # no bloquear la cancelación local si Clip falla
    if asiento.usuario_id:
        u = db.session.get(User, asiento.usuario_id)
        if u:
            u.is_active = False
    asiento.estado = ASIENTO_CANCELADA
    db.session.commit()
    return asiento


def desligar_usuario(user):
    """Suelta el asiento que ocupaba `user` (usuario_id=None) y hace flush.

    CONTRATO: el caller DEBE llamar esto ANTES de borrar el usuario y luego
    commitear en la misma transacción. El flush aquí garantiza que el FK
    asientos_recepcionista.usuario_id quede en NULL antes del DELETE del user,
    evitando un IntegrityError. No hace commit (lo hace el caller).
    """
    a = AsientoRecepcionista.query.filter_by(usuario_id=user.id).first()
    if a:
        a.usuario_id = None
        db.session.flush()


def serialize_asiento(asiento, with_usuario=False):
    out = {
        "id": asiento.id,
        "tenant_id": asiento.tenant_id,
        "estado": asiento.estado,
        "monto": asiento.monto,
        "pago_metodo": asiento.pago_metodo,
        "clip_subscription_id": asiento.clip_subscription_id,
        "usuario_id": asiento.usuario_id,
        "rechazo_motivo": asiento.rechazo_motivo,
        "aprobado_at": asiento.aprobado_at.isoformat() if asiento.aprobado_at else None,
        "created_at": asiento.created_at.isoformat() if asiento.created_at else None,
    }
    if with_usuario and asiento.usuario_id:
        u = db.session.get(User, asiento.usuario_id)
        out["usuario_email"] = u.email if u else None
    return out
