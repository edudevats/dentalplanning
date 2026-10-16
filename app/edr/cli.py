import click
from flask.cli import AppGroup

from app.extensions import db
from app.edr import recurrentes
from app.edr.models import GastoRecurrente

gastos_cli = AppGroup("gastos", help="Comandos de gastos operativos")


@gastos_cli.command("generar-recurrentes")
@click.option("--tenant-id", type=int, default=None, help="Solo este tenant")
@click.option("--dry-run", is_flag=True, help="Solo cuenta, sin escribir")
def generar_recurrentes(tenant_id, dry_run):
    """Crea los gastos recurrentes pendientes hasta hoy.

    No hace falta para que funcionen (cada lectura de gastos ya los genera);
    sirve para un cron opcional y para soporte.
    """
    q = db.session.query(GastoRecurrente.tenant_id).filter(
        GastoRecurrente.activo.is_(True)).distinct()
    if tenant_id is not None:
        q = q.filter(GastoRecurrente.tenant_id == tenant_id)
    tenant_ids = [t for (t,) in q.all()]

    total = 0
    for tid in tenant_ids:
        n = recurrentes.generar_pendientes(tid, commit=not dry_run)
        if dry_run:
            db.session.rollback()
        total += n
        if n:
            click.echo(f"tenant {tid}: {n} gasto(s)")
    verbo = "Se generarían" if dry_run else "Se generaron"
    click.echo(f"{verbo} {total} gasto(s) recurrente(s).")
