def test_master_disponibles(client, auth_headers, db):
    from app.catalogo.models import MaterialMaster
    db.session.add_all([
        MaterialMaster(nombre="A", categoria="general"),
        MaterialMaster(nombre="B", categoria="general"),
    ])
    db.session.commit()
    resp = client.get("/api/v1/inventario/master-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


def test_importar(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import MaterialMaster, Material
    tenant, _ = tenant_and_user
    a = MaterialMaster(nombre="A", categoria="general")
    b = MaterialMaster(nombre="B", categoria="general")
    db.session.add_all([a, b]); db.session.commit()
    resp = client.post(
        "/api/v1/inventario/materiales/importar-master",
        json={"master_ids": [a.id, b.id]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    count = Material.query.filter_by(tenant_id=tenant.id, en_inventario=True).count()
    assert count == 2


def test_importar_no_duplica(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import MaterialMaster, Material
    tenant, _ = tenant_and_user
    master = MaterialMaster(nombre="A", categoria="general")
    db.session.add(master); db.session.flush()
    db.session.add(Material(
        tenant_id=tenant.id, nombre="A", master_id=master.id, en_inventario=False
    ))
    db.session.commit()
    client.post(
        "/api/v1/inventario/materiales/importar-master",
        json={"master_ids": [master.id]},
        headers=auth_headers,
    )
    mats = Material.query.filter_by(tenant_id=tenant.id, nombre="A").all()
    assert len(mats) == 1
    assert mats[0].en_inventario is True
