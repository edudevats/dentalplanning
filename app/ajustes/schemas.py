from marshmallow import Schema, fields, validate, validates_schema, ValidationError


class EspecialistaSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    comision_pct = fields.Float(load_default=0, validate=validate.Range(min=0, max=100))
    is_active = fields.Bool(load_default=True)


class MetodoPagoSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    comision_pct = fields.Float(load_default=0, validate=validate.Range(min=0, max=100))


class GastoConceptoSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    tipo = fields.Str(
        load_default="fijo",
        validate=validate.OneOf(["fijo", "variable"]),
    )
    categoria = fields.Str(
        load_default="operativo",
        validate=validate.OneOf(["operativo", "pago_doctor"]),
    )


class EstrategiaMarketingSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))


class DistribucionConfigSchema(Schema):
    pct_sueldo = fields.Float(required=True, validate=validate.Range(min=0, max=100))
    pct_bonos = fields.Float(required=True, validate=validate.Range(min=0, max=100))
    pct_mcmp = fields.Float(required=True, validate=validate.Range(min=0, max=100))
    pct_fondo_emergencia = fields.Float(required=True, validate=validate.Range(min=0, max=100))
    pct_marketing = fields.Float(required=True, validate=validate.Range(min=0, max=100))

    @validates_schema
    def validate_total(self, data, **kwargs):
        total = sum(data.get(k, 0) for k in [
            "pct_sueldo", "pct_bonos", "pct_mcmp",
            "pct_fondo_emergencia", "pct_marketing",
        ])
        if abs(total - 100) > 0.01:
            raise ValidationError(
                f"Los porcentajes deben sumar 100%. Total actual: {total}%"
            )
