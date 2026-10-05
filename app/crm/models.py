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
    # Visita creada automáticamente desde el EDR: una visita por GRUPO de
    # ingresos (visita_uid), anclada a uno solo de sus renglones — el ancla.
    # Los demás hermanos del grupo no tienen fila propia en esta tabla.
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


class DienteEstado(db.Model):
    """Estado de un diente que se aparta de lo esperado por la edad.

    Sin fila = estado por defecto (ver app/crm/odontograma.estado_por_defecto).
    """
    __tablename__ = "dientes_estado"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)  # FDI
    estado = db.Column(db.String(20), nullable=False)
    fecha = db.Column(db.Date, nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("paciente_id", "numero", name="uq_dientes_estado_paciente_numero"),
    )


class DienteTratamiento(db.Model):
    """Una unidad de tratamiento puesta en un diente.

    El origen es un concepto de cotización (nace planeado) o un ingreso directo
    (nace realizado). Descripción, tratamiento y especialista son snapshot para
    que el historial sobreviva si el origen se borra (FK SET NULL +
    origen_eliminado).
    """
    __tablename__ = "dientes_tratamientos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)  # FDI
    caras = db.Column(db.String(20), nullable=True)  # "O,D"; NULL = diente completo
    estatus = db.Column(db.String(20), nullable=False)  # planeado | realizado
    fecha_realizado = db.Column(db.Date, nullable=True)
    especialista_id = db.Column(db.Integer, db.ForeignKey("especialistas.id"), nullable=True)
    tratamiento_id = db.Column(db.Integer, db.ForeignKey("tratamientos.id"), nullable=True)
    descripcion = db.Column(db.String(300), nullable=False)
    cotizacion_concepto_id = db.Column(
        db.Integer, db.ForeignKey("cotizacion_conceptos.id", ondelete="SET NULL"),
        nullable=True,
    )
    ingreso_id = db.Column(
        db.Integer, db.ForeignKey("ingresos.id", ondelete="SET NULL"), nullable=True,
    )
    origen_eliminado = db.Column(db.Boolean, nullable=False, default=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    concepto = db.relationship("CotizacionConcepto")
    ingreso = db.relationship("Ingreso")
    especialista = db.relationship("Especialista")

    __table_args__ = (
        # La misma línea de origen no puede caer dos veces en el mismo diente.
        # En MySQL los NULL no colisionan, así que las filas huérfanas no estorban.
        db.UniqueConstraint("cotizacion_concepto_id", "numero",
                            name="uq_dientes_trat_concepto_numero"),
        db.UniqueConstraint("ingreso_id", "numero", name="uq_dientes_trat_ingreso_numero"),
        db.Index("ix_dientes_trat_tenant_paciente", "tenant_id", "paciente_id"),
    )