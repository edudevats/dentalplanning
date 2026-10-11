"""Permisos configurables del rol recepcionista.

La recepcionista nació con una allowlist fija de rutas. Aquí esa lista se
reparte en una BASE que siempre aplica (identidad, contraseña, turno de caja y
los catálogos de solo lectura que usa cualquier formulario) y en BLOQUES con
nombre que el admin puede apagar desde Ajustes → Usuarios.

Además, el admin puede sumarle EXTRAS: recursos del catálogo del asistente
(`app/middleware/permisos.py`) que no se cruzan con ningún bloque. Esos se
resuelven con el mismo motor recurso → nivel del asistente.

`User.permisos` de una recepcionista guarda {"bloques_apagados": [...],
"extras": {recurso: nivel}}. Se guarda lo APAGADO a propósito: NULL o {} es
"todo encendido, sin extras", exactamente la recepcionista de siempre, sin
migración.
"""
import re

from app.middleware.permisos import CATALOGO, NIVELES

BASE_RECEPCION = [
    ("GET", r"/api/v1/auth/me"),
    ("PUT", r"/api/v1/auth/password"),
    # Turno de caja: es lo PRIMERO que hace la recepcionista al llegar. Sin
    # estas dos reglas no puede abrir su caja y, como el candado exige turno
    # abierto, no puede capturar absolutamente nada.
    ("GET", r"/api/v1/caja/turno"),
    ("POST", r"/api/v1/caja/turno"),
    # Catálogos de solo lectura que alimentan los formularios de cualquier
    # bloque (ingresos, cotizaciones, tickets).
    ("GET", r"/api/v1/ajustes/especialistas"),
    ("GET", r"/api/v1/ajustes/metodos-pago"),
    ("GET", r"/api/v1/ajustes/estrategias"),
    ("GET", r"/api/v1/ajustes/descuentos"),
    ("GET", r"/api/v1/ajustes/descuentos/config"),
    ("GET", r"/api/v1/ajustes/cupones"),
    ("POST", r"/api/v1/ajustes/cupones/validar"),
    ("GET", r"/api/v1/tratamientos"),
    ("GET", r"/api/v1/facturacion/sucursales"),
    ("GET", r"/api/v1/facturacion/configuracion"),
    ("GET", r"/api/v1/facturacion/print-agent/key"),
]

BLOQUES = {
    "ingresos": {
        "label": "Registro de ingresos",
        "reglas": [
            ("GET", r"/api/v1/edr/ingresos"),
            ("POST", r"/api/v1/edr/ingresos"),
            ("POST", r"/api/v1/edr/ingresos/visita"),
            ("PUT", r"/api/v1/edr/ingresos/\d+"),
            ("GET", r"/api/v1/facturacion/ingresos/\d+/ticket-simple"),
        ],
    },
    "tickets": {
        "label": "Tickets y facturas",
        "reglas": [
            ("GET", r"/api/v1/facturacion/tickets"),
            ("GET", r"/api/v1/facturacion/tickets/resumen-iva"),
            ("GET", r"/api/v1/facturacion/tickets/\d+"),
            ("GET", r"/api/v1/facturacion/tickets/\d+/impresion"),
            ("POST", r"/api/v1/facturacion/tickets/\d+/timbrar"),
            ("POST", r"/api/v1/facturacion/tickets/\d+/cancelar"),
        ],
    },
    "crm": {
        # Todo excepto DELETE paciente y PUT config.
        "label": "CRM de pacientes",
        "reglas": [
            ("GET", r"/api/v1/crm/pacientes"),
            ("POST", r"/api/v1/crm/pacientes"),
            ("GET", r"/api/v1/crm/pacientes/\d+"),
            ("PUT", r"/api/v1/crm/pacientes/\d+"),
            ("PUT", r"/api/v1/crm/pacientes/\d+/estatus"),
            ("POST", r"/api/v1/crm/pacientes/\d+/visitas"),
            ("POST", r"/api/v1/crm/pacientes/\d+/seguimientos"),
            ("POST", r"/api/v1/crm/seguimientos/\d+/completar"),
            ("POST", r"/api/v1/crm/pacientes/\d+/notas"),
            ("POST", r"/api/v1/crm/pacientes/importar/preview"),
            ("POST", r"/api/v1/crm/pacientes/importar/confirmar"),
            ("GET", r"/api/v1/crm/sugerencias-edr"),
            ("POST", r"/api/v1/crm/sugerencias-edr/vincular"),
            ("GET", r"/api/v1/crm/resumen"),
            ("GET", r"/api/v1/crm/config"),
            # Odontograma: recepción ve, asigna y marca realizado lo que dicta
            # el doctor. Corregir, desasignar y cambiar estado son del admin.
            ("GET", r"/api/v1/crm/pacientes/\d+/odontograma"),
            ("POST", r"/api/v1/crm/pacientes/\d+/odontograma/asignaciones"),
            ("POST", r"/api/v1/crm/pacientes/\d+/odontograma/asignaciones/\d+/realizar"),
        ],
    },
    "cobranza": {
        # Consultar, capturar/enviar cotizaciones y registrar cobros. Aprobar,
        # cancelar, borrar y reintentar facturación quedan fuera.
        "label": "Cotizaciones y cobranza",
        "reglas": [
            ("GET", r"/api/v1/cobranza/cotizaciones"),
            ("POST", r"/api/v1/cobranza/cotizaciones"),
            ("GET", r"/api/v1/cobranza/cotizaciones/\d+"),
            ("PUT", r"/api/v1/cobranza/cotizaciones/\d+"),
            ("POST", r"/api/v1/cobranza/cotizaciones/\d+/enviar"),
            ("POST", r"/api/v1/cobranza/cotizaciones/\d+/pagos"),
            ("GET", r"/api/v1/cobranza/cotizaciones/\d+/estado-cuenta"),
            ("GET", r"/api/v1/cobranza/cotizaciones/\d+/estado-cuenta\.pdf"),
            ("GET", r"/api/v1/cobranza/cotizaciones/\d+/pdf"),
            ("GET", r"/api/v1/cobranza/resumen"),
        ],
    },
    "corte": {
        # Consulta el día, registra salidas chicas y cierra. El histórico y la
        # reapertura son del admin.
        "label": "Corte de caja",
        "reglas": [
            ("GET", r"/api/v1/caja/corte"),
            ("POST", r"/api/v1/caja/corte"),
            ("GET", r"/api/v1/caja/salidas"),
            ("POST", r"/api/v1/caja/salidas"),
            ("DELETE", r"/api/v1/caja/salidas/\d+"),
        ],
    },
    "pagos_cajon": {
        # Pagos a doctores desde el cajón. Las rutas de admin
        # (/edr/pagos-doctores, /edr/comisiones) son el extra edr.pagos_doctores.
        "label": "Pagos a doctores (desde caja)",
        "reglas": [
            ("GET", r"/api/v1/caja/doctores"),
            ("GET", r"/api/v1/caja/pagos-doctores"),
            ("POST", r"/api/v1/caja/pagos-doctores"),
            ("POST", r"/api/v1/caja/pagos-doctores/comisiones"),
            ("DELETE", r"/api/v1/caja/pagos-doctores/\d+"),
            ("GET", r"/api/v1/caja/pagos-doctores/\d+/comprobante"),
            ("GET", r"/api/v1/caja/comisiones-pendientes"),
        ],
    },
}

