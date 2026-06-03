from datetime import datetime, date, timedelta
from sqlalchemy import asc, nullslast
from app.extensions import db
from app.catalogo.models import Material
from app.configuracion.models import ConfigConsultorio
from app.inventario.models import (
    Operatorio, Lote, LoteUbicacion, StockUbicacion, Compra, MovimientoInventario,
    OPERATORIO_ACTIVO,
)


class CapacidadDecreaseError(Exception):
    """Bajar el numero de operatorios requiere suspender o poner en reparacion."""

    def __init__(self, operatorios):
        super().__init__("Reduzca capacidad suspendiendo o reparando operatorios.")
        self.operatorios = operatorios


def _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_id):
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant_id, material_id=material_id, operatorio_id=operatorio_id
    ).first()
    if not su:
        su = StockUbicacion(
            tenant_id=tenant_id, material_id=material_id,
            operatorio_id=operatorio_id, cantidad=0,
        )
        db.session.add(su)
        db.session.flush()
    return su


def _operatorio_activo_o_error(tenant_id, operatorio_id, descripcion):
    """Si el operatorio no esta activo, levanta ValueError. None = Almacen, permitido."""
    if operatorio_id is None:
        return
    op = Operatorio.query.filter_by(id=operatorio_id, tenant_id=tenant_id).first()
    if op is None:
        raise ValueError(f"{descripcion} no existe")
    if op.estado != OPERATORIO_ACTIVO:
        raise ValueError(
            f"{descripcion} esta '{op.estado}'; no se permiten movimientos"
        )


def _inicializar_stock_material(tenant_id, material_id):
    """Crea StockUbicacion(cantidad=0) para todos los operatorios del tenant.

    Idempotente: si ya existen filas, no las altera. Incluye operatorios
    en cualquier estado (suspendido/reparacion conservan la fila para que
    al reactivar no haya gaps).
    """
    ops = Operatorio.query.filter_by(tenant_id=tenant_id).all()
    for op in ops:
        _get_or_create_stock_ubicacion(tenant_id, material_id, op.id)


def ajustar_numero_operatorios(tenant_id, nuevo_total):
    """Sincroniza la capacidad de operatorios y ConfigConsultorio.numero_unidades.

    Si sube: crea operatorios faltantes ('Operatorio N') con stock=0 para
    todos los materiales del tenant (fuente unica = catalogo).
    Si baja: levanta CapacidadDecreaseError con la lista actual; el caller
    decide cuales suspender o poner en reparacion antes de reintentar.
    Sincroniza numero_unidades = nuevo_total al final.
    """
    if nuevo_total < 1:
        raise ValueError("numero_unidades debe ser >= 1")

    config = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    if config is None:
        raise ValueError("ConfigConsultorio no existe para este tenant")

    actuales = (
        Operatorio.query.filter_by(tenant_id=tenant_id)
        .order_by(Operatorio.orden, Operatorio.nombre)
        .all()
    )
    actual_total = len(actuales)

    if nuevo_total < actual_total:
        raise CapacidadDecreaseError(
            [
                {
                    "id": op.id,
                    "nombre": op.nombre,
                    "orden": op.orden,
                    "estado": op.estado,
                }
                for op in actuales
            ]
        )

    creados = []
    if nuevo_total > actual_total:
        max_orden = max((op.orden for op in actuales), default=-1)
        nombres_existentes = {op.nombre for op in actuales}
        # Init stock para todos los materiales del tenant (fuente unica).
        materiales = Material.query.filter_by(tenant_id=tenant_id).all()
        for i in range(nuevo_total - actual_total):
            n = actual_total + i + 1
            base_nombre = f"Operatorio {n}"
            nombre = base_nombre
            sufijo = 1
            while nombre in nombres_existentes:
                sufijo += 1
                nombre = f"{base_nombre} ({sufijo})"
            nombres_existentes.add(nombre)
            op = Operatorio(
                tenant_id=tenant_id,
                nombre=nombre,
                orden=max_orden + 1 + i,
                estado=OPERATORIO_ACTIVO,
            )
            db.session.add(op)
            db.session.flush()
            for m in materiales:
                _get_or_create_stock_ubicacion(tenant_id, m.id, op.id)
            creados.append(op)

    config.numero_unidades = nuevo_total
    return {"creados": creados, "total": nuevo_total}


