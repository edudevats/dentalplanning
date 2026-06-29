"""
Módulo de Facturación Electrónica (SAT CFDI 4.0).
Incluye parches y monkeypatches globales para la librería satcfdi.
"""
# Monkeypatch satcfdi's incorrect timezone mappings
# satcfdi maps 'Tiempo del Pacífico' to 'America/La_Paz' (Bolivia, UTC-4!)
# and 'Tiempo del Noroeste' to 'America/Matamoros' (UTC-6)
try:
    import satcfdi.transform as _sat_transform
    _sat_transform.HUSO_HORARIOS['Tiempo del Pacífico'] = 'America/Mazatlan'
    _sat_transform.HUSO_HORARIOS['Tiempo del Noroeste'] = 'America/Tijuana'
except Exception:
    pass
