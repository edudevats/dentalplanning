from datetime import datetime, timezone
from app.extensions import db


SUBSCRIPTION_ACTIVA = "activa"
SUBSCRIPTION_VENCIDA = "vencida"
SUBSCRIPTION_CANCELADA = "cancelada"
SUBSCRIPTION_ESTADOS = (SUBSCRIPTION_ACTIVA, SUBSCRIPTION_VENCIDA, SUBSCRIPTION_CANCELADA)

PAYMENT_METODOS = ("transferencia", "efectivo", "tarjeta", "otro")


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    precio_mensual = db.Column(db.Float, nullable=False, default=0)
    descripcion = db.Column(db.String(500), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
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
