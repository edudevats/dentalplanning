from datetime import datetime, timezone
from app.extensions import db


class Ingreso(db.Model):
    """Cada tratamiento realizado / ingreso registrado."""
    __tablename__ = "ingresos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    tratamiento_id = db.Column(
        db.Integer, db.ForeignKey("tratamientos.id"), nullable=True
    )
    nombre_tratamiento = db.Column(db.String(200))
    paciente = db.Column(db.String(200))
    especialista_id = db.Column(
        db.Integer, db.ForeignKey("especialistas.id"), nullable=True
    )
    metodo_pago_id = db.Column(
        db.Integer, db.ForeignKey("metodos_pago.id"), nullable=True
    )
    monto = db.Column(db.Float, nullable=False)
    comision_bancaria = db.Column(db.Float, default=0)
    comision_doctor = db.Column(db.Float, default=0)
    factura = db.Column(db.Boolean, default=False)
    estrategia_id = db.Column(
        db.Integer, db.ForeignKey("estrategias_marketing.id"), nullable=True
    )
    comentarios = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tratamiento = db.relationship("Tratamiento", backref="ingresos")
    especialista = db.relationship("Especialista", backref="ingresos")
    metodo_pago = db.relationship("MetodoPago", backref="ingresos")
    estrategia = db.relationship("EstrategiaMarketing", backref="ingresos")


class GastoOperativo(db.Model):
    __tablename__ = "gastos_operativos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    concepto_id = db.Column(
        db.Integer, db.ForeignKey("gastos_conceptos.id"), nullable=True
    )
    concepto_nombre = db.Column(db.String(200))
    tipo = db.Column(db.String(20), default="fijo")  # fijo / variable
    monto = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    concepto = db.relationship("GastoConcepto", backref="gastos")


class PagoDoctor(db.Model):
    __tablename__ = "pagos_doctores"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    especialista_id = db.Column(
        db.Integer, db.ForeignKey("especialistas.id"), nullable=True
    )
    concepto = db.Column(db.String(200))
    tipo = db.Column(db.String(20), default="variable")  # fijo / variable
    monto = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    especialista = db.relationship("Especialista", backref="pagos")
