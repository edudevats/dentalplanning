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


class TurnoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    # La fecha NO se recibe: la pone el servidor. Es justo el dato que el
    # candado le va a imponer a todo lo que capture.
    sucursal_id = fields.Int(allow_none=True, load_default=None)
    fondo_inicial = fields.Float(load_default=0, validate=validate.Range(min=0))


class FondoSchema(Schema):
    """Corrección del fondo del día. La fecha NO se recibe: siempre es hoy."""

    class Meta:
        unknown = EXCLUDE

    sucursal_id = fields.Int(allow_none=True, load_default=None)
    # Requerido, a diferencia de `TurnoSchema`: al abrir, omitirlo significa
    # "arranco sin cambio"; al corregir, omitirlo solo puede ser un descuido.
    fondo_inicial = fields.Float(required=True, validate=validate.Range(min=0))


class SalidaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    fecha = fields.Date(required=True)
    concepto_nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    monto = fields.Float(required=True, validate=validate.Range(min=0.01))
    sucursal_id = fields.Int(allow_none=True, load_default=None)
