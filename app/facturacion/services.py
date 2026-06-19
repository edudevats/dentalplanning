"""Lógica de escritura de facturación: folios y agrupación de tickets.

Toda escritura de tickets pasa por aquí (patrón como inventario/services.py).
Las funciones NO hacen commit; lo hace el llamador.
"""
import secrets
from datetime import date
from app.extensions import db
from app.facturacion.models import Ticket, Sucursal, TICKET_SIN_TIMBRAR


class FacturacionError(Exception):
    """Error de negocio de facturación (sucursal inexistente, ticket timbrado, etc.)."""


def siguiente_folio(tenant_id, sucursal_id):
    """Siguiente folio secuencial para (tenant, sucursal). Empieza en 1."""
    ultimo = (
        db.session.query(db.func.max(Ticket.folio))
        .filter(Ticket.tenant_id == tenant_id, Ticket.sucursal_id == sucursal_id)
        .scalar()
    )
    return (ultimo or 0) + 1


def recalcular_total(ticket):
    """Recalcula el total del ticket sumando el monto de sus ingresos (vía query,
    robusto ante relaciones en caché)."""
    from app.edr.models import Ingreso  # import diferido para evitar ciclos
    total = (
        db.session.query(db.func.coalesce(db.func.sum(Ingreso.monto), 0.0))
        .filter(Ingreso.ticket_id == ticket.id)
        .scalar()
    )
    ticket.total = round(float(total or 0.0), 2)


def asignar_ticket(ingreso, sucursal_id, ticket_folio=None):
    """Asigna `ingreso` a un ticket. Si `ticket_folio` se da, lo agrega a ese ticket
    sin timbrar de la misma sucursal; si no, crea un ticket nuevo con folio propio.
    Devuelve el Ticket. No hace commit.
    """
    suc = Sucursal.query.filter_by(
        id=sucursal_id, tenant_id=ingreso.tenant_id
    ).first()
    if not suc:
        raise FacturacionError("Selecciona una sucursal válida para facturar.")

    if ticket_folio is not None:
        ticket = Ticket.query.filter_by(
            tenant_id=ingreso.tenant_id, sucursal_id=sucursal_id, folio=ticket_folio,
        ).first()
        if not ticket:
            raise FacturacionError(
                f"No existe el ticket {suc.serie}-{ticket_folio} en esa sucursal."
            )
        if ticket.estado != TICKET_SIN_TIMBRAR:
            raise FacturacionError(
                "Ese ticket ya fue timbrado; no admite más conceptos."
            )
    else:
        ticket = Ticket(
            tenant_id=ingreso.tenant_id,
            sucursal_id=sucursal_id,
            serie=suc.serie or "",
            folio=siguiente_folio(ingreso.tenant_id, sucursal_id),
            fecha=ingreso.fecha or date.today(),
            estado=TICKET_SIN_TIMBRAR,
            token=secrets.token_urlsafe(24),
            total=0.0,
        )
        db.session.add(ticket)
        db.session.flush()  # asegurar ticket.id

    ingreso.ticket_id = ticket.id
    ingreso.sucursal_id = sucursal_id
    db.session.flush()
    recalcular_total(ticket)
    return ticket
