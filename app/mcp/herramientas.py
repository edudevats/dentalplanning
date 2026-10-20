"""Catálogo de herramientas MCP: nombre, descripción para Claude y su consulta."""
from app.mcp import consultas

_MES = {"type": "string", "pattern": r"^\d{4}-\d{2}$", "description": "Mes en formato AAAA-MM"}
_FECHA = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$", "description": "Fecha AAAA-MM-DD"}

_SOLO_LECTURA = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


def _herramienta(nombre, titulo, descripcion, propiedades, requeridas, consulta, modulo=None):
    return {
        "name": nombre,
        "title": titulo,
        "description": descripcion,
        "inputSchema": {
            "type": "object",
            "properties": propiedades,
            "required": list(requeridas),
            "additionalProperties": False,
        },
        "annotations": {"title": titulo, **_SOLO_LECTURA},
        # Lo de abajo no viaja a Claude (ver definicion_publica).
        "_consulta": consulta,
        "_modulo": modulo,
    }


HERRAMIENTAS = [
    _herramienta(
        "resumen_mes",
        "Resumen financiero del mes",
        "Estado de resultados de un mes: ventas (total_ingresos, sin IVA), efectivo "
        "vs banco, gastos fijos y variables, impuestos, pagos a doctores, comisiones "
        "bancarias, utilidad neta y punto de equilibrio. Son las mismas cifras de la "
        "pantalla Reportes > Resumen. Montos en pesos mexicanos.",
        {"mes": _MES}, ["mes"],
        lambda t, a: consultas.resumen_mes(t, a.get("mes")),
    ),
    _herramienta(
        "comparar_meses",
        "Comparar dos meses",
        "Compara las métricas principales de dos meses (por ejemplo marzo de este año "
        "contra marzo del año pasado): valor de cada mes, diferencia y variación "
        "porcentual. Montos en pesos mexicanos.",
        {"mes_a": {**_MES, "description": "Mes base, AAAA-MM (el más antiguo)"},
         "mes_b": {**_MES, "description": "Mes a comparar, AAAA-MM"}},
        ["mes_a", "mes_b"],
        lambda t, a: consultas.comparar_meses(t, a.get("mes_a"), a.get("mes_b")),
    ),
    _herramienta(
        "ventas_del_dia",
        "Ventas del día",
        "Ventas de un día (hoy si no se indica fecha): total vendido sin IVA, número "
        "de cobros, y desglose por sucursal y por método de pago.",
        {"fecha": {**_FECHA, "description": "Día a consultar AAAA-MM-DD; omitir para hoy"}},
        [],
        lambda t, a: consultas.ventas_del_dia(t, a.get("fecha")),
    ),
    _herramienta(
        "gastos_principales",
        "Mayores gastos",
        "Ranking de los conceptos en los que más se gastó en un rango de fechas, con "
        "monto, porcentaje del total y número de movimientos.",
        {"desde": {**_FECHA, "description": "Inicio del rango AAAA-MM-DD (incluido)"},
         "hasta": {**_FECHA, "description": "Fin del rango AAAA-MM-DD (incluido)"},
         "limite": {"type": "integer", "minimum": 1, "maximum": 50,
                    "description": "Cuántos conceptos devolver (10 por omisión)"}},
        ["desde", "hasta"],
        lambda t, a: consultas.gastos_principales(
            t, a.get("desde"), a.get("hasta"), a.get("limite")),
    ),
    _herramienta(
        "gasto_por_concepto",
        "Gasto de un concepto en el año",
        "Cuánto se ha gastado en un concepto en un año, con desglose mensual. Busca por "
        "coincidencia parcial del nombre (\"luz\" encuentra \"Luz CFE\"). Si no hay "
        "coincidencias devuelve la lista de conceptos existentes para reintentar.",
        {"concepto": {"type": "string", "description": "Nombre o parte del nombre del concepto"},
         "anio": {"type": "integer", "description": "Año; omitir para el año en curso"}},
        ["concepto"],
        lambda t, a: consultas.gasto_por_concepto(t, a.get("concepto"), a.get("anio")),
    ),
    _herramienta(
        "inventario_bajo",
        "Inventario bajo o agotado",
        "Materiales con existencia en o por debajo de su mínimo (por ubicación) y "
        "materiales sin existencia en ninguna ubicación.",
        {}, [],
        lambda t, a: consultas.inventario_bajo(t),
        modulo="inventario",
    ),
    _herramienta(
        "pagos_vencidos",
        "Pagos vencidos de planes",
        "Pacientes con mensualidades vencidas en sus planes de pago aprobados: nombre, "
        "folio de la cotización, monto vencido y días de atraso desde la parcialidad "
        "vencida más antigua.",
        {}, [],
        lambda t, a: consultas.pagos_vencidos(t),
        modulo="cobranza",
    ),
]

_POR_NOMBRE = {h["name"]: h for h in HERRAMIENTAS}


def disponibles(tenant):
    """Las herramientas que el plan de la clínica permite (respeta los módulos)."""
    modulos = set(tenant.allowed_modules or [])
    return [h for h in HERRAMIENTAS if h["_modulo"] is None or h["_modulo"] in modulos]


def buscar(tenant, nombre):
    herramienta = _POR_NOMBRE.get(nombre)
    if herramienta is None or herramienta not in disponibles(tenant):
        return None
    return herramienta


def definicion_publica(herramienta):
    return {k: v for k, v in herramienta.items() if not k.startswith("_")}
