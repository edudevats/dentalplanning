"""Regla central de IVA: cuándo grava un concepto y cuánto (IVA por encima)."""

TASA_IVA = 0.16

NATURALEZA_MORAL_MERCANTIL = "moral_mercantil"
NATURALEZA_FISICA_O_CIVIL = "fisica_o_civil"


def grava_iva(naturaleza, tipo_servicio, factura):
    """True si el concepto debe gravar IVA 16%.

    - Sin factura → nunca grava.
    - Persona Moral Mercantil → grava TODO.
    - Persona Física / Moral Civil (o naturaleza no definida) → grava solo 'estetico'.
    """
    if not factura:
        return False
    if naturaleza == NATURALEZA_MORAL_MERCANTIL:
        return True
    return tipo_servicio == "estetico"


def iva_de(monto, naturaleza, tipo_servicio, factura):
    """IVA (por encima) del monto base. 0.0 si no grava."""
    if grava_iva(naturaleza, tipo_servicio, factura):
        return round((monto or 0.0) * TASA_IVA, 2)
    return 0.0
