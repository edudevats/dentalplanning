"""Revisión de la cadena de migraciones de Alembic, sin importar los archivos.

Detecta lo que hace fallar `flask db upgrade` en producción:
  - más de una head (dos ramas salieron de la misma migración y nadie las unió);
  - un mismo `revision` en dos archivos (p. ej. una unión creada a mano en el
    servidor y otra igual traída después en el repo);
  - un `down_revision` que apunta a una revisión que no existe.

Lo usan la prueba `tests/test_migraciones_cadena.py` (antes de mergear) y el
comando `flask migraciones revisar` (en el servidor, antes del upgrade). Lee los
archivos con `ast` para no ejecutar las migraciones ni depender de Alembic.
"""
import ast
import os
import subprocess
from collections import namedtuple

VERSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations", "versions"
)

Revision = namedtuple("Revision", "archivo revision padres")


def _valor(nodo):
    try:
        return ast.literal_eval(nodo)
    except ValueError:
        return None


def leer_revisiones(versions_dir=VERSIONS_DIR):
    """Una Revision por archivo .py de migración, ordenadas por nombre."""
    revisiones = []
    for nombre in sorted(os.listdir(versions_dir)):
        if not nombre.endswith(".py") or nombre.startswith("__"):
            continue
        with open(os.path.join(versions_dir, nombre), encoding="utf-8") as f:
            arbol = ast.parse(f.read(), filename=nombre)
        valores = {}
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign):
                objetivos, valor = nodo.targets, nodo.value
            elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
                objetivos, valor = [nodo.target], nodo.value
            else:
                continue
            for obj in objetivos:
                if isinstance(obj, ast.Name) and obj.id in ("revision", "down_revision"):
                    valores[obj.id] = _valor(valor)
        if "revision" not in valores:
            continue
        down = valores.get("down_revision")
        padres = () if down is None else (tuple(down) if isinstance(down, (tuple, list)) else (down,))
        revisiones.append(Revision(nombre, valores["revision"], padres))
    return revisiones


def revisar_migraciones(versions_dir=VERSIONS_DIR):
    """Lista de problemas en español; vacía si la cadena está sana."""
    revisiones = leer_revisiones(versions_dir)
    problemas = []

    por_id = {}
    for r in revisiones:
        por_id.setdefault(r.revision, []).append(r.archivo)
    for rev, archivos in sorted(por_id.items()):
        if len(archivos) > 1:
            problemas.append(
                f"La revisión {rev} está en {len(archivos)} archivos: {', '.join(archivos)}. "
                "Deja solo el que está en git."
            )

    for r in revisiones:
        for padre in r.padres:
            if padre not in por_id:
                problemas.append(
                    f"{r.archivo} depende de {padre}, que no existe en migrations/versions."
                )

    usados = {p for r in revisiones for p in r.padres}
    heads = sorted({r.revision for r in revisiones} - usados)
    if len(heads) > 1:
        problemas.append(
            f"Hay {len(heads)} heads ({', '.join(heads)}). Únelas EN LOCAL con "
            '`flask db merge heads -m "union de heads: ..."`, commitea y despliega; '
            "nunca crees la unión en el servidor."
        )
    return problemas


def migraciones_sin_git(versions_dir=VERSIONS_DIR):
    """Archivos .py de migración que git no conoce (creados a mano fuera del repo).

    Devuelve None si git no está disponible: en ese caso no se puede saber.
    """
    try:
        salida = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", "."],
            cwd=versions_dir, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    sueltos = []
    for linea in salida.splitlines():
        if linea.startswith("??") and linea.endswith(".py"):
            sueltos.append(os.path.basename(linea[3:].strip().strip('"')))
    return sueltos
