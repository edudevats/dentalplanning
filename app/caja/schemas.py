"""Validación de entrada para el blueprint de caja."""
from marshmallow import EXCLUDE, Schema, fields, validate


class CierreSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    fecha = fields.Date(required=True)
    sucursal_id = fields.Int(allow_none=True, load_default=None)
    efectivo_contado = fields.Float(required=True, validate=validate.Range(min=0))
    comentario = fields.Str(allow_none=True, load_default=None)


class ReaperturaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    motivo = fields.Str(required=True, validate=validate.Length(min=1))


class SalidaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    fecha = fields.Date(required=True)
    concepto_nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    monto = fields.Float(required=True, validate=validate.Range(min=0.01))
    sucursal_id = fields.Int(allow_none=True, load_default=None)
