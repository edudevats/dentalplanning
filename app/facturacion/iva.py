"""Regla central de IVA: cuándo grava un concepto y cuánto (IVA por encima).

El IVA lo determina el tipo de servicio del tratamiento, no la razón social del
consultorio: los tratamientos clínicos/terapéuticos están exentos (Art. 15-XIV
LIVA) y solo los estéticos gravan 16%.
"""

TASA_IVA = 0.16


def grava_iva(tipo_servicio, factura):
    """True si el concepto debe gravar IVA 16%.

    - Sin factura → nunca grava.
    - Estético → grava.
    - Clínico/terapéutico (o tipo no definido) → exento.
    """
    return bool(factura) and tipo_servicio == "estetico"


def iva_de(monto, tipo_servicio, factura):
    """IVA (por encima) del monto base. 0.0 si no grava."""
    if grava_iva(tipo_servicio, factura):
        return round((monto or 0.0) * TASA_IVA, 2)
    return 0.0
