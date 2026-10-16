import click
from flask.cli import AppGroup

from app.migraciones_check import migraciones_sin_git, revisar_migraciones

migraciones_cli = AppGroup("migraciones", help="Chequeos de la cadena de migraciones")


@migraciones_cli.command("revisar")
def revisar():
    """Correr ANTES de `flask db upgrade` en cada deploy.

    Falla (exit 1) si hay varias heads, IDs duplicados, dependencias rotas o
    migraciones que no vienen de git.
    """
    problemas = revisar_migraciones()
    sueltos = migraciones_sin_git()
    if sueltos:
        problemas.append(
            f"Migraciones que no están en git: {', '.join(sueltos)}. Las migraciones "
            "se crean en local y llegan por git; muévelas fuera de migrations/versions "
            "(no las borres hasta confirmar que no hacen nada que el repo no tenga)."
        )
    if problemas:
        for p in problemas:
            click.echo(f"ERROR: {p}", err=True)
        raise SystemExit(1)
    click.echo("OK: una sola head, sin duplicados ni migraciones fuera de git.")
