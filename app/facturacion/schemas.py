from marshmallow import Schema, fields, validate, EXCLUDE


class SucursalSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    direccion = fields.Str(allow_none=True)
    codigo_postal = fields.Str(allow_none=True, validate=validate.Length(max=5))
    telefono = fields.Str(allow_none=True)
    serie = fields.Str(load_default="", validate=validate.Length(max=10))
    activa = fields.Bool(load_default=True)
    created_at = fields.DateTime(dump_only=True)


class TicketSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    sucursal_id = fields.Int(dump_only=True)
    serie = fields.Str(dump_only=True)
    folio = fields.Int(dump_only=True)
    folio_display = fields.Str(dump_only=True)
    fecha = fields.Date(dump_only=True)
    total = fields.Float(dump_only=True)
    estado = fields.Str(dump_only=True)
    receptor_rfc = fields.Str(dump_only=True)
    receptor_nombre = fields.Str(dump_only=True)
    uuid = fields.Str(dump_only=True)
    email = fields.Str(dump_only=True)
    error_timbrado = fields.Str(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)


class ConfiguracionFiscalSchema(Schema):
    """Solo expone campos no sensibles. El CSD y el logo se suben aparte."""
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    rfc = fields.Str(allow_none=True, validate=validate.Length(max=13))
    razon_social = fields.Str(allow_none=True)
    regimen_fiscal = fields.Str(allow_none=True, validate=validate.Length(max=5))
    naturaleza_juridica = fields.Str(
        allow_none=True,
        validate=validate.OneOf(["moral_mercantil", "fisica_o_civil"]),
    )
    clave_prod_serv_default = fields.Str(load_default="85121800")
    clave_unidad_default = fields.Str(load_default="E48")
    objeto_imp_default = fields.Str(load_default="01")
    ventana_facturacion = fields.Str(
        load_default="fin_de_mes", validate=validate.OneOf(["fin_de_mes"])
    )
    facturacion_activa = fields.Bool(load_default=False)
    facturacion_activada_at = fields.DateTime(dump_only=True)
    # Estado del CSD (solo lectura)
    csd_no_certificado = fields.Str(dump_only=True)
    csd_valido_desde = fields.DateTime(dump_only=True)
    csd_valido_hasta = fields.DateTime(dump_only=True)
    csd_configurado = fields.Bool(dump_only=True)
    # Estado de la FIEL (solo lectura)
    fiel_configurada = fields.Bool(dump_only=True)
    fiel_no_certificado = fields.Str(dump_only=True)
    fiel_valido_hasta = fields.DateTime(dump_only=True)
    # Estado del registro en Finkok (solo lectura)
    finkok_registrado = fields.Bool(dump_only=True)
    finkok_registrado_at = fields.DateTime(dump_only=True)
    finkok_rfc_registrado = fields.Str(dump_only=True, allow_none=True)


class ReceptorSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    rfc = fields.Str(required=True, validate=validate.Length(min=12, max=13))
    nombre = fields.Str(required=True, validate=validate.Length(min=1))
    cp = fields.Str(required=True, validate=validate.Length(equal=5))
    regimen_fiscal = fields.Str(required=True)
    uso_cfdi = fields.Str(required=True)
    email = fields.Email(required=True)


class CancelacionSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    motivo = fields.Str(required=True, validate=validate.OneOf(["01", "02", "03", "04"]))
    uuid_sustitucion = fields.Str(allow_none=True)
