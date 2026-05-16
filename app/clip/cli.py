import click
from datetime import date, timedelta
from flask.cli import AppGroup
from app.extensions import db
from app.superadmin.models import (
    Plan, Subscription, Payment,
    SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA, SUBSCRIPTION_VENCIDA,
)
from app.clip.service import create_checkout_link, ClipAPIError

billing_cli = AppGroup("billing", help="Comandos de facturación y cobros Clip")

GRACE_DAYS = 3

DEFAULT_PLANS = [
    {
        "nombre": "Prueba Gratis",
        "precio_mensual": 0,
        "descripcion": "Prueba gratuita de 8 días con acceso al sistema contable",
        "modulos": ["contable"],
        "es_temporal": True,
        "dias_expiracion": 8,
        "publico": True,
    },
    {
        "nombre": "Básico",
        "precio_mensual": 499.0,
        "descripcion": "Sistema contable: tratamientos, precios, dashboard y reportes",
        "modulos": ["contable"],
    },
    {
        "nombre": "Pro",
        "precio_mensual": 899.0,
        "descripcion": "Contable + Inventario: stock, almacén y operatorios",
        "modulos": ["contable", "inventario"],
    },
    {
        "nombre": "Premium",
        "precio_mensual": 1299.0,
        "descripcion": "Todos los módulos: contable, inventario y finanzas personales",
        "modulos": ["contable", "inventario", "finanzas_personales"],
    },
    {
        "nombre": "Demo",
        "precio_mensual": 0,
        "descripcion": "Acceso demo para convenciones y presentaciones",
        "modulos": ["contable", "inventario", "finanzas_personales"],
        "es_temporal": True,
        "dias_expiracion": 3,
        "publico": False,
    },
]


@billing_cli.command("cycle")
@click.option("--dry-run", is_flag=True, help="Solo muestra qué haría, sin ejecutar")
def billing_cycle(dry_run):
    """Procesa cobros recurrentes para suscripciones vencidas."""
    from flask import current_app

    today = date.today()
    base_url = current_app.config.get("APP_BASE_URL", "http://localhost:5000")
    webhook_url = f"{base_url}/api/v1/clip/webhook"
    redirect_url = f"{base_url}/selector"

    due = Subscription.query.filter(
        Subscription.estado.in_([SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA]),
        Subscription.proximo_cobro <= today,
    ).all()

    if not due:
        click.echo("No hay suscripciones pendientes de cobro.")
        return

    click.echo(f"Suscripciones a procesar: {len(due)}")

    charged = 0
    graced = 0
    suspended = 0
    errors = 0

    for sub in due:
        tenant_name = sub.tenant.name if sub.tenant else f"tenant#{sub.tenant_id}"
        plan = sub.plan

        if plan and plan.es_temporal:
            click.echo(f"  EXPIRE {tenant_name}: plan temporal '{plan.nombre}' venció")
            if not dry_run:
                sub.estado = SUBSCRIPTION_VENCIDA
                db.session.commit()
            suspended += 1
            continue

        if not plan or plan.precio_mensual <= 0:
            click.echo(f"  SKIP {tenant_name}: plan sin precio")
            continue

        if sub.estado == SUBSCRIPTION_GRACIA and sub.grace_expires_at and today > sub.grace_expires_at:
            click.echo(f"  SUSPEND {tenant_name}: gracia expirada {sub.grace_expires_at}")
            if not dry_run:
                sub.estado = SUBSCRIPTION_VENCIDA
                sub.grace_expires_at = None
                db.session.commit()
            suspended += 1
            continue

        click.echo(f"  CHARGE {tenant_name}: {plan.nombre} ${plan.precio_mensual:.2f}")
        if dry_run:
            charged += 1
            continue

        try:
            periodo_inicio = sub.proximo_cobro
            periodo_fin = periodo_inicio + timedelta(days=30)
            desc = f"{plan.nombre} — {tenant_name} ({periodo_inicio} a {periodo_fin})"

            result = create_checkout_link(
                amount=plan.precio_mensual,
                description=desc,
                webhook_url=webhook_url,
                redirect_url=redirect_url,
                metadata={"tenant_id": sub.tenant_id, "subscription_id": sub.id},
            )

            clip_id = result.get("payment_request_id", "")
            payment = Payment(
                tenant_id=sub.tenant_id,
                subscription_id=sub.id,
                fecha=today,
                monto=plan.precio_mensual,
                metodo="clip",
                periodo_inicio=periodo_inicio,
                periodo_fin=periodo_fin,
                comentarios=f"Cobro automático — {desc}",
                registrado_por_id=1,
                clip_payment_id=clip_id,
                clip_status="PENDING",
            )
            db.session.add(payment)

            sub.clip_checkout_id = clip_id
            if sub.estado == SUBSCRIPTION_ACTIVA:
                sub.estado = SUBSCRIPTION_GRACIA
                sub.grace_expires_at = today + timedelta(days=GRACE_DAYS)

            db.session.commit()
            charged += 1
            click.echo(f"    → Clip link creado: {clip_id}")

        except ClipAPIError as e:
            db.session.rollback()
            click.echo(f"    ✗ Error Clip: {e}")
            errors += 1
        except Exception as e:
            db.session.rollback()
            click.echo(f"    ✗ Error inesperado: {e}")
            errors += 1

    click.echo(f"\nResultado: {charged} cobrados, {graced} en gracia, {suspended} suspendidos, {errors} errores")


@billing_cli.command("seed-plans")
def seed_plans():
    """Crea los planes por defecto (Básico, Pro, Premium) si no existen."""
    created = 0
    for p in DEFAULT_PLANS:
        existing = Plan.query.filter_by(nombre=p["nombre"]).first()
        if existing:
            click.echo(f"  EXISTS {p['nombre']} (id={existing.id})")
            continue
        plan = Plan(
            nombre=p["nombre"],
            precio_mensual=p["precio_mensual"],
            descripcion=p["descripcion"],
            modulos=p["modulos"],
            activo=True,
            publico=p.get("publico", True),
            es_temporal=p.get("es_temporal", False),
            dias_expiracion=p.get("dias_expiracion"),
        )
        db.session.add(plan)
        created += 1
        click.echo(f"  CREATED {p['nombre']}")

    db.session.commit()
    click.echo(f"\n{created} planes creados.")
