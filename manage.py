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
@click.option("--debug/--no-debug", default=True, show_default=True, help="Modo debug")
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

@app.cli.command("create-admin")
@click.option("--email", prompt="Email del admin")
@click.option("--password", prompt="Password", hide_input=True, confirmation_prompt=True)
@click.option("--name", prompt="Nombre", default="Admin", show_default=True)
def create_admin(email, password, name):
    """Crea un usuario administrador."""
    with app.app_context():
        try:
            from app.auth.models import User
            if User.query.filter_by(email=email).first():
                click.echo(f"  Ya existe un usuario con el email {email}.")
                sys.exit(1)
            user = User(email=email, name=name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo(f"  Admin creado: {email}")
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
        debug = True
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
            from app.auth.models import User
            email = input("Email: ")
            import getpass
            password = getpass.getpass("Password: ")
            name = input("Nombre [Admin]: ") or "Admin"
            if User.query.filter_by(email=email).first():
                click.echo("Ya existe ese usuario.")
                sys.exit(1)
            user = User(email=email, name=name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo(f"Admin creado: {email}")

    else:
        click.echo(f"Comando desconocido: {cmd}")
        click.echo(__doc__)
        sys.exit(1)
