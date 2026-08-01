from datetime import datetime, timezone
from app.extensions import db

ESTATUS_COTIZACION = (
    "borrador", "enviada", "aprobada", "liquidada", "rechazada", "cancelada",
)
# "vencida" NO se almacena: se deriva de valida_hasta al leer.

FRECUENCIAS = ("mensual", "quincenal")
ESTATUS_PROGRAMADO = ("pendiente", "parcial", "pagado", "cancelado")
DESCUENTO_TIPOS = ("monto", "porcentaje")
FACTURACION_ESTADOS = (
    "no_requerida",
    "pendiente",
    "ticket_creado",
    "completada",
    "error_ticket",
    "error_correo",
    "sin_ingresos",
    # El ticket se creó y el correo salió, pero sólo cubre los abonos
    # registrados en el sistema: el resto del plan son pagos históricos.
    "parcial_historicos",
)


class Cotizacion(db.Model):
    """Presupuesto de tratamiento con su plan de pagos diferido."""
    __tablename__ = "cotizaciones"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    folio = db.Column(db.String(20), nullable=False)  # COT-2026-0001
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), nullable=False)
    especialista_id = db.Column(db.Integer, db.ForeignKey("especialistas.id"), nullable=True)
    # Sucursal con la que se facturará al liquidar.
    sucursal_id = db.Column(db.Integer, db.ForeignKey("sucursales.id"), nullable=True)

    fecha = db.Column(db.Date, nullable=False)
    valida_hasta = db.Column(db.Date, nullable=False)
    # La que aparece en el estado de cuenta ("Comenzaron el día ..."). En un plan
    # capturado en curso es anterior a la fecha de la cotización.
    fecha_inicio_tratamiento = db.Column(db.Date, nullable=True)

    estatus = db.Column(db.String(20), nullable=False, default="borrador")

    subtotal = db.Column(db.Float, nullable=False, default=0)
    descuento_tipo = db.Column(db.String(20), nullable=True)  # monto | porcentaje
    descuento_valor = db.Column(db.Float, nullable=False, default=0)
    total = db.Column(db.Float, nullable=False, default=0)

    # Config del plan. Se captura num_parcialidades O monto_parcialidad.
    frecuencia = db.Column(db.String(20), nullable=False, default="mensual")
    num_parcialidades = db.Column(db.Integer, nullable=False, default=1)
    monto_parcialidad = db.Column(db.Float, nullable=True)
    anticipo = db.Column(db.Float, nullable=False, default=0)
    fecha_primer_pago = db.Column(db.Date, nullable=True)

    # Congelada al aprobar: cambiar el catálogo después no mueve la cotización.
    comision_doctor_total = db.Column(db.Float, nullable=False, default=0)

    requiere_factura = db.Column(db.Boolean, nullable=False, default=False)
    # La liquidación del dinero y los efectos externos de facturación se
    # registran por separado. Así un fallo de SMTP o del ticket nunca revierte
    # un abono ya cobrado y puede reintentarse de forma segura.
    facturacion_estado = db.Column(
        db.String(30), nullable=False, default="no_requerida",
    )
    facturacion_error = db.Column(db.Text, nullable=True)
    facturacion_actualizada_at = db.Column(db.DateTime, nullable=True)
    notas = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    aprobada_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    aprobada_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    paciente = db.relationship("Paciente", backref="cotizaciones")
    especialista = db.relationship("Especialista", backref="cotizaciones")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "folio", name="uq_cotizacion_tenant_folio"),
        db.Index("ix_cotizaciones_tenant_estatus", "tenant_id", "estatus"),
        db.Index("ix_cotizaciones_tenant_paciente", "tenant_id", "paciente_id"),
    )


class CotizacionConcepto(db.Model):
    """Renglón de la cotización: del catálogo o libre (aparato, guarda, material)."""
    __tablename__ = "cotizacion_conceptos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    cotizacion_id = db.Column(
        db.Integer, db.ForeignKey("cotizaciones.id"), nullable=False,
    )
    # NULL = renglón libre; el doctor capturó descripción y precio a mano.
    tratamiento_id = db.Column(db.Integer, db.ForeignKey("tratamientos.id"), nullable=True)
    descripcion = db.Column(db.String(300), nullable=False)  # snapshot, siempre poblado
    cantidad = db.Column(db.Float, nullable=False, default=1)
    precio_unitario = db.Column(db.Float, nullable=False, default=0)
    importe = db.Column(db.Float, nullable=False, default=0)
    tipo_servicio = db.Column(db.String(20), default="clinico")  # snapshot
    comision_especialista_tipo = db.Column(db.String(20), default="porcentaje")  # snapshot
    comision_especialista_valor = db.Column(db.Float, nullable=False, default=0)
    orden = db.Column(db.Integer, nullable=False, default=0)

    cotizacion = db.relationship(
        "Cotizacion",
        backref=db.backref("conceptos", cascade="all, delete-orphan",
                           order_by="CotizacionConcepto.orden"),
    )


class PagoProgramado(db.Model):
    """Renglón del calendario. numero 0 = anticipo, 1..N = parcialidades.

    Las fechas son una proyección: no existe estado "vencido" por parcialidad.
    """
    __tablename__ = "pagos_programados"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey("cotizaciones.id"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    monto_programado = db.Column(db.Float, nullable=False)
    # Derivado: lo recalcula aplicar_cascada() en cada alta o baja de pago.
    monto_pagado = db.Column(db.Float, nullable=False, default=0)
    estatus = db.Column(db.String(20), nullable=False, default="pendiente")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cotizacion = db.relationship(
        "Cotizacion",
        backref=db.backref("programados", cascade="all, delete-orphan",
                           order_by="PagoProgramado.numero"),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "cotizacion_id", "numero",
            name="uq_programados_tenant_cot_num",
        ),
    )


