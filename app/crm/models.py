from datetime import datetime, timezone
from app.extensions import db

ESTATUS_CRM = ("prospecto", "activo", "alta", "baja")
SEGUIMIENTO_TIPOS = ("llamada", "whatsapp", "otro")


class Paciente(db.Model):
    __tablename__ = "pacientes"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    nombre = db.Column(db.String(200), nullable=False)
    telefono = db.Column(db.String(30))
    whatsapp = db.Column(db.String(30))
    email = db.Column(db.String(255))
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    estatus_crm = db.Column(db.String(20), nullable=False, default="prospecto")
    especialista_id = db.Column(db.Integer, db.ForeignKey("especialistas.id"), nullable=True)
    es_problematico = db.Column(db.Boolean, nullable=False, default=False)
    notas_generales = db.Column(db.Text)
    eliminado = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    especialista = db.relationship("Especialista", backref="pacientes")

    __table_args__ = (
        db.Index("ix_pacientes_tenant_estatus", "tenant_id", "estatus_crm"),
    )


class PacienteVisita(db.Model):
    __tablename__ = "pacientes_visitas"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(300))
    # Visita creada automáticamente desde un ingreso del EDR (una visita por ingreso)
    ingreso_id = db.Column(db.Integer, db.ForeignKey("ingresos.id"), nullable=True, unique=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    paciente = db.relationship(
        "Paciente", backref=db.backref("visitas", lazy="dynamic", cascade="all, delete-orphan")
    )

    __table_args__ = (
        db.Index("ix_visitas_tenant_paciente_fecha", "tenant_id", "paciente_id", "fecha"),
    )


class PacienteSeguimiento(db.Model):
    __tablename__ = "pacientes_seguimientos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="llamada")  # llamada | whatsapp | otro
    fecha_programada = db.Column(db.Date, nullable=False)
    notas = db.Column(db.Text)
    completado = db.Column(db.Boolean, nullable=False, default=False)
    fecha_completado = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    paciente = db.relationship(
        "Paciente", backref=db.backref("seguimientos", lazy="dynamic", cascade="all, delete-orphan")
    )


class PacienteEvento(db.Model):
    __tablename__ = "pacientes_eventos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # cambio_estatus | nota
    detalle = db.Column(db.Text)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    paciente = db.relationship(
        "Paciente", backref=db.backref("eventos", lazy="dynamic", cascade="all, delete-orphan")
    )


class CrmConfig(db.Model):
    __tablename__ = "crm_config"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, unique=True)
    meses_inactividad = db.Column(db.Integer, nullable=False, default=4)
