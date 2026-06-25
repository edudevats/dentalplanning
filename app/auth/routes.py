from flask import Blueprint, request, jsonify, g, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from app.extensions import db
from app.auth.models import (
    Tenant, User, SYSTEM_TENANT_SLUG,
    TENANT_STATUS_PENDING, TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED, TENANT_STATUS_REJECTED,
)
from app.auth.schemas import RegisterSchema, LoginSchema, InviteSchema, ChangePasswordSchema
from app.middleware.tenant import require_auth, require_role
from app.middleware.rate_limit import rate_limit
from app.configuracion.models import ConfigConsultorio
from app.ajustes.models import DistribucionConfig, ensure_impuesto_concepto
from app.superadmin.models import Plan, Subscription, Payment, SUBSCRIPTION_ACTIVA

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


_LOGIN_STATUS_MESSAGES = {
    TENANT_STATUS_PENDING: "Tu cuenta está pendiente de aprobación",
    TENANT_STATUS_SUSPENDED: "Cuenta suspendida. Contacta al soporte",
    TENANT_STATUS_REJECTED: "Tu solicitud fue rechazada",
}


def _plan_is_available(plan, codigo=None, today=None):
    """Check if a plan should be shown in /register or accepted at signup.

    Soft cupo: once cupo_usados >= cupo_maximo, plan disappears from listing.
    Date range: only visible during [fecha_inicio_promo, fecha_fin_promo] if set.
    Invitation code: only visible when caller provides matching codigo.
    """
    from datetime import date as _date
    today = today or _date.today()

    if not plan.activo or not plan.publico:
        return False
    if plan.cupo_maximo is not None and (plan.cupo_usados or 0) >= plan.cupo_maximo:
        return False
    if plan.fecha_inicio_promo and plan.fecha_inicio_promo > today:
        return False
    if plan.fecha_fin_promo and plan.fecha_fin_promo < today:
        return False
    if plan.codigo_invitacion:
        if not codigo or codigo.strip().lower() != plan.codigo_invitacion.lower():
            return False
    return True


@auth_bp.route("/plans", methods=["GET"])
def public_plans():
    codigo = request.args.get("codigo")
    plans = Plan.query.filter_by(activo=True, publico=True).order_by(Plan.precio_mensual.asc()).all()
    visible = [p for p in plans if _plan_is_available(p, codigo=codigo)]
    return jsonify({
        "plans": [
            {
                "id": p.id,
                "nombre": p.nombre,
                "precio_mensual": p.precio_mensual,
                "descripcion": p.descripcion,
                "modulos": p.modulos or [],
                "es_temporal": p.es_temporal,
                "dias_expiracion": p.dias_expiracion,
                "es_promocional": bool(
                    p.cupo_maximo or p.fecha_fin_promo or p.codigo_invitacion
                ),
            }
            for p in visible
        ]
    })


@auth_bp.route("/register", methods=["POST"])
@rate_limit(max_calls=3, period_seconds=60)
def register():
    from datetime import date, timedelta

    schema = RegisterSchema()
    data = schema.load(request.get_json() or {})

    if data["tenant_slug"] == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "No se pudo completar el registro"}), 409

    if Tenant.query.filter_by(slug=data["tenant_slug"]).first():
        return jsonify({"error": "No se pudo completar el registro"}), 409

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Este correo ya está registrado.", "code": "email_already_registered"}), 409

    plan = Plan.query.get(data["plan_id"])
    if not plan or not plan.activo:
        return jsonify({"error": "Plan inválido"}), 400

    codigo = (request.get_json() or {}).get("codigo_invitacion") or request.args.get("codigo")
    if not _plan_is_available(plan, codigo=codigo):
        return jsonify({"error": "Este plan ya no está disponible."}), 410

    is_paid = plan.precio_mensual > 0

    # For paid plans we require a pre-synced Clip recurring price.
    if is_paid and not plan.clip_subscription_link:
        current_app.logger.error(
            "Plan %s (id=%s) has no clip_subscription_link. Run `flask billing sync-prices`.",
            plan.nombre, plan.id,
        )
        return jsonify({
            "error": "Este plan no está disponible para suscripción en este momento. "
                     "Intenta de nuevo en unos minutos o contacta al soporte."
        }), 503

    initial_status = TENANT_STATUS_ACTIVE if is_paid else TENANT_STATUS_PENDING
    initial_active = is_paid

    tenant = Tenant(
        name=data["tenant_name"],
        slug=data["tenant_slug"],
        status=initial_status,
        contact_email=data.get("contact_email") or data["email"],
        is_active=initial_active,
        plan=plan.nombre,
    )
    db.session.add(tenant)
    db.session.flush()

    user = User(
        tenant_id=tenant.id,
        email=data["email"],
        name=data["name"],
        role="admin",
    )
    user.set_password(data["password"])
    db.session.add(user)

    config = ConfigConsultorio(tenant_id=tenant.id)
    db.session.add(config)

    distribucion = DistribucionConfig(tenant_id=tenant.id)
    db.session.add(distribucion)
    ensure_impuesto_concepto(db.session, tenant.id)

    today = date.today()
    if plan.es_temporal and plan.dias_expiracion:
        proximo_cobro = today + timedelta(days=plan.dias_expiracion)
    else:
        proximo_cobro = today + timedelta(days=30)

    sub = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        inicio=today,
        proximo_cobro=proximo_cobro,
        estado=SUBSCRIPTION_ACTIVA,
    )
    db.session.add(sub)
    db.session.flush()

    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    if is_paid:
        msg = "Cuenta creada. Suscríbete para activar tu acceso."
        clip_url = plan.clip_subscription_link
    else:
        msg = "Cuenta creada. Tu acceso será activado por el administrador."
        clip_url = None

    return jsonify({
        "message": msg,
        "clip_url": clip_url,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "status": tenant.status,
            "plan": plan.nombre,
        },
    }), 201


