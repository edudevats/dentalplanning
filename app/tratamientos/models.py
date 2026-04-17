from datetime import datetime, timezone
from app.extensions import db


class Tratamiento(db.Model):
    __tablename__ = "tratamientos"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    horas_invertidas = db.Column(db.Float, default=1.0)
    precio_paciente = db.Column(db.Float, default=0)
    comision_bancaria_pct = db.Column(db.Float, default=5.0)
    comision_especialista_tipo = db.Column(db.String(20), default="porcentaje")
    comision_especialista_valor = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    materiales = db.relationship(
        "TratamientoMaterial",
        backref="tratamiento",
        lazy="joined",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_tratamiento"),
    )


class TratamientoMaterial(db.Model):
    __tablename__ = "tratamiento_materiales"

    id = db.Column(db.Integer, primary_key=True)
    tratamiento_id = db.Column(
        db.Integer, db.ForeignKey("tratamientos.id"), nullable=False
    )
    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.id"), nullable=False
    )
    cantidad = db.Column(db.Float, default=1.0)

    material = db.relationship("Material", lazy="joined")
