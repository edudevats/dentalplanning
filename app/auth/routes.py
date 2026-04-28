from flask import Blueprint, request, jsonify, g
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
from app.configuracion.models import ConfigConsultorio
from app.ajustes.models import DistribucionConfig

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


_LOGIN_STATUS_MESSAGES = {
    TENANT_STATUS_PENDING: "Tu cuenta está pendiente de aprobación",
    TENANT_STATUS_SUSPENDED: "Cuenta suspendida. Contacta al soporte",
    TENANT_STATUS_REJECTED: "Tu solicitud fue rechazada",
}


@auth_bp.route("/register", methods=["POST"])
def register():
    schema = RegisterSchema()
    data = schema.load(request.get_json())

    if data["tenant_slug"] == SYSTEM_TENANT_SLUG:
        return jsonify({"error": "Slug reservado"}), 409

    if Tenant.query.filter_by(slug=data["tenant_slug"]).first():
        return jsonify({"error": "Este slug ya está en uso"}), 409

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "Este email ya está registrado"}), 409

    tenant = Tenant(
        name=data["tenant_name"],
        slug=data["tenant_slug"],
        status=TENANT_STATUS_PENDING,
        contact_email=data.get("contact_email") or data["email"],
        is_active=False,
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

    db.session.commit()

    return jsonify({
        "message": "Solicitud recibida. Revisaremos tu cuenta y te contactaremos pronto.",
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "status": tenant.status,
        },
    }), 202


@auth_bp.route("/login", methods=["POST"])
def login():
    schema = LoginSchema()
    data = schema.load(request.get_json())

    user = User.query.filter_by(email=data["email"]).first()
    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Credenciales inválidas"}), 401

    # Super-admin bypassa el chequeo de status
    if not user.is_superuser and user.tenant.status != TENANT_STATUS_ACTIVE:
        msg = _LOGIN_STATUS_MESSAGES.get(user.tenant.status, "Cuenta no activa")
        return jsonify({"error": msg, "status": user.tenant.status}), 403

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
    access_token = create_access_token(identity=str(user_id))
    return jsonify({"access_token": access_token})


@auth_bp.route("/invite", methods=["POST"])
@require_auth
@require_role("admin")
def invite():
    schema = InviteSchema()
    data = schema.load(request.get_json())

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
def change_password():
    schema = ChangePasswordSchema()
    data = schema.load(request.get_json())

    if not g.current_user.check_password(data["current_password"]):
        return jsonify({"error": "Contraseña actual incorrecta"}), 400

    g.current_user.set_password(data["new_password"])
    db.session.commit()
    return jsonify({"message": "Contraseña actualizada"})


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    user = g.current_user
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
        },
    })
