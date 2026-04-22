from datetime import date


def _seed(db, tenant_id, user_id, cantidad=20):
    from app.catalogo.models import Material
    from app.inventario.models import Operatorio
    from app.inventario.services import registrar_compra
    m = Material(tenant_id=tenant_id, nombre="Alg", en_inventario=True)
    db.session.add(m); db.session.flush()
    op = Operatorio(tenant_id=tenant_id, nombre="Op 1")
    db.session.add(op); db.session.flush()
    registrar_compra(
        tenant_id=tenant_id, user_id=user_id, material_id=m.id,
        cantidad=cantidad, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    return m, op


def test_transferencia(client, auth_headers, db, tenant_and_user):
    tenant, user = tenant_and_user
    m, op = _seed(db, tenant.id, user.id)
    resp = client.post(
        "/api/v1/inventario/transferencias",
        json={
            "material_id": m.id, "origen_operatorio_id": None,
            "destino_operatorio_id": op.id, "cantidad": 5, "motivo": "r",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_transferencia_sin_stock_409(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import Operatorio
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add_all([m, op]); db.session.commit()
    resp = client.post(
        "/api/v1/inventario/transferencias",
        json={
            "material_id": m.id, "origen_operatorio_id": None,
            "destino_operatorio_id": op.id, "cantidad": 5, "motivo": None,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_ajuste(client, auth_headers, db, tenant_and_user):
    tenant, user = tenant_and_user
    m, _ = _seed(db, tenant.id, user.id, cantidad=10)
    resp = client.post(
        "/api/v1/inventario/ajustes",
        json={
            "material_id": m.id, "operatorio_id": None,
            "cantidad_nueva": 7, "motivo": "conteo",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_listar_movimientos(client, auth_headers, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant.id, user.id)
    resp = client.get("/api/v1/inventario/movimientos", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) >= 1
