"""Búsqueda en los catálogos SAT que trae satcfdi (Régimen, ClaveProdServ, ClaveUnidad).

satcfdi guarda los catálogos en un sqlite (~45 MB) con claves/valores pickled.
`select_all` deserializa todo el catálogo (ClaveProdServ ~52k entradas, ~185 ms),
así que cacheamos en memoria la primera vez y luego filtramos en proceso.
"""
import threading

# tipo expuesto en la API → tabla del catálogo en satcfdi
CATALOGS = {
    "regimenes": "C756_c_RegimenFiscal",
    "productos": "C756_c_ClaveProdServ",
    "unidades": "C756_c_ClaveUnidad",
}

_cache = {}          # tipo -> [(code, descripcion, code_lower, desc_lower), ...]
_lock = threading.Lock()


def _load(tipo):
    """Carga (una vez) el catálogo como lista normalizada para búsquedas rápidas."""
    if tipo in _cache:
        return _cache[tipo]
    with _lock:
        if tipo in _cache:  # otro hilo lo cargó mientras esperábamos
            return _cache[tipo]
        from satcfdi import catalogs
        data = catalogs.select_all(CATALOGS[tipo])
        rows = [
            (code, str(desc), code.lower(), str(desc).lower())
            for code, desc in data.items()
        ]
        rows.sort(key=lambda r: r[0])
        _cache[tipo] = rows
        return rows


def buscar(tipo, q, limit=50):
    """Devuelve [{code, description}] que casan con q por clave o descripción.

    Prioriza coincidencias por prefijo (clave o descripción) sobre las que
    contienen el texto en medio. Búsqueda case-insensitive.
    """
    q = (q or "").strip().lower()
    if not q or tipo not in CATALOGS:
        return []
    rows = _load(tipo)
    prefijo, contiene = [], []
    for code, desc, code_l, desc_l in rows:
        if code_l.startswith(q) or desc_l.startswith(q):
            prefijo.append((code, desc))
            if len(prefijo) >= limit:
                break
        elif q in code_l or q in desc_l:
            if len(contiene) < limit:
                contiene.append((code, desc))
    res = (prefijo + contiene)[:limit]
    return [{"code": c, "description": d} for c, d in res]
