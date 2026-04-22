def test_listar_categorias(client, auth_headers, db):
    from app.inventario.models import Categoria
    db.session.add_all([
        Categoria(nombre="mesa_control"),
        Categoria(nombre="instrumental"),
    ])
    db.session.commit()

    resp = client.get("/api/v1/inventario/categorias", headers=auth_headers)
    assert resp.status_code == 200
    nombres = sorted(c["nombre"] for c in resp.get_json())
    assert "mesa_control" in nombres
    assert "instrumental" in nombres
