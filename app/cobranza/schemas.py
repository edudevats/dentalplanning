from marshmallow import (
    EXCLUDE,
    Schema,
    ValidationError,
    fields,
    validate,
    validates_schema,
)

from app.cobranza.calculo import MAX_PARCIALIDADES
from app.cobranza.models import (
    DESCUENTO_TIPOS,
    ESTATUS_COTIZACION,
    FACTURACION_ESTADOS,
    FRECUENCIAS,
)


class ConceptoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    tratamiento_id = fields.Int(allow_none=True)
    descripcion = fields.Str(
        allow_none=True, validate=validate.Length(max=300),
    )
    cantidad = fields.Float(
        load_default=1, validate=validate.Range(min=0.01),
    )
    precio_unitario = fields.Float(
        load_default=0, validate=validate.Range(min=0),
    )
    importe = fields.Float(dump_only=True)
    tipo_servicio = fields.Str(
        allow_none=True,
        validate=validate.OneOf(["clinico", "estetico"]),
    )
    comision_especialista_tipo = fields.Str(
        allow_none=True,
        validate=validate.OneOf(["porcentaje", "monto"]),
    )
    comision_especialista_valor = fields.Float(
        allow_none=True, validate=validate.Range(min=0),
    )
    orden = fields.Int(dump_only=True)


class ProgramadoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    numero = fields.Int(dump_only=True)
    fecha_vencimiento = fields.Date(dump_only=True)
    monto_programado = fields.Float(dump_only=True)
    monto_pagado = fields.Float(dump_only=True)
    estatus = fields.Str(dump_only=True)


class CalendarioItemSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    numero = fields.Int(required=True, validate=validate.Range(min=0))
    fecha_vencimiento = fields.Date(required=True)
    monto_programado = fields.Float(
        required=True, validate=validate.Range(min=0.01),
    )


class PagoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    monto = fields.Float(required=True, validate=validate.Range(min=0.01))
    # Obligatorio: un abono sin método se convierte en un Ingreso con
    # metodo_pago_id NULL, y ese ingreso cae en `sin_clasificar`, que bloquea el
    # cierre de caja con 409 sin que recepción tenga forma de arreglarlo (editar
    # el ingreso de un abono está prohibido y borrar el pago es admin-only).
    # Cerrar la puerta al capturar es lo barato; después ya no hay salida.
    metodo_pago_id = fields.Int(required=True)
    historico = fields.Bool(load_default=False)
    notas = fields.Str(
        allow_none=True, validate=validate.Length(max=2000),
    )
    ingreso_id = fields.Int(dump_only=True)
    metodo_pago_nombre = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class CotizacionSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    folio = fields.Str(dump_only=True)
    paciente_id = fields.Int(required=True)
    especialista_id = fields.Int(allow_none=True)
    sucursal_id = fields.Int(allow_none=True)
    fecha = fields.Date(dump_only=True)
    valida_hasta = fields.Date(allow_none=True)
    fecha_inicio_tratamiento = fields.Date(allow_none=True)
    estatus = fields.Str(
        dump_only=True, validate=validate.OneOf(ESTATUS_COTIZACION),
    )
    subtotal = fields.Float(dump_only=True)
    descuento_tipo = fields.Str(
        allow_none=True, validate=validate.OneOf(DESCUENTO_TIPOS),
    )
    descuento_valor = fields.Float(
        load_default=0, validate=validate.Range(min=0),
    )
    total = fields.Float(dump_only=True)
    frecuencia = fields.Str(
        load_default="mensual", validate=validate.OneOf(FRECUENCIAS),
    )
    num_parcialidades = fields.Int(
        allow_none=True,
        validate=validate.Range(min=1, max=MAX_PARCIALIDADES),
    )
    monto_parcialidad = fields.Float(
        allow_none=True, validate=validate.Range(min=1),
    )
    anticipo = fields.Float(
        load_default=0, validate=validate.Range(min=0),
    )
    fecha_primer_pago = fields.Date(allow_none=True)
    requiere_factura = fields.Bool(load_default=False)
    notas = fields.Str(
        allow_none=True, validate=validate.Length(max=5000),
    )
    conceptos = fields.List(
        fields.Nested(ConceptoSchema), load_default=list,
    )
    calendario = fields.List(
        fields.Nested(CalendarioItemSchema), load_only=True, allow_none=True,
    )

    comision_doctor_total = fields.Float(dump_only=True)
    paciente_nombre = fields.Str(dump_only=True)
    especialista_nombre = fields.Str(dump_only=True)
    pagado = fields.Float(dump_only=True)
    saldo = fields.Float(dump_only=True)
    parcialidades_pagadas = fields.Int(dump_only=True)
    vencida = fields.Bool(dump_only=True)
    sin_pagos_recientes = fields.Bool(dump_only=True)
    dias_sin_pago = fields.Int(dump_only=True, allow_none=True)
    programados = fields.List(
        fields.Nested(ProgramadoSchema), dump_only=True,
    )
    pagos = fields.List(fields.Nested(PagoSchema), dump_only=True)
    facturacion_estado = fields.Str(
        dump_only=True, validate=validate.OneOf(FACTURACION_ESTADOS),
    )
    facturacion_error = fields.Str(dump_only=True, allow_none=True)
    facturacion_actualizada_at = fields.DateTime(
        dump_only=True, allow_none=True,
    )
    created_at = fields.DateTime(dump_only=True)

    @validates_schema
    def validar_modo_y_descuento(self, data, **kwargs):
        por_numero = data.get("num_parcialidades") is not None
        por_monto = data.get("monto_parcialidad") is not None
        if por_numero == por_monto:
            raise ValidationError(
                "Captura el número de parcialidades o el monto, no ambos",
                field_name="num_parcialidades",
            )
        if (
            data.get("descuento_tipo") == "porcentaje"
            and data.get("descuento_valor", 0) > 100
        ):
            raise ValidationError(
                "El descuento porcentual no puede ser mayor a 100",
                field_name="descuento_valor",
            )


class ConceptoExtraSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    tratamiento_id = fields.Int(allow_none=True)
    descripcion = fields.Str(allow_none=True, validate=validate.Length(max=300))
    cantidad = fields.Float(load_default=1, validate=validate.Range(min=0.01))
    precio_unitario = fields.Float(load_default=0, validate=validate.Range(min=0))
    tipo_servicio = fields.Str(
        allow_none=True, validate=validate.OneOf(["clinico", "estetico"]),
    )
    comision_especialista_tipo = fields.Str(
        allow_none=True, validate=validate.OneOf(["porcentaje", "monto"]),
    )
    comision_especialista_valor = fields.Float(
        allow_none=True, validate=validate.Range(min=0),
    )


class AprobarSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sucursal_id = fields.Int(allow_none=True)


class DevolucionSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    fecha = fields.Date(required=True)
    monto = fields.Float(required=True, validate=validate.Range(min=0.01))
    # Igual que en PagoSchema: la devolución genera un GastoOperativo y sin
    # método no se sabe si salió del cajón, así que el corte no lo puede restar.
    metodo_pago_id = fields.Int(required=True)
    motivo = fields.Str(allow_none=True, validate=validate.Length(max=2000))


class EditarCalendarioSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    calendario = fields.List(
        fields.Nested(CalendarioItemSchema), required=True,
        validate=validate.Length(min=1),
    )


class ReasignarEspecialistaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    especialista_id = fields.Int(required=True)
