from datetime import date, datetime

from app.catalogo.models import Material, MaterialMaster
from app.inventario.models import (
    Categoria, MaterialCategoria, MaterialMasterCategoria, Operatorio,
    Lote, LoteUbicacion, StockUbicacion, Compra, MovimientoInventario,
)


def test_crear_categoria(app, db):
    c = Categoria(nombre="mesa_control", descripcion="Mesa de control")
    db.session.add(c)
    db.session.commit()
    assert c.id is not None


def test_material_con_multiples_categorias(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    cat1 = Categoria(nombre="mesa_control")
    cat2 = Categoria(nombre="instrumental")
    db.session.add_all([cat1, cat2])
    db.session.flush()

    m = Material(tenant_id=tenant.id, nombre="Espejo")
    db.session.add(m)
    db.session.flush()

    db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cat1.id))
    db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cat2.id))
    db.session.commit()

    assert len(m.categorias) == 2
    nombres = sorted(c.nombre for c in m.categorias)
    assert nombres == ["instrumental", "mesa_control"]


def test_material_tiene_campos_inventario(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Guantes")
    db.session.add(m)
    db.session.commit()

    assert m.expira is True
    assert m.unidad_inventario == "pieza"
    assert m.en_inventario is False


def test_material_master_tiene_campos_inventario(app, db):
    m = MaterialMaster(nombre="Guantes", categoria="general")
    db.session.add(m)
    db.session.commit()

    assert m.expira is True
    assert m.unidad_inventario == "pieza"


def test_crear_operatorio(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    op = Operatorio(tenant_id=tenant.id, nombre="Operatorio 1", orden=1)
    db.session.add(op)
    db.session.commit()
    assert op.id is not None
    assert op.activo is True


def test_operatorio_nombre_unique_por_tenant(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    db.session.add(Operatorio(tenant_id=tenant.id, nombre="Op 1"))
    db.session.commit()
    db.session.add(Operatorio(tenant_id=tenant.id, nombre="Op 1"))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def _mk_material(db, tenant_id, nombre="Abatelenguas"):
    m = Material(tenant_id=tenant_id, nombre=nombre, en_inventario=True)
    db.session.add(m)
    db.session.flush()
    return m


def test_crear_lote_con_caducidad(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = _mk_material(db, tenant.id)
    lote = Lote(
        tenant_id=tenant.id, material_id=m.id, cantidad_inicial=100,
        fecha_surtido=date(2026, 4, 1), fecha_caducidad=date(2027, 4, 1),
        precio_unitario=1.5,
    )
    db.session.add(lote)
    db.session.commit()
    assert lote.id is not None
    assert lote.agotado is False


def test_lote_ubicacion_y_stock_ubicacion(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = _mk_material(db, tenant.id)
    lote = Lote(
        tenant_id=tenant.id, material_id=m.id, cantidad_inicial=100,
        fecha_surtido=date(2026, 4, 1),
    )
    db.session.add(lote)
    db.session.flush()

    lu = LoteUbicacion(lote_id=lote.id, operatorio_id=None, cantidad_restante=100)
    su = StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None,
        cantidad=100, minimo=30, maximo=300,
    )
    db.session.add_all([lu, su])
    db.session.commit()
    assert lu.id is not None
    assert su.id is not None


def test_stock_ubicacion_unique(app, db, tenant_and_user):
    # Use a concrete operatorio_id so the unique constraint fires on SQLite too
    # (SQLite treats every NULL as distinct, so NULL-keyed rows never collide).
    tenant, _ = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op-unique-test")
    db.session.add(op)
    db.session.flush()

    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id, cantidad=0
    ))
    db.session.commit()
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id, cantidad=5
    ))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_crear_compra(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, "Aguja corta")
    lote = Lote(
        tenant_id=tenant.id, material_id=m.id, cantidad_inicial=100,
        fecha_surtido=date(2026, 4, 1),
    )
    db.session.add(lote)
    db.session.flush()

    compra = Compra(
        tenant_id=tenant.id, material_id=m.id, lote_id=lote.id,
        fecha=date(2026, 4, 1), cantidad=100, precio_unitario=2.0,
        user_id=user.id, actualizo_costo_master=True,
    )
    db.session.add(compra)
    db.session.commit()
    assert compra.id is not None


def test_crear_movimiento(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, "Algodon")
    mov = MovimientoInventario(
        tenant_id=tenant.id, material_id=m.id,
        tipo="compra", cantidad=50, user_id=user.id,
        fecha=datetime.utcnow(),
    )
    db.session.add(mov)
    db.session.commit()
    assert mov.id is not None
