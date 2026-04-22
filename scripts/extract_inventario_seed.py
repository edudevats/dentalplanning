"""Lee Inventario smile studio.xlsx y emite seed_data/inventario_materiales.json.

Uso:
    python scripts/extract_inventario_seed.py "Inventario smile studio.xlsx"
"""
import json
import sys
from pathlib import Path
import pandas as pd

NO_EXPIRA = {"no", "NO", "No"}


def _extraer_hoja(xlsx_path, sheet):
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    out = {}
    for _, row in df.iloc[7:].iterrows():
        nombre = row[0]
        if pd.isna(nombre):
            continue
        nombre = str(nombre).strip()
        if not nombre:
            continue
        cad_val = row[6]
        no_expira = (
            not pd.isna(cad_val) and str(cad_val).strip() in NO_EXPIRA
        )
        out[nombre.upper()] = {"expira": not no_expira}
    return out


def main():
    if len(sys.argv) < 2:
        print("Uso: extract_inventario_seed.py <archivo.xlsx>")
        sys.exit(1)
    xlsx = sys.argv[1]
    mesa = _extraer_hoja(xlsx, "MESA DE CONTROL")
    inst = _extraer_hoja(xlsx, "INSTRUMENTAL")

    todos = {}
    for nombre, info in mesa.items():
        todos[nombre] = {
            "nombre": nombre, "expira": info["expira"],
            "unidad_inventario": "pieza",
            "categorias": ["mesa_control"],
        }
    for nombre, info in inst.items():
        if nombre in todos:
            if "instrumental" not in todos[nombre]["categorias"]:
                todos[nombre]["categorias"].append("instrumental")
            todos[nombre]["expira"] = todos[nombre]["expira"] and info["expira"]
        else:
            todos[nombre] = {
                "nombre": nombre, "expira": info["expira"],
                "unidad_inventario": "pieza",
                "categorias": ["instrumental"],
            }

    salida = sorted(todos.values(), key=lambda m: m["nombre"])
    out = Path("seed_data/inventario_materiales.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {out} con {len(salida)} materiales")


if __name__ == "__main__":
    main()