def registrar_compra(
    *, tenant_id, user_id, material_id, cantidad, precio_unitario,
    fecha_surtido, fecha_caducidad, operatorio_destino_id,
    comentarios, actualizar_costo_master,
):
    material = Material.query.filter_by(id=material_id, tenant_id=tenant_id).first()
    if not material:
        raise ValueError("Material no existe")
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser > 0")

    _operatorio_activo_o_error(
        tenant_id, operatorio_destino_id, "Operatorio destino"
    )

    caducidad = fecha_caducidad if material.expira else None

    lote = Lote(
        tenant_id=tenant_id, material_id=material_id,
        cantidad_inicial=cantidad, fecha_surtido=fecha_surtido,
        fecha_caducidad=caducidad, precio_unitario=precio_unitario,
        comentarios=comentarios,
    )
    db.session.add(lote)
    db.session.flush()

    db.session.add(LoteUbicacion(
        lote_id=lote.id, operatorio_id=operatorio_destino_id,
        cantidad_restante=cantidad,
    ))

    su = _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_destino_id)
    su.cantidad += cantidad

    compra = Compra(
        tenant_id=tenant_id, material_id=material_id, lote_id=lote.id,
        fecha=fecha_surtido, cantidad=cantidad, precio_unitario=precio_unitario,
        comentarios=comentarios, actualizo_costo_master=actualizar_costo_master,
        user_id=user_id,
    )
    db.session.add(compra)

    db.session.add(MovimientoInventario(
        tenant_id=tenant_id, material_id=material_id, lote_id=lote.id,
        tipo="compra", destino_operatorio_id=operatorio_destino_id,
        cantidad=cantidad, fecha=datetime.utcnow(), user_id=user_id,
    ))

    if actualizar_costo_master:
        material.costo_paquete = precio_unitario * cantidad
        material.unidades_paquete = cantidad

    return compra


def _lotes_disponibles(tenant_id, material_id, operatorio_id):
    material = Material.query.filter_by(
        id=material_id, tenant_id=tenant_id
    ).first()
    if not material:
        raise ValueError("Material no existe")
    q = (
        db.session.query(LoteUbicacion, Lote)
        .join(Lote, LoteUbicacion.lote_id == Lote.id)
        .filter(
            Lote.tenant_id == tenant_id,
            Lote.material_id == material_id,
            LoteUbicacion.operatorio_id == operatorio_id,
            LoteUbicacion.cantidad_restante > 0,
        )
    )
    if material.expira:
        q = q.order_by(nullslast(asc(Lote.fecha_caducidad)), asc(Lote.fecha_surtido))
    else:
        q = q.order_by(asc(Lote.fecha_surtido))
    return q.all()


def transferir(
    *, tenant_id, user_id, material_id, origen_operatorio_id,
    destino_operatorio_id, cantidad, lote_id, motivo,
):
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser > 0")
    if origen_operatorio_id == destino_operatorio_id:
        raise ValueError("Origen y destino no pueden ser iguales")

    _operatorio_activo_o_error(tenant_id, origen_operatorio_id, "Operatorio origen")
    _operatorio_activo_o_error(tenant_id, destino_operatorio_id, "Operatorio destino")

    su_origen = _get_or_create_stock_ubicacion(
        tenant_id, material_id, origen_operatorio_id
    )
    if su_origen.cantidad < cantidad:
        raise ValueError(
            f"Stock insuficiente (hay {su_origen.cantidad}, piden {cantidad})"
        )

    if lote_id is not None:
        lote = Lote.query.filter_by(
            id=lote_id, tenant_id=tenant_id
        ).first()
        if not lote:
            raise ValueError("Lote no encontrado")
        lu = LoteUbicacion.query.filter_by(
            lote_id=lote_id, operatorio_id=origen_operatorio_id
        ).first()
        if not lu or lu.cantidad_restante == 0:
            raise ValueError("Lote sin stock en la ubicación de origen")
        lotes = [(lu, lote)]
    else:
        lotes = _lotes_disponibles(tenant_id, material_id, origen_operatorio_id)

    movs = []
    restante = cantidad
    for lu, lote in lotes:
        if restante == 0:
            break
        tomar = min(restante, lu.cantidad_restante)
        lu.cantidad_restante -= tomar

        lu_dest = LoteUbicacion.query.filter_by(
            lote_id=lote.id, operatorio_id=destino_operatorio_id
        ).first()
        if not lu_dest:
            lu_dest = LoteUbicacion(
                lote_id=lote.id, operatorio_id=destino_operatorio_id,
                cantidad_restante=0,
            )
            db.session.add(lu_dest)
            db.session.flush()
        lu_dest.cantidad_restante += tomar

        mov = MovimientoInventario(
            tenant_id=tenant_id, material_id=material_id, lote_id=lote.id,
            tipo="transferencia",
            origen_operatorio_id=origen_operatorio_id,
            destino_operatorio_id=destino_operatorio_id,
            cantidad=tomar, fecha=datetime.utcnow(),
            user_id=user_id, motivo=motivo,
        )
        db.session.add(mov)
        movs.append(mov)
        restante -= tomar

    if restante > 0:
        raise ValueError("Stock insuficiente en lotes disponibles")

    su_origen.cantidad -= cantidad
    su_destino = _get_or_create_stock_ubicacion(
        tenant_id, material_id, destino_operatorio_id
    )
    su_destino.cantidad += cantidad

    return movs


