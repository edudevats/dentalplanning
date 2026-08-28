from marshmallow import Schema, fields, validate, EXCLUDE


class IngresoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    tratamiento_id = fields.Int(allow_none=True)
    nombre_tratamiento = fields.Str()
    paciente = fields.Str()
    paciente_id = fields.Int(allow_none=True)  # FK opcional al CRM
    especialista_id = fields.Int(allow_none=True)
    metodo_pago_id = fields.Int(allow_none=True)
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    comision_bancaria = fields.Float(load_default=0)
    comision_doctor = fields.Float(load_default=0)
    descuento_pct = fields.Float(load_default=0)
    factura = fields.Bool(load_default=False)
    sucursal_id = fields.Int(allow_none=True)
    tipo_servicio = fields.Str(dump_only=True)
    # Enriquecidos (solo lectura)
    ticket_id = fields.Int(dump_only=True)
    ticket_folio = fields.Int(dump_only=True)
    ticket_folio_display = fields.Str(dump_only=True)
    # Solo lectura: lo asigna el servicio al crear la visita, nunca el cliente.
    visita_uid = fields.Str(dump_only=True, allow_none=True)
    estrategia_id = fields.Int(allow_none=True)
    comentarios = fields.Str(allow_none=True)
    # Read-only enriched fields
    especialista_nombre = fields.Str(dump_only=True)
    metodo_pago_nombre = fields.Str(dump_only=True)
    estrategia_nombre = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class LineaVisitaSchema(Schema):
    """Un tratamiento dentro de una visita."""
    class Meta:
        unknown = EXCLUDE

    tratamiento_id = fields.Int(allow_none=True, load_default=None)
    nombre_tratamiento = fields.Str(allow_none=True, load_default=None)
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    comision_doctor = fields.Float(load_default=0)


class VisitaSchema(Schema):
    """Los datos que la visita comparte, más sus líneas.

    Especialista, método de pago y descuento son de la visita entera: el
    paciente vino una vez y pagó una vez.
    """
    class Meta:
        unknown = EXCLUDE

    fecha = fields.Date(required=True)
    paciente = fields.Str()
    paciente_id = fields.Int(allow_none=True)
    especialista_id = fields.Int(allow_none=True)
    metodo_pago_id = fields.Int(allow_none=True)
    descuento_pct = fields.Float(load_default=0)
    comision_bancaria = fields.Float(load_default=0)
    factura = fields.Bool(load_default=False)
    sucursal_id = fields.Int(allow_none=True)
    estrategia_id = fields.Int(allow_none=True)
    comentarios = fields.Str(allow_none=True)
    lineas = fields.List(
        fields.Nested(LineaVisitaSchema),
        required=True,
        validate=validate.Length(min=1, error="La visita necesita al menos un tratamiento."),
    )


class GastoOperativoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    concepto_id = fields.Int(allow_none=True)
    concepto_nombre = fields.Str(required=True)
    tipo = fields.Str(
        load_default="fijo",
        validate=validate.OneOf(["fijo", "variable"]),
    )
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    # Obligatorio: sin saber con qué se pagó, el corte no puede saber cuánto
    # queda en el cajón.
    metodo_pago_id = fields.Int(required=True)
    sucursal_id = fields.Int(allow_none=True, load_default=None)
    # El cliente lo propone; el servidor lo decide (ver _resolver_salida_caja).
    sale_de_caja = fields.Bool(load_default=None, allow_none=True)
    metodo_pago_nombre = fields.Str(dump_only=True)
    metodo_pago_tipo = fields.Str(dump_only=True)
    created_by = fields.Int(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class PagoDoctorSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    especialista_id = fields.Int(allow_none=True)
    concepto = fields.Str(required=True)
    tipo = fields.Str(
        load_default="comision",
        validate=validate.OneOf(["salario", "comision"]),
    )
    monto = fields.Float(required=True, validate=validate.Range(min=0))
    especialista_nombre = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class ComisionPagoSchema(Schema):
    """Request para liquidar comisiones pendientes de un doctor."""
    class Meta:
        unknown = EXCLUDE

    especialista_id = fields.Int(required=True)
    fecha = fields.Date(required=True)
    ingreso_ids = fields.List(
        fields.Int(), required=True, validate=validate.Length(min=1)
    )
