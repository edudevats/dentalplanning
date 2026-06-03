from marshmallow import Schema, fields, validate, EXCLUDE


class CategoriaSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    descripcion = fields.Str(allow_none=True)


OPERATORIO_ESTADOS_VALIDOS = ("activo", "suspendido", "reparacion")


class OperatorioSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    orden = fields.Int(load_default=0)
    estado = fields.Str(
        load_default="activo",
        validate=validate.OneOf(OPERATORIO_ESTADOS_VALIDOS),
    )
    disponible = fields.Bool(dump_only=True)


class OperatorioEstadoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    estado = fields.Str(
        required=True, validate=validate.OneOf(OPERATORIO_ESTADOS_VALIDOS)
    )


class UmbralesUbicacionSchema(Schema):
    operatorio_id = fields.Int(allow_none=True)
    minimo = fields.Int(allow_none=True)
    maximo = fields.Int(allow_none=True)


class MaterialInventarioSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True)
    categorias = fields.List(fields.Int(), load_default=[])
    expira = fields.Bool(load_default=True)
    unidad_inventario = fields.Str(load_default="pieza")
    en_inventario = fields.Bool(dump_only=True)  # politica auto-sync: siempre True
    umbrales = fields.List(fields.Nested(UmbralesUbicacionSchema), load_default=[])


class CompraSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    material_id = fields.Int(required=True)
    cantidad = fields.Int(required=True, validate=validate.Range(min=1))
    precio_unitario = fields.Float(required=True, validate=validate.Range(min=0))
    fecha_surtido = fields.Date(required=True)
    fecha_caducidad = fields.Date(allow_none=True)
    no_caduca = fields.Bool(load_default=False)
    operatorio_destino_id = fields.Int(allow_none=True, load_default=None)
    comentarios = fields.Str(allow_none=True)
    actualizar_costo_master = fields.Bool(load_default=False)


class TransferenciaSchema(Schema):
    material_id = fields.Int(required=True)
    origen_operatorio_id = fields.Int(allow_none=True)
    destino_operatorio_id = fields.Int(allow_none=True)
    cantidad = fields.Int(required=True, validate=validate.Range(min=1))
    lote_id = fields.Int(allow_none=True, load_default=None)
    motivo = fields.Str(allow_none=True)


class AjusteSchema(Schema):
    material_id = fields.Int(required=True)
    operatorio_id = fields.Int(allow_none=True)
    cantidad_nueva = fields.Int(required=True, validate=validate.Range(min=0))
    motivo = fields.Str(required=True, validate=validate.Length(min=1))
    lote_id = fields.Int(allow_none=True, load_default=None)


class ImportMasterInventarioSchema(Schema):
    master_ids = fields.List(fields.Int(), required=True)
