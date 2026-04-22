def test_listar_operatorios_vacio(client, auth_headers):
    resp = client.get("/api/v1/inventario/operatorios", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_crear_operatorio(client, auth_headers):
    resp = client.post(
        "/api/v1/inventario/operatorios",
        json={"nombre": "Op Infantil", "orden": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["nombre"] == "Op Infantil"


def test_no_borrar_operatorio_con_stock(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import Operatorio, StockUbicacion
    tenant, _ = tenant_and_user
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.flush()
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id, cantidad=5
    ))
    db.session.commit()

    resp = client.delete(
        f"/api/v1/inventario/operatorios/{op.id}", headers=auth_headers
    )
    assert resp.status_code == 409
