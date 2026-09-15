from marshmallow import Schema, fields, validate, validates_schema, ValidationError, EXCLUDE

from app.ajustes.models import TIPOS_METODO, TIPO_OTRO, CUPON_TIPOS, CUPON_PORCENTAJE


class EspecialistaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    comision_pct = fields.Float(load_default=0, validate=validate.Range(min=0, max=100))
    is_active = fields.Bool(load_default=True)


class MetodoPagoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    comision_pct = fields.Float(load_default=0, validate=validate.Range(min=0, max=100))
    # Qué es este método para el corte de caja. `otro` no cuenta como efectivo.
    tipo = fields.Str(
        load_default=TIPO_OTRO,
        validate=validate.OneOf(TIPOS_METODO),
    )


class GastoConceptoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

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
    es_impuesto = fields.Bool(dump_only=True)


class EstrategiaMarketingSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=200))


class DistribucionConfigSchema(Schema):
    class Meta:
        unknown = EXCLUDE

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


class DistribucionCategoriaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    clave = fields.Str(dump_only=True, allow_none=True)
    color = fields.Str(load_default="#6b7280", validate=validate.Regexp(r'^#[0-9a-fA-F]{6}$'))
    porcentaje = fields.Float(required=True, validate=validate.Range(min=0, max=100))
    es_sistema = fields.Bool(dump_only=True)
    sort_order = fields.Int(load_default=99)


class DistribucionBatchSchema(Schema):
    """Validates a full list of category updates for batch save."""
    class Meta:
        unknown = EXCLUDE

    categorias = fields.List(fields.Dict(), required=True)

    @validates_schema
    def validate_total(self, data, **kwargs):
        cats = data.get("categorias", [])
        total = sum(float(c.get("porcentaje", 0)) for c in cats)
        if abs(total - 100) > 0.01:
            raise ValidationError(
                f"Los porcentajes deben sumar 100%. Total actual: {total:.1f}%"
            )


class DescuentoSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    # min=0.01 y no min=0: un descuento de 0% no descuenta nada y sólo ensucia
    # el select de captura. "Sin descuento" ya es la primera opción del select.
    porcentaje = fields.Float(
        required=True, validate=validate.Range(min=0.01, max=100),
    )
    is_active = fields.Bool(load_default=True)


class DescuentosConfigSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    activo = fields.Bool(required=True)


class CuponSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    codigo = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    tratamiento_id = fields.Int(required=True)
    tipo = fields.Str(
        load_default=CUPON_PORCENTAJE, validate=validate.OneOf(CUPON_TIPOS),
    )
    valor = fields.Float(required=True, validate=validate.Range(min=0.01))
    vigencia_desde = fields.Date(allow_none=True, load_default=None)
    vigencia_hasta = fields.Date(allow_none=True, load_default=None)
    max_usos = fields.Int(allow_none=True, load_default=None,
                          validate=validate.Range(min=1))
    is_active = fields.Bool(load_default=True)
    # Derivados, para que la tabla de Ajustes atenúe agotados y vencidos.
    usos = fields.Int(dump_only=True)
    agotado = fields.Bool(dump_only=True)
    vencido = fields.Bool(dump_only=True)
    tratamiento_nombre = fields.Str(dump_only=True)

    @validates_schema
    def validar_valor_y_vigencia(self, data, **kwargs):
        if (data.get("tipo") == CUPON_PORCENTAJE
                and (data.get("valor") or 0) > 100):
            raise ValidationError(
                "Un cupón de porcentaje no puede pasar de 100",
                field_name="valor",
            )
        desde, hasta = data.get("vigencia_desde"), data.get("vigencia_hasta")
        if desde and hasta and hasta < desde:
            raise ValidationError(
                "La vigencia termina antes de empezar",
                field_name="vigencia_hasta",
            )


class ValidarCuponSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    codigo = fields.Str(required=True)
    tratamiento_id = fields.Int(required=True)
    fecha = fields.Date(required=True)
    precio = fields.Float(required=True, validate=validate.Range(min=0))
