"""Lógica de escritura de facturación: folios y agrupación de tickets.

Toda escritura de tickets pasa por aquí (patrón como inventario/services.py).
Las funciones NO hacen commit; lo hace el llamador.
"""
import secrets
from app.extensions import db
from app.facturacion.models import Ticket, Sucursal, TICKET_SIN_TIMBRAR
from app.facturacion.timezone_helper import get_today


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
    """Total del ticket = Σ (base + IVA por encima). IVA solo en facturables gravados."""
    from app.edr.models import Ingreso
    from app.facturacion.iva import iva_de
    ingresos = Ingreso.query.filter_by(ticket_id=ticket.id).all()
    total = 0.0
    for i in ingresos:
        base = i.monto or 0.0
        total += base + iva_de(base, i.tipo_servicio, i.factura)
    ticket.total = round(total, 2)


def asignar_ticket(ingreso, sucursal_id, ticket_folio=None):
    """Asigna `ingreso` a un ticket. Si `ticket_folio` se da, lo agrega a ese ticket
    sin timbrar de la misma sucursal; si no, crea un ticket nuevo con folio propio.
    Devuelve el Ticket. No hace commit.

    TODO cobro lleva ticket, se facture o no: el folio es el número con el que
    el paciente reclama, y un cobro sin folio no se puede rastrear. Los
    requisitos que son del CFDI -configuración fiscal activa y el candado de
    los abonos de un plan abierto- se exigen sólo cuando el ingreso viene
    marcado `factura`, que es la intención de timbrar; el ticket sin factura es
    un comprobante interno y no necesita ninguno de los dos.
    """
    from app.facturacion.models import ConfiguracionFiscal

    if ingreso.factura:
        # Cobranza conserva la regla de bloqueo junto a su dominio. El import
        # local evita cargar el módulo si el ingreso no proviene de un plan.
        from app.cobranza.services import ingreso_bloqueado_para_factura
        bloqueo = ingreso_bloqueado_para_factura(ingreso)
        if bloqueo:
            raise FacturacionError(bloqueo)

        cfg = ConfiguracionFiscal.query.filter_by(tenant_id=ingreso.tenant_id).first()
        if not cfg or not cfg.facturacion_activa:
            raise FacturacionError(
                "Activa la facturación en Ajustes > Configuración fiscal antes de generar facturas."
            )

    suc = Sucursal.query.filter_by(
        id=sucursal_id, tenant_id=ingreso.tenant_id
    ).first()
    if not suc:
        raise FacturacionError(
            "Selecciona una sucursal válida: de ella salen la serie y el folio "
            "del ticket."
        )

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
            fecha=ingreso.fecha or get_today(),
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