def ajustar(
    *, tenant_id, user_id, material_id, operatorio_id, cantidad_nueva,
    motivo, lote_id,
):
    if cantidad_nueva < 0:
        raise ValueError("cantidad_nueva no puede ser negativa")
    if not motivo:
        raise ValueError("motivo es requerido")

    _operatorio_activo_o_error(tenant_id, operatorio_id, "Operatorio")

    su = _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_id)
    delta = cantidad_nueva - su.cantidad
    if delta == 0:
        raise ValueError("Ajuste sin cambio real")

    su.cantidad = cantidad_nueva

    if lote_id:
        lote = Lote.query.filter_by(
            id=lote_id, tenant_id=tenant_id
        ).first()
        if not lote:
            raise ValueError("Lote no encontrado")
        lu = LoteUbicacion.query.filter_by(
            lote_id=lote_id, operatorio_id=operatorio_id
        ).first()
        if lu:
            lu.cantidad_restante = max(0, lu.cantidad_restante + delta)

    mov = MovimientoInventario(
        tenant_id=tenant_id, material_id=material_id, lote_id=lote_id,
        tipo="ajuste",
        origen_operatorio_id=operatorio_id if delta < 0 else None,
        destino_operatorio_id=operatorio_id if delta > 0 else None,
        cantidad=delta, fecha=datetime.utcnow(),
        user_id=user_id, motivo=motivo,
    )
    db.session.add(mov)
    return mov


def _ubicacion_nombre(tenant_id, operatorio_id):
    if operatorio_id is None:
        return "Almacén"
    op = Operatorio.query.filter_by(id=operatorio_id, tenant_id=tenant_id).first()
    return op.nombre if op else "Desconocida"


def _stock_total_lote(lote_id):
    total = (
        db.session.query(db.func.coalesce(db.func.sum(LoteUbicacion.cantidad_restante), 0))
        .filter(LoteUbicacion.lote_id == lote_id)
        .scalar()
    )
    return total or 0


def calcular_alertas(*, tenant_id):
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    dias = cfg.dias_alerta_caducidad if cfg else 30
    limite = date.today() + timedelta(days=dias)

    stocks = StockUbicacion.query.filter_by(tenant_id=tenant_id).all()
    bajo, alto = [], []
    for su in stocks:
        material = Material.query.get(su.material_id)
        base = {
            "material_id": su.material_id,
            "material_nombre": material.nombre,
            "operatorio_id": su.operatorio_id,
            "ubicacion": _ubicacion_nombre(tenant_id, su.operatorio_id),
            "cantidad": su.cantidad,
        }
        if su.minimo is not None and su.cantidad <= su.minimo:
            bajo.append({**base, "minimo": su.minimo})
        if su.maximo is not None and su.cantidad >= su.maximo:
            alto.append({**base, "maximo": su.maximo})

    caducidad = []
    lotes = (
        db.session.query(Lote, Material)
        .join(Material, Lote.material_id == Material.id)
        .filter(
            Lote.tenant_id == tenant_id,
            Lote.agotado == False,  # noqa: E712
            Lote.fecha_caducidad.isnot(None),
            Lote.fecha_caducidad <= limite,
            Material.expira == True,  # noqa: E712
        ).all()
    )
    for lote, material in lotes:
        caducidad.append({
            "lote_id": lote.id,
            "material_id": material.id,
            "material_nombre": material.nombre,
            "fecha_caducidad": lote.fecha_caducidad.isoformat(),
            "cantidad_restante": _stock_total_lote(lote.id),
        })

    return {"bajo": bajo, "alto": alto, "caducidad": caducidad}


def calcular_kpis_dashboard(*, tenant_id):
    from app.catalogo.models import Material
    from app.inventario.models import Lote, LoteUbicacion, StockUbicacion

    asset_value = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(LoteUbicacion.cantidad_restante * Lote.precio_unitario),
                0.0,
            )
        )
        .join(Lote, Lote.id == LoteUbicacion.lote_id)
        .filter(Lote.tenant_id == tenant_id, Lote.agotado.is_(False))
        .scalar()
    )

    # Fuente unica: todos los materiales del tenant (los mismos que /materiales).
    active_materials = (
        db.session.query(db.func.count(Material.id))
        .filter(Material.tenant_id == tenant_id)
        .scalar()
    )

    critical_rows = (
        db.session.query(StockUbicacion.material_id)
        .filter(
            StockUbicacion.tenant_id == tenant_id,
            StockUbicacion.minimo.isnot(None),
            StockUbicacion.cantidad < StockUbicacion.minimo,
        )
        .distinct()
        .all()
    )

    return {
        "total_asset_value": float(asset_value or 0),
        "active_materials": int(active_materials or 0),
        "critical_items": len(critical_rows),
    }
