def test_registrar_compra_endpoint(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    db.session.add(m); db.session.commit()

    resp = client.post(
        "/api/v1/inventario/compras",
        json={
            "material_id": m.id, "cantidad": 50, "precio_unitario": 2.5,
            "fecha_surtido": "2026-04-20", "fecha_caducidad": "2027-04-20",
            "actualizar_costo_master": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["cantidad"] == 50


def test_viewer_no_puede_registrar_compra(client, db, tenant_and_user):
    from app.auth.models import User
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    v = User(tenant_id=tenant.id, email="v@t.com", name="V", role="viewer")
    v.set_password("password123")
    db.session.add(v)
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.commit()

    login = client.post("/api/v1/auth/login", json={
        "email": "v@t.com", "password": "password123",
    })
    headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}
    resp = client.post(
        "/api/v1/inventario/compras",
        json={
            "material_id": m.id, "cantidad": 1, "precio_unitario": 1,
            "fecha_surtido": "2026-04-20", "actualizar_costo_master": False,
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_listar_compras(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.commit()
    client.post("/api/v1/inventario/compras", json={
        "material_id": m.id, "cantidad": 5, "precio_unitario": 1,
        "fecha_surtido": "2026-04-20", "actualizar_costo_master": False,
    }, headers=auth_headers)
    resp = client.get("/api/v1/inventario/compras", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1
