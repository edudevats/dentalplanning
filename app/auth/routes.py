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
from app.auth.schemas import RegisterSchema, LoginSchema, UserCreateSchema, UserUpdateSchema, ChangePasswordSchema
from app.middleware.tenant import require_auth, require_role
from app.middleware.permisos import (
    CATALOGO, ROLE_ASISTENTE, RECURSO_INVENTARIO, normalizar_permisos,
)
from app.middleware.rate_limit import rate_limit
from app.configuracion.models import ConfigConsultorio
from app.ajustes.models import DistribucionConfig, ensure_impuesto_concepto
from app.superadmin.models import Plan, Subscription, Payment, SUBSCRIPTION_ACTIVA
from app.auth import seats_service
from app.clip.billing import add_one_month, create_initial_charge
from app.clip.service import ClipAPIError
from app.facturacion.timezone_helper import get_today

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

    today = get_today()
    if plan.es_temporal and plan.dias_expiracion:
        proximo_cobro = today + timedelta(days=plan.dias_expiracion)
    else:
        proximo_cobro = add_one_month(today)

    sub = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        inicio=today,
        proximo_cobro=proximo_cobro,
        estado=SUBSCRIPTION_ACTIVA,
    )
    db.session.add(sub)
    db.session.flush()

    initial_payment = None
    if is_paid:
        try:
            initial_payment, _ = create_initial_charge(
                sub,
                registered_by_id=user.id,
                base_url=request.host_url.rstrip("/"),
                today=today,
            )
        except (ClipAPIError, ValueError) as exc:
            db.session.rollback()
            current_app.logger.error(
                "No se pudo generar el cobro inicial del plan %s: %s",
                plan.id,
                exc,
            )
            return jsonify({
                "error": "No se pudo generar el link de pago. Intenta de nuevo en unos minutos."
            }), 502

    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    if is_paid:
        msg = "Cuenta creada. Completa el pago inicial de tu mensualidad."
        clip_url = initial_payment.clip_payment_url
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
            "must_change_password": user.must_change_password,
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


def _user_dump(u):
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "permisos": u.permisos or {},
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


@auth_bp.route("/users", methods=["GET"])
@require_auth
@require_role("admin")
def listar_users():
    users = User.query.filter_by(tenant_id=g.tenant_id).order_by(User.created_at).all()
    return jsonify([_user_dump(u) for u in users])


@auth_bp.route("/permisos/catalogo", methods=["GET"])
@require_auth
@require_role("admin")
def catalogo_permisos():
    """Catálogo de recursos otorgables, con lo que el plan del tenant permite.

    Evita duplicar el catálogo en el JS de Ajustes.
    """
    tenant = db.session.get(Tenant, g.tenant_id)
    modulos = tenant.allowed_modules if tenant else []
    return jsonify({
        "recursos": [
            {
                "recurso": recurso,
                "label": meta["label"],
                "disponible": all(slug in modulos for slug in meta["modulos"]),
                "fijo": recurso == RECURSO_INVENTARIO,
            }
            for recurso, meta in CATALOGO.items()
        ]
    })


