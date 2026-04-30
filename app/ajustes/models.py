from datetime import datetime, timezone
from app.extensions import db


class Especialista(db.Model):
    __tablename__ = "especialistas"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    comision_pct = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_especialista"),
    )


class MetodoPago(db.Model):
    __tablename__ = "metodos_pago"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    comision_pct = db.Column(db.Float, default=0)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_metodo_pago"),
    )


class GastoConcepto(db.Model):
    __tablename__ = "gastos_conceptos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), default="fijo")  # fijo / variable
    categoria = db.Column(db.String(20), default="operativo")  # operativo / pago_doctor

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_gasto_concepto"),
    )


class EstrategiaMarketing(db.Model):
    __tablename__ = "estrategias_marketing"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_estrategia"),
    )


class DistribucionConfig(db.Model):
    __tablename__ = "distribucion_config"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), unique=True, nullable=False
    )
    pct_sueldo = db.Column(db.Float, default=50)
    pct_bonos = db.Column(db.Float, default=10)
    pct_mcmp = db.Column(db.Float, default=20)
    pct_fondo_emergencia = db.Column(db.Float, default=10)
    pct_marketing = db.Column(db.Float, default=10)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def total_porcentaje(self):
        return (
            self.pct_sueldo
            + self.pct_bonos
            + self.pct_mcmp
            + self.pct_fondo_emergencia
            + self.pct_marketing
        )
