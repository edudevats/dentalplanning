import calendar
import csv
import io
import secrets
import string
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, g, current_app, Response
from sqlalchemy import func
from app.extensions import db
from app.middleware.tenant import require_superuser
from app.auth.models import (
    Tenant, User, SYSTEM_TENANT_SLUG,
    TENANT_STATUS_PENDING, TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED, TENANT_STATUS_REJECTED,
    TENANT_STATUSES,
)
from app.superadmin.models import (
    Plan, Subscription, Payment, TenantNote, AdminAuditLog,
    AsientoRecepcionista,
    SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA, SUBSCRIPTION_VENCIDA,
)
from app.auth import seats_service
from app.clip.service import create_checkout_link, ClipAPIError
from app.superadmin.schemas import (
    PlanSchema, ApproveTenantSchema, RejectTenantSchema,
    TenantUpdateSchema, PaymentSchema, TenantNoteSchema,
    SubscriptionUpdateSchema, AssignPlanSchema, ChangeUserRoleSchema,
    ToggleActiveSchema, RechazarAsientoSchema, ActivarManualSchema,
)
from app.catalogo.models import Material
from app.tratamientos.models import Tratamiento

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/api/v1/superadmin")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_one_month(d):
    """Avanza ``d`` un mes calendario, ajustando al último día válido del mes
    destino (p. ej. 2026-01-31 -> 2026-02-28)."""
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _compute_proximo_cobro(plan, inicio):
    """Fecha de próximo cobro / fin de vigencia para una suscripción.

    Planes con ventana de vigencia (``dias_expiracion``) expiran a esos días.
    Los planes sin ella se tratan como mensuales.
    """
    if plan.dias_expiracion and plan.dias_expiracion > 0:
        return inicio + timedelta(days=plan.dias_expiracion)
    return _add_one_month(inicio)


def _grace_after(proximo):
    """Fecha límite de gracia: proximo_cobro + BILLING_GRACE_DAYS (default 3)."""
    if not proximo:
        return None
    dias = current_app.config.get("BILLING_GRACE_DAYS", 3)
    return proximo + timedelta(days=dias)


