from datetime import datetime, timezone
from app.extensions import db


class ConfiguracionFiscal(db.Model):
    """Datos fiscales del emisor (1 por tenant). RFC/CSD compartidos por sucursales."""
    __tablename__ = "configuracion_fiscal"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), unique=True, nullable=False
    )
    # Emisor
    rfc = db.Column(db.String(13))
    razon_social = db.Column(db.String(255))
    regimen_fiscal = db.Column(db.String(5))  # clave SAT, p. ej. "626"
    naturaleza_juridica = db.Column(db.String(20))  # moral_mercantil | fisica_o_civil
    # El logo de la clínica vive en ConfigConsultorio (lo usan también el ticket,
    # el portal y las cotizaciones). Se lee vía app/configuracion/logo.py.
    # Defaults para los conceptos del CFDI
    clave_prod_serv_default = db.Column(db.String(8), default="85121800")
    clave_unidad_default = db.Column(db.String(3), default="E48")
    objeto_imp_default = db.Column(db.String(2), default="01")
    # CSD: cer en claro; key y contraseña CIFRADOS con Fernet
    csd_cer = db.Column(db.LargeBinary)
    csd_key_cifrada = db.Column(db.LargeBinary)
    csd_password_cifrada = db.Column(db.LargeBinary)
    csd_no_certificado = db.Column(db.String(20))
    csd_valido_desde = db.Column(db.DateTime)
    csd_valido_hasta = db.Column(db.DateTime)
    # FIEL (e.firma) — SOLO para cancelar CFDI (key y contraseña cifradas)
    fiel_cer = db.Column(db.LargeBinary)
    fiel_key_cifrada = db.Column(db.LargeBinary)
    fiel_password_cifrada = db.Column(db.LargeBinary)
    fiel_no_certificado = db.Column(db.String(20))
    fiel_valido_desde = db.Column(db.DateTime)
    fiel_valido_hasta = db.Column(db.DateTime)
    # Portal de autofacturación
    ventana_facturacion = db.Column(db.String(20), default="fin_de_mes")
    # Activación comercial del módulo. Al activarlo se cobra una cuota mensual
    # y cada CFDI timbrado se contabiliza por separado en el siguiente corte.
    facturacion_activa = db.Column(db.Boolean, default=False, nullable=False)
    facturacion_activada_at = db.Column(db.DateTime)
    # Conserva el cargo de uso aunque el tenant desactive el módulo antes del
    # corte. Se limpia únicamente cuando el cobro mensual queda generado.
    facturacion_cargo_pendiente = db.Column(db.Boolean, default=False, nullable=False)
    # API key compartida con el agente de impresión local (cifrada con Fernet)
    print_agent_key_cifrada = db.Column(db.LargeBinary)
    # Registro del RFC bajo la cuenta del socio Finkok (Registro de Clientes).
    # Rastrea si el RFC actual ya está dado de alta para decidir add vs edit.
    finkok_registrado_at = db.Column(db.DateTime)
    finkok_rfc_registrado = db.Column(db.String(13))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def csd_configurado(self):
        return bool(self.csd_cer and self.csd_key_cifrada)

    @property
    def fiel_configurada(self):
        return bool(self.fiel_cer and self.fiel_key_cifrada)

    @property
    def print_agent_configurado(self):
        return bool(self.print_agent_key_cifrada)

    @property
    def finkok_registrado(self):
        return bool(self.finkok_registrado_at)


class Sucursal(db.Model):
    """Domicilio/sucursal del tenant. Aporta nombre, dirección, CP y serie de folio."""
    __tablename__ = "sucursales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    direccion = db.Column(db.String(400))
    codigo_postal = db.Column(db.String(5))   # lugar de expedición del CFDI
    telefono = db.Column(db.String(30))
    serie = db.Column(db.String(10), default="")  # prefijo de folio, p. ej. "MTY"
    activa = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index("ix_sucursales_tenant", "tenant_id"),
    )


TICKET_SIN_TIMBRAR = "sin_timbrar"
TICKET_TIMBRADA = "timbrada"
TICKET_EN_PROCESO_CANCELACION = "en_proceso_cancelacion"
TICKET_CANCELADA = "cancelada"
TICKET_ERROR = "error"


class Ticket(db.Model):
    """Ticket facturable: agrupa uno o varios ingresos de una sucursal.

    Folio secuencial POR sucursal. Es la entidad central de la pantalla Facturas.
    Las columnas de CFDI/cancelación se llenan en fases posteriores.
    """
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey("sucursales.id"), nullable=False)
    serie = db.Column(db.String(10), default="")
    folio = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    total = db.Column(db.Float, default=0)
    token = db.Column(db.String(64))
    estado = db.Column(db.String(30), default=TICKET_SIN_TIMBRAR, nullable=False)
    # Receptor (snapshot al timbrar) — Fase 4
    receptor_rfc = db.Column(db.String(13))
    receptor_nombre = db.Column(db.String(255))
    uso_cfdi = db.Column(db.String(5))
    regimen_receptor = db.Column(db.String(5))
    cp_receptor = db.Column(db.String(5))
    email = db.Column(db.String(255))
    # CFDI — Fase 4
    uuid = db.Column(db.String(36))
    # Fecha de emisión del CFDI, fijada en el primer intento de timbrado. Al
    # reintentar un ticket en 'error' se reutiliza para regenerar un comprobante
    # byte-idéntico (mismo sello): si el intento previo sí timbró pero se perdió
    # la respuesta, Finkok lo deduplica en vez de emitir un segundo UUID.
    cfdi_fecha = db.Column(db.DateTime)
    fecha_timbrado = db.Column(db.DateTime)
    xml = db.Column(db.Text)
    forma_pago = db.Column(db.String(5))
    metodo_pago = db.Column(db.String(5))
    # Cancelación — Fase 5
    motivo_cancelacion = db.Column(db.String(2))
    uuid_sustitucion = db.Column(db.String(36))
    acuse_xml = db.Column(db.Text)
    fecha_cancelacion = db.Column(db.DateTime)
    # Errores / correo
    error_timbrado = db.Column(db.Text)
    email_enviado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sucursal = db.relationship("Sucursal")
    ingresos = db.relationship(
        "Ingreso", backref="ticket", foreign_keys="Ingreso.ticket_id"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "sucursal_id", "folio", name="uq_ticket_folio_sucursal"
        ),
        db.Index("ix_tickets_tenant_estado", "tenant_id", "estado"),
    )

    @property
    def folio_display(self):
        return f"{self.serie}-{self.folio}" if self.serie else str(self.folio)
