from marshmallow import Schema, fields, validate, EXCLUDE


class ConfigSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Int(dump_only=True)
    gastos_fijos = fields.Float(validate=validate.Range(min=0))
    horas_lunes = fields.Float(validate=validate.Range(min=0, max=24))
    horas_martes = fields.Float(validate=validate.Range(min=0, max=24))
    horas_miercoles = fields.Float(validate=validate.Range(min=0, max=24))
    horas_jueves = fields.Float(validate=validate.Range(min=0, max=24))
    horas_viernes = fields.Float(validate=validate.Range(min=0, max=24))
    horas_sabado = fields.Float(validate=validate.Range(min=0, max=24))
    horas_domingo = fields.Float(validate=validate.Range(min=0, max=24))
    numero_unidades = fields.Int(dump_only=True)
    # Tasa de impuesto informativa (estimación). Editable.
    tasa_impuesto_pct = fields.Float(validate=validate.Range(min=0, max=100))
    # Diferencia en pesos que el corte de caja tolera sin exigir comentario.
    tolerancia_corte_caja = fields.Float(
        load_default=0, validate=validate.Range(min=0))
    # Calculados (read only)
    horas_semana = fields.Float(dump_only=True)
    horas_mes = fields.Float(dump_only=True)
    costo_hora = fields.Float(dump_only=True)
    costo_operario_hora = fields.Float(dump_only=True)

