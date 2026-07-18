from datetime import datetime, timezone
from app.extensions import db


SUBSCRIPTION_ACTIVA = "activa"
SUBSCRIPTION_VENCIDA = "vencida"
SUBSCRIPTION_CANCELADA = "cancelada"
SUBSCRIPTION_GRACIA = "gracia"
SUBSCRIPTION_ESTADOS = (SUBSCRIPTION_ACTIVA, SUBSCRIPTION_VENCIDA, SUBSCRIPTION_CANCELADA, SUBSCRIPTION_GRACIA)

PAYMENT_METODOS = ("transferencia", "efectivo", "tarjeta", "clip", "otro")

ADDON_TIPO_RECEPCIONISTA = "recepcionista"

ASIENTO_PENDIENTE = "pendiente"
ASIENTO_RECHAZADA = "rechazada"
ASIENTO_APROBADA = "aprobada"
ASIENTO_ACTIVA = "activa"
ASIENTO_CANCELADA = "cancelada"
ASIENTO_ESTADOS = (
    ASIENTO_PENDIENTE, ASIENTO_RECHAZADA, ASIENTO_APROBADA,
    ASIENTO_ACTIVA, ASIENTO_CANCELADA,
)


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
    addon_tipo = db.Column(db.String(30), nullable=True)
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
    # Datos del corte variable. Los pagos manuales históricos mantienen estos
    # campos en NULL; los cobros automáticos tienen un solo registro por corte.
    billing_cycle_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    plan_amount = db.Column(db.Float, nullable=True)
    invoice_base_fee = db.Column(db.Float, nullable=True)
    stamp_count = db.Column(db.Integer, nullable=True)
    stamp_unit_price = db.Column(db.Float, nullable=True)
    stamp_amount = db.Column(db.Float, nullable=True)
    clip_payment_url = db.Column(db.String(500), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship("Tenant", backref=db.backref("payments", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "billing_cycle_date", name="uq_payment_tenant_billing_cycle"
        ),
    )


class TenantNote(db.Model):
    __tablename__ = "tenant_notes"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    autor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    texto = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    autor = db.relationship("User")


class AdminAuditLog(db.Model):
    __tablename__ = "admin_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(20), nullable=True)   # tenant|user|subscription|payment|plan
    target_id = db.Column(db.Integer, nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=True)
    summary = db.Column(db.String(500), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    actor = db.relationship("User", foreign_keys=[actor_id])
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])


class AsientoRecepcionista(db.Model):
    __tablename__ = "asientos_recepcionista"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    estado = db.Column(db.String(20), nullable=False, default=ASIENTO_PENDIENTE)
    solicitado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    aprobado_at = db.Column(db.DateTime, nullable=True)
    rechazo_motivo = db.Column(db.String(500), nullable=True)
    monto = db.Column(db.Float, nullable=True)
    pago_metodo = db.Column(db.String(20), nullable=True)
    clip_subscription_id = db.Column(db.String(100), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
