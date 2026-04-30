from datetime import datetime, date, timedelta
from sqlalchemy import asc, nullslast
from app.extensions import db
from app.catalogo.models import Material
from app.configuracion.models import ConfigConsultorio
from app.inventario.models import (
    Operatorio, Lote, LoteUbicacion, StockUbicacion, Compra, MovimientoInventario,
)


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
    material = Material.query.get(material_id)
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

    su_origen = _get_or_create_stock_ubicacion(
        tenant_id, material_id, origen_operatorio_id
    )
    if su_origen.cantidad < cantidad:
        raise ValueError(
            f"Stock insuficiente (hay {su_origen.cantidad}, piden {cantidad})"
        )

    if lote_id is not None:
        lu = LoteUbicacion.query.filter_by(
            lote_id=lote_id, operatorio_id=origen_operatorio_id
        ).first()
        if not lu or lu.cantidad_restante == 0:
            raise ValueError("Lote sin stock en la ubicación de origen")
        lote = Lote.query.get(lote_id)
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

    su = _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_id)
    delta = cantidad_nueva - su.cantidad
    if delta == 0:
        raise ValueError("Ajuste sin cambio real")

    su.cantidad = cantidad_nueva

    if lote_id:
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

    active_materials = (
        db.session.query(db.func.count(Material.id))
        .filter(Material.tenant_id == tenant_id, Material.en_inventario.is_(True))
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
