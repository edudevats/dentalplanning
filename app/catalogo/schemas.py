from marshmallow import Schema, fields, validate, EXCLUDE


class MaterialMasterSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str()
    es_medible = fields.Bool()
    categoria = fields.Str()


class MaterialSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    master_id = fields.Int(allow_none=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    es_medible = fields.Bool(load_default=False)
    costo_paquete = fields.Float(required=True, validate=validate.Range(min=0))
    unidades_paquete = fields.Int(required=True, validate=validate.Range(min=1))
    costo_unitario = fields.Float(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ImportMasterSchema(Schema):
    material_ids = fields.List(
        fields.Int(), required=True, validate=validate.Length(min=1)
    )
    costos = fields.Dict(
        keys=fields.Int(),
        values=fields.Dict(
            keys=fields.Str(),
            values=fields.Float(),
        ),
        load_default={},
    )
