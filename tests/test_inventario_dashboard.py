from datetime import date
from app.catalogo.models import Material
from app.inventario.models import Lote, LoteUbicacion, StockUbicacion


def test_dashboard_kpis_returns_aggregates(app, db, tenant_and_user, auth_headers, client):
    tenant, _user = tenant_and_user

    m1 = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    m2 = Material(tenant_id=tenant.id, nombre="Lidocaína", en_inventario=True)
    m3 = Material(tenant_id=tenant.id, nombre="Oculto", en_inventario=False)
    db.session.add_all([m1, m2, m3]); db.session.flush()

    lote = Lote(tenant_id=tenant.id, material_id=m1.id, cantidad_inicial=100,
                fecha_surtido=date.today(), precio_unitario=5.0)
    db.session.add(lote); db.session.flush()
    db.session.add(LoteUbicacion(lote_id=lote.id, operatorio_id=None, cantidad_restante=100))
    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=m1.id,
                                  operatorio_id=None, cantidad=100, minimo=150))
    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=m2.id,
                                  operatorio_id=None, cantidad=50, minimo=10))
    db.session.commit()

    r = client.get("/api/v1/inventario/dashboard", headers=auth_headers)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_asset_value"] == 500.0        # 100 * 5.0
    assert data["active_materials"] == 2             # m3 excluded
    assert data["critical_items"] == 1               # only m1 below minimum


def test_operatory_distribution(app, db, tenant_and_user, auth_headers, client):
    tenant, _user = tenant_and_user
    from app.inventario.models import Operatorio, StockUbicacion
    from app.catalogo.models import Material

    op1 = Operatorio(tenant_id=tenant.id, nombre="Alpha", orden=1, activo=True)
    op2 = Operatorio(tenant_id=tenant.id, nombre="Beta", orden=2, activo=True)
    db.session.add_all([op1, op2]); db.session.flush()

    mat = Material(tenant_id=tenant.id, nombre="Gasa", en_inventario=True)
    db.session.add(mat); db.session.flush()

    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=mat.id,
                                  operatorio_id=op1.id, cantidad=1240, minimo=100))
    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=mat.id,
                                  operatorio_id=op2.id, cantidad=50, minimo=100))
    db.session.commit()

    r = client.get("/api/v1/inventario/operatorios/distribucion", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    by_name = {row["nombre"]: row for row in body}
    assert by_name["Alpha"]["total_units"] == 1240
    assert by_name["Alpha"]["status"] == "stable"
    assert by_name["Beta"]["total_units"] == 50
    assert by_name["Beta"]["status"] == "restock_needed"


def test_movimientos_recientes(app, db, tenant_and_user, auth_headers, client):
    from datetime import datetime
    from app.catalogo.models import Material
    from app.inventario.models import MovimientoInventario, Operatorio

    tenant, user = tenant_and_user
    op = Operatorio(tenant_id=tenant.id, nombre="Alpha", orden=1, activo=True)
    mat = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    db.session.add_all([op, mat]); db.session.flush()

    mv = MovimientoInventario(
        tenant_id=tenant.id, material_id=mat.id, tipo="compra",
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=150, fecha=datetime.utcnow(), user_id=user.id,
    )
    db.session.add(mv); db.session.commit()

    r = client.get("/api/v1/inventario/movimientos/recientes", headers=auth_headers)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["material_nombre"] == "Guantes"
    assert items[0]["destino_nombre"] == "Alpha"
    assert items[0]["cantidad"] == 150
    assert items[0]["tipo"] == "compra"