def _serialize_tenant(t, *, with_counts=False):
    out = {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "plan": t.plan,
        "status": t.status,
        "contact_email": t.contact_email,
        "approved_at": t.approved_at.isoformat() if t.approved_at else None,
        "rejected_reason": t.rejected_reason,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if with_counts:
        out["users_count"] = User.query.filter_by(tenant_id=t.id).count()
        out["tratamientos_count"] = Tratamiento.query.filter_by(tenant_id=t.id).count()
        out["materiales_count"] = Material.query.filter_by(tenant_id=t.id).count()
        last = (
            Payment.query.filter_by(tenant_id=t.id)
            .order_by(Payment.fecha.desc()).first()
        )
        out["ultimo_pago"] = (
            {"fecha": last.fecha.isoformat(), "monto": last.monto} if last else None
        )
        sub = Subscription.query.filter_by(tenant_id=t.id).first()
        if sub:
            out["subscription"] = {
                "estado": sub.estado,
                "plan_nombre": sub.plan.nombre if sub.plan else None,
                "plan_modulos": sub.plan.modulos if sub.plan else [],
                "proximo_cobro": sub.proximo_cobro.isoformat() if sub.proximo_cobro else None,
                "grace_expires_at": sub.grace_expires_at.isoformat() if sub.grace_expires_at else None,
            }
        out["ultima_actividad"] = (
            db.session.query(func.max(User.last_login))
            .filter(User.tenant_id == t.id)
            .scalar()
        )
        out["ultima_actividad"] = out["ultima_actividad"].isoformat() if out["ultima_actividad"] else None
    return out


def _serialize_plan(p):
    return {
        "id": p.id, "nombre": p.nombre, "precio_mensual": p.precio_mensual,
        "descripcion": p.descripcion, "activo": p.activo,
        "modulos": p.modulos or [],
        "publico": p.publico, "es_temporal": p.es_temporal,
        "dias_expiracion": p.dias_expiracion,
        "clip_price_id": p.clip_price_id,
        "clip_subscription_link": p.clip_subscription_link,
        "clip_synced": bool(p.clip_price_id and p.clip_subscription_link),
        "cupo_maximo": p.cupo_maximo,
        "cupo_usados": p.cupo_usados or 0,
        "cupo_disponible": (p.cupo_maximo - (p.cupo_usados or 0)) if p.cupo_maximo is not None else None,
        "fecha_inicio_promo": p.fecha_inicio_promo.isoformat() if p.fecha_inicio_promo else None,
        "fecha_fin_promo": p.fecha_fin_promo.isoformat() if p.fecha_fin_promo else None,
        "codigo_invitacion": p.codigo_invitacion,
        "es_promocional": bool(p.cupo_maximo or p.fecha_fin_promo or p.codigo_invitacion),
    }


def _serialize_subscription(s):
    return {
        "id": s.id, "tenant_id": s.tenant_id, "plan_id": s.plan_id,
        "plan_nombre": s.plan.nombre if s.plan else None,
        "plan_modulos": s.plan.modulos if s.plan else [],
        "inicio": s.inicio.isoformat() if s.inicio else None,
        "proximo_cobro": s.proximo_cobro.isoformat() if s.proximo_cobro else None,
        "estado": s.estado,
        "clip_checkout_id": s.clip_checkout_id,
        "grace_expires_at": s.grace_expires_at.isoformat() if s.grace_expires_at else None,
    }


def _serialize_payment(p):
    return {
        "id": p.id, "tenant_id": p.tenant_id,
        "subscription_id": p.subscription_id,
        "fecha": p.fecha.isoformat(),
        "monto": p.monto, "metodo": p.metodo,
        "periodo_inicio": p.periodo_inicio.isoformat() if p.periodo_inicio else None,
        "periodo_fin": p.periodo_fin.isoformat() if p.periodo_fin else None,
        "comentarios": p.comentarios,
        "registrado_por_id": p.registrado_por_id,
        "clip_payment_id": p.clip_payment_id,
        "clip_status": p.clip_status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_note(n):
    return {
        "id": n.id, "texto": n.texto,
        "autor_id": n.autor_id,
        "autor_name": n.autor.name if n.autor else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def _exclude_system(query):
    return query.filter(Tenant.slug != SYSTEM_TENANT_SLUG)


def _generate_temp_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def log_admin_action(action, *, target_type=None, target_id=None,
                     tenant_id=None, summary=None, details=None):
    """Crea una entrada de bitácora con el super-admin actual como actor.
    Agrega a la sesión; el caller hace el commit."""
    entry = AdminAuditLog(
        actor_id=g.current_user.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        tenant_id=tenant_id,
        summary=summary,
        details=details,
    )
    db.session.add(entry)
    return entry


# ── Tenants ──────────────────────────────────────────────────────────────────

def _query_tenants(args):
    """Aplica filtros (status, search, sub_estado) y orden (sort) a la lista de
    clínicas. Usado por la ruta JSON y por el export CSV."""
    status = args.get("status")
    search = (args.get("search") or "").strip()
    sub_estado = args.get("sub_estado")
    sort = args.get("sort") or "reciente"
    today = date.today()

    q = _exclude_system(Tenant.query).outerjoin(
        Subscription, Subscription.tenant_id == Tenant.id
    )
    if status and status in TENANT_STATUSES:
        q = q.filter(Tenant.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            Tenant.name.ilike(like), Tenant.slug.ilike(like),
            Tenant.contact_email.ilike(like),
        ))

    if sub_estado == "activa":
        q = q.filter(Subscription.estado == SUBSCRIPTION_ACTIVA).filter(
            db.or_(Subscription.proximo_cobro.is_(None),
                   Subscription.proximo_cobro >= today))
    elif sub_estado == "mora":
        q = q.filter(Subscription.estado == SUBSCRIPTION_ACTIVA).filter(
            Subscription.proximo_cobro.isnot(None),
            Subscription.proximo_cobro < today)
    elif sub_estado == "gracia":
        q = q.filter(Subscription.estado == SUBSCRIPTION_GRACIA)
    elif sub_estado == "vencida":
        q = q.filter(Subscription.estado == SUBSCRIPTION_VENCIDA)

    if sort == "proximo_cobro":
        q = q.order_by(Subscription.proximo_cobro.is_(None),
                       Subscription.proximo_cobro.asc())
    elif sort == "-proximo_cobro":
        q = q.order_by(Subscription.proximo_cobro.is_(None),
                       Subscription.proximo_cobro.desc())
    elif sort == "plan":
        q = q.order_by(Tenant.plan.asc())
    else:
        q = q.order_by(Tenant.created_at.desc())

    return q.all()


@superadmin_bp.route("/tenants", methods=["GET"])
@require_superuser
def list_tenants():
    tenants = _query_tenants(request.args)
    return jsonify({
        "tenants": [_serialize_tenant(t, with_counts=True) for t in tenants],
    })


@superadmin_bp.route("/tenants/<int:tenant_id>", methods=["GET"])
@require_superuser
def get_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 404
    data = _serialize_tenant(t, with_counts=True)
    sub = Subscription.query.filter_by(tenant_id=t.id).first()
    data["subscription"] = _serialize_subscription(sub) if sub else None
    data["notes_count"] = TenantNote.query.filter_by(tenant_id=t.id).count()
    return jsonify(data)


@superadmin_bp.route("/tenants/<int:tenant_id>/approve", methods=["POST"])
@require_superuser
def approve_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400
    if t.status == TENANT_STATUS_ACTIVE:
        return jsonify({"error": "Tenant ya está activo"}), 409

    data = ApproveTenantSchema().load(request.get_json() or {})
    plan = Plan.query.get(data["plan_id"])
    if not plan or not plan.activo:
        return jsonify({"error": "Plan inválido"}), 400

    inicio = data.get("inicio") or date.today()
    proximo = data.get("proximo_cobro") or _compute_proximo_cobro(plan, inicio)

    t.status = TENANT_STATUS_ACTIVE
    t.is_active = True
    t.approved_at = datetime.now(timezone.utc)
    t.approved_by_id = g.current_user.id
    t.rejected_reason = None
    t.plan = plan.nombre

    sub = Subscription.query.filter_by(tenant_id=t.id).first()
    if sub:
        sub.plan_id = plan.id
        sub.inicio = inicio
        sub.proximo_cobro = proximo
        sub.grace_expires_at = _grace_after(proximo)
        sub.estado = SUBSCRIPTION_ACTIVA
    else:
        sub = Subscription(
            tenant_id=t.id, plan_id=plan.id, inicio=inicio,
            proximo_cobro=proximo, grace_expires_at=_grace_after(proximo),
            estado=SUBSCRIPTION_ACTIVA,
        )
        db.session.add(sub)

    log_admin_action("tenant.approve", target_type="tenant", target_id=t.id,
                     tenant_id=t.id, summary=f"Aprobó la clínica con plan {plan.nombre}")
    db.session.commit()
    return jsonify(_serialize_tenant(t, with_counts=True))


@superadmin_bp.route("/tenants/<int:tenant_id>/reject", methods=["POST"])
@require_superuser
def reject_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400

    data = RejectTenantSchema().load(request.get_json() or {})
    t.status = TENANT_STATUS_REJECTED
    t.is_active = False
    t.rejected_reason = data["razon"]
    log_admin_action("tenant.reject", target_type="tenant", target_id=t.id,
                     tenant_id=t.id, summary="Rechazó la clínica",
                     details={"razon": data["razon"]})
    db.session.commit()
    return jsonify(_serialize_tenant(t))


@superadmin_bp.route("/tenants/<int:tenant_id>/suspend", methods=["POST"])
@require_superuser
def suspend_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400
    t.status = TENANT_STATUS_SUSPENDED
    t.is_active = False
    log_admin_action("tenant.suspend", target_type="tenant", target_id=t.id,
                     tenant_id=t.id, summary="Suspendió la clínica")
    db.session.commit()
    return jsonify(_serialize_tenant(t))


@superadmin_bp.route("/tenants/<int:tenant_id>/activate", methods=["POST"])
@require_superuser
def activate_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400
    t.status = TENANT_STATUS_ACTIVE
    t.is_active = True
    if not t.approved_at:
        t.approved_at = datetime.now(timezone.utc)
        t.approved_by_id = g.current_user.id
    log_admin_action("tenant.activate", target_type="tenant", target_id=t.id,
                     tenant_id=t.id, summary="Reactivó la clínica")
    db.session.commit()
    return jsonify(_serialize_tenant(t))


@superadmin_bp.route("/tenants/<int:tenant_id>", methods=["PUT"])
@require_superuser
def update_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400
    data = TenantUpdateSchema().load(request.get_json() or {})
    for k, v in data.items():
        setattr(t, k, v)
    log_admin_action("tenant.update", target_type="tenant", target_id=t.id,
                     tenant_id=t.id, summary="Editó datos de la clínica", details=data)
    db.session.commit()
    return jsonify(_serialize_tenant(t))


# ── Soporte: read-only data ─────────────────────────────────────────────────

@superadmin_bp.route("/tenants/<int:tenant_id>/users", methods=["GET"])
@require_superuser
def tenant_users(tenant_id):
    Tenant.query.get_or_404(tenant_id)
    users = User.query.filter_by(tenant_id=tenant_id).order_by(User.created_at.asc()).all()
    return jsonify({
        "users": [
            {
                "id": u.id, "email": u.email, "name": u.name, "role": u.role,
                "is_superuser": u.is_superuser, "is_active": u.is_active,
                "must_change_password": u.must_change_password,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    })


@superadmin_bp.route("/tenants/<int:tenant_id>/materiales", methods=["GET"])
@require_superuser
def tenant_materiales(tenant_id):
    Tenant.query.get_or_404(tenant_id)
    mats = Material.query.filter_by(tenant_id=tenant_id).order_by(Material.nombre.asc()).all()
    return jsonify({
        "materiales": [
            {
                "id": m.id, "nombre": m.nombre, "costo_paquete": m.costo_paquete,
                "unidades_paquete": m.unidades_paquete, "costo_unitario": m.costo_unitario,
                "en_inventario": m.en_inventario, "expira": m.expira,
            }
            for m in mats
        ]
    })


@superadmin_bp.route("/tenants/<int:tenant_id>/tratamientos", methods=["GET"])
@require_superuser
def tenant_tratamientos(tenant_id):
    Tenant.query.get_or_404(tenant_id)
    txs = Tratamiento.query.filter_by(tenant_id=tenant_id).order_by(Tratamiento.nombre.asc()).all()
    return jsonify({
        "tratamientos": [
            {
                "id": t.id, "nombre": t.nombre,
                "horas_invertidas": t.horas_invertidas,
                "precio_paciente": t.precio_paciente,
            }
            for t in txs
        ]
    })


@superadmin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@require_superuser
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superuser or (user.tenant and user.tenant.slug == SYSTEM_TENANT_SLUG):
        return jsonify({"error": "No se puede resetear un super-admin"}), 403
    temp = _generate_temp_password()
    user.set_password(temp)
    user.must_change_password = True
    log_admin_action("user.reset_password", target_type="user", target_id=user.id,
                     tenant_id=user.tenant_id,
                     summary=f"Generó contraseña temporal para {user.email}")
    db.session.commit()
    return jsonify({
        "message": "Password temporal generado. Compártelo de forma segura.",
        "user_id": user.id, "email": user.email,
        "temp_password": temp,
    })


@superadmin_bp.route("/users/<int:user_id>/role", methods=["PUT"])
@require_superuser
def change_user_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superuser or (user.tenant and user.tenant.slug == SYSTEM_TENANT_SLUG):
        return jsonify({"error": "No se puede cambiar el rol de un super-admin"}), 403

    data = ChangeUserRoleSchema().load(request.get_json() or {})
    new_role = data["role"]

    if user.role == "admin" and new_role != "admin":
        admin_count = User.query.filter_by(tenant_id=user.tenant_id, role="admin").count()
        if admin_count <= 1:
            return jsonify({
                "error": "No puedes quitar el rol admin al último administrador de la clínica."
            }), 409

    old_role = user.role
    user.role = new_role
    log_admin_action("user.role_change", target_type="user", target_id=user.id,
                     tenant_id=user.tenant_id,
                     summary=f"Cambió rol de {old_role} a {new_role}",
                     details={"old_role": old_role, "new_role": new_role})
    db.session.commit()
    return jsonify({
        "id": user.id, "email": user.email, "name": user.name, "role": user.role,
        "is_superuser": user.is_superuser,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    })


@superadmin_bp.route("/users/<int:user_id>/active", methods=["PUT"])
@require_superuser
def change_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superuser or (user.tenant and user.tenant.slug == SYSTEM_TENANT_SLUG):
        return jsonify({"error": "No se puede deshabilitar un super-admin"}), 403

    data = ToggleActiveSchema().load(request.get_json() or {})
    new_active = data["is_active"]

    if not new_active and user.role == "admin" and user.is_active:
        active_admins = User.query.filter_by(
            tenant_id=user.tenant_id, role="admin", is_active=True
        ).count()
        if active_admins <= 1:
            return jsonify({
                "error": "No puedes desactivar al último administrador activo de la clínica."
            }), 409

    user.is_active = new_active
    log_admin_action("user.activate" if new_active else "user.deactivate",
                     target_type="user", target_id=user.id, tenant_id=user.tenant_id,
                     summary=("Habilitó" if new_active else "Deshabilitó") + f" a {user.email}")
    db.session.commit()
    return jsonify({
        "id": user.id, "email": user.email, "name": user.name, "role": user.role,
        "is_superuser": user.is_superuser, "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    })


@superadmin_bp.route("/users/search", methods=["GET"])
@require_superuser
def search_users():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"users": []})
    like = f"%{q}%"
    users = (
        User.query.join(Tenant, Tenant.id == User.tenant_id)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .filter(db.or_(User.name.ilike(like), User.email.ilike(like)))
        .order_by(User.name.asc())
        .limit(50)
        .all()
    )
    return jsonify({"users": [
        {
            "id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "must_change_password": u.must_change_password,
            "is_superuser": u.is_superuser, "is_active": u.is_active,
            "tenant_id": u.tenant_id,
            "tenant_name": u.tenant.name if u.tenant else None,
            "tenant_slug": u.tenant.slug if u.tenant else None,
            "tenant_status": u.tenant.status if u.tenant else None,
        }
        for u in users
    ]})


# ── Notas internas ──────────────────────────────────────────────────────────

@superadmin_bp.route("/tenants/<int:tenant_id>/notes", methods=["GET"])
@require_superuser
def list_notes(tenant_id):
    Tenant.query.get_or_404(tenant_id)
    notes = (
        TenantNote.query.filter_by(tenant_id=tenant_id)
        .order_by(TenantNote.created_at.desc()).all()
    )
    return jsonify({"notes": [_serialize_note(n) for n in notes]})


@superadmin_bp.route("/tenants/<int:tenant_id>/notes", methods=["POST"])
@require_superuser
def create_note(tenant_id):
    Tenant.query.get_or_404(tenant_id)
    data = TenantNoteSchema().load(request.get_json() or {})
    note = TenantNote(
        tenant_id=tenant_id, autor_id=g.current_user.id, texto=data["texto"],
    )
    db.session.add(note)
    db.session.commit()
    return jsonify(_serialize_note(note)), 201


@superadmin_bp.route("/notes/<int:note_id>", methods=["DELETE"])
@require_superuser
def delete_note(note_id):
    note = TenantNote.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    return jsonify({"message": "Nota eliminada"})


# ── Plans ───────────────────────────────────────────────────────────────────

@superadmin_bp.route("/plans", methods=["GET"])
@require_superuser
def list_plans():
    plans = Plan.query.order_by(Plan.precio_mensual.asc()).all()
    return jsonify({"plans": [_serialize_plan(p) for p in plans]})


def _sync_plan_to_clip(plan, app_base_url):
    """Create a recurring price in Clip for this plan and store the id + link.

    Idempotent: if plan already has clip_price_id, no-op.
    Skips trial plans and free plans (precio_mensual <= 0).

    Raises ClipAPIError on failure. Caller decides whether to fail or just log.
    """
    from app.clip.service import create_price

    if plan.es_temporal or plan.precio_mensual <= 0:
        return False
    if plan.clip_price_id and plan.clip_subscription_link:
        return False

    # `or` encadenado: APP_BASE_URL puede existir con valor None; un base vacío
    # mandaría URLs relativas rotas a Clip, así que caemos al dominio de producción.
    base = (app_base_url or current_app.config.get("APP_BASE_URL")
            or "http://www.dentalplanning.mx").rstrip("/")
    result = create_price(
        name=plan.nombre,
        description=plan.descripcion or plan.nombre,
        amount=plan.precio_mensual,
        webhook_url=f"{base}/api/v1/clip/webhook",
        success_url=f"{base}/registro-exitoso",
        error_url=f"{base}/registro-error",
        default_url=f"{base}/registro-exitoso",
        anchor_on_first_payment=True,
        grace_period_days=current_app.config.get("BILLING_GRACE_DAYS", 3),
    )
    plan.clip_price_id = result.get("id", "")
    plan.clip_subscription_link = (result.get("recurring") or {}).get("subscription_link", "")
    return True


@superadmin_bp.route("/plans", methods=["POST"])
@require_superuser
def create_plan():
    data = PlanSchema().load(request.get_json() or {})
    if Plan.query.filter_by(nombre=data["nombre"]).first():
        return jsonify({"error": "Ya existe un plan con ese nombre"}), 409
    p = Plan(**data)
    db.session.add(p)
    db.session.flush()

    base_url = request.host_url.rstrip("/")
    sync_warning = None
    try:
        _sync_plan_to_clip(p, base_url)
    except ClipAPIError as e:
        current_app.logger.warning("Clip price sync failed for new plan %s: %s", p.nombre, e)
        sync_warning = "Plan creado, pero no se pudo sincronizar con Clip. Usa el botón 'Sincronizar con Clip' después."

    log_admin_action("plan.create", target_type="plan", target_id=p.id,
                     summary=f"Creó el plan {p.nombre}")
    db.session.commit()
    body = _serialize_plan(p)
    if sync_warning:
        body["sync_warning"] = sync_warning
    return jsonify(body), 201


@superadmin_bp.route("/plans/<int:plan_id>", methods=["PUT"])
@require_superuser
def update_plan(plan_id):
    p = Plan.query.get_or_404(plan_id)
    data = PlanSchema().load(request.get_json() or {})
    other = Plan.query.filter(Plan.nombre == data["nombre"], Plan.id != plan_id).first()
    if other:
        return jsonify({"error": "Ya existe un plan con ese nombre"}), 409

    price_changed = (
        "precio_mensual" in data and data["precio_mensual"] != p.precio_mensual
    )
    es_temporal_changed = (
        "es_temporal" in data and bool(data["es_temporal"]) != bool(p.es_temporal)
    )

    for k, v in data.items():
        setattr(p, k, v)

    sync_warning = None
    # If price or es_temporal changed, the Clip price is stale. We can't update
    # /prices/{id} via API (no PUT documented), so we clear it and re-create.
    if (price_changed or es_temporal_changed) and p.clip_price_id:
        current_app.logger.info(
            "Plan %s changed price/temporality; clearing stale Clip price %s",
            p.nombre, p.clip_price_id,
        )
        p.clip_price_id = None
        p.clip_subscription_link = None

    base_url = request.host_url.rstrip("/")
    try:
        _sync_plan_to_clip(p, base_url)
    except ClipAPIError as e:
        current_app.logger.warning("Clip price sync failed for plan %s: %s", p.nombre, e)
        sync_warning = "Plan actualizado, pero no se pudo sincronizar con Clip."

    log_admin_action("plan.update", target_type="plan", target_id=p.id,
                     summary=f"Editó el plan {p.nombre}")
    db.session.commit()
    body = _serialize_plan(p)
    if sync_warning:
        body["sync_warning"] = sync_warning
    return jsonify(body)


@superadmin_bp.route("/plans/<int:plan_id>/sync-clip", methods=["POST"])
@require_superuser
def sync_plan_clip(plan_id):
    """Force re-sync of a single plan to Clip (creates a new /prices entry)."""
    p = Plan.query.get_or_404(plan_id)
    if p.es_temporal or p.precio_mensual <= 0:
        return jsonify({"error": "Solo planes de paga no temporales pueden sincronizarse"}), 400

    p.clip_price_id = None
    p.clip_subscription_link = None
    base_url = request.host_url.rstrip("/")
    try:
        _sync_plan_to_clip(p, base_url)
    except ClipAPIError as e:
        db.session.rollback()
        return jsonify({"error": f"Clip API: {e}"}), 502

    db.session.commit()
    return jsonify(_serialize_plan(p))


@superadmin_bp.route("/plans/sync-clip", methods=["POST"])
@require_superuser
def sync_all_plans_clip():
    """Bulk sync: create Clip prices for all paid non-trial plans missing one."""
    base_url = request.host_url.rstrip("/")
    candidates = Plan.query.filter(
        Plan.activo.is_(True),
        Plan.es_temporal.is_(False),
        Plan.precio_mensual > 0,
        db.or_(Plan.clip_price_id.is_(None), Plan.clip_price_id == ""),
    ).all()

    synced = []
    skipped = []
    errors = []

    for p in candidates:
        try:
            did = _sync_plan_to_clip(p, base_url)
            if did:
                synced.append({"id": p.id, "nombre": p.nombre, "clip_price_id": p.clip_price_id})
            else:
                skipped.append({"id": p.id, "nombre": p.nombre, "reason": "already synced"})
        except ClipAPIError as e:
            errors.append({"id": p.id, "nombre": p.nombre, "error": str(e)})

    db.session.commit()
    return jsonify({"synced": synced, "skipped": skipped, "errors": errors,
                    "total_candidates": len(candidates)})


# ── Subscriptions ───────────────────────────────────────────────────────────

@superadmin_bp.route("/subscriptions", methods=["GET"])
@require_superuser
def list_subscriptions():
    subs = (
        Subscription.query.join(Tenant)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .order_by(Subscription.proximo_cobro.is_(None), Subscription.proximo_cobro.asc())
        .all()
    )
    out = []
    for s in subs:
        d = _serialize_subscription(s)
        d["tenant_name"] = s.tenant.name if s.tenant else None
        d["tenant_status"] = s.tenant.status if s.tenant else None
        out.append(d)
    return jsonify({"subscriptions": out})


@superadmin_bp.route("/subscriptions/<int:sub_id>", methods=["PUT"])
@require_superuser
def update_subscription(sub_id):
    s = Subscription.query.get_or_404(sub_id)
    data = SubscriptionUpdateSchema().load(request.get_json() or {})
    if "plan_id" in data:
        plan = Plan.query.get(data["plan_id"])
        if not plan:
            return jsonify({"error": "Plan inválido"}), 400
        s.tenant.plan = plan.nombre
    for k, v in data.items():
        setattr(s, k, v)
    log_admin_action("subscription.update", target_type="subscription",
                     target_id=s.id, tenant_id=s.tenant_id,
                     summary="Actualizó la suscripción",
                     details={"estado": data.get("estado"), "plan_id": data.get("plan_id")})
    db.session.commit()
    return jsonify(_serialize_subscription(s))


@superadmin_bp.route("/tenants/<int:tenant_id>/assign-plan", methods=["POST"])
@require_superuser
def assign_plan(tenant_id):
    """Assign or change a plan for any tenant (cash/manual payment flow).

    Creates the subscription as 'vencida' if none exists — the account is only
    activated when a payment is explicitly registered via POST /payments.
    If a subscription already exists, only the plan (and optional dates) are updated.
    """
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400

    data = AssignPlanSchema().load(request.get_json() or {})
    plan = Plan.query.get(data["plan_id"])
    if not plan or not plan.activo:
        return jsonify({"error": "Plan inválido o inactivo"}), 400

    inicio = data.get("inicio") or date.today()
    proximo = data.get("proximo_cobro") or _compute_proximo_cobro(plan, inicio)

    sub = Subscription.query.filter_by(tenant_id=t.id).first()
    if sub:
        sub.plan_id = plan.id
        sub.inicio = inicio
        sub.proximo_cobro = proximo
        sub.grace_expires_at = _grace_after(proximo)
    else:
        sub = Subscription(
            tenant_id=t.id,
            plan_id=plan.id,
            inicio=inicio,
            proximo_cobro=proximo,
            grace_expires_at=_grace_after(proximo),
            estado=SUBSCRIPTION_VENCIDA,
        )
        db.session.add(sub)

    t.plan = plan.nombre

    # Free plans and trial plans activate immediately — no payment required.
    # Paid plans stay 'vencida' until a payment is registered.
    is_free_or_trial = plan.precio_mensual <= 0 or plan.es_temporal
    if is_free_or_trial:
        sub.estado = SUBSCRIPTION_ACTIVA
        if not t.is_active:
            t.status = TENANT_STATUS_ACTIVE
            t.is_active = True
            if not t.approved_at:
                t.approved_at = datetime.now(timezone.utc)
                t.approved_by_id = g.current_user.id

    db.session.flush()
    log_admin_action("subscription.assign_plan", target_type="subscription",
                     target_id=sub.id, tenant_id=t.id,
                     summary=f"Asignó/cambió el plan a {plan.nombre}")
    db.session.commit()

    out = _serialize_tenant(t, with_counts=True)
    out["subscription"] = _serialize_subscription(sub)
    return jsonify(out)


# ── Payments ────────────────────────────────────────────────────────────────

def _query_payments(args):
    """Aplica filtros (tenant_id, desde, hasta, metodo, clip_status) a los pagos.
    Usado por la ruta JSON y por el export CSV."""
    q = Payment.query.join(Tenant).filter(Tenant.slug != SYSTEM_TENANT_SLUG)
    tenant_id = args.get("tenant_id")
    if tenant_id:
        q = q.filter(Payment.tenant_id == int(tenant_id))
    desde = args.get("desde")
    if desde:
        q = q.filter(Payment.fecha >= desde)
    hasta = args.get("hasta")
    if hasta:
        q = q.filter(Payment.fecha <= hasta)
    metodo = args.get("metodo")
    if metodo:
        q = q.filter(Payment.metodo == metodo)
    clip_status = args.get("clip_status")
    if clip_status:
        q = q.filter(Payment.clip_status == clip_status)
    return q.order_by(Payment.fecha.desc()).all()


@superadmin_bp.route("/payments", methods=["GET"])
@require_superuser
def list_payments():
    payments = _query_payments(request.args)
    out = []
    for p in payments:
        d = _serialize_payment(p)
        d["tenant_name"] = p.tenant.name if p.tenant else None
        out.append(d)
    return jsonify({"payments": out})


@superadmin_bp.route("/payments", methods=["POST"])
@require_superuser
def create_payment():
    data = PaymentSchema().load(request.get_json() or {})
    tenant = Tenant.query.get(data["tenant_id"])
    if not tenant or tenant.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant inválido"}), 400

    sub_id = data.get("subscription_id")
    if sub_id:
        sub = Subscription.query.get(sub_id)
        if not sub or sub.tenant_id != tenant.id:
            return jsonify({"error": "Suscripción no pertenece al tenant"}), 400
    else:
        sub = Subscription.query.filter_by(tenant_id=tenant.id).first()

    payment = Payment(
        tenant_id=data["tenant_id"],
        subscription_id=sub.id if sub else None,
        fecha=data["fecha"],
        monto=data["monto"],
        metodo=data.get("metodo") or "transferencia",
        periodo_inicio=data.get("periodo_inicio"),
        periodo_fin=data.get("periodo_fin"),
        comentarios=data.get("comentarios"),
        registrado_por_id=g.current_user.id,
    )
    db.session.add(payment)
    db.session.flush()
    log_admin_action("payment.create", target_type="payment", target_id=payment.id,
                     tenant_id=tenant.id,
                     summary=f"Registró un pago de {data['monto']} ({payment.metodo})",
                     details={"monto": data["monto"], "metodo": payment.metodo})

    if sub and data.get("periodo_fin"):
        sub.proximo_cobro = data["periodo_fin"] + timedelta(days=1)
        sub.grace_expires_at = _grace_after(sub.proximo_cobro)
        sub.estado = SUBSCRIPTION_ACTIVA
        # Activate the tenant so billing reminders and module access work
        if tenant.status != TENANT_STATUS_ACTIVE:
            tenant.status = TENANT_STATUS_ACTIVE
            tenant.is_active = True
            if not tenant.approved_at:
                tenant.approved_at = datetime.now(timezone.utc)
                tenant.approved_by_id = g.current_user.id

    db.session.commit()
    return jsonify(_serialize_payment(payment)), 201


@superadmin_bp.route("/payments/<int:payment_id>", methods=["DELETE"])
@require_superuser
def delete_payment(payment_id):
    p = Payment.query.get_or_404(payment_id)
    log_admin_action("payment.delete", target_type="payment", target_id=p.id,
                     tenant_id=p.tenant_id, summary=f"Eliminó un pago de {p.monto}")
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Pago eliminado"})


@superadmin_bp.route("/payments/sync-clip", methods=["POST"])
@require_superuser
def sync_clip_payments():
    """Cross-check PENDING Clip payments by querying their subscription/invoice in Clip.

    For each local Payment with metodo='clip' and clip_status != 'PAID',
    look up its subscription in Clip and reconcile invoice statuses.
    Used as a fallback when webhooks were missed.
    """
    from app.clip.service import get_invoice

    pending = Payment.query.filter(
        Payment.metodo == "clip",
        Payment.clip_payment_id.isnot(None),
        Payment.clip_payment_id != "",
        db.or_(Payment.clip_status != "PAID", Payment.clip_status.is_(None)),
    ).all()

    updated = []
    errors = []
    unchanged = 0

    for p in pending:
        try:
            invoice = get_invoice(p.clip_payment_id)
        except ClipAPIError as e:
            errors.append({"payment_id": p.id, "error": str(e)})
            continue
        if not invoice:
            errors.append({"payment_id": p.id, "error": "invoice not found in Clip"})
            continue

        clip_status = (invoice.get("status") or "").upper()
        old_status = p.clip_status

        if clip_status == "PAID":
            p.clip_status = "PAID"
            if p.subscription_id:
                sub = db.session.get(Subscription, p.subscription_id)
                if sub:
                    sub.estado = SUBSCRIPTION_ACTIVA
                    sub.grace_expires_at = None
                    if p.periodo_fin:
                        sub.proximo_cobro = p.periodo_fin + timedelta(days=1)
            tenant = db.session.get(Tenant, p.tenant_id)
            if tenant and tenant.status != TENANT_STATUS_ACTIVE:
                tenant.status = TENANT_STATUS_ACTIVE
                tenant.is_active = True
            updated.append({"payment_id": p.id, "from": old_status, "to": "PAID"})
        elif clip_status in ("FAILED", "OVERDUE"):
            new_local = clip_status
            if old_status != new_local:
                p.clip_status = new_local
                updated.append({"payment_id": p.id, "from": old_status, "to": new_local})
            else:
                unchanged += 1
        else:
            unchanged += 1

    db.session.commit()
    return jsonify({
        "checked": len(pending),
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
    })


# ── Clip charge ────────────────────────────────────────────────────────────

@superadmin_bp.route("/tenants/<int:tenant_id>/charge", methods=["POST"])
@require_superuser
def charge_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    if t.slug == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Tenant del sistema"}), 400

    sub = Subscription.query.filter_by(tenant_id=t.id).first()
    if not sub:
        return jsonify({"error": "Tenant no tiene suscripción"}), 400

    plan = sub.plan
    if not plan:
        return jsonify({"error": "Plan no encontrado"}), 400

    today = date.today()
    periodo_inicio = today
    periodo_fin = today + timedelta(days=30)

    try:
        result = create_checkout_link(
            amount=plan.precio_mensual,
            description=f"Suscripción {plan.nombre} — {t.name}",
            webhook_url=request.host_url.rstrip("/") + "/api/v1/clip/webhook",
            redirection_url={
                "success": request.host_url.rstrip("/") + f"/admin/tenants/{t.id}",
                "error": request.host_url.rstrip("/") + f"/admin/tenants/{t.id}",
                "default": request.host_url.rstrip("/") + "/admin/tenants",
            },
            metadata={"tenant_id": t.id, "subscription_id": sub.id},
        )
    except ClipAPIError as e:
        return jsonify({"error": str(e)}), 502

    clip_id = result.get("payment_request_id", "")
    clip_url = result.get("payment_request_url", "")

    payment = Payment(
        tenant_id=t.id,
        subscription_id=sub.id,
        fecha=today,
        monto=plan.precio_mensual,
        metodo="clip",
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        comentarios=f"Cobro Clip — {plan.nombre}",
        registrado_por_id=g.current_user.id,
        clip_payment_id=clip_id,
        clip_status="PENDING",
    )
    db.session.add(payment)
    sub.clip_checkout_id = clip_id
    db.session.flush()
    log_admin_action("payment.charge_clip", target_type="tenant", target_id=t.id,
                     tenant_id=t.id, summary=f"Generó cobro Clip por {plan.precio_mensual}")
    db.session.commit()

    return jsonify({
        "clip_url": clip_url,
        "clip_payment_id": clip_id,
        "payment": _serialize_payment(payment),
    }), 201


# ── Stats ───────────────────────────────────────────────────────────────────

@superadmin_bp.route("/stats/overview", methods=["GET"])
@require_superuser
def stats_overview():
    base = _exclude_system(Tenant.query)
    total = base.count()
    activos = base.filter(Tenant.status == TENANT_STATUS_ACTIVE).count()
    pendientes = base.filter(Tenant.status == TENANT_STATUS_PENDING).count()
    suspendidos = base.filter(Tenant.status == TENANT_STATUS_SUSPENDED).count()
    rechazados = base.filter(Tenant.status == TENANT_STATUS_REJECTED).count()

    total_users = (
        db.session.query(func.count(User.id))
        .join(Tenant, Tenant.id == User.tenant_id)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .scalar() or 0
    )

    today = date.today()
    inicio_mes = date(today.year, today.month, 1)
    nuevos_mes = base.filter(Tenant.created_at >= inicio_mes).count()

    en_gracia = (
        Subscription.query.join(Tenant)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .filter(Subscription.estado == SUBSCRIPTION_GRACIA)
        .count()
    )

    subs_by_plan = (
        db.session.query(Plan.nombre, func.count(Subscription.id))
        .join(Subscription, Subscription.plan_id == Plan.id)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .group_by(Plan.nombre)
        .all()
    )

    return jsonify({
        "total_tenants": total,
        "activos": activos,
        "pendientes": pendientes,
        "suspendidos": suspendidos,
        "rechazados": rechazados,
        "total_users": int(total_users),
        "nuevos_este_mes": nuevos_mes,
        "en_gracia": en_gracia,
        "subs_by_plan": [{"plan": r[0], "count": int(r[1])} for r in subs_by_plan],
    })


@superadmin_bp.route("/stats/mrr", methods=["GET"])
@require_superuser
def stats_mrr():
    today = date.today()
    inicio_mes = date(today.year, today.month, 1)

    mrr_actual = (
        db.session.query(func.coalesce(func.sum(Payment.monto), 0.0))
        .join(Tenant, Tenant.id == Payment.tenant_id)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .filter(Payment.fecha >= inicio_mes)
        .scalar()
    )

    serie = []
    for i in range(11, -1, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        ini = date(year, month, 1)
        if month == 12:
            fin = date(year + 1, 1, 1)
        else:
            fin = date(year, month + 1, 1)
        total = (
            db.session.query(func.coalesce(func.sum(Payment.monto), 0.0))
            .join(Tenant, Tenant.id == Payment.tenant_id)
            .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
            .filter(Payment.fecha >= ini, Payment.fecha < fin)
            .scalar()
        )
        serie.append({"mes": ini.isoformat()[:7], "total": float(total or 0)})

    return jsonify({"mrr_actual": float(mrr_actual or 0), "serie": serie})


@superadmin_bp.route("/stats/uso", methods=["GET"])
@require_superuser
def stats_uso():
    metric = request.args.get("metric", "tratamientos")
    if metric == "tratamientos":
        rows = (
            db.session.query(Tenant.id, Tenant.name, func.count(Tratamiento.id))
            .join(Tratamiento, Tratamiento.tenant_id == Tenant.id)
            .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.count(Tratamiento.id).desc())
            .limit(10).all()
        )
    elif metric == "users":
        rows = (
            db.session.query(Tenant.id, Tenant.name, func.count(User.id))
            .join(User, User.tenant_id == Tenant.id)
            .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.count(User.id).desc())
            .limit(10).all()
        )
    elif metric == "materiales":
        rows = (
            db.session.query(Tenant.id, Tenant.name, func.count(Material.id))
            .join(Material, Material.tenant_id == Tenant.id)
            .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.count(Material.id).desc())
            .limit(10).all()
        )
    else:
        return jsonify({"error": "metric inválido"}), 400

    return jsonify({
        "metric": metric,
        "top": [{"tenant_id": r[0], "tenant_name": r[1], "count": int(r[2])} for r in rows],
    })


@superadmin_bp.route("/stats/salud", methods=["GET"])
@require_superuser
def stats_salud():
    today = date.today()
    cola = _exclude_system(Tenant.query).filter(Tenant.status == TENANT_STATUS_PENDING).count()

    def _row(sub):
        return {
            "tenant_id": sub.tenant_id,
            "tenant_name": sub.tenant.name if sub.tenant else None,
            "plan": sub.plan.nombre if sub.plan else None,
            "proximo_cobro": sub.proximo_cobro.isoformat() if sub.proximo_cobro else None,
            "grace_expires_at": sub.grace_expires_at.isoformat() if sub.grace_expires_at else None,
        }

    base = (
        Subscription.query.join(Tenant)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
    )

    en_mora_subs = (
        base.filter(Subscription.estado == SUBSCRIPTION_ACTIVA)
        .filter(Subscription.proximo_cobro.isnot(None))
        .filter(Subscription.proximo_cobro < today)
        .order_by(Subscription.proximo_cobro.asc())
        .all()
    )
    en_gracia_subs = (
        base.filter(Subscription.estado == SUBSCRIPTION_GRACIA)
        .order_by(Subscription.grace_expires_at.asc())
        .all()
    )
    por_vencer_subs = (
        base.filter(Subscription.estado == SUBSCRIPTION_ACTIVA)
        .filter(Subscription.proximo_cobro.isnot(None))
        .filter(Subscription.proximo_cobro >= today)
        .filter(Subscription.proximo_cobro <= today + timedelta(days=7))
        .order_by(Subscription.proximo_cobro.asc())
        .all()
    )

    return jsonify({
        "cola_pendientes": cola,
        "en_mora": len(en_mora_subs),
        "en_gracia": len(en_gracia_subs),
        "por_vencer_7d": len(por_vencer_subs),
        "en_mora_list": [_row(s) for s in en_mora_subs],
        "en_gracia_list": [_row(s) for s in en_gracia_subs],
        "por_vencer_7d_list": [_row(s) for s in por_vencer_subs],
    })


@superadmin_bp.route("/audit", methods=["GET"])
@require_superuser
def list_audit():
    q = AdminAuditLog.query
    tenant_id = request.args.get("tenant_id", type=int)
    if tenant_id:
        q = q.filter(AdminAuditLog.tenant_id == tenant_id)
    action = request.args.get("action")
    if action:
        q = q.filter(AdminAuditLog.action == action)
    desde = request.args.get("desde")
    if desde:
        q = q.filter(AdminAuditLog.created_at >= desde)
    hasta = request.args.get("hasta")
    if hasta:
        q = q.filter(AdminAuditLog.created_at <= hasta)
    rows = q.order_by(AdminAuditLog.created_at.desc()).limit(200).all()
    return jsonify({"events": [
        {
            "id": r.id, "action": r.action,
            "target_type": r.target_type, "target_id": r.target_id,
            "tenant_id": r.tenant_id,
            "tenant_name": r.tenant.name if r.tenant else None,
            "actor_id": r.actor_id,
            "actor_name": r.actor.name if r.actor else None,
            "summary": r.summary, "details": r.details,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]})


# ── Export CSV ───────────────────────────────────────────────────────────────

def _csv_response(header, rows, filename):
    buf = io.StringIO()
    buf.write("﻿")  # BOM para que Excel detecte UTF-8
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@superadmin_bp.route("/tenants/export.csv", methods=["GET"])
@require_superuser
def export_tenants_csv():
    tenants = _query_tenants(request.args)
    header = [
        "nombre", "slug", "email_contacto", "estado", "plan",
        "estado_suscripcion", "proximo_cobro", "usuarios",
        "ultimo_pago_fecha", "ultimo_pago_monto", "creada",
    ]
    rows = []
    for t in tenants:
        r = _serialize_tenant(t, with_counts=True)
        sub = r.get("subscription") or {}
        up = r.get("ultimo_pago") or {}
        rows.append([
            r["name"], r["slug"], r.get("contact_email") or "",
            r["status"], r.get("plan") or "",
            sub.get("estado") or "", sub.get("proximo_cobro") or "",
            r.get("users_count", 0),
            up.get("fecha") or "", up.get("monto") if up else "",
            r.get("created_at") or "",
        ])
    return _csv_response(header, rows, "clinicas.csv")


# ── Asientos de recepcionista ────────────────────────────────────────────────

def _serialize_asiento_admin(a):
    d = seats_service.serialize_asiento(a, with_usuario=True)
    d["tenant_name"] = a.tenant.name if a.tenant else None
    d["solicitado_por_id"] = a.solicitado_por_id
    return d


@superadmin_bp.route("/asientos", methods=["GET"])
@require_superuser
def list_asientos():
    q = AsientoRecepcionista.query
    estado = request.args.get("estado")
    if estado:
        q = q.filter_by(estado=estado)
    asientos = q.order_by(AsientoRecepcionista.created_at.desc()).all()
    return jsonify({"asientos": [_serialize_asiento_admin(a) for a in asientos]})


@superadmin_bp.route("/tenants/<int:tenant_id>/asientos", methods=["GET"])
@require_superuser
def tenant_asientos(tenant_id):
    asientos = AsientoRecepcionista.query.filter_by(
        tenant_id=tenant_id
    ).order_by(AsientoRecepcionista.created_at.desc()).all()
    return jsonify({"asientos": [_serialize_asiento_admin(a) for a in asientos]})


@superadmin_bp.route("/asientos/<int:asiento_id>/aprobar", methods=["POST"])
@require_superuser
def aprobar_asiento_endpoint(asiento_id):
    a = AsientoRecepcionista.query.get_or_404(asiento_id)
    try:
        seats_service.aprobar_asiento(a, g.current_user.id)
    except seats_service.SeatError as e:
        return jsonify({"error": str(e)}), 400
    log_admin_action("asiento.aprobar", target_type="asiento", target_id=a.id,
                     tenant_id=a.tenant_id, summary="Aprobó un asiento de recepcionista")
    db.session.commit()
    return jsonify(_serialize_asiento_admin(a))


@superadmin_bp.route("/asientos/<int:asiento_id>/rechazar", methods=["POST"])
@require_superuser
def rechazar_asiento_endpoint(asiento_id):
    a = AsientoRecepcionista.query.get_or_404(asiento_id)
    data = RechazarAsientoSchema().load(request.get_json() or {})
    try:
        seats_service.rechazar_asiento(a, data["motivo"])
    except seats_service.SeatError as e:
        return jsonify({"error": str(e)}), 400
    log_admin_action("asiento.rechazar", target_type="asiento", target_id=a.id,
                     tenant_id=a.tenant_id, summary="Rechazó un asiento de recepcionista")
    db.session.commit()
    return jsonify(_serialize_asiento_admin(a))


@superadmin_bp.route("/asientos/<int:asiento_id>/activar-manual", methods=["POST"])
@require_superuser
def activar_manual_endpoint(asiento_id):
    a = AsientoRecepcionista.query.get_or_404(asiento_id)
    if a.estado != "aprobada":
        return jsonify({"error": "El asiento no está aprobado"}), 400
    data = ActivarManualSchema().load(request.get_json() or {})
    monto = data.get("monto") if data.get("monto") is not None else (a.monto or 0)
    sub = Subscription.query.filter_by(tenant_id=a.tenant_id).first()
    payment = Payment(
        tenant_id=a.tenant_id,
        subscription_id=sub.id if sub else None,
        fecha=data.get("fecha") or date.today(),
        monto=monto,
        metodo="transferencia",
        comentarios=data.get("comentarios") or "Asiento recepcionista (manual)",
        registrado_por_id=g.current_user.id,
    )
    db.session.add(payment)
    seats_service.activar_asiento(a, "manual")
    log_admin_action("asiento.activar_manual", target_type="asiento", target_id=a.id,
                     tenant_id=a.tenant_id, summary=f"Activó asiento (pago manual {monto})")
    db.session.commit()
    return jsonify(_serialize_asiento_admin(a))


@superadmin_bp.route("/asientos/<int:asiento_id>/cancelar", methods=["POST"])
@require_superuser
def cancelar_asiento_admin_endpoint(asiento_id):
    a = AsientoRecepcionista.query.get_or_404(asiento_id)
    seats_service.cancelar_asiento(a)
    log_admin_action("asiento.cancelar", target_type="asiento", target_id=a.id,
                     tenant_id=a.tenant_id, summary="Canceló un asiento de recepcionista")
    db.session.commit()
    return jsonify(_serialize_asiento_admin(a))


@superadmin_bp.route("/payments/export.csv", methods=["GET"])
@require_superuser
def export_payments_csv():
    payments = _query_payments(request.args)
    header = [
        "clinica", "fecha", "monto", "metodo",
        "periodo_inicio", "periodo_fin", "estado_clip",
        "comentarios", "registrado_por_id",
    ]
    rows = []
    for p in payments:
        rows.append([
            p.tenant.name if p.tenant else "",
            p.fecha.isoformat() if p.fecha else "",
            p.monto,
            p.metodo or "",
            p.periodo_inicio.isoformat() if p.periodo_inicio else "",
            p.periodo_fin.isoformat() if p.periodo_fin else "",
            p.clip_status or "",
            p.comentarios or "",
            p.registrado_por_id or "",
        ])
    return _csv_response(header, rows, "pagos.csv")