class Pago(db.Model):
    """Abono real recibido del paciente."""
    __tablename__ = "cobranza_pagos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey("cotizaciones.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Float, nullable=False)
    metodo_pago_id = db.Column(db.Integer, db.ForeignKey("metodos_pago.id"), nullable=True)
    # Pago recibido ANTES de adoptar el módulo: cuenta para el saldo y el estado
    # de cuenta, pero no genera Ingreso ni comisión (ese dinero ya se registró).
    historico = db.Column(db.Boolean, nullable=False, default=False)
    # Clave enviada por el cliente para que un reintento de red no duplique un
    # abono. NULL conserva compatibilidad con pagos creados sin API.
    idempotency_key = db.Column(db.String(64), nullable=True)
    ingreso_id = db.Column(
        db.Integer, db.ForeignKey("ingresos.id"), nullable=True, unique=True,
    )
    notas = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cotizacion = db.relationship(
        "Cotizacion",
        backref=db.backref("pagos", cascade="all, delete-orphan",
                           order_by="Pago.fecha, Pago.id"),
    )
    metodo_pago = db.relationship("MetodoPago")
    # backref en Ingreso: permite preguntarle a un ingreso si viene de un plan
    # sin tocar la tabla `ingresos`.
    ingreso = db.relationship(
        "Ingreso", backref=db.backref("cobranza_pago", uselist=False),
    )

    __table_args__ = (
        db.Index("ix_cobranza_pagos_tenant_cot_fecha", "tenant_id", "cotizacion_id", "fecha"),
        db.UniqueConstraint(
            "tenant_id", "cotizacion_id", "idempotency_key",
            name="uq_cobranza_pago_idempotency",
        ),
    )


class Devolucion(db.Model):
    """Devolución de dinero a un paciente sobre un plan cancelado.

    No toca `Pago`: los abonos ocurrieron de verdad y su historia se conserva.
    El reflejo contable es un `GastoOperativo` (el dinero sale de caja) y la
    comisión del doctor devengada sobre esos abonos se revierte mediante
    `ComisionReversion`. No crea `Ingreso` (`ingreso_id` queda en NULL; se
    conserva sólo por compatibilidad con devoluciones antiguas).
    """
    __tablename__ = "cobranza_devoluciones"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey("cotizaciones.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    monto = db.Column(db.Float, nullable=False)  # siempre positivo
    metodo_pago_id = db.Column(db.Integer, db.ForeignKey("metodos_pago.id"), nullable=True)
    motivo = db.Column(db.Text, nullable=True)
    ingreso_id = db.Column(
        db.Integer, db.ForeignKey("ingresos.id"), nullable=True, unique=True,
    )
    gasto_id = db.Column(
        db.Integer, db.ForeignKey("gastos_operativos.id"), nullable=True,
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    cotizacion = db.relationship(
        "Cotizacion",
        backref=db.backref("devoluciones", cascade="all, delete-orphan",
                           order_by="Devolucion.fecha, Devolucion.id"),
    )
    metodo_pago = db.relationship("MetodoPago")
    ingreso = db.relationship(
        "Ingreso", backref=db.backref("cobranza_devolucion", uselist=False),
    )
    gasto = db.relationship("GastoOperativo")

    __table_args__ = (
        db.Index("ix_cobranza_devoluciones_tenant_cot", "tenant_id", "cotizacion_id"),
    )


class CobranzaAuditoria(db.Model):
    """Bitácora de operaciones sensibles. `cotizacion_id` va SIN ForeignKey
    a propósito: el registro de un borrado debe sobrevivir a la cotización.
    """
    __tablename__ = "cobranza_auditoria"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    accion = db.Column(db.String(40), nullable=False)
    cotizacion_id = db.Column(db.Integer, nullable=True)  # sin FK: sobrevive al borrado
    cotizacion_folio = db.Column(db.String(20), nullable=False)
    paciente = db.Column(db.String(200), nullable=True)
    monto = db.Column(db.Float, nullable=True)
    detalle = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    usuario = db.relationship("User")

    __table_args__ = (
        db.Index("ix_cobranza_auditoria_tenant_fecha", "tenant_id", "created_at"),
    )


class ComisionReversion(db.Model):
    """Comisión de doctor revertida por una devolución, por abono (Ingreso).

    Si el ingreso NO estaba liquidado al revertir (pagada_al_revertir=False) su
    comisión se saca de pendientes. Si ya estaba pagado (True) el doctor queda
    con un saldo negativo que se descuenta de sus próximas comisiones.
    """
    __tablename__ = "comision_reversiones"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    devolucion_id = db.Column(
        db.Integer, db.ForeignKey("cobranza_devoluciones.id"), nullable=False,
    )
    ingreso_id = db.Column(db.Integer, db.ForeignKey("ingresos.id"), nullable=False)
    monto = db.Column(db.Float, nullable=False)  # comisión revertida (positivo)
    pagada_al_revertir = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    devolucion = db.relationship(
        "Devolucion",
        backref=db.backref("reversiones", cascade="all, delete-orphan"),
    )
    ingreso = db.relationship("Ingreso")

    __table_args__ = (
        db.Index("ix_comision_reversiones_tenant_ing", "tenant_id", "ingreso_id"),
    )
