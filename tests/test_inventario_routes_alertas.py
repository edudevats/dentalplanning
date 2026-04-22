from datetime import date, timedelta


def test_alertas_endpoint(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import StockUbicacion
    from app.inventario.services import registrar_compra
    tenant, user = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=2, precio_unitario=1, fecha_surtido=date.today(),
        fecha_caducidad=date.today() + timedelta(days=10),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id
    ).first()
    su.minimo = 5
    db.session.commit()

    resp = client.get("/api/v1/inventario/alertas", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["bajo"]) == 1
    assert len(data["caducidad"]) == 1


def test_alertas_resumen(client, auth_headers):
    resp = client.get("/api/v1/inventario/alertas/resumen", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"bajo", "alto", "caducidad"}
