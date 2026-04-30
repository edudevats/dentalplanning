from marshmallow import Schema, fields, validate


class CategoriaPersonalSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    icon = fields.Str(load_default="circle", validate=validate.Length(max=40))
    color = fields.Str(load_default="#0891b2", validate=validate.Length(min=4, max=9))
    orden = fields.Int(load_default=0)
    activo = fields.Bool(load_default=True)


class FuenteIngresoSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    icon = fields.Str(load_default="briefcase", validate=validate.Length(max=40))
    orden = fields.Int(load_default=0)
    activo = fields.Bool(load_default=True)


class IngresoPersonalSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    fuente_id = fields.Int(allow_none=True, load_default=None)
    concepto = fields.Str(load_default="", validate=validate.Length(max=200))
    monto = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    comentarios = fields.Str(allow_none=True)


class GastoPersonalSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    categoria_id = fields.Int(allow_none=True, load_default=None)
    concepto = fields.Str(load_default="", validate=validate.Length(max=200))
    monto = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    comentarios = fields.Str(allow_none=True)


class PresupuestoCategoriaSchema(Schema):
    id = fields.Int(dump_only=True)
    categoria_id = fields.Int(required=True)
    monto_mensual = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    vigente_desde = fields.Date(required=True)


class MetaAhorroSchema(Schema):
    id = fields.Int(dump_only=True)
    label = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    icon = fields.Str(load_default="target", validate=validate.Length(max=40))
    color = fields.Str(load_default="#059669", validate=validate.Length(min=4, max=9))
    monto_objetivo = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    monto_actual = fields.Decimal(load_default=0, as_string=True, places=2, validate=validate.Range(min=0))
    fecha_objetivo = fields.Date(allow_none=True, load_default=None)


class DashboardQuerySchema(Schema):
    """Query string for /dashboard?year=2026&month=4"""
    year = fields.Int(required=True, validate=validate.Range(min=2000, max=2100))
    month = fields.Int(required=True, validate=validate.Range(min=1, max=12))
