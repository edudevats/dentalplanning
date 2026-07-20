"""Servicios de suscripción del panel de superadmin.

Aquí vive la lógica de negocio que se invoca desde varios puntos (rutas, CLI de
cobros), para no duplicarla ni engrosar ``routes.py``.
"""
from app.superadmin.models import Plan
from app.facturacion.timezone_helper import get_today


def es_plan_de_pago(plan):
    """Plan mensual de cobro real (no free, no temporal)."""
    return bool(plan) and plan.precio_mensual > 0 and not plan.es_temporal


def aplicar_plan_programado(sub, today=None):
    """Aplica el downgrade programado si ya llegó su fecha.

    Devuelve ``True`` si aplicó el cambio. No hace commit: el llamador decide
    cuándo persistir.
    """
    if not sub or not sub.plan_programado_id or not sub.plan_programado_desde:
        return False
    today = today or get_today()
    if sub.plan_programado_desde > today:
        return False

    plan = Plan.query.get(sub.plan_programado_id)
    if not plan:
        # El plan programado ya no existe: se descarta el cambio pendiente.
        sub.plan_programado_id = None
        sub.plan_programado_desde = None
        return False

    sub.plan_id = plan.id
    if sub.tenant:
        sub.tenant.plan = plan.nombre
    sub.plan_programado_id = None
    sub.plan_programado_desde = None
    return True
