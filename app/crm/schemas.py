from marshmallow import Schema, fields, validate, EXCLUDE
from app.crm.models import ESTATUS_CRM, SEGUIMIENTO_TIPOS


class PacienteSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    telefono = fields.Str(allow_none=True, validate=validate.Length(max=30))
    whatsapp = fields.Str(allow_none=True, validate=validate.Length(max=30))
    email = fields.Str(allow_none=True, validate=validate.Length(max=255))
    fecha_nacimiento = fields.Date(allow_none=True)
    estatus_crm = fields.Str(validate=validate.OneOf(ESTATUS_CRM))
    especialista_id = fields.Int(allow_none=True)
    es_problematico = fields.Bool()
    notas_generales = fields.Str(allow_none=True)
    # Enriquecidos (solo lectura)
    especialista_nombre = fields.Str(dump_only=True)
    ultima_visita = fields.Date(dump_only=True)
    siguiente_seguimiento = fields.Date(dump_only=True)
    inactivo = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class VisitaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    motivo = fields.Str(allow_none=True, validate=validate.Length(max=300))
    ingreso_id = fields.Int(dump_only=True)


class SeguimientoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    tipo = fields.Str(load_default="llamada", validate=validate.OneOf(SEGUIMIENTO_TIPOS))
    fecha_programada = fields.Date(required=True)
    notas = fields.Str(allow_none=True)
    completado = fields.Bool(dump_only=True)
    fecha_completado = fields.Date(dump_only=True)


class NotaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    texto = fields.Str(required=True, validate=validate.Length(min=1))


class CrmConfigSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    meses_inactividad = fields.Int(
        required=True, validate=validate.Range(min=1, max=60)
    )
