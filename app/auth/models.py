from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


TENANT_STATUS_PENDING = "pending"
TENANT_STATUS_ACTIVE = "active"
TENANT_STATUS_SUSPENDED = "suspended"
TENANT_STATUS_REJECTED = "rejected"
TENANT_STATUSES = (
    TENANT_STATUS_PENDING,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    TENANT_STATUS_REJECTED,
)

SYSTEM_TENANT_SLUG = "__system__"


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    plan = db.Column(db.String(20), default="free")
    is_active = db.Column(db.Boolean, default=True)
    status = db.Column(
        db.String(20), nullable=False, default=TENANT_STATUS_PENDING
    )
    contact_email = db.Column(db.String(255), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", use_alter=True), nullable=True
    )
    rejected_reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    users = db.relationship(
        "User", backref="tenant", lazy="dynamic", foreign_keys="User.tenant_id"
    )
    materiales = db.relationship("Material", backref="tenant", lazy="dynamic")
    config = db.relationship(
        "ConfigConsultorio", backref="tenant", uselist=False
    )
    tratamientos = db.relationship(
        "Tratamiento", backref="tenant", lazy="dynamic"
    )

    @property
    def is_system(self):
        return self.slug == SYSTEM_TENANT_SLUG

    @property
    def allowed_modules(self):
        if not self.subscription or not self.subscription.plan:
            return []
        return self.subscription.plan.modulos or []


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="editor")  # admin / editor / viewer
    is_superuser = db.Column(db.Boolean, default=False, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
