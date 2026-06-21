from marshmallow import Schema, fields, validate, EXCLUDE


class TratamientoMaterialInputSchema(Schema):
    material_id = fields.Int(required=True)
    cantidad = fields.Float(required=True, validate=validate.Range(min=0.01))


class TratamientoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    horas_invertidas = fields.Float(load_default=1.0, validate=validate.Range(min=0))
    precio_paciente = fields.Float(required=True, validate=validate.Range(min=0))
    comision_bancaria_pct = fields.Float(load_default=5.0, validate=validate.Range(min=0, max=100))
    comision_especialista_tipo = fields.Str(
        load_default="porcentaje",
        validate=validate.OneOf(["porcentaje", "fijo"]),
    )
    comision_especialista_valor = fields.Float(load_default=0, validate=validate.Range(min=0))
    tipo_servicio = fields.Str(
        load_default="clinico",
        validate=validate.OneOf(["clinico", "estetico"]),
    )
    materiales = fields.List(fields.Nested(TratamientoMaterialInputSchema), load_default=[])
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class SimularSchema(Schema):
    precio_paciente = fields.Float(required=True, validate=validate.Range(min=0))
    comision_bancaria_pct = fields.Float()
    comision_especialista_tipo = fields.Str(validate=validate.OneOf(["porcentaje", "fijo"]))
    comision_especialista_valor = fields.Float()
