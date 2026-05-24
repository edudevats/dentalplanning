from datetime import datetime, timezone
from app.extensions import db


SUBSCRIPTION_ACTIVA = "activa"
SUBSCRIPTION_VENCIDA = "vencida"
SUBSCRIPTION_CANCELADA = "cancelada"
SUBSCRIPTION_GRACIA = "gracia"
SUBSCRIPTION_ESTADOS = (SUBSCRIPTION_ACTIVA, SUBSCRIPTION_VENCIDA, SUBSCRIPTION_CANCELADA, SUBSCRIPTION_GRACIA)

PAYMENT_METODOS = ("transferencia", "efectivo", "tarjeta", "clip", "otro")


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    precio_mensual = db.Column(db.Float, nullable=False, default=0)
    descripcion = db.Column(db.String(500), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    modulos = db.Column(db.JSON, nullable=False, default=list)
    publico = db.Column(db.Boolean, nullable=False, default=True)
    es_temporal = db.Column(db.Boolean, nullable=False, default=False)
    dias_expiracion = db.Column(db.Integer, nullable=True)
    clip_price_id = db.Column(db.String(100), nullable=True)
    clip_subscription_link = db.Column(db.String(500), nullable=True)
    # Promotional plan limits — all optional, combinable
    cupo_maximo = db.Column(db.Integer, nullable=True)
    cupo_usados = db.Column(db.Integer, nullable=False, default=0)
    fecha_inicio_promo = db.Column(db.Date, nullable=True)
    fecha_fin_promo = db.Column(db.Date, nullable=True)
    codigo_invitacion = db.Column(db.String(50), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), unique=True, nullable=False
    )
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    inicio = db.Column(db.Date, nullable=False)
    proximo_cobro = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default=SUBSCRIPTION_ACTIVA)
    clip_checkout_id = db.Column(db.String(100), nullable=True)  # legacy: one-time /v2/checkout link id
    clip_customer_id = db.Column(db.String(100), nullable=True)
    clip_subscription_id = db.Column(db.String(100), nullable=True)  # active: Clip /subscriptions id
    grace_expires_at = db.Column(db.Date, nullable=True)
    counted_in_cupo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship("Tenant", backref=db.backref("subscription", uselist=False))
    plan = db.relationship("Plan")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id"), nullable=True
    )
    fecha = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Float, nullable=False)
    metodo = db.Column(db.String(20), nullable=False, default="transferencia")
    periodo_inicio = db.Column(db.Date, nullable=True)
    periodo_fin = db.Column(db.Date, nullable=True)
    comentarios = db.Column(db.String(500), nullable=True)
    registrado_por_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    clip_payment_id = db.Column(db.String(100), nullable=True)  # invoice_id (recurring) or payment_request_id (legacy)
    clip_status = db.Column(db.String(20), nullable=True)  # PAID | PENDING | OVERDUE | FAILED | EXPIRED | CANCELLED
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship("Tenant", backref=db.backref("payments", lazy="dynamic"))


class TenantNote(db.Model):
    __tablename__ = "tenant_notes"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    texto = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    autor = db.relationship("User")
