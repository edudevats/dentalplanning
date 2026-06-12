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
    descuento_pct = db.Column(db.Float, default=0.0)
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


class PagoComisionIngreso(db.Model):
    """Liga un PagoDoctor (tipo comisión) con los ingresos cuya comisión liquida.

    Permite el seguimiento por-comisión: un ingreso se considera liquidado si
    tiene al menos una fila aquí. La comisión pendiente = ingresos con
    comision_doctor > 0 sin fila en esta tabla. El pago entra como gasto en la
    fecha del PagoDoctor (base de caja), no en la fecha del ingreso.
    """
    __tablename__ = "pago_comision_ingreso"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    pago_id = db.Column(
        db.Integer, db.ForeignKey("pagos_doctores.id"), nullable=False
    )
    ingreso_id = db.Column(
        db.Integer, db.ForeignKey("ingresos.id"), nullable=False
    )
    # Comisión liquidada de ese ingreso (= Ingreso.comision_doctor al pagar).
    monto = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    pago = db.relationship("PagoDoctor", backref="comisiones_liquidadas")
    ingreso = db.relationship("Ingreso", backref="comision_liquidacion")
