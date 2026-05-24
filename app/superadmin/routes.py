import secrets
import string
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, g
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
    Plan, Subscription, Payment, TenantNote,
    SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA,
)
from app.clip.service import create_checkout_link, ClipAPIError
from app.superadmin.schemas import (
    PlanSchema, ApproveTenantSchema, RejectTenantSchema,
    TenantUpdateSchema, PaymentSchema, TenantNoteSchema,
    SubscriptionUpdateSchema,
)
from app.catalogo.models import Material
from app.tratamientos.models import Tratamiento

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/api/v1/superadmin")


# ── Helpers ──────────────────────────────────────────────────────────────────

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
                "grace_expires_at": sub.grace_expires_at.isoformat() if sub.grace_expires_at else None,
            }
    return out


def _serialize_plan(p):
    return {
        "id": p.id, "nombre": p.nombre, "precio_mensual": p.precio_mensual,
        "descripcion": p.descripcion, "activo": p.activo,
        "modulos": p.modulos or [],
        "publico": p.publico, "es_temporal": p.es_temporal,
        "dias_expiracion": p.dias_expiracion,
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


# ── Tenants ──────────────────────────────────────────────────────────────────

@superadmin_bp.route("/tenants", methods=["GET"])
@require_superuser
def list_tenants():
    status = request.args.get("status")
    search = (request.args.get("search") or "").strip()
    q = _exclude_system(Tenant.query)
    if status and status in TENANT_STATUSES:
        q = q.filter(Tenant.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter((Tenant.name.ilike(like)) | (Tenant.slug.ilike(like)) | (Tenant.contact_email.ilike(like)))
    tenants = q.order_by(Tenant.created_at.desc()).all()
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
    proximo = data.get("proximo_cobro") or (inicio + timedelta(days=30))

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
        sub.estado = SUBSCRIPTION_ACTIVA
    else:
        sub = Subscription(
            tenant_id=t.id, plan_id=plan.id, inicio=inicio,
            proximo_cobro=proximo, estado=SUBSCRIPTION_ACTIVA,
        )
        db.session.add(sub)

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
                "is_superuser": u.is_superuser,
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
    db.session.commit()
    return jsonify({
        "message": "Password temporal generado. Compártelo de forma segura.",
        "user_id": user.id, "email": user.email,
        "temp_password": temp,
    })


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


@superadmin_bp.route("/plans", methods=["POST"])
@require_superuser
def create_plan():
    data = PlanSchema().load(request.get_json() or {})
    if Plan.query.filter_by(nombre=data["nombre"]).first():
        return jsonify({"error": "Ya existe un plan con ese nombre"}), 409
    p = Plan(**data)
    db.session.add(p)
    db.session.commit()
    return jsonify(_serialize_plan(p)), 201


@superadmin_bp.route("/plans/<int:plan_id>", methods=["PUT"])
@require_superuser
def update_plan(plan_id):
    p = Plan.query.get_or_404(plan_id)
    data = PlanSchema().load(request.get_json() or {})
    other = Plan.query.filter(Plan.nombre == data["nombre"], Plan.id != plan_id).first()
    if other:
        return jsonify({"error": "Ya existe un plan con ese nombre"}), 409
    for k, v in data.items():
        setattr(p, k, v)
    db.session.commit()
    return jsonify(_serialize_plan(p))


# ── Subscriptions ───────────────────────────────────────────────────────────

@superadmin_bp.route("/subscriptions", methods=["GET"])
@require_superuser
def list_subscriptions():
    subs = (
        Subscription.query.join(Tenant)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .order_by(Subscription.proximo_cobro.asc().nullslast())
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
        if not Plan.query.get(data["plan_id"]):
            return jsonify({"error": "Plan inválido"}), 400
    for k, v in data.items():
        setattr(s, k, v)
    db.session.commit()
    return jsonify(_serialize_subscription(s))


# ── Payments ────────────────────────────────────────────────────────────────

@superadmin_bp.route("/payments", methods=["GET"])
@require_superuser
def list_payments():
    tenant_id = request.args.get("tenant_id", type=int)
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    q = Payment.query.join(Tenant).filter(Tenant.slug != SYSTEM_TENANT_SLUG)
    if tenant_id:
        q = q.filter(Payment.tenant_id == tenant_id)
    if desde:
        q = q.filter(Payment.fecha >= desde)
    if hasta:
        q = q.filter(Payment.fecha <= hasta)
    payments = q.order_by(Payment.fecha.desc()).all()
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

    if sub and data.get("periodo_fin"):
        sub.proximo_cobro = data["periodo_fin"] + timedelta(days=1)
        sub.estado = SUBSCRIPTION_ACTIVA

    db.session.commit()
    return jsonify(_serialize_payment(payment)), 201


@superadmin_bp.route("/payments/<int:payment_id>", methods=["DELETE"])
@require_superuser
def delete_payment(payment_id):
    p = Payment.query.get_or_404(payment_id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Pago eliminado"})


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
    en_mora = (
        Subscription.query.join(Tenant)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .filter(Subscription.estado == SUBSCRIPTION_ACTIVA)
        .filter(Subscription.proximo_cobro.isnot(None))
        .filter(Subscription.proximo_cobro < today)
        .count()
    )
    en_gracia = (
        Subscription.query.join(Tenant)
        .filter(Tenant.slug != SYSTEM_TENANT_SLUG)
        .filter(Subscription.estado == SUBSCRIPTION_GRACIA)
        .count()
    )
    return jsonify({"cola_pendientes": cola, "en_mora": en_mora, "en_gracia": en_gracia})