# Recursos del catálogo del asistente que se le pueden sumar. Quedan fuera los
# que ya cubren los bloques con reglas más finas (crm, cobranza, facturacion,
# edr.ingresos, caja): darlos como recurso abriría lo que el bloque cierra a
# propósito (aprobar cotizaciones, reabrir caja...).
EXTRAS_RECEPCION = (
    "inventario", "tratamientos", "catalogo", "reportes", "ajustes",
    "edr.gastos", "edr.pagos_doctores",
)

# Bloques con página propia en el menú de la recepcionista (app.js,
# `rutasPermitidas`): ingresos → /ingresos, tickets → /facturas, corte y
# pagos_cajon → /corte-caja. crm y cobranza no tienen página en su menú: dan
# servicio a la pantalla de ingresos (buscar paciente, cobrar cotización).
# El modal de Ajustes repite esta lista en JS; mantenerlas iguales.
BLOQUES_NAVEGABLES = ("ingresos", "tickets", "corte", "pagos_cajon")

TODAS_LAS_REGLAS = BASE_RECEPCION + [r for b in BLOQUES.values() for r in b["reglas"]]


def compilar(reglas):
    return [(m, re.compile("^" + p + "/?$")) for m, p in reglas]


def normalizar_permisos_recepcion(permisos, modulos_permitidos=None):
    """Deja solo bloques y extras válidos, en forma canónica.

    `modulos_permitidos` funciona igual que en `normalizar_permisos` del
    asistente: un extra cuyo recurso exige un módulo que el plan no incluye se
    descarta, para no persistir permisos latentes.
    """
    permisos = permisos if isinstance(permisos, dict) else {}
    apagados = permisos.get("bloques_apagados")
    # Solo cadenas: un elemento no hashable ([1], {}) reventaría set() con 500.
    apagados = (
        {b for b in apagados if isinstance(b, str)} if isinstance(apagados, list) else set()
    )
    extras_in = permisos.get("extras")
    extras_in = extras_in if isinstance(extras_in, dict) else {}

    extras = {}
    for recurso, nivel in extras_in.items():
        if recurso not in EXTRAS_RECEPCION or nivel not in NIVELES:
            continue
        if modulos_permitidos is not None:
            requeridos = CATALOGO[recurso]["modulos"]
            if requeridos and not all(m in modulos_permitidos for m in requeridos):
                continue
        extras[recurso] = nivel

    return {
        "bloques_apagados": [b for b in BLOQUES if b in apagados],
        "extras": extras,
    }


def tiene_algun_area(permisos_normalizados):
    """True si le queda al menos un área NAVEGABLE: un extra, o un bloque de
    `BLOQUES_NAVEGABLES` encendido.

    crm y cobranza solos no cuentan: no tienen página en su menú, así que con
    solo esos dos la recepcionista entraría a un sistema sin secciones.
    """
    apagados = set(permisos_normalizados["bloques_apagados"])
    return bool(permisos_normalizados["extras"]) or any(
        b not in apagados for b in BLOQUES_NAVEGABLES)
