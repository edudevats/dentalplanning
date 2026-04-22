def test_seed_inserta_categorias_y_materiales(app, db, tmp_path):
    from app.inventario.cli import run_seed
    from app.inventario.models import Categoria
    from app.catalogo.models import MaterialMaster
    import json

    seed_file = tmp_path / "inv.json"
    seed_file.write_text(json.dumps([
        {"nombre": "ABATELENGUAS", "expira": True, "unidad_inventario": "pieza",
         "categorias": ["mesa_control", "instrumental"]},
        {"nombre": "GUANTES", "expira": True, "unidad_inventario": "caja",
         "categorias": ["mesa_control"]},
    ]), encoding="utf-8")

    run_seed(str(seed_file))

    cats = {c.nombre for c in Categoria.query.all()}
    assert {"mesa_control", "instrumental", "general"} <= cats

    nombres = {m.nombre for m in MaterialMaster.query.all()}
    assert "ABATELENGUAS" in nombres
    assert "GUANTES" in nombres


def test_seed_no_duplica(app, db, tmp_path):
    from app.inventario.cli import run_seed
    from app.catalogo.models import MaterialMaster
    import json

    db.session.add(MaterialMaster(nombre="alcohol", categoria="general"))
    db.session.commit()

    seed_file = tmp_path / "inv.json"
    seed_file.write_text(json.dumps([
        {"nombre": "ALCOHOL", "expira": True, "unidad_inventario": "pieza",
         "categorias": ["mesa_control"]},
    ]), encoding="utf-8")

    run_seed(str(seed_file))
    count = MaterialMaster.query.filter(
        db.func.upper(MaterialMaster.nombre) == "ALCOHOL"
    ).count()
    assert count == 1
