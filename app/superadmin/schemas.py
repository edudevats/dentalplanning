from marshmallow import Schema, fields, validate, EXCLUDE
from app.superadmin.models import SUBSCRIPTION_ESTADOS, PAYMENT_METODOS


class PlanSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    precio_mensual = fields.Float(required=True, validate=validate.Range(min=0))
    descripcion = fields.Str(load_default=None, validate=validate.Length(max=500))
    activo = fields.Bool(load_default=True)
    modulos = fields.List(fields.Str(), load_default=[])
    publico = fields.Bool(load_default=True)
    es_temporal = fields.Bool(load_default=False)
    dias_expiracion = fields.Int(load_default=None, allow_none=True, validate=validate.Range(min=1))
    cupo_maximo = fields.Int(load_default=None, allow_none=True, validate=validate.Range(min=1))
    fecha_inicio_promo = fields.Date(load_default=None, allow_none=True)
    fecha_fin_promo = fields.Date(load_default=None, allow_none=True)
    codigo_invitacion = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=50))


class ApproveTenantSchema(Schema):
    plan_id = fields.Int(required=True)
    inicio = fields.Date(load_default=None)
    proximo_cobro = fields.Date(load_default=None)


class RejectTenantSchema(Schema):
    razon = fields.Str(required=True, validate=validate.Length(min=3, max=500))


class TenantUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=2, max=200))
    contact_email = fields.Email(allow_none=True)
    plan = fields.Str(validate=validate.Length(max=20))


class PaymentSchema(Schema):
    id = fields.Int(dump_only=True)
    tenant_id = fields.Int(required=True)
    subscription_id = fields.Int(load_default=None)
    fecha = fields.Date(required=True)
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    metodo = fields.Str(load_default="transferencia", validate=validate.OneOf(PAYMENT_METODOS))
    periodo_inicio = fields.Date(load_default=None)
    periodo_fin = fields.Date(load_default=None)
    comentarios = fields.Str(load_default=None, validate=validate.Length(max=500))
    clip_payment_id = fields.Str(dump_only=True)
    clip_status = fields.Str(dump_only=True)


class TenantNoteSchema(Schema):
    id = fields.Int(dump_only=True)
    texto = fields.Str(required=True, validate=validate.Length(min=1, max=2000))


class SubscriptionUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    plan_id = fields.Int()
    proximo_cobro = fields.Date(allow_none=True)
    estado = fields.Str(validate=validate.OneOf(SUBSCRIPTION_ESTADOS))
