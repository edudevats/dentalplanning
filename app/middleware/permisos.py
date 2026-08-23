"""Catálogo y resolución de permisos por usuario para el rol asistente dental.

A diferencia de `recepcionista` —cuya allowlist de rutas está hardcodeada en
`app/middleware/tenant.py`— el rol `asistente` guarda sus permisos en la columna
JSON `User.permisos`, con forma {"<recurso>": "ver"|"editar"}. El administrador
de la clínica los reparte desde Ajustes → Usuarios.

La política es deny by default: una clave ausente significa 403.
"""

ROLE_ASISTENTE = "asistente"

NIVEL_VER = "ver"
NIVEL_EDITAR = "editar"
NIVELES = (NIVEL_VER, NIVEL_EDITAR)

RECURSO_INVENTARIO = "inventario"

# Inventario es el mínimo irreductible del rol: siempre presente, siempre en
# `editar`. Es lo que hace que un asistente recién creado pueda trabajar.
PERMISOS_MINIMOS = {RECURSO_INVENTARIO: NIVEL_EDITAR}

# Blueprint del que ningún asistente puede tocar nada, pase lo que pase.
BLUEPRINT_PROHIBIDO = "finanzas_personales"

# Rutas accesibles sin permiso alguno: identidad y cambio de contraseña propia.
# Se mantiene mínima a propósito — el inventario es autocontenido (`invApi`
# apunta solo a /api/v1/inventario), así que no necesita préstamos de otros
# blueprints.
BASE_PERMITIDA = frozenset({
    ("GET", "/api/v1/auth/me"),
    ("PUT", "/api/v1/auth/password"),
})

# recurso -> rutas: tupla de (blueprint, prefijos de path).
#   prefijos == ()  → todo el blueprint pertenece al recurso
#   prefijos != ()  → solo esos prefijos (para blueprints que agrupan varias
#                     secciones, como `edr`, o que montan en /api/v1 pelado,
#                     como `dashboard`)
# modulos: slugs que el plan del tenant debe incluir para que el recurso sea
#   otorgable. Informativo para la UI; el bloqueo real lo hace
#   check_module_access(), que corre antes que este motor.
CATALOGO = {
    "inventario": {
        "rutas": (("inventario", ()),),
        "label": "Inventario",
        "modulos": ("inventario",),
    },
    "crm": {
        "rutas": (("crm", ()),),
        "label": "CRM de Pacientes",
        "modulos": ("crm",),
    },
    "cobranza": {
        "rutas": (("cobranza", ()),),
        "label": "Cotizaciones y Cobranza",
        "modulos": ("cobranza", "crm"),
    },
    "facturacion": {
        "rutas": (("facturacion", ()),),
        "label": "Facturación",
        "modulos": (),
    },
    "tratamientos": {
        "rutas": (("tratamientos", ()),),
        "label": "Precios y Tratamientos",
        "modulos": (),
    },
    "catalogo": {
        "rutas": (("catalogo", ()),),
        "label": "Catálogo de materiales",
        "modulos": (),
    },
    "reportes": {
        "rutas": (("dashboard", ("/api/v1/dashboard", "/api/v1/reportes")),),
        "label": "Reportes",
        "modulos": (),
    },
    "ajustes": {
        "rutas": (("ajustes", ()), ("configuracion", ())),
        "label": "Ajustes",
        "modulos": (),
    },
    "edr.ingresos": {
        "rutas": (("edr", ("/api/v1/edr/ingresos",)),),
        "label": "EDR · Ingresos",
        "modulos": (),
    },
    "edr.gastos": {
        "rutas": (("edr", ("/api/v1/edr/gastos",)),),
        "label": "EDR · Gastos",
        "modulos": (),
    },
    "edr.pagos_doctores": {
        "rutas": (("edr", ("/api/v1/edr/pagos-doctores", "/api/v1/edr/comisiones")),),
        "label": "EDR · Pagos a doctores",
        "modulos": (),
    },
    "caja": {
        "rutas": (("caja", ()),),
        "label": "Corte de caja",
        "modulos": (),
    },
}

# Blueprints que deliberadamente no participan del catálogo. `finanzas_personales`
# está aquí porque se deniega con un chequeo explícito en el motor, no por
# ausencia de clave.
BLUEPRINTS_NO_APLICA = frozenset({
    "auth", "frontend", "superadmin", "clip", "portal", "finanzas_personales",
})

# Operaciones que ningún asistente alcanza, tenga el nivel que tenga en el
# recurso. No son deny-by-default (ahí el admin no otorgó nada): aquí el admin
# SÍ otorgó `editar`, pero estas rutas siguen siendo exclusivas del admin.
#
# Existen porque `editar` sobre un recurso concede todas sus rutas de escritura,
# y algunas de esas rutas manejan credenciales fiscales o la base del motor de
# precios. Un admin que marca "Facturación: editar" está pensando "que timbre
# tickets", no "que reemplace el certificado de sello digital de la clínica".
#
# Cada entrada es (método, prefijo de path); el match es por segmento, igual que
# en el resolver.
RUTAS_CRITICAS = (
    # Credenciales fiscales e infraestructura de facturación
    ("PUT", "/api/v1/facturacion/configuracion"),
    ("POST", "/api/v1/facturacion/configuracion/csd"),
    ("POST", "/api/v1/facturacion/configuracion/fiel"),
    ("POST", "/api/v1/facturacion/configuracion/finkok/registrar"),
    ("POST", "/api/v1/facturacion/print-agent/key/regenerate"),
    # Base del motor de precios e identidad del consultorio
    ("PUT", "/api/v1/config"),
    ("POST", "/api/v1/config/logo"),
    # Economía de la clínica: comisiones de doctores y reparto de utilidades
    ("POST", "/api/v1/ajustes/especialistas"),
    ("PUT", "/api/v1/ajustes/especialistas"),
    ("DELETE", "/api/v1/ajustes/especialistas"),
    ("PUT", "/api/v1/ajustes/distribucion"),
    ("POST", "/api/v1/ajustes/distribucion/categorias"),
    ("PUT", "/api/v1/ajustes/distribucion/categorias"),
    ("DELETE", "/api/v1/ajustes/distribucion/categorias"),
    # Corte de caja: reabrir un corte firmado y ver el histórico son del admin,
    # aunque el asistente tenga `editar` sobre el recurso.
    ("POST", "/api/v1/caja/reabrir"),
    ("GET", "/api/v1/caja/cortes"),
)


