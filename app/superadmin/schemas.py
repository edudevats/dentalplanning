from marshmallow import Schema, fields, validate, EXCLUDE, post_load
from app.superadmin.models import SUBSCRIPTION_ESTADOS, PAYMENT_METODOS


class PlanSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=4, max=50))
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

    @post_load
    def resolver_dependencias_modulos(self, data, **kwargs):
        """Cobranza requiere pacientes y visitas del CRM."""
        modulos = list(dict.fromkeys(data.get("modulos") or []))
        if "cobranza" in modulos and "crm" not in modulos:
            modulos.append("crm")
        data["modulos"] = modulos
        return data


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
    # Permite liquidar el mismo corte variable en lugar de insertar un pago
    # duplicado. ``billing_cycle_date`` se usa cuando el corte se crea manual.
    pending_payment_id = fields.Int(load_default=None)
    billing_cycle_date = fields.Date(load_default=None)
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


class FechaCobroSchema(Schema):
    proximo_cobro = fields.Date(required=True)


class CambioPlanSchema(Schema):
    """Upgrade/downgrade entre planes de pago. El monto de la diferencia se
    calcula en el servidor; el cliente solo elige plan y método de cobro."""
    class Meta:
        unknown = EXCLUDE

    plan_id = fields.Int(required=True)
    metodo = fields.Str(load_default="transferencia",
                        validate=validate.OneOf(PAYMENT_METODOS))
    comentarios = fields.Str(load_default=None, validate=validate.Length(max=500))


class AssignPlanSchema(Schema):
    plan_id = fields.Int(required=True)
    inicio = fields.Date(load_default=None)
    proximo_cobro = fields.Date(load_default=None)


class ChangeUserRoleSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    role = fields.Str(
        required=True,
        validate=validate.OneOf(["admin", "recepcionista", "asistente"]),
    )


class ToggleActiveSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    is_active = fields.Bool(required=True)


class RechazarAsientoSchema(Schema):
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=500))


class ActivarManualSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    monto = fields.Float(load_default=None, validate=validate.Range(min=0))
    fecha = fields.Date(load_default=None)
    comentarios = fields.Str(load_default=None, validate=validate.Length(max=500))
