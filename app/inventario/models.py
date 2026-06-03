from app.extensions import db


class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.String(200))


class MaterialCategoria(db.Model):
    __tablename__ = "material_categoria"

    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.id", ondelete="CASCADE"), primary_key=True
    )
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categorias.id"), primary_key=True
    )
    __table_args__ = (
        db.Index("ix_material_categoria_categoria_id", "categoria_id"),
    )


class MaterialMasterCategoria(db.Model):
    __tablename__ = "material_master_categoria"

    material_master_id = db.Column(
        db.Integer, db.ForeignKey("materiales_master.id", ondelete="CASCADE"), primary_key=True
    )
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categorias.id"), primary_key=True
    )
    __table_args__ = (
        db.Index("ix_material_master_categoria_categoria_id", "categoria_id"),
    )


OPERATORIO_ACTIVO = "activo"
OPERATORIO_SUSPENDIDO = "suspendido"
OPERATORIO_REPARACION = "reparacion"
OPERATORIO_ESTADOS = (OPERATORIO_ACTIVO, OPERATORIO_SUSPENDIDO, OPERATORIO_REPARACION)


class Operatorio(db.Model):
    __tablename__ = "operatorios"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    orden = db.Column(db.Integer, default=0, nullable=False)
    estado = db.Column(
        db.String(20), default=OPERATORIO_ACTIVO, nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_operatorio"),
    )

    @property
    def disponible(self):
        return self.estado == OPERATORIO_ACTIVO


class Lote(db.Model):
    __tablename__ = "lotes"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    cantidad_inicial = db.Column(db.Integer, nullable=False)
    fecha_surtido = db.Column(db.Date, nullable=False)
    fecha_caducidad = db.Column(db.Date, nullable=True)
    precio_unitario = db.Column(db.Float, nullable=True)
    comentarios = db.Column(db.String(500), nullable=True)
    agotado = db.Column(db.Boolean, default=False, nullable=False)


class LoteUbicacion(db.Model):
    __tablename__ = "lote_ubicacion"

    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=False)
    operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    cantidad_restante = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("lote_id", "operatorio_id", name="uq_lote_ubicacion"),
    )


class StockUbicacion(db.Model):
    __tablename__ = "stock_ubicacion"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    cantidad = db.Column(db.Integer, default=0, nullable=False)
    minimo = db.Column(db.Integer, nullable=True)
    maximo = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "material_id", "operatorio_id",
            name="uq_stock_ubicacion",
        ),
    )


class Compra(db.Model):
    __tablename__ = "compras"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    comentarios = db.Column(db.String(500), nullable=True)
    actualizo_costo_master = db.Column(db.Boolean, default=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class MovimientoInventario(db.Model):
    __tablename__ = "movimientos_inventario"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=True)
    tipo = db.Column(db.String(20), nullable=False)
    origen_operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    destino_operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    motivo = db.Column(db.String(500), nullable=True)
