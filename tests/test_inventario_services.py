from datetime import date
import pytest
from app.catalogo.models import Material
from app.inventario.models import (
    Operatorio, Lote, LoteUbicacion, StockUbicacion, Compra,
    MovimientoInventario,
)
from app.inventario.services import (
    registrar_compra, transferir, ajustar, calcular_alertas,
)
from datetime import timedelta


def _mk_material(db, tenant_id, nombre="Guantes", costo_paquete=0, unidades_paquete=1):
    m = Material(
        tenant_id=tenant_id, nombre=nombre, en_inventario=True,
        costo_paquete=costo_paquete, unidades_paquete=unidades_paquete,
    )
    db.session.add(m)
    db.session.flush()
    return m


def test_registrar_compra_crea_lote_y_suma_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)

    compra = registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=50, precio_unitario=2.0,
        fecha_surtido=date(2026, 4, 20),
        fecha_caducidad=date(2027, 4, 20),
        operatorio_destino_id=None,
        comentarios="Compra abril",
        actualizar_costo_master=False,
    )
    db.session.commit()

    lote = Lote.query.get(compra.lote_id)
    assert lote.cantidad_inicial == 50
    assert lote.fecha_caducidad == date(2027, 4, 20)

    lu = LoteUbicacion.query.filter_by(lote_id=lote.id, operatorio_id=None).first()
    assert lu.cantidad_restante == 50

    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    assert su.cantidad == 50

    mov = MovimientoInventario.query.filter_by(lote_id=lote.id).first()
    assert mov.tipo == "compra"


def test_registrar_compra_con_actualizar_costo_master(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, costo_paquete=100, unidades_paquete=100)

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=50, precio_unitario=3.0,
        fecha_surtido=date(2026, 4, 20), fecha_caducidad=None,
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=True,
    )
    db.session.commit()
    db.session.refresh(m)
    assert m.costo_paquete == 150.0
    assert m.unidades_paquete == 50


def test_registrar_compra_sin_actualizar_no_toca_costo(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, costo_paquete=100, unidades_paquete=100)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=50, precio_unitario=3.0,
        fecha_surtido=date(2026, 4, 20), fecha_caducidad=None,
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    db.session.commit()
    db.session.refresh(m)
    assert m.costo_paquete == 100
    assert m.unidades_paquete == 100


def test_registrar_compra_material_no_expira_ignora_caducidad(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    m.expira = False
    db.session.flush()

    compra = registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=10, precio_unitario=5.0,
        fecha_surtido=date(2026, 4, 20),
        fecha_caducidad=date(2027, 4, 20),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    db.session.commit()
    lote = Lote.query.get(compra.lote_id)
    assert lote.fecha_caducidad is None


def test_transferencia_resta_origen_suma_destino(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=20, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=date(2027, 1, 1), operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()

    transferir(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=5, lote_id=None, motivo="reabasto",
    )
    db.session.commit()

    su_alm = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    su_op = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id
    ).first()
    assert su_alm.cantidad == 15
    assert su_op.cantidad == 5


def test_transferencia_fifo_por_caducidad(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 1, 1),
        fecha_caducidad=date(2027, 12, 1), operatorio_destino_id=None,
        comentarios="A", actualizar_costo_master=False,
    )
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 2, 1),
        fecha_caducidad=date(2027, 6, 1), operatorio_destino_id=None,
        comentarios="B", actualizar_costo_master=False,
    )
    db.session.flush()

    movs = transferir(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=3, lote_id=None, motivo=None,
    )
    db.session.commit()
    lote_consumido = Lote.query.get(movs[0].lote_id)
    assert lote_consumido.comentarios == "B"


def test_transferencia_multi_lote(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=3, precio_unitario=1.0, fecha_surtido=date(2026, 1, 1),
        fecha_caducidad=date(2027, 5, 1), operatorio_destino_id=None,
        comentarios="A", actualizar_costo_master=False,
    )
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 2, 1),
        fecha_caducidad=date(2027, 10, 1), operatorio_destino_id=None,
        comentarios="B", actualizar_costo_master=False,
    )
    db.session.flush()

    movs = transferir(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=5, lote_id=None, motivo=None,
    )
    db.session.commit()
    assert len(movs) == 2
    assert sum(mv.cantidad for mv in movs) == 5


def test_transferencia_sin_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    with pytest.raises(ValueError, match="Stock insuficiente"):
        transferir(
            tenant_id=tenant.id, user_id=user.id, material_id=m.id,
            origen_operatorio_id=None, destino_operatorio_id=op.id,
            cantidad=5, lote_id=None, motivo=None,
        )


def test_ajuste_aumenta_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()

    mov = ajustar(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        operatorio_id=None, cantidad_nueva=15, motivo="conteo",
        lote_id=None,
    )
    db.session.commit()
    assert mov.tipo == "ajuste"
    assert mov.cantidad == 5
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    assert su.cantidad == 15


def test_ajuste_reduce_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()
    mov = ajustar(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        operatorio_id=None, cantidad_nueva=3, motivo="merma",
        lote_id=None,
    )
    db.session.commit()
    assert mov.cantidad == -7


def test_alerta_stock_bajo_independiente_por_ubicacion(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, "Guantes")
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=5, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    su.minimo = 10
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id,
        cantidad=0, minimo=1,
    ))
    db.session.commit()

    alertas = calcular_alertas(tenant_id=tenant.id)
    assert len(alertas["bajo"]) == 2


def test_alerta_caducidad_respeta_config(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    from app.configuracion.models import ConfigConsultorio
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant.id).first()
    cfg.dias_alerta_caducidad = 30
    db.session.flush()
    hoy = date.today()
    m = _mk_material(db, tenant.id)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=hoy,
        fecha_caducidad=hoy + timedelta(days=15),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=hoy,
        fecha_caducidad=hoy + timedelta(days=90),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    db.session.commit()
    alertas = calcular_alertas(tenant_id=tenant.id)
    assert len(alertas["caducidad"]) == 1


def test_material_no_expira_sin_alerta_caducidad(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    m.expira = False
    db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    alertas = calcular_alertas(tenant_id=tenant.id)
    assert len(alertas["caducidad"]) == 0
