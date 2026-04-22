from datetime import datetime, timezone
from app.extensions import db


class MaterialMaster(db.Model):
    """Catálogo global de materiales (SaaS). Los tenants copian de aquí."""
    __tablename__ = "materiales_master"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), unique=True, nullable=False)
    es_medible = db.Column(db.Boolean, default=False)
    categoria = db.Column(db.String(100), default="general")
    expira = db.Column(db.Boolean, default=True, nullable=False)
    unidad_inventario = db.Column(db.String(30), default="pieza", nullable=False)

    categorias = db.relationship(
        "Categoria",
        secondary="material_master_categoria",
        backref="materiales_master",
        passive_deletes=True,
    )


class Material(db.Model):
    """Materiales del tenant (copiados del master o creados propios)."""
    __tablename__ = "materiales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    master_id = db.Column(
        db.Integer, db.ForeignKey("materiales_master.id"), nullable=True
    )
    nombre = db.Column(db.String(200), nullable=False)
    es_medible = db.Column(db.Boolean, default=False)
    costo_paquete = db.Column(db.Float, default=0)
    unidades_paquete = db.Column(db.Integer, default=1)
    expira = db.Column(db.Boolean, default=True, nullable=False)
    unidad_inventario = db.Column(db.String(30), default="pieza", nullable=False)
    en_inventario = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_material"),
    )

    @property
    def costo_unitario(self):
        if self.unidades_paquete and self.unidades_paquete > 0:
            return round(self.costo_paquete / self.unidades_paquete, 4)
        return 0

    master = db.relationship("MaterialMaster", backref="copies")

    categorias = db.relationship(
        "Categoria",
        secondary="material_categoria",
        backref="materiales",
        passive_deletes=True,
    )
