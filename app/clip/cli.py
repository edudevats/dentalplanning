import click
from flask.cli import AppGroup
from flask import current_app
from app.extensions import db
from app.superadmin.models import (
    Plan, Subscription,
    SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA, SUBSCRIPTION_VENCIDA,
)
from app.superadmin.models import ADDON_TIPO_RECEPCIONISTA
from app.clip.service import (
    create_price, get_price, cancel_subscription, ClipAPIError,
)
from app.clip.billing import calculate_variable_breakdown, create_variable_charge
from app.facturacion.timezone_helper import get_today

billing_cli = AppGroup("billing", help="Comandos de facturacion Clip")


DEFAULT_PLANS = [
    {
        "nombre": "Prueba Gratis",
        "precio_mensual": 0,
        "descripcion": "Prueba gratuita de 8 dias con acceso al sistema contable",
        "modulos": ["contable"],
        "es_temporal": True,
        "dias_expiracion": 8,
        "publico": True,
    },
    {
        "nombre": "Basico",
        "precio_mensual": 499.0,
        "descripcion": "Sistema contable: tratamientos, precios, dashboard y reportes",
        "modulos": ["contable"],
    },
    {
        "nombre": "Pro",
        "precio_mensual": 899.0,
        "descripcion": "Contable + Inventario: stock, almacen y operatorios",
        "modulos": ["contable", "inventario"],
    },
    {
        "nombre": "Premium",
        "precio_mensual": 1299.0,
        "descripcion": "Todos los modulos: contable, inventario y finanzas personales",
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
@click.option("--dry-run", is_flag=True, help="Solo muestra que haria, sin ejecutar")
def billing_cycle(dry_run):
    """Cierra mensualidades variables, expira trials y termina la gracia."""
    today = get_today()

    trial_expired = Subscription.query.filter(
        Subscription.estado.in_([SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA]),
        Subscription.proximo_cobro <= today,
    ).join(Plan).filter(Plan.es_temporal.is_(True)).all()

    due_subscriptions = (
        Subscription.query.join(Plan)
        .filter(
            Subscription.estado.in_([SUBSCRIPTION_ACTIVA, SUBSCRIPTION_GRACIA]),
            Subscription.proximo_cobro <= today,
            Plan.es_temporal.is_(False),
            Plan.precio_mensual > 0,
            Plan.addon_tipo.is_(None),
        )
        .all()
    )

    click.echo(f"Trial vencido:   {len(trial_expired)}")
    click.echo(f"Cortes variables: {len(due_subscriptions)}")

    suspended = 0
    charges = 0
    errors = 0

    for sub in trial_expired:
        tenant_name = sub.tenant.name if sub.tenant else f"tenant#{sub.tenant_id}"
        click.echo(f"  EXPIRE trial {tenant_name}: '{sub.plan.nombre}' vencido")
        if not dry_run:
            sub.estado = SUBSCRIPTION_VENCIDA
            if sub.tenant:
                sub.tenant.is_active = False
            db.session.commit()
        suspended += 1

    for sub in due_subscriptions:
        tenant_name = sub.tenant.name if sub.tenant else f"tenant#{sub.tenant_id}"
        try:
            if dry_run:
                detail = calculate_variable_breakdown(sub, sub.proximo_cobro)
                click.echo(
                    f"  CHARGE {tenant_name}: ${detail['total']:.2f} "
                    f"(plan ${detail['plan_amount']:.2f} + facturacion "
                    f"${detail['invoice_base_fee']:.2f} + "
                    f"{detail['stamp_count']} timbres)"
                )
                charges += 1
                continue
            payment, created = create_variable_charge(
                sub, cycle_date=sub.proximo_cobro, today=today
            )
            db.session.commit()
            if created:
                click.echo(
                    f"  CHARGE {tenant_name}: ${payment.monto:.2f}, "
                    f"vence {payment.due_date}"
                )
                charges += 1
            else:
                click.echo(f"  SKIP {tenant_name}: corte ya generado")
        except Exception as exc:  # continuar con los demas tenants
            db.session.rollback()
            errors += 1
            click.echo(f"  ERROR {tenant_name}: {exc}")

    grace_expired = Subscription.query.filter(
        Subscription.estado == SUBSCRIPTION_GRACIA,
        Subscription.grace_expires_at < today,
    ).all()
    click.echo(f"Gracia expirada: {len(grace_expired)}")

    for sub in grace_expired:
        tenant_name = sub.tenant.name if sub.tenant else f"tenant#{sub.tenant_id}"
        click.echo(f"  SUSPEND {tenant_name}: gracia expirada {sub.grace_expires_at}")
        if not dry_run:
            sub.estado = SUBSCRIPTION_VENCIDA
            sub.grace_expires_at = None
            if sub.tenant:
                sub.tenant.is_active = False
            db.session.commit()
        suspended += 1

    click.echo(
        f"\nResultado: {charges} cobros, {suspended} suspendidos, {errors} errores"
    )


@billing_cli.command("sync-prices")
@click.option("--dry-run", is_flag=True, help="Solo muestra que haria, sin ejecutar")
def sync_prices(dry_run):
    """Sincroniza precios recurrentes solo para addons heredados.

    Los planes principales usan checkout normal de monto variable y ya no deben
    crear precios recurrentes en Clip.
    """
    # `or` (no el default de .get): la clave puede existir con valor None.
    base_url = (current_app.config.get("APP_BASE_URL") or "http://localhost:5000").rstrip("/")
    webhook_url = f"{base_url}/api/v1/clip/webhook"
    success_url = f"{base_url}/registro-exitoso"
    error_url = f"{base_url}/registro-error"
    default_url = f"{base_url}/registro-exitoso"

    plans = Plan.query.filter(
        Plan.activo.is_(True),
        Plan.es_temporal.is_(False),
        Plan.precio_mensual > 0,
        Plan.addon_tipo.isnot(None),
    ).all()

    created = synced = skipped = errors = 0

    for plan in plans:
        if plan.clip_price_id:
            try:
                existing = get_price(plan.clip_price_id)
            except ClipAPIError as e:
                click.echo(f"  ERROR verifying {plan.nombre}: {e}")
                errors += 1
                continue
            if existing:
                link = (existing.get("recurring") or {}).get("subscription_link")
                if link and plan.clip_subscription_link != link:
                    if not dry_run:
                        plan.clip_subscription_link = link
                        db.session.commit()
                    synced += 1
                    click.echo(f"  SYNCED {plan.nombre}: link refreshed")
                else:
                    skipped += 1
                    click.echo(f"  SKIP {plan.nombre}: ya tiene clip_price_id={plan.clip_price_id}")
                continue
            click.echo(f"  REBUILD {plan.nombre}: clip_price_id estaba pero no existe en Clip")

        click.echo(f"  CREATE {plan.nombre}: ${plan.precio_mensual:.2f}/mes")
        if dry_run:
            created += 1
            continue
        try:
            result = create_price(
                name=plan.nombre,
                description=plan.descripcion or plan.nombre,
                amount=plan.precio_mensual,
                webhook_url=webhook_url,
                success_url=success_url,
                error_url=error_url,
                default_url=default_url,
                anchor_on_first_payment=True,
                interval="month",
                frequency=1,
                repeat=0,
                grace_period_days=current_app.config.get("BILLING_GRACE_DAYS", 3),
            )
        except ClipAPIError as e:
            click.echo(f"    Clip error: {e}")
            errors += 1
            continue

        plan.clip_price_id = result.get("id", "")
        plan.clip_subscription_link = (result.get("recurring") or {}).get("subscription_link", "")
        db.session.commit()
        created += 1
        click.echo(f"    -> price_id={plan.clip_price_id} link={plan.clip_subscription_link}")

    click.echo(f"\nResultado: {created} creados, {synced} sincronizados, "
               f"{skipped} sin cambios, {errors} errores")


@billing_cli.command("disable-main-recurring")
@click.option(
    "--apply", "apply_changes", is_flag=True,
    help="Cancela realmente las suscripciones principales en Clip.",
)
def disable_main_recurring(apply_changes):
    """Migra suscripciones principales heredadas al cobro variable.

    Sin ``--apply`` solo muestra las suscripciones que se cancelarían. Los
    addons de recepcionista se conservan sin cambios.
    """
    subscriptions = (
        Subscription.query.join(Plan)
        .filter(
            Subscription.clip_subscription_id.isnot(None),
            Subscription.clip_subscription_id != "",
            Plan.addon_tipo.is_(None),
        )
        .all()
    )
    click.echo(f"Suscripciones principales recurrentes: {len(subscriptions)}")
    errors = 0
    for sub in subscriptions:
        tenant_name = sub.tenant.name if sub.tenant else f"tenant#{sub.tenant_id}"
        click.echo(f"  {tenant_name}: {sub.clip_subscription_id}")
        if not apply_changes:
            continue
        try:
            cancel_subscription(sub.clip_subscription_id)
            sub.clip_subscription_id = None
            db.session.commit()
        except ClipAPIError as exc:
            db.session.rollback()
            errors += 1
            click.echo(f"    ERROR: {exc}")

    if apply_changes:
        if errors == 0:
            Plan.query.filter(Plan.addon_tipo.is_(None)).update(
                {Plan.clip_price_id: None, Plan.clip_subscription_link: None},
                synchronize_session=False,
            )
            db.session.commit()
        click.echo(f"Resultado: {len(subscriptions) - errors} canceladas, {errors} errores")
    else:
        click.echo("Vista previa; vuelve a ejecutar con --apply para cancelar.")


@billing_cli.command("seed-addon")
@click.option("--precio", default=199.0, type=float, help="Precio mensual del recepcionista adicional")
def seed_addon(precio):
    """Crea el Plan oculto 'Recepcionista adicional' si no existe."""
    existing = Plan.query.filter_by(addon_tipo=ADDON_TIPO_RECEPCIONISTA).first()
    if existing:
        click.echo(f"  EXISTS Recepcionista adicional (id={existing.id})")
        return
    plan = Plan(
        nombre="Recepcionista adicional",
        precio_mensual=precio,
        descripcion="Asiento adicional de recepcionista (cobro recurrente mensual)",
        modulos=[],
        activo=True,
        publico=False,
        es_temporal=False,
        addon_tipo=ADDON_TIPO_RECEPCIONISTA,
    )
    db.session.add(plan)
    db.session.commit()
    click.echo(f"  CREATED Recepcionista adicional id={plan.id} precio={precio}. "
               f"Corre `flask billing sync-prices` para sincronizar con Clip.")


@billing_cli.command("seed-plans")
def seed_plans():
    """Crea los planes por defecto si no existen."""
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
