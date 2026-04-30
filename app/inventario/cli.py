import json
import click
from flask.cli import AppGroup
from app.extensions import db
from app.catalogo.models import MaterialMaster
from app.inventario.models import Categoria, MaterialMasterCategoria

inventario_cli = AppGroup("inventario", help="Comandos del módulo inventario")

CATEGORIAS_BASE = [
    ("mesa_control", "Materiales de la mesa de control"),
    ("instrumental", "Instrumental dental"),
    ("general", "Uso general"),
]


def _get_or_create_cat(nombre, desc=""):
    cat = Categoria.query.filter_by(nombre=nombre).first()
    if not cat:
        cat = Categoria(nombre=nombre, descripcion=desc)
        db.session.add(cat); db.session.flush()
    return cat


def run_seed(seed_path):
    for nombre, desc in CATEGORIAS_BASE:
        _get_or_create_cat(nombre, desc)

    with open(seed_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    existentes = {
        m.nombre.strip().upper(): m for m in MaterialMaster.query.all()
    }

    nuevos = 0
    for item in items:
        key = item["nombre"].strip().upper()
        if key in existentes:
            continue
        master = MaterialMaster(
            nombre=item["nombre"],
            expira=item.get("expira", True),
            unidad_inventario=item.get("unidad_inventario", "pieza"),
            categoria="general",
        )
        db.session.add(master); db.session.flush()
        for cat_nombre in item.get("categorias", []):
            cat = _get_or_create_cat(cat_nombre)
            db.session.add(MaterialMasterCategoria(
                material_master_id=master.id, categoria_id=cat.id
            ))
        existentes[key] = master
        nuevos += 1

    db.session.commit()
    click.echo(f"Seed completado: {nuevos} materiales nuevos agregados.")
    return nuevos


@inventario_cli.command("seed")
@click.argument("seed_path", default="seed_data/inventario_materiales.json")
def seed_cmd(seed_path):
    run_seed(seed_path)
