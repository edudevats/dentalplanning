from datetime import datetime, timezone
from app.extensions import db


class CategoriaPersonal(db.Model):
    __tablename__ = "categorias_personales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="circle")
    color = db.Column(db.String(9), nullable=False, default="#0891b2")
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "nombre", name="uq_categoria_personal_user_nombre"),
        db.Index("ix_categoria_personal_user", "tenant_id", "user_id"),
    )


class FuenteIngreso(db.Model):
    __tablename__ = "fuentes_ingreso"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="briefcase")
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "nombre", name="uq_fuente_ingreso_user_nombre"),
        db.Index("ix_fuente_ingreso_user", "tenant_id", "user_id"),
    )


class IngresoPersonal(db.Model):
    __tablename__ = "ingresos_personales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    fuente_id = db.Column(db.Integer, db.ForeignKey("fuentes_ingreso.id", ondelete="SET NULL"), nullable=True)
    concepto = db.Column(db.String(200), nullable=False, default="")
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    comentarios = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    fuente = db.relationship("FuenteIngreso")

    __table_args__ = (
        db.Index("ix_ingreso_personal_user_fecha", "tenant_id", "user_id", "fecha"),
    )


class GastoPersonal(db.Model):
    __tablename__ = "gastos_personales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias_personales.id", ondelete="SET NULL"), nullable=True)
    concepto = db.Column(db.String(200), nullable=False, default="")
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    comentarios = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    categoria = db.relationship("CategoriaPersonal")

    __table_args__ = (
        db.Index("ix_gasto_personal_user_fecha", "tenant_id", "user_id", "fecha"),
    )


class PresupuestoCategoria(db.Model):
    __tablename__ = "presupuestos_categoria"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias_personales.id", ondelete="CASCADE"), nullable=False)
    monto_mensual = db.Column(db.Numeric(12, 2), nullable=False)
    vigente_desde = db.Column(db.Date, nullable=False)

    categoria = db.relationship("CategoriaPersonal")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "categoria_id", "vigente_desde", name="uq_presupuesto_user_cat_fecha"),
        db.Index("ix_presupuesto_user", "tenant_id", "user_id"),
    )


class MetaAhorro(db.Model):
    __tablename__ = "metas_ahorro"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="target")
    color = db.Column(db.String(9), nullable=False, default="#059669")
    monto_objetivo = db.Column(db.Numeric(12, 2), nullable=False)
    monto_actual = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    fecha_objetivo = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.Index("ix_meta_ahorro_user", "tenant_id", "user_id"),
    )