def es_ruta_critica(method, path):
    """True si la ruta es exclusiva del admin aunque el asistente tenga `editar`."""
    for m, prefijo in RUTAS_CRITICAS:
        if method == m and (path == prefijo or path.startswith(prefijo + "/")):
            return True
    return False


def _build_index():
    """blueprint -> [(recurso, prefijos)], con los prefijados primero.

    El orden importa: dentro de un mismo blueprint, una entrada con prefijos es
    más específica que una que abarca el blueprint entero.
    """
    idx = {}
    for recurso, meta in CATALOGO.items():
        for blueprint, prefijos in meta["rutas"]:
            idx.setdefault(blueprint, []).append((recurso, prefijos))
    for blueprint in idx:
        idx[blueprint].sort(key=lambda par: 0 if par[1] else 1)
    return idx


_INDEX = _build_index()


def resolver_recurso(blueprint, path):
    """Devuelve el recurso del catálogo al que pertenece la ruta, o None."""
    if not blueprint:
        return None
    for recurso, prefijos in _INDEX.get(blueprint, ()):
        if not prefijos:
            return recurso
        for prefijo in prefijos:
            # Comparación por segmento: "/edr/ingresos-especiales" NO cae en
            # "/edr/ingresos".
            if path == prefijo or path.startswith(prefijo + "/"):
                return recurso
    return None


def normalizar_permisos(permisos, modulos_permitidos=None):
    """Descarta recursos y niveles inválidos, y fuerza inventario=editar.

    `modulos_permitidos`: lista de slugs de módulos que el plan del tenant
    incluye (`tenant.allowed_modules`). Cuando se recibe, un recurso cuyo
    `CATALOGO[recurso]["modulos"]` no esté completamente contenido en esa
    lista se descarta — evita persistir permisos "latentes" que el plan
    todavía no habilita y que se activarían solos el día que el tenant
    contrate ese módulo. Si es None (el default), no se filtra por plan; lo
    usan los llamadores que no tienen — o no necesitan — ese contexto.

    Pase lo que pase, `inventario` siempre queda en `editar`: es el mínimo
    irreductible del rol asistente, incluso si el plan del tenant no incluye
    el módulo `inventario`. Sin esta garantía, un asistente cuyo tenant
    tuviera un plan tan reducido que ni inventario incluyera quedaría sin
    ningún acceso — deny-by-default lo dejaría encerrado.
    """
    limpio = {}
    for recurso, nivel in (permisos or {}).items():
        if recurso not in CATALOGO or nivel not in NIVELES:
            continue
        if modulos_permitidos is not None:
            requeridos = CATALOGO[recurso]["modulos"]
            if requeridos and not all(m in modulos_permitidos for m in requeridos):
                continue
        limpio[recurso] = nivel
    limpio[RECURSO_INVENTARIO] = NIVEL_EDITAR
    return limpio


def _denegado():
    from flask import jsonify
    return jsonify({"error": "No tienes acceso a esta sección"}), 403


def check_asistente_access():
    """Aplica los permisos por usuario al rol asistente. Deny by default.

    Devuelve None si la petición puede seguir, o una respuesta 403.
    """
    from flask import g, request

    if not hasattr(g, "current_user"):
        return None
    if g.current_user.is_superuser:
        return None
    if g.current_user.role != ROLE_ASISTENTE:
        return None

    method = request.method
    path = request.path.rstrip("/") or "/"

    # HEAD es una lectura (algunos clientes la usan para chequear existencia
    # sin traer el body), así que cuenta como GET para BASE_PERMITIDA igual que
    # ya cuenta como GET para el nivel `ver` más abajo.
    metodo_base = "GET" if method == "HEAD" else method
    if (metodo_base, path) in BASE_PERMITIDA:
        return None

    blueprint = request.blueprints[0] if request.blueprints else None

    # Finanzas Personales es exclusivo del admin: se deniega explícitamente, no
    # solo por ausencia de clave en el JSON.
    if blueprint == BLUEPRINT_PROHIBIDO:
        return _denegado()

    if es_ruta_critica(method, path):
        return _denegado()

    recurso = resolver_recurso(blueprint, path)
    if recurso is None:
        return _denegado()

    nivel = (g.current_user.permisos or {}).get(recurso)
    if nivel not in NIVELES:
        return _denegado()
    nivel_requerido = NIVEL_VER if method in ("GET", "HEAD") else NIVEL_EDITAR
    if nivel_requerido == NIVEL_EDITAR and nivel != NIVEL_EDITAR:
        return _denegado()

    return None
