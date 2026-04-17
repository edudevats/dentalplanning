from marshmallow import Schema, fields, validate


class IngresoSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    tratamiento_id = fields.Int(allow_none=True)
    nombre_tratamiento = fields.Str()
    paciente = fields.Str()
    especialista_id = fields.Int(allow_none=True)
    metodo_pago_id = fields.Int(allow_none=True)
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    comision_bancaria = fields.Float(load_default=0)
    comision_doctor = fields.Float(load_default=0)
    factura = fields.Bool(load_default=False)
    estrategia_id = fields.Int(allow_none=True)
    comentarios = fields.Str(allow_none=True)
    # Read-only enriched fields
    especialista_nombre = fields.Str(dump_only=True)
    metodo_pago_nombre = fields.Str(dump_only=True)
    estrategia_nombre = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class GastoOperativoSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    concepto_id = fields.Int(allow_none=True)
    concepto_nombre = fields.Str(required=True)
    tipo = fields.Str(
        load_default="fijo",
        validate=validate.OneOf(["fijo", "variable"]),
    )
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    created_at = fields.DateTime(dump_only=True)


class PagoDoctorSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    especialista_id = fields.Int(allow_none=True)
    concepto = fields.Str(required=True)
    tipo = fields.Str(
        load_default="variable",
        validate=validate.OneOf(["fijo", "variable"]),
    )
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    especialista_nombre = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
