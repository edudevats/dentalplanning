#!/usr/bin/env python
"""
manage.py — CLI para gestionar la aplicacion Dental Planning.

Uso:
  python manage.py runserver          # Inicia el servidor (API + frontend)
  python manage.py runserver --port 8000 --host 0.0.0.0

  python manage.py db init            # Inicializa la carpeta migrations/
  python manage.py db migrate -m "msg"# Genera una nueva migracion
  python manage.py db upgrade         # Aplica migraciones pendientes
  python manage.py db downgrade       # Revierte la ultima migracion
  python manage.py db current         # Muestra la revision actual
  python manage.py db history         # Muestra el historial de migraciones

  python manage.py shell              # Abre un shell con el contexto de la app
  python manage.py create-admin       # Crea un usuario administrador
"""

import sys
import os
import time

# Forzar zona horaria de México en todo el proceso.
os.environ['TZ'] = 'America/Mexico_City'
try:
    time.tzset()
except AttributeError:
    pass  # time.tzset() solo disponible en Unix

import click
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db

app = create_app()


# ── runserver ────────────────────────────────────────────────────────────────

@app.cli.command("runserver")
@click.option("--host", default="127.0.0.1", show_default=True, help="Direccion de escucha")
@click.option("--port", default=5000, show_default=True, help="Puerto")
@click.option("--debug/--no-debug", default=False, show_default=True, help="Modo debug")
def runserver(host, port, debug):
    """Inicia el servidor Flask (API + frontend)."""
    click.echo(f"  Servidor iniciado en http://{host}:{port}")
    click.echo("  Presiona CTRL+C para detener.\n")
    app.run(host=host, port=port, debug=debug)


# ── db commands (delegados a Flask-Migrate) ──────────────────────────────────

@app.cli.command("db")
@click.argument("action", required=False)
@click.argument("args", nargs=-1)
@click.pass_context
def db_cmd(ctx, action, args):
    """Alias conveniente — usa 'flask db <accion>' directamente."""
    click.echo("Usa: flask db <accion>  (init | migrate | upgrade | downgrade | current | history)")
    click.echo("Ejemplo: flask db upgrade")


# ── shell ────────────────────────────────────────────────────────────────────

@app.cli.command("shell")
def shell_cmd():
    """Abre un shell interactivo con el contexto de la app."""
    import code
    with app.app_context():
        ctx = {"app": app, "db": db}
        try:
            from app.auth.models import User
            from app.catalogo.models import Material
            from app.tratamientos.models import Tratamiento
            from app.edr.models import Ingreso, Gasto
            ctx.update({"User": User, "Material": Material, "Tratamiento": Tratamiento, "Ingreso": Ingreso, "Gasto": Gasto})
        except Exception:
            pass
        click.echo("Shell Dental Planning. Variables disponibles: " + ", ".join(ctx.keys()))
        code.interact(local=ctx)


# ── create-admin ─────────────────────────────────────────────────────────────

def _do_create_admin(email, password, name, super_admin, tenant_slug):
    """Crea un User. Si super_admin=True, lo asocia al tenant __system__
    y marca is_superuser=True. Si no, lo asocia al tenant_slug indicado."""
    from app.auth.models import (
        User, Tenant, SYSTEM_TENANT_SLUG, TENANT_STATUS_ACTIVE,
    )

    if User.query.filter_by(email=email).first():
        click.echo(f"  Ya existe un usuario con el email {email}.")
        sys.exit(1)

    if super_admin:
        tenant = Tenant.query.filter_by(slug=SYSTEM_TENANT_SLUG).first()
        if not tenant:
            tenant = Tenant(
                name="System (super-admin)",
                slug=SYSTEM_TENANT_SLUG,
                plan="system",
                is_active=True,
                status=TENANT_STATUS_ACTIVE,
            )
            db.session.add(tenant)
            db.session.flush()
        role = "admin"
        is_super = True
    else:
        if not tenant_slug:
            click.echo("  Falta --tenant-slug para usuario no super-admin.")
            sys.exit(1)
        tenant = Tenant.query.filter_by(slug=tenant_slug).first()
        if not tenant:
            click.echo(f"  No existe el tenant con slug '{tenant_slug}'.")
            sys.exit(1)
        role = "admin"
        is_super = False

    user = User(
        email=email,
        name=name,
        role=role,
        tenant_id=tenant.id,
        is_superuser=is_super,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    if is_super:
        click.echo(f"  Super-admin creado: {email} (tenant={tenant.slug})")
    else:
        click.echo(f"  Admin creado: {email} (tenant={tenant.slug})")


@app.cli.command("create-admin")
@click.option("--email", prompt="Email del admin")
@click.option("--password", prompt="Password", hide_input=True, confirmation_prompt=True)
@click.option("--name", prompt="Nombre", default="Admin", show_default=True)
@click.option("--super/--no-super", "super_admin", default=True, show_default=True,
              help="Crea super-admin global asociado al tenant __system__")
@click.option("--tenant-slug", default=None,
              help="Slug del tenant (solo si --no-super)")
def create_admin(email, password, name, super_admin, tenant_slug):
    """Crea un usuario administrador (por default, super-admin global)."""
    with app.app_context():
        try:
            _do_create_admin(email, password, name, super_admin, tenant_slug)
        except Exception as e:
            click.echo(f"  Error: {e}")
            sys.exit(1)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Soporte para: python manage.py runserver / db upgrade / etc.
    if len(sys.argv) < 2:
        click.echo(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "runserver":
        # Parsear flags manualmente para el entry point directo
        host = "127.0.0.1"
        port = 5000
        debug = False
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] in ("--host",) and i + 1 < len(args):
                host = args[i + 1]; i += 2
            elif args[i] in ("--port",) and i + 1 < len(args):
                port = int(args[i + 1]); i += 2
            elif args[i] == "--no-debug":
                debug = False; i += 1
            else:
                i += 1
        click.echo(f"  Servidor iniciado en http://{host}:{port}")
        click.echo("  Presiona CTRL+C para detener.\n")
        app.run(host=host, port=port, debug=debug)

    elif cmd == "db":
        # Delegar a flask-migrate via subprocess para mantener el contexto correcto
        import subprocess
        flask_args = ["flask", "db"] + sys.argv[2:]
        result = subprocess.run(flask_args, env={**__import__("os").environ, "FLASK_APP": "manage.py"})
        sys.exit(result.returncode)

    elif cmd == "shell":
        with app.app_context():
            import code
            ctx = {"app": app, "db": db}
            try:
                from app.auth.models import User
                ctx["User"] = User
            except Exception:
                pass
            click.echo("Shell Dental Planning. Variables: " + ", ".join(ctx.keys()))
            code.interact(local=ctx)

    elif cmd == "create-admin":
        with app.app_context():
            email = input("Email: ")
            import getpass
            password = getpass.getpass("Password: ")
            name = input("Nombre [Admin]: ") or "Admin"
            ans = input("¿Super-admin global? [Y/n]: ").strip().lower()
            super_admin = ans in ("", "y", "yes", "s", "si")
            tenant_slug = None
            if not super_admin:
                tenant_slug = input("Tenant slug: ").strip()
            try:
                _do_create_admin(email, password, name, super_admin, tenant_slug)
            except Exception as e:
                click.echo(f"  Error: {e}")
                sys.exit(1)

    else:
        click.echo(f"Comando desconocido: {cmd}")
        click.echo(__doc__)
        sys.exit(1)