@auth_bp.route("/users", methods=["POST"])
@require_auth
@require_role("admin")
def crear_user():
    data = UserCreateSchema().load(request.get_json() or {})
    rol = data["role"]
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Este email ya está registrado"}), 409
    if not seats_service.puede_crear(g.tenant_id, rol):
        etiqueta = "asistente" if rol == ROLE_ASISTENTE else "recepcionista"
        return jsonify({
            "error": f"Necesitas un asiento de pago activo para agregar otro "
                     f"{etiqueta}. Solicítalo desde esta sección."
        }), 409
    era_primero = seats_service.usuarios_actuales(g.tenant_id, rol) == 0
    permisos = {}
    if rol == ROLE_ASISTENTE:
        tenant = db.session.get(Tenant, g.tenant_id)
        permisos = normalizar_permisos(
            data["permisos"], modulos_permitidos=tenant.allowed_modules if tenant else []
        )
    user = User(
        tenant_id=g.tenant_id,
        email=data["email"],
        name=data["name"],
        role=rol,
        permisos=permisos,
        must_change_password=True,
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()
    if not era_primero:
        libre = seats_service.asiento_libre_activo(g.tenant_id, rol)
        if libre:
            libre.usuario_id = user.id
    db.session.commit()
    return jsonify(_user_dump(user)), 201


@auth_bp.route("/users/<int:user_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def actualizar_user(user_id):
    user = User.query.filter_by(id=user_id, tenant_id=g.tenant_id).first_or_404()
    if user.role == "admin":
        return jsonify({"error": "No puedes editar al administrador desde aquí"}), 403
    data = UserUpdateSchema().load(request.get_json() or {})
    if "name" in data:
        user.name = data["name"]
    if "is_active" in data:
        user.is_active = data["is_active"]
    if data.get("password"):
        user.set_password(data["password"])
        user.must_change_password = True
    if "permisos" in data and user.role == ROLE_ASISTENTE:
        tenant = db.session.get(Tenant, g.tenant_id)
        user.permisos = normalizar_permisos(
            data["permisos"], modulos_permitidos=tenant.allowed_modules if tenant else []
        )
    db.session.commit()
    return jsonify(_user_dump(user))


@auth_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_user(user_id):
    user = User.query.filter_by(id=user_id, tenant_id=g.tenant_id).first_or_404()
    if user.id == g.current_user.id:
        return jsonify({"error": "No puedes eliminarte a ti mismo"}), 400
    if user.role == "admin":
        return jsonify({"error": "No puedes eliminar a un administrador"}), 403
    seats_service.desligar_usuario(user)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Usuario eliminado"})


@auth_bp.route("/asientos", methods=["GET"])
@require_auth
@require_role("admin")
def listar_asientos():
    rol = request.args.get("rol", "recepcionista")
    if rol not in seats_service.ROLES_CON_ASIENTO:
        return jsonify({"error": "Rol no válido"}), 400
    asientos = seats_service.AsientoRecepcionista.query.filter_by(
        tenant_id=g.tenant_id, rol=rol
    ).order_by(seats_service.AsientoRecepcionista.created_at.desc()).all()
    plan = seats_service.get_addon_plan(rol)
    return jsonify({
        "rol": rol,
        "capacidad": seats_service.capacidad(g.tenant_id, rol),
        "usados": seats_service.usuarios_actuales(g.tenant_id, rol),
        "precio_addon": plan.precio_mensual if plan else None,
        "subscription_link": plan.clip_subscription_link if plan else None,
        "asientos": [
            seats_service.serialize_asiento(a, with_usuario=True) for a in asientos
        ],
    })


@auth_bp.route("/asientos", methods=["POST"])
@require_auth
@require_role("admin")
def solicitar_asiento_endpoint():
    rol = (request.get_json(silent=True) or {}).get("rol", "recepcionista")
    if rol not in seats_service.ROLES_CON_ASIENTO:
        return jsonify({"error": "Rol no válido"}), 400
    try:
        a = seats_service.solicitar_asiento(g.tenant_id, g.current_user.id, rol)
    except seats_service.SeatError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify(seats_service.serialize_asiento(a)), 201


@auth_bp.route("/asientos/<int:asiento_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def cancelar_asiento_endpoint(asiento_id):
    a = seats_service.AsientoRecepcionista.query.filter_by(
        id=asiento_id, tenant_id=g.tenant_id
    ).first_or_404()
    seats_service.cancelar_asiento(a)
    return jsonify({"message": "Asiento cancelado"})


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
    pending_charge = (
        Payment.query.filter(
            Payment.tenant_id == user.tenant.id,
            Payment.billing_cycle_date.isnot(None),
            db.or_(Payment.clip_status != "PAID", Payment.clip_status.is_(None)),
        )
        .order_by(Payment.billing_cycle_date.desc(), Payment.id.desc())
        .first()
    )
    if pending_charge:
        from app.clip.billing import serialize_charge

        billing_nag = serialize_charge(pending_charge)
        billing_nag.update({
            "estado": sub.estado if sub else None,
            "plan_nombre": sub.plan.nombre if sub and sub.plan else None,
            "proximo_cobro": (
                sub.proximo_cobro.isoformat() if sub and sub.proximo_cobro else None
            ),
        })

    return jsonify({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "permisos": user.permisos or {},
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
