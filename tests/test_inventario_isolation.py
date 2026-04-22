from datetime import date


def test_operatorio_de_otro_tenant_no_aparece(client, auth_headers, db, tenant_and_user):
    from app.auth.models import Tenant
    from app.inventario.models import Operatorio
    otro = Tenant(name="Otro", slug="otro")
    db.session.add(otro); db.session.flush()
    db.session.add(Operatorio(tenant_id=otro.id, nombre="Op Ajeno"))
    db.session.commit()
    resp = client.get("/api/v1/inventario/operatorios", headers=auth_headers)
    nombres = [o["nombre"] for o in resp.get_json()]
    assert "Op Ajeno" not in nombres


def test_compra_de_otro_tenant_no_aparece(client, auth_headers, db, tenant_and_user):
    from app.auth.models import Tenant, User
    from app.catalogo.models import Material
    from app.inventario.services import registrar_compra
    otro = Tenant(name="Otro", slug="otro")
    db.session.add(otro); db.session.flush()
    u = User(tenant_id=otro.id, email="o@o.com", name="o", role="admin")
    u.set_password("password12345")
    db.session.add(u); db.session.flush()
    m = Material(tenant_id=otro.id, nombre="Ajeno", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=otro.id, user_id=u.id, material_id=m.id,
        cantidad=5, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    resp = client.get("/api/v1/inventario/compras", headers=auth_headers)
    assert resp.get_json() == []


def test_flujo_completo(client, auth_headers, db, tenant_and_user):
    """compra -> umbrales -> transferencia -> alerta baja."""
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Flujo", en_inventario=True)
    db.session.add(m); db.session.commit()

    op_resp = client.post(
        "/api/v1/inventario/operatorios",
        json={"nombre": "Op 1"}, headers=auth_headers,
    )
    op_id = op_resp.get_json()["id"]

    cad = (date.today().replace(year=date.today().year + 1)).isoformat()
    client.post("/api/v1/inventario/compras", json={
        "material_id": m.id, "cantidad": 10, "precio_unitario": 2,
        "fecha_surtido": "2026-04-20", "fecha_caducidad": cad,
        "actualizar_costo_master": False,
    }, headers=auth_headers)

    client.put("/api/v1/inventario/materiales/" + str(m.id), json={
        "umbrales": [
            {"operatorio_id": None, "minimo": 3, "maximo": 50},
            {"operatorio_id": op_id, "minimo": 5, "maximo": None},
        ],
    }, headers=auth_headers)

    client.post("/api/v1/inventario/transferencias", json={
        "material_id": m.id, "origen_operatorio_id": None,
        "destino_operatorio_id": op_id, "cantidad": 4,
    }, headers=auth_headers)

    alertas = client.get(
        "/api/v1/inventario/alertas", headers=auth_headers
    ).get_json()
    bajo_op = [a for a in alertas["bajo"] if a["operatorio_id"] == op_id]
    assert len(bajo_op) == 1
    assert bajo_op[0]["cantidad"] == 4
    assert bajo_op[0]["minimo"] == 5
