from datetime import datetime, timezone

from app.extensions import db

EVENTO_CIERRE = "cierre"
EVENTO_REAPERTURA = "reapertura"
EVENTO_RECIERRE = "recierre"
EVENTOS = (EVENTO_CIERRE, EVENTO_REAPERTURA, EVENTO_RECIERRE)


class CorteCaja(db.Model):
    """Cierre de caja de un día en una sucursal.

    La fila existe SOLO cuando el día se cerró: "abierto" es la ausencia de
    fila, no un estado persistido que pueda quedar huérfano. Los totales son
    la foto congelada del momento del cierre — su razón de ser es justamente
    no volver a calcularse.
    """
    __tablename__ = "cortes_caja"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey("sucursales.id"), nullable=True)
    fecha = db.Column(db.Date, nullable=False)

    total_efectivo = db.Column(db.Float, nullable=False, default=0)
    total_tarjeta = db.Column(db.Float, nullable=False, default=0)
    total_transferencia = db.Column(db.Float, nullable=False, default=0)
    total_otro = db.Column(db.Float, nullable=False, default=0)
    # Comisión bancaria de los ingresos de tarjeta: permite conciliar el corte
    # contra el estado de cuenta sin sacar calculadora.
    comision_tarjeta = db.Column(db.Float, nullable=False, default=0)
    salidas_efectivo = db.Column(db.Float, nullable=False, default=0)
    # Fondo con el que arrancó el cajón ese día. Se congela al cerrar, igual que
    # los demás totales: el corte es una foto firmada y el fondo es parte de la
    # foto. Los cortes anteriores a esta migración quedan en 0, que describe
    # bien esos días.
    fondo_inicial = db.Column(db.Float, nullable=False, default=0)
    efectivo_contado = db.Column(db.Float, nullable=False, default=0)

    comentario = db.Column(db.Text)
    cerrado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cerrado_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    usuario = db.relationship("User")
    sucursal = db.relationship("Sucursal")
    eventos = db.relationship(
        "CorteCajaEvento", back_populates="corte",
        order_by="CorteCajaEvento.id", cascade="all, delete-orphan",
    )

    # OJO: en MySQL y SQLite un NULL no colisiona consigo mismo en un índice
    # único, así que esto NO impide dos cortes del mismo día sin sucursal. Esa
    # unicidad la valida services.cerrar_corte(); el índice es la red de
    # seguridad para el caso con sucursal.
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "sucursal_id", "fecha",
                            name="uq_corte_caja_tenant_sucursal_fecha"),
        db.Index("ix_cortes_caja_tenant_fecha", "tenant_id", "fecha"),
    )

    @property
    def esperado_efectivo(self):
        """Lo que debería haber en el cajón: fondo + cobrado en efectivo − salidas."""
        return round((self.fondo_inicial or 0) + (self.total_efectivo or 0)
                     - (self.salidas_efectivo or 0), 2)

    @property
    def diferencia(self):
        """Negativa = faltante, positiva = sobrante."""
        return round((self.efectivo_contado or 0) - self.esperado_efectivo, 2)

    @property
    def total_dia(self):
        return round(
            (self.total_efectivo or 0) + (self.total_tarjeta or 0)
            + (self.total_transferencia or 0) + (self.total_otro or 0), 2,
        )

    @property
    def neto_tarjeta(self):
        return round((self.total_tarjeta or 0) - (self.comision_tarjeta or 0), 2)

    @property
    def cerrado(self):
        """Cerrado salvo que el último evento sea una reapertura.

        Sin eventos también cuenta como cerrado: la fila solo nace al cerrar.
        """
        if not self.eventos:
            return True
        return self.eventos[-1].evento != EVENTO_REAPERTURA


class CorteCajaEvento(db.Model):
    """Bitácora del corte: cierre, reapertura y recierre.

    Existe porque una reapertura sobrescribe los totales de la fila. Sin esta
    tabla, reabrir borraría el rastro del cierre anterior y el candado dejaría
    de significar nada.
    """
    __tablename__ = "cortes_caja_eventos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    corte_id = db.Column(db.Integer, db.ForeignKey("cortes_caja.id"), nullable=False)
    evento = db.Column(db.String(20), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    motivo = db.Column(db.Text)
    # Snapshot de los totales al momento del evento: la historia de lo que la
    # fila decía antes de que un recierre la sobrescribiera.
    datos = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    corte = db.relationship("CorteCaja", back_populates="eventos")
    usuario = db.relationship("User")

    __table_args__ = (
        db.Index("ix_cortes_caja_eventos_tenant_corte", "tenant_id", "corte_id"),
    )


class TurnoCaja(db.Model):
    """Dónde y cuándo trabaja una persona hoy.

    Es contexto de trabajo, NO una entidad contable: el corte sigue siendo uno
    por sucursal y por día, y varias personas pueden alimentar el mismo corte.
    De aquí salen la sucursal y la fecha que se le imponen a todo lo que esa
    persona capture.

    El `fondo_inicial` lo declara quien abre primero ese día en esa sucursal;
    quien abra después lo hereda (services.abrir_turno). Hay UN cajón por
    sucursal, así que el fondo pertenece al día, no a la persona.
    """
    __tablename__ = "turnos_caja"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey("sucursales.id"),
                            nullable=True)
    fecha = db.Column(db.Date, nullable=False)
    fondo_inicial = db.Column(db.Float, nullable=False, default=0)
    abierto_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    # Lo llena el cierre del día; reabrir el corte lo devuelve a NULL.
    cerrado_at = db.Column(db.DateTime)

    usuario = db.relationship("User")
    sucursal = db.relationship("Sucursal")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "usuario_id", "fecha",
                            name="uq_turno_caja_tenant_usuario_fecha"),
        db.Index("ix_turnos_caja_tenant_fecha", "tenant_id", "fecha"),
    )
