from datetime import date


def test_listar_materiales(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.services import registrar_compra
    tenant, user = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()

    resp = client.get("/api/v1/inventario/materiales", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["total_global"] == 10


def test_no_lista_sin_en_inventario(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    db.session.add(Material(tenant_id=tenant.id, nombre="SoloPricing", en_inventario=False))
    db.session.commit()
    resp = client.get("/api/v1/inventario/materiales", headers=auth_headers)
    assert len(resp.get_json()) == 0


def test_inspeccionar(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.services import registrar_compra
    tenant, user = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Aguja", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=20, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=date(2027, 1, 1), operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    resp = client.get(
        f"/api/v1/inventario/materiales/{m.id}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["lotes"]) == 1
    assert len(data["stock_por_ubicacion"]) == 1


def test_isolation_material(client, auth_headers, db, tenant_and_user):
    from app.auth.models import Tenant
    from app.catalogo.models import Material
    otro = Tenant(name="Otro", slug="otro")
    db.session.add(otro); db.session.flush()
    m = Material(tenant_id=otro.id, nombre="Ajeno", en_inventario=True)
    db.session.add(m); db.session.commit()
    resp = client.get(f"/api/v1/inventario/materiales/{m.id}", headers=auth_headers)
    assert resp.status_code == 404


def test_actualizar_umbrales(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import StockUbicacion
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.commit()
    resp = client.put(
        f"/api/v1/inventario/materiales/{m.id}",
        json={
            "expira": False, "unidad_inventario": "caja",
            "umbrales": [{"operatorio_id": None, "minimo": 5, "maximo": 30}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    assert su.minimo == 5 and su.maximo == 30
