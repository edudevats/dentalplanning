from marshmallow import Schema, fields, validate
from app.superadmin.models import SUBSCRIPTION_ESTADOS, PAYMENT_METODOS


class PlanSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    precio_mensual = fields.Float(required=True, validate=validate.Range(min=0))
    descripcion = fields.Str(load_default=None, validate=validate.Length(max=500))
    activo = fields.Bool(load_default=True)


class ApproveTenantSchema(Schema):
    plan_id = fields.Int(required=True)
    inicio = fields.Date(load_default=None)
    proximo_cobro = fields.Date(load_default=None)


class RejectTenantSchema(Schema):
    razon = fields.Str(required=True, validate=validate.Length(min=3, max=500))


class TenantUpdateSchema(Schema):
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


class TenantNoteSchema(Schema):
    id = fields.Int(dump_only=True)
    texto = fields.Str(required=True, validate=validate.Length(min=1, max=2000))


class SubscriptionUpdateSchema(Schema):
    plan_id = fields.Int()
    proximo_cobro = fields.Date(allow_none=True)
    estado = fields.Str(validate=validate.OneOf(SUBSCRIPTION_ESTADOS))
