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


# Default system categories that seed DistribucionCategoria on first use
DIST_CATEGORIAS_DEFAULT = [
    {"clave": "pct_sueldo",           "nombre": "Sueldo",           "color": "#0891b2", "porcentaje": 50, "sort_order": 0},
    {"clave": "pct_bonos",            "nombre": "Bonos",            "color": "#059669", "porcentaje": 10, "sort_order": 1},
    {"clave": "pct_mcmp",             "nombre": "MCMP",             "color": "#f59e0b", "porcentaje": 20, "sort_order": 2},
    {"clave": "pct_fondo_emergencia", "nombre": "Fondo Emergencia", "color": "#8b5cf6", "porcentaje": 10, "sort_order": 3},
    {"clave": "pct_marketing",        "nombre": "Marketing",        "color": "#ec4899", "porcentaje": 10, "sort_order": 4},
]


class DistribucionCategoria(db.Model):
    """Dynamic distribution categories per tenant.

    The 5 system categories (es_sistema=True) are seeded from
    DIST_CATEGORIAS_DEFAULT on first access and map back to
    DistribucionConfig columns via `clave`.  Custom categories
    (es_sistema=False) can be freely added and deleted.
    """
    __tablename__ = "distribucion_categorias"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    clave = db.Column(db.String(50))          # maps to DistribucionConfig column for system ones
    color = db.Column(db.String(7), default="#6b7280")
    porcentaje = db.Column(db.Float, default=0)
    es_sistema = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=99)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_dist_categoria"),
    )