@auth_bp.route("/login", methods=["POST"])
@rate_limit(max_calls=5, period_seconds=60)
def login():
    schema = LoginSchema()
    data = schema.load(request.get_json() or {})

    user = User.query.filter_by(email=data["email"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Credenciales inválidas"}), 401

    if not user.is_superuser and not user.is_active:
        return jsonify({"error": "Usuario deshabilitado. Contacta al administrador."}), 403

    # Super-admin bypassa el chequeo de status
    if not user.is_superuser and user.tenant.status != TENANT_STATUS_ACTIVE:
        msg = _LOGIN_STATUS_MESSAGES.get(user.tenant.status, "Cuenta no activa")
        return jsonify({"error": msg, "status": user.tenant.status}), 403

    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_superuser": user.is_superuser,
            "tenant_id": user.tenant_id,
            "tenant_name": user.tenant.name,
        },
        "access_token": access_token,
        "refresh_token": refresh_token,
    })


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 401
    # Super-admin bypasses tenant check
    if not user.is_superuser:
        if not user.tenant or user.tenant.status != TENANT_STATUS_ACTIVE:
            return jsonify({"error": "Cuenta no activa"}), 403
    access_token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": access_token})


@auth_bp.route("/invite", methods=["POST"])
@require_auth
@require_role("admin")
def invite():
    schema = InviteSchema()
    data = schema.load(request.get_json() or {})

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Este email ya está registrado"}), 409

    user = User(
        tenant_id=g.tenant_id,
        email=data["email"],
        name=data["name"],
        role=data["role"],
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "Usuario invitado exitosamente",
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role},
    }), 201


@auth_bp.route("/password", methods=["PUT"])
@require_auth
@rate_limit(max_calls=5, period_seconds=60)
def change_password():
    schema = ChangePasswordSchema()
    data = schema.load(request.get_json() or {})

    if not g.current_user.check_password(data["current_password"]):
        return jsonify({"error": "Contraseña actual incorrecta"}), 400

    g.current_user.set_password(data["new_password"])
    g.current_user.must_change_password = False
    db.session.commit()
    return jsonify({"message": "Contraseña actualizada"})


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    from datetime import date as date_cls

    user = g.current_user
    sub = user.tenant.subscription
    trial_info = None
    if sub and sub.plan and sub.plan.es_temporal:
        expira = sub.proximo_cobro
        dias_restantes = (expira - date_cls.today()).days if expira else 0
        trial_info = {
            "es_temporal": True,
            "dias_expiracion": sub.plan.dias_expiracion,
            "expira": expira.isoformat() if expira else None,
            "dias_restantes": max(dias_restantes, 0),
            "expirado": dias_restantes <= 0,
        }

    billing_nag = None
    if sub and sub.plan and not sub.plan.es_temporal and sub.proximo_cobro and sub.plan.precio_mensual > 0:
        from app.superadmin.models import SUBSCRIPTION_GRACIA
        today = date_cls.today()
        dias_hasta_cobro = (sub.proximo_cobro - today).days
        is_overdue = sub.estado == SUBSCRIPTION_GRACIA
        # "no_suscrito" = el tenant no tiene cobro recurrente en Clip NI ningún
        # pago registrado. Un pago manual capturado por el super-admin cuenta
        # como suscrito aunque no exista clip_subscription_id.
        has_payment = db.session.query(
            Payment.query.filter_by(tenant_id=user.tenant.id).exists()
        ).scalar()
        not_subscribed = not sub.clip_subscription_id and not has_payment
        if dias_hasta_cobro <= 1 or is_overdue or not_subscribed:
            billing_nag = {
                "estado": sub.estado,
                "plan_nombre": sub.plan.nombre,
                "proximo_cobro": sub.proximo_cobro.isoformat(),
                "dias_hasta_cobro": dias_hasta_cobro,
                "monto": sub.plan.precio_mensual,
                "en_gracia": is_overdue,
                "gracia_expira": sub.grace_expires_at.isoformat() if sub.grace_expires_at else None,
                "no_suscrito": not_subscribed,
                "subscription_link": sub.plan.clip_subscription_link,
            }

    return jsonify({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_superuser": user.is_superuser,
        "tenant": {
            "id": user.tenant.id,
            "name": user.tenant.name,
            "slug": user.tenant.slug,
            "plan": user.tenant.plan,
            "status": user.tenant.status,
            "allowed_modules": user.tenant.allowed_modules,
        },
        "trial": trial_info,
        "billing_nag": billing_nag,
    })
