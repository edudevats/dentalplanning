# Finanzas Personales Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-user "Finanzas Personales" module (income/expenses tracker, NOT a clinic ledger) accessible from the system selector and the main sidebar, using the existing React UI prototype in `finanzas/personal_finance/` wired to a new Flask backend.

**Architecture:** New Flask blueprint `app/finanzas_personales/` follows the existing module pattern (models / schemas / routes / services). Data is scoped by `(tenant_id, user_id)` because each user owns separate personal finances even within the same clinic. The existing React UI prototype (babel-standalone, jsx files) is moved into `app/static/js/finanzas_personales/` and served via Jinja shells; its mock `data.jsx` is replaced with `api.jsx` that calls `/api/v1/finanzas-personales/*`.

**Tech Stack:** Flask 2.x + SQLAlchemy + Marshmallow + Flask-Migrate (backend), React 18 via `@babel/standalone` (frontend, matches prototype), Lucide icons, hand-rolled SVG charts (no Chart.js). Tests in pytest.

---

## File Structure

**New backend:**
- `app/finanzas_personales/__init__.py` — package marker
- `app/finanzas_personales/models.py` — `CategoriaPersonal`, `FuenteIngreso`, `IngresoPersonal`, `GastoPersonal`, `PresupuestoCategoria`, `MetaAhorro`
- `app/finanzas_personales/schemas.py` — Marshmallow schemas for all models + DashboardSummarySchema
- `app/finanzas_personales/services.py` — `seed_defaults_for_user`, `build_dashboard_summary`, `build_category_detail`, `list_movements`, insight generator
- `app/finanzas_personales/routes.py` — blueprint `finanzas_personales_bp` at `/api/v1/finanzas-personales`

**New migration:**
- `migrations/versions/<hash>_add_finanzas_personales.py`

**New static (React prototype, moved from `finanzas/personal_finance/`):**
- `app/static/js/finanzas_personales/Atoms.jsx`
- `app/static/js/finanzas_personales/Charts.jsx`
- `app/static/js/finanzas_personales/Shell.jsx`
- `app/static/js/finanzas_personales/AddMovementModal.jsx`
- `app/static/js/finanzas_personales/Dashboard.jsx`
- `app/static/js/finanzas_personales/screens.jsx`
- `app/static/js/finanzas_personales/Budgets.jsx`
- `app/static/js/finanzas_personales/api.jsx` — replaces `data.jsx`, uses real fetch
- `app/static/js/finanzas_personales/main.jsx` — single entry point, picks screen by `window.FP_SCREEN`

**New templates:**
- `app/templates/finanzas_personales/_shell.html` — common shell that loads jsx and React deps
- `app/templates/finanzas_personales/dashboard.html`
- `app/templates/finanzas_personales/category.html`
- `app/templates/finanzas_personales/history.html`
- `app/templates/finanzas_personales/metas.html`
- `app/templates/finanzas_personales/presupuestos.html`

**Modified:**
- `app/__init__.py` — register blueprint + import models
- `app/frontend/routes.py` — add `/finanzas-personales/*` routes
- `app/templates/partials/sidebar_content.html` — new "FINANZAS PERSONALES" section
- `app/templates/selector.html` — add 3rd card "Finanzas Personales"

**New tests:**
- `tests/test_finanzas_personales_models.py`
- `tests/test_finanzas_personales_services.py`
- `tests/test_finanzas_personales_routes.py`
- `tests/test_finanzas_personales_isolation.py`

---

## Data model summary

All tables scoped by `(tenant_id, user_id)`. Defaults are seeded per-user the first time the dashboard endpoint is hit. Categorías and fuentes are user-owned (each user can rename / re-color).

```
categorias_personales        (id, tenant_id, user_id, nombre, icon, color, orden, activo)
fuentes_ingreso              (id, tenant_id, user_id, nombre, icon, orden, activo)
ingresos_personales          (id, tenant_id, user_id, fecha, fuente_id, concepto, monto, comentarios, created_at)
gastos_personales            (id, tenant_id, user_id, fecha, categoria_id, concepto, monto, comentarios, created_at)
presupuestos_categoria       (id, tenant_id, user_id, categoria_id, monto_mensual, vigente_desde)  unique(user_id, categoria_id, vigente_desde)
metas_ahorro                 (id, tenant_id, user_id, label, icon, color, monto_objetivo, monto_actual, fecha_objetivo, created_at)
```

`monto` columns are `db.Numeric(12, 2)` to avoid float drift. All FK to `users.id` and `tenants.id` set `ondelete="CASCADE"`.

---

## Task 1: Create finanzas_personales package skeleton

**Files:**
- Create: `app/finanzas_personales/__init__.py`

- [ ] **Step 1: Create the package marker**

```python
# app/finanzas_personales/__init__.py
"""Finanzas Personales — per-user personal income/expense tracker.

Scoped by (tenant_id, user_id). Independent from the clinic EDR module.
"""
```

- [ ] **Step 2: Commit**

```bash
git add app/finanzas_personales/__init__.py
git commit -m "feat(finanzas-personales): create module skeleton"
```

---

## Task 2: Create SQLAlchemy models

**Files:**
- Create: `app/finanzas_personales/models.py`

- [ ] **Step 1: Write the file**

```python
# app/finanzas_personales/models.py
from datetime import datetime, timezone
from app.extensions import db


class CategoriaPersonal(db.Model):
    __tablename__ = "categorias_personales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="circle")
    color = db.Column(db.String(9), nullable=False, default="#0891b2")
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "nombre", name="uq_categoria_personal_user_nombre"),
        db.Index("ix_categoria_personal_user", "tenant_id", "user_id"),
    )


class FuenteIngreso(db.Model):
    __tablename__ = "fuentes_ingreso"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="briefcase")
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "nombre", name="uq_fuente_ingreso_user_nombre"),
        db.Index("ix_fuente_ingreso_user", "tenant_id", "user_id"),
    )


class IngresoPersonal(db.Model):
    __tablename__ = "ingresos_personales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    fuente_id = db.Column(db.Integer, db.ForeignKey("fuentes_ingreso.id", ondelete="SET NULL"), nullable=True)
    concepto = db.Column(db.String(200), nullable=False, default="")
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    comentarios = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    fuente = db.relationship("FuenteIngreso")

    __table_args__ = (
        db.Index("ix_ingreso_personal_user_fecha", "tenant_id", "user_id", "fecha"),
    )


class GastoPersonal(db.Model):
    __tablename__ = "gastos_personales"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fecha = db.Column(db.Date, nullable=False, index=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias_personales.id", ondelete="SET NULL"), nullable=True)
    concepto = db.Column(db.String(200), nullable=False, default="")
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    comentarios = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    categoria = db.relationship("CategoriaPersonal")

    __table_args__ = (
        db.Index("ix_gasto_personal_user_fecha", "tenant_id", "user_id", "fecha"),
    )


class PresupuestoCategoria(db.Model):
    __tablename__ = "presupuestos_categoria"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias_personales.id", ondelete="CASCADE"), nullable=False)
    monto_mensual = db.Column(db.Numeric(12, 2), nullable=False)
    vigente_desde = db.Column(db.Date, nullable=False)

    categoria = db.relationship("CategoriaPersonal")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "categoria_id", "vigente_desde", name="uq_presupuesto_user_cat_fecha"),
        db.Index("ix_presupuesto_user", "tenant_id", "user_id"),
    )


class MetaAhorro(db.Model):
    __tablename__ = "metas_ahorro"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    icon = db.Column(db.String(40), nullable=False, default="target")
    color = db.Column(db.String(9), nullable=False, default="#059669")
    monto_objetivo = db.Column(db.Numeric(12, 2), nullable=False)
    monto_actual = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    fecha_objetivo = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.Index("ix_meta_ahorro_user", "tenant_id", "user_id"),
    )
```

- [ ] **Step 2: Register the module in `app/__init__.py`**

In `app/__init__.py`, in the `with app.app_context():` block (around line 48-56), add the import after `inventario_models`:

```python
    with app.app_context():
        from app.auth import models as auth_models  # noqa: F401
        from app.catalogo import models as catalogo_models  # noqa: F401
        from app.configuracion import models as config_models  # noqa: F401
        from app.tratamientos import models as tx_models  # noqa: F401
        from app.edr import models as edr_models  # noqa: F401
        from app.ajustes import models as ajustes_models  # noqa: F401
        from app.inventario import models as inventario_models  # noqa: F401
        from app.finanzas_personales import models as fp_models  # noqa: F401
        from app.superadmin import models as superadmin_models  # noqa: F401
```

- [ ] **Step 3: Generate the migration**

Run: `flask db migrate -m "add finanzas personales tables"`
Expected: a new file under `migrations/versions/` containing `op.create_table` calls for the 6 new tables.

- [ ] **Step 4: Inspect the migration file**

Open the generated file. Verify:
- All 6 tables present
- `tenant_id` and `user_id` are NOT NULL
- The unique constraints are present
- No accidental drops of existing tables (autogenerate sometimes reorders columns)

If you see spurious `op.alter_column` lines for unrelated tables (Alembic noise), delete them.

- [ ] **Step 5: Apply the migration**

Run: `flask db upgrade`
Expected: "INFO  [alembic.runtime.migration] Running upgrade ..." and tables created.

Verify with sqlite:
```bash
python -c "from app import create_app; from app.extensions import db; app=create_app(); ctx=app.app_context(); ctx.push(); from sqlalchemy import inspect; print(sorted(inspect(db.engine).get_table_names()))"
```
Expected: list includes `categorias_personales`, `fuentes_ingreso`, `ingresos_personales`, `gastos_personales`, `presupuestos_categoria`, `metas_ahorro`.

- [ ] **Step 6: Commit**

```bash
git add app/finanzas_personales/models.py app/__init__.py migrations/versions/
git commit -m "feat(finanzas-personales): add models and migration"
```

---

## Task 3: Marshmallow schemas

**Files:**
- Create: `app/finanzas_personales/schemas.py`

- [ ] **Step 1: Write the schemas file**

```python
# app/finanzas_personales/schemas.py
from marshmallow import Schema, fields, validate


class CategoriaPersonalSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    icon = fields.Str(load_default="circle", validate=validate.Length(max=40))
    color = fields.Str(load_default="#0891b2", validate=validate.Length(min=4, max=9))
    orden = fields.Int(load_default=0)
    activo = fields.Bool(load_default=True)


class FuenteIngresoSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    icon = fields.Str(load_default="briefcase", validate=validate.Length(max=40))
    orden = fields.Int(load_default=0)
    activo = fields.Bool(load_default=True)


class IngresoPersonalSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    fuente_id = fields.Int(allow_none=True, load_default=None)
    concepto = fields.Str(load_default="", validate=validate.Length(max=200))
    monto = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    comentarios = fields.Str(allow_none=True)


class GastoPersonalSchema(Schema):
    id = fields.Int(dump_only=True)
    fecha = fields.Date(required=True)
    categoria_id = fields.Int(allow_none=True, load_default=None)
    concepto = fields.Str(load_default="", validate=validate.Length(max=200))
    monto = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    comentarios = fields.Str(allow_none=True)


class PresupuestoCategoriaSchema(Schema):
    id = fields.Int(dump_only=True)
    categoria_id = fields.Int(required=True)
    monto_mensual = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    vigente_desde = fields.Date(required=True)


class MetaAhorroSchema(Schema):
    id = fields.Int(dump_only=True)
    label = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    icon = fields.Str(load_default="target", validate=validate.Length(max=40))
    color = fields.Str(load_default="#059669", validate=validate.Length(min=4, max=9))
    monto_objetivo = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    monto_actual = fields.Decimal(load_default=0, as_string=True, places=2, validate=validate.Range(min=0))
    fecha_objetivo = fields.Date(allow_none=True, load_default=None)


class DashboardQuerySchema(Schema):
    """Query string for /dashboard?year=2026&month=4"""
    year = fields.Int(required=True, validate=validate.Range(min=2000, max=2100))
    month = fields.Int(required=True, validate=validate.Range(min=1, max=12))
```

- [ ] **Step 2: Commit**

```bash
git add app/finanzas_personales/schemas.py
git commit -m "feat(finanzas-personales): add marshmallow schemas"
```

---

## Task 4: Default seeder + dashboard summary service

**Files:**
- Create: `app/finanzas_personales/services.py`

The dashboard summary returns the exact shape the React UI expects (KPIs, byCat, history6m, recent, insight).

- [ ] **Step 1: Write the services file**

```python
# app/finanzas_personales/services.py
from __future__ import annotations
from calendar import monthrange
from datetime import date
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso,
    IngresoPersonal, GastoPersonal,
    PresupuestoCategoria,
)


DEFAULT_CATEGORIES = [
    {"nombre": "Comida",          "icon": "utensils",        "color": "#f59e0b", "orden": 1},
    {"nombre": "Transporte",      "icon": "car",             "color": "#0891b2", "orden": 2},
    {"nombre": "Vivienda",        "icon": "home",            "color": "#8b5cf6", "orden": 3},
    {"nombre": "Entretenimiento", "icon": "film",            "color": "#ec4899", "orden": 4},
    {"nombre": "Salud",           "icon": "heart-pulse",     "color": "#059669", "orden": 5},
    {"nombre": "Otros",           "icon": "more-horizontal", "color": "#f97316", "orden": 6},
]

DEFAULT_FUENTES = [
    {"nombre": "Salario",   "icon": "briefcase", "orden": 1},
    {"nombre": "Extras",    "icon": "sparkles",  "orden": 2},
    {"nombre": "Freelance", "icon": "laptop",    "orden": 3},
]


def seed_defaults_for_user(tenant_id: int, user_id: int) -> None:
    """Idempotent — only inserts categories/fuentes if user has none."""
    has_cats = db.session.query(CategoriaPersonal.id).filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not has_cats:
        for c in DEFAULT_CATEGORIES:
            db.session.add(CategoriaPersonal(tenant_id=tenant_id, user_id=user_id, **c))

    has_fuentes = db.session.query(FuenteIngreso.id).filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not has_fuentes:
        for f in DEFAULT_FUENTES:
            db.session.add(FuenteIngreso(tenant_id=tenant_id, user_id=user_id, **f))

    db.session.commit()


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start, end


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _money(x) -> float:
    if x is None:
        return 0.0
    return float(x)


def build_dashboard_summary(tenant_id: int, user_id: int, year: int, month: int) -> dict:
    """
    Returns a dict shaped exactly for the React dashboard:
      {
        "month": {"year": 2026, "month": 4},
        "totals": {"ingresos": float, "gastos": float, "balance": float, "ahorroPct": int},
        "trends": {"ingresos": int_pct, "gastos": int_pct},
        "byCat": [{"id","label","icon","color","value","pct"}],
        "history6m": [{"name","ingresos","gastos"}, ... 6 items],
        "recent": [{"id","kind","fecha","concepto","monto","label","icon","color"}, ... up to 6],
        "insight": str
      }
    """
    start, end = _month_bounds(year, month)

    ingresos_total = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= start, IngresoPersonal.fecha <= end,
    ).scalar())
    gastos_total = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
    ).scalar())

    balance = ingresos_total - gastos_total
    ahorro_pct = round((balance / ingresos_total) * 100) if ingresos_total else 0

    py, pm = _prev_month(year, month)
    pstart, pend = _month_bounds(py, pm)
    prev_ing = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= pstart, IngresoPersonal.fecha <= pend,
    ).scalar())
    prev_gas = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= pstart, GastoPersonal.fecha <= pend,
    ).scalar())
    trend_ing = round(((ingresos_total - prev_ing) / prev_ing) * 100) if prev_ing else 0
    trend_gas = round(((gastos_total - prev_gas) / prev_gas) * 100) if prev_gas else 0

    cat_rows = db.session.query(
        CategoriaPersonal.id, CategoriaPersonal.nombre, CategoriaPersonal.icon,
        CategoriaPersonal.color, func.coalesce(func.sum(GastoPersonal.monto), 0),
    ).outerjoin(
        GastoPersonal,
        (GastoPersonal.categoria_id == CategoriaPersonal.id)
        & (GastoPersonal.fecha >= start) & (GastoPersonal.fecha <= end)
        & (GastoPersonal.tenant_id == tenant_id) & (GastoPersonal.user_id == user_id),
    ).filter(
        CategoriaPersonal.tenant_id == tenant_id,
        CategoriaPersonal.user_id == user_id,
        CategoriaPersonal.activo.is_(True),
    ).group_by(CategoriaPersonal.id).all()

    by_cat = []
    for cid, nombre, icon, color, suma in cat_rows:
        v = _money(suma)
        if v <= 0:
            continue
        by_cat.append({
            "id": cid, "label": nombre, "icon": icon, "color": color,
            "value": v,
            "pct": round((v / gastos_total) * 100) if gastos_total else 0,
        })
    by_cat.sort(key=lambda c: c["value"], reverse=True)

    months_back = []
    yy, mm = year, month
    for _ in range(6):
        months_back.append((yy, mm))
        yy, mm = _prev_month(yy, mm)
    months_back.reverse()
    month_names_es = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    history6m = []
    for yy, mm in months_back:
        ms, me = _month_bounds(yy, mm)
        i = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
            IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
            IngresoPersonal.fecha >= ms, IngresoPersonal.fecha <= me,
        ).scalar())
        g = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
            GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
            GastoPersonal.fecha >= ms, GastoPersonal.fecha <= me,
        ).scalar())
        history6m.append({"name": month_names_es[mm - 1], "ingresos": i, "gastos": g})

    recent = []
    ing_q = db.session.query(IngresoPersonal, FuenteIngreso).outerjoin(
        FuenteIngreso, IngresoPersonal.fuente_id == FuenteIngreso.id,
    ).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= start, IngresoPersonal.fecha <= end,
    ).order_by(IngresoPersonal.fecha.desc(), IngresoPersonal.id.desc()).limit(6).all()
    for ing, fuente in ing_q:
        recent.append({
            "id": f"i{ing.id}", "kind": "ingreso",
            "fecha": ing.fecha.isoformat(), "concepto": ing.concepto,
            "monto": _money(ing.monto),
            "label": fuente.nombre if fuente else "Ingreso",
            "icon": fuente.icon if fuente else "trending-up",
            "color": "#059669",
        })
    gas_q = db.session.query(GastoPersonal, CategoriaPersonal).outerjoin(
        CategoriaPersonal, GastoPersonal.categoria_id == CategoriaPersonal.id,
    ).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
    ).order_by(GastoPersonal.fecha.desc(), GastoPersonal.id.desc()).limit(6).all()
    for gas, cat in gas_q:
        recent.append({
            "id": f"g{gas.id}", "kind": "gasto",
            "fecha": gas.fecha.isoformat(), "concepto": gas.concepto,
            "monto": _money(gas.monto),
            "label": cat.nombre if cat else "Gasto",
            "icon": cat.icon if cat else "circle",
            "color": cat.color if cat else "#94a3b8",
        })
    recent.sort(key=lambda m: m["fecha"], reverse=True)
    recent = recent[:6]

    insight = _build_insight(balance=balance, ahorro_pct=ahorro_pct, by_cat=by_cat, prev_gas=prev_gas)

    return {
        "month": {"year": year, "month": month},
        "totals": {
            "ingresos": ingresos_total, "gastos": gastos_total,
            "balance": balance, "ahorroPct": ahorro_pct,
        },
        "trends": {"ingresos": trend_ing, "gastos": trend_gas},
        "byCat": by_cat,
        "history6m": history6m,
        "recent": recent,
        "insight": insight,
    }


def _build_insight(balance: float, ahorro_pct: int, by_cat: list, prev_gas: float) -> str:
    if balance <= 0:
        return "Estás gastando más de lo que ingresas. Revisa tus categorías más altas."
    top = by_cat[0] if by_cat else None
    if top and prev_gas > 0:
        return (
            f"Llevas ${balance:,.0f} ahorrados este mes ({ahorro_pct}% de tus ingresos). "
            f"Tu mayor gasto es {top['label']} (${top['value']:,.0f})."
        )
    return f"Llevas ${balance:,.0f} ahorrados este mes ({ahorro_pct}% de tus ingresos). Sigue así."


def list_movements(tenant_id: int, user_id: int, year: int, month: int,
                   kind: Optional[str] = None) -> list:
    """For the History screen. kind in (None, 'ingreso', 'gasto')."""
    start, end = _month_bounds(year, month)
    out = []
    if kind != "gasto":
        rows = db.session.query(IngresoPersonal, FuenteIngreso).outerjoin(
            FuenteIngreso, IngresoPersonal.fuente_id == FuenteIngreso.id,
        ).filter(
            IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
            IngresoPersonal.fecha >= start, IngresoPersonal.fecha <= end,
        ).all()
        for ing, fuente in rows:
            out.append({
                "id": f"i{ing.id}", "kind": "ingreso",
                "fecha": ing.fecha.isoformat(), "concepto": ing.concepto,
                "monto": _money(ing.monto),
                "label": fuente.nombre if fuente else "Ingreso",
                "icon": fuente.icon if fuente else "trending-up",
                "color": "#059669",
            })
    if kind != "ingreso":
        rows = db.session.query(GastoPersonal, CategoriaPersonal).outerjoin(
            CategoriaPersonal, GastoPersonal.categoria_id == CategoriaPersonal.id,
        ).filter(
            GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
            GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
        ).all()
        for gas, cat in rows:
            out.append({
                "id": f"g{gas.id}", "kind": "gasto",
                "fecha": gas.fecha.isoformat(), "concepto": gas.concepto,
                "monto": _money(gas.monto),
                "label": cat.nombre if cat else "Gasto",
                "icon": cat.icon if cat else "circle",
                "color": cat.color if cat else "#94a3b8",
            })
    out.sort(key=lambda m: m["fecha"], reverse=True)
    return out


def build_category_detail(tenant_id: int, user_id: int, categoria_id: int,
                          year: int, month: int) -> dict:
    """Detail screen: monthly total, daily avg, max, 6m series, all movements, budget."""
    cat = CategoriaPersonal.query.filter_by(
        id=categoria_id, tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not cat:
        return {}

    start, end = _month_bounds(year, month)
    movs_q = GastoPersonal.query.filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.categoria_id == categoria_id,
        GastoPersonal.fecha >= start, GastoPersonal.fecha <= end,
    ).order_by(GastoPersonal.fecha.desc()).all()

    movs = [{
        "id": f"g{m.id}", "kind": "gasto",
        "fecha": m.fecha.isoformat(), "concepto": m.concepto,
        "monto": _money(m.monto),
        "label": cat.nombre, "icon": cat.icon, "color": cat.color,
    } for m in movs_q]

    total = sum(m["monto"] for m in movs)
    days = (end - start).days + 1
    daily_avg = total / days if days else 0
    max_mov = max(movs, key=lambda m: m["monto"]) if movs else None

    months_back = []
    yy, mm = year, month
    for _ in range(6):
        months_back.append((yy, mm))
        yy, mm = _prev_month(yy, mm)
    months_back.reverse()
    month_names_es = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    history6m = []
    for yy, mm in months_back:
        ms, me = _month_bounds(yy, mm)
        s = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
            GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
            GastoPersonal.categoria_id == categoria_id,
            GastoPersonal.fecha >= ms, GastoPersonal.fecha <= me,
        ).scalar())
        history6m.append({"name": month_names_es[mm - 1], "ingresos": 0, "gastos": s})

    pres = PresupuestoCategoria.query.filter(
        PresupuestoCategoria.tenant_id == tenant_id,
        PresupuestoCategoria.user_id == user_id,
        PresupuestoCategoria.categoria_id == categoria_id,
        PresupuestoCategoria.vigente_desde <= end,
    ).order_by(PresupuestoCategoria.vigente_desde.desc()).first()

    return {
        "categoria": {"id": cat.id, "label": cat.nombre, "icon": cat.icon, "color": cat.color},
        "month": {"year": year, "month": month},
        "total": total,
        "promedioDiario": daily_avg,
        "max": max_mov,
        "movimientos": movs,
        "history6m": history6m,
        "presupuesto": _money(pres.monto_mensual) if pres else None,
    }
```

- [ ] **Step 2: Commit**

```bash
git add app/finanzas_personales/services.py
git commit -m "feat(finanzas-personales): add seeder + dashboard/category services"
```

---

## Task 5: Routes (CRUD + dashboard)

**Files:**
- Create: `app/finanzas_personales/routes.py`

The blueprint exposes:
- `GET/POST /api/v1/finanzas-personales/categorias` (auto-seeds defaults)
- `PUT/DELETE /api/v1/finanzas-personales/categorias/<id>`
- `GET/POST/PUT/DELETE` mirror for `/fuentes`
- `GET/POST/PUT/DELETE /ingresos`, `/gastos`
- `GET /dashboard?year=&month=`
- `GET /movimientos?year=&month=&kind=`
- `GET /categorias/<id>/detalle?year=&month=`
- `GET/POST/PUT/DELETE /presupuestos`, `/metas`

- [ ] **Step 1: Write the routes file**

```python
# app/finanzas_personales/routes.py
from flask import Blueprint, request, jsonify, g
from marshmallow import ValidationError

from app.extensions import db
from app.middleware.tenant import require_auth
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso,
    IngresoPersonal, GastoPersonal,
    PresupuestoCategoria, MetaAhorro,
)
from app.finanzas_personales.schemas import (
    CategoriaPersonalSchema, FuenteIngresoSchema,
    IngresoPersonalSchema, GastoPersonalSchema,
    PresupuestoCategoriaSchema, MetaAhorroSchema,
    DashboardQuerySchema,
)
from app.finanzas_personales.services import (
    seed_defaults_for_user, build_dashboard_summary,
    list_movements, build_category_detail, _month_bounds,
)


finanzas_personales_bp = Blueprint(
    "finanzas_personales", __name__, url_prefix="/api/v1/finanzas-personales",
)


def _scope():
    return g.tenant_id, g.current_user.id


# ── Categorías ────────────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/categorias", methods=["GET"])
@require_auth
def listar_categorias():
    tenant_id, user_id = _scope()
    seed_defaults_for_user(tenant_id, user_id)
    cats = CategoriaPersonal.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(CategoriaPersonal.orden, CategoriaPersonal.nombre).all()
    return jsonify(CategoriaPersonalSchema(many=True).dump(cats))


@finanzas_personales_bp.route("/categorias", methods=["POST"])
@require_auth
def crear_categoria():
    tenant_id, user_id = _scope()
    try:
        data = CategoriaPersonalSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    cat = CategoriaPersonal(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(cat)
    db.session.commit()
    return jsonify(CategoriaPersonalSchema().dump(cat)), 201


@finanzas_personales_bp.route("/categorias/<int:cat_id>", methods=["PUT"])
@require_auth
def actualizar_categoria(cat_id):
    tenant_id, user_id = _scope()
    cat = CategoriaPersonal.query.filter_by(
        id=cat_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = CategoriaPersonalSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(cat, k, v)
    db.session.commit()
    return jsonify(CategoriaPersonalSchema().dump(cat))


@finanzas_personales_bp.route("/categorias/<int:cat_id>", methods=["DELETE"])
@require_auth
def eliminar_categoria(cat_id):
    tenant_id, user_id = _scope()
    cat = CategoriaPersonal.query.filter_by(
        id=cat_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    cat.activo = False  # soft delete preserves history
    db.session.commit()
    return jsonify({"message": "Categoría desactivada"})


# ── Fuentes de ingreso ────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/fuentes", methods=["GET"])
@require_auth
def listar_fuentes():
    tenant_id, user_id = _scope()
    seed_defaults_for_user(tenant_id, user_id)
    fuentes = FuenteIngreso.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(FuenteIngreso.orden, FuenteIngreso.nombre).all()
    return jsonify(FuenteIngresoSchema(many=True).dump(fuentes))


@finanzas_personales_bp.route("/fuentes", methods=["POST"])
@require_auth
def crear_fuente():
    tenant_id, user_id = _scope()
    try:
        data = FuenteIngresoSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    f = FuenteIngreso(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(f)
    db.session.commit()
    return jsonify(FuenteIngresoSchema().dump(f)), 201


@finanzas_personales_bp.route("/fuentes/<int:f_id>", methods=["PUT"])
@require_auth
def actualizar_fuente(f_id):
    tenant_id, user_id = _scope()
    f = FuenteIngreso.query.filter_by(
        id=f_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = FuenteIngresoSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(f, k, v)
    db.session.commit()
    return jsonify(FuenteIngresoSchema().dump(f))


@finanzas_personales_bp.route("/fuentes/<int:f_id>", methods=["DELETE"])
@require_auth
def eliminar_fuente(f_id):
    tenant_id, user_id = _scope()
    f = FuenteIngreso.query.filter_by(
        id=f_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    f.activo = False
    db.session.commit()
    return jsonify({"message": "Fuente desactivada"})


# ── Ingresos / Gastos ─────────────────────────────────────────────────────────

def _parse_year_month():
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
        if not (1 <= month <= 12):
            raise ValueError
        return year, month
    except (TypeError, ValueError):
        return None, None


@finanzas_personales_bp.route("/ingresos", methods=["GET"])
@require_auth
def listar_ingresos():
    tenant_id, user_id = _scope()
    year, month = _parse_year_month()
    q = IngresoPersonal.query.filter_by(tenant_id=tenant_id, user_id=user_id)
    if year and month:
        s, e = _month_bounds(year, month)
        q = q.filter(IngresoPersonal.fecha >= s, IngresoPersonal.fecha <= e)
    rows = q.order_by(IngresoPersonal.fecha.desc(), IngresoPersonal.id.desc()).all()
    return jsonify(IngresoPersonalSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/ingresos", methods=["POST"])
@require_auth
def crear_ingreso():
    tenant_id, user_id = _scope()
    try:
        data = IngresoPersonalSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    if data.get("fuente_id"):
        owns = FuenteIngreso.query.filter_by(
            id=data["fuente_id"], tenant_id=tenant_id, user_id=user_id,
        ).first()
        if not owns:
            return jsonify({"errors": {"fuente_id": ["Fuente no encontrada"]}}), 400
    ing = IngresoPersonal(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(ing)
    db.session.commit()
    return jsonify(IngresoPersonalSchema().dump(ing)), 201


@finanzas_personales_bp.route("/ingresos/<int:ing_id>", methods=["PUT"])
@require_auth
def actualizar_ingreso(ing_id):
    tenant_id, user_id = _scope()
    ing = IngresoPersonal.query.filter_by(
        id=ing_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = IngresoPersonalSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(ing, k, v)
    db.session.commit()
    return jsonify(IngresoPersonalSchema().dump(ing))


@finanzas_personales_bp.route("/ingresos/<int:ing_id>", methods=["DELETE"])
@require_auth
def eliminar_ingreso(ing_id):
    tenant_id, user_id = _scope()
    ing = IngresoPersonal.query.filter_by(
        id=ing_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(ing)
    db.session.commit()
    return jsonify({"message": "Ingreso eliminado"})


@finanzas_personales_bp.route("/gastos", methods=["GET"])
@require_auth
def listar_gastos():
    tenant_id, user_id = _scope()
    year, month = _parse_year_month()
    q = GastoPersonal.query.filter_by(tenant_id=tenant_id, user_id=user_id)
    if year and month:
        s, e = _month_bounds(year, month)
        q = q.filter(GastoPersonal.fecha >= s, GastoPersonal.fecha <= e)
    rows = q.order_by(GastoPersonal.fecha.desc(), GastoPersonal.id.desc()).all()
    return jsonify(GastoPersonalSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/gastos", methods=["POST"])
@require_auth
def crear_gasto():
    tenant_id, user_id = _scope()
    try:
        data = GastoPersonalSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    if data.get("categoria_id"):
        owns = CategoriaPersonal.query.filter_by(
            id=data["categoria_id"], tenant_id=tenant_id, user_id=user_id,
        ).first()
        if not owns:
            return jsonify({"errors": {"categoria_id": ["Categoría no encontrada"]}}), 400
    gas = GastoPersonal(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(gas)
    db.session.commit()
    return jsonify(GastoPersonalSchema().dump(gas)), 201


@finanzas_personales_bp.route("/gastos/<int:gas_id>", methods=["PUT"])
@require_auth
def actualizar_gasto(gas_id):
    tenant_id, user_id = _scope()
    gas = GastoPersonal.query.filter_by(
        id=gas_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = GastoPersonalSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(gas, k, v)
    db.session.commit()
    return jsonify(GastoPersonalSchema().dump(gas))


@finanzas_personales_bp.route("/gastos/<int:gas_id>", methods=["DELETE"])
@require_auth
def eliminar_gasto(gas_id):
    tenant_id, user_id = _scope()
    gas = GastoPersonal.query.filter_by(
        id=gas_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(gas)
    db.session.commit()
    return jsonify({"message": "Gasto eliminado"})


# ── Dashboard / agregados ─────────────────────────────────────────────────────

@finanzas_personales_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard():
    tenant_id, user_id = _scope()
    try:
        q = DashboardQuerySchema().load(request.args)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    seed_defaults_for_user(tenant_id, user_id)
    return jsonify(build_dashboard_summary(tenant_id, user_id, q["year"], q["month"]))


@finanzas_personales_bp.route("/movimientos", methods=["GET"])
@require_auth
def movimientos():
    tenant_id, user_id = _scope()
    try:
        q = DashboardQuerySchema().load(request.args)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    kind = request.args.get("kind")
    if kind not in (None, "ingreso", "gasto"):
        kind = None
    return jsonify(list_movements(tenant_id, user_id, q["year"], q["month"], kind=kind))


@finanzas_personales_bp.route("/categorias/<int:cat_id>/detalle", methods=["GET"])
@require_auth
def categoria_detalle(cat_id):
    tenant_id, user_id = _scope()
    try:
        q = DashboardQuerySchema().load(request.args)
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    detail = build_category_detail(tenant_id, user_id, cat_id, q["year"], q["month"])
    if not detail:
        return jsonify({"error": "Categoría no encontrada"}), 404
    return jsonify(detail)


# ── Presupuestos ──────────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/presupuestos", methods=["GET"])
@require_auth
def listar_presupuestos():
    tenant_id, user_id = _scope()
    rows = PresupuestoCategoria.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(PresupuestoCategoria.vigente_desde.desc()).all()
    return jsonify(PresupuestoCategoriaSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/presupuestos", methods=["POST"])
@require_auth
def crear_presupuesto():
    tenant_id, user_id = _scope()
    try:
        data = PresupuestoCategoriaSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    owns = CategoriaPersonal.query.filter_by(
        id=data["categoria_id"], tenant_id=tenant_id, user_id=user_id,
    ).first()
    if not owns:
        return jsonify({"errors": {"categoria_id": ["Categoría no encontrada"]}}), 400
    p = PresupuestoCategoria(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(p)
    db.session.commit()
    return jsonify(PresupuestoCategoriaSchema().dump(p)), 201


@finanzas_personales_bp.route("/presupuestos/<int:p_id>", methods=["PUT"])
@require_auth
def actualizar_presupuesto(p_id):
    tenant_id, user_id = _scope()
    p = PresupuestoCategoria.query.filter_by(
        id=p_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = PresupuestoCategoriaSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(p, k, v)
    db.session.commit()
    return jsonify(PresupuestoCategoriaSchema().dump(p))


@finanzas_personales_bp.route("/presupuestos/<int:p_id>", methods=["DELETE"])
@require_auth
def eliminar_presupuesto(p_id):
    tenant_id, user_id = _scope()
    p = PresupuestoCategoria.query.filter_by(
        id=p_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Presupuesto eliminado"})


# ── Metas de ahorro ───────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/metas", methods=["GET"])
@require_auth
def listar_metas():
    tenant_id, user_id = _scope()
    rows = MetaAhorro.query.filter_by(
        tenant_id=tenant_id, user_id=user_id,
    ).order_by(MetaAhorro.created_at.desc()).all()
    return jsonify(MetaAhorroSchema(many=True).dump(rows))


@finanzas_personales_bp.route("/metas", methods=["POST"])
@require_auth
def crear_meta():
    tenant_id, user_id = _scope()
    try:
        data = MetaAhorroSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    m = MetaAhorro(tenant_id=tenant_id, user_id=user_id, **data)
    db.session.add(m)
    db.session.commit()
    return jsonify(MetaAhorroSchema().dump(m)), 201


@finanzas_personales_bp.route("/metas/<int:m_id>", methods=["PUT"])
@require_auth
def actualizar_meta(m_id):
    tenant_id, user_id = _scope()
    m = MetaAhorro.query.filter_by(
        id=m_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    try:
        data = MetaAhorroSchema(partial=True).load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(m, k, v)
    db.session.commit()
    return jsonify(MetaAhorroSchema().dump(m))


@finanzas_personales_bp.route("/metas/<int:m_id>", methods=["DELETE"])
@require_auth
def eliminar_meta(m_id):
    tenant_id, user_id = _scope()
    m = MetaAhorro.query.filter_by(
        id=m_id, tenant_id=tenant_id, user_id=user_id,
    ).first_or_404()
    db.session.delete(m)
    db.session.commit()
    return jsonify({"message": "Meta eliminada"})
```

- [ ] **Step 2: Register the blueprint in `app/__init__.py`**

In `app/__init__.py`, in the imports block (~line 21-30), add:
```python
    from app.finanzas_personales.routes import finanzas_personales_bp
```

In the `app.register_blueprint(...)` block (~line 32-41), add (after `inventario_bp`):
```python
    app.register_blueprint(finanzas_personales_bp)
```

- [ ] **Step 3: Quick smoke test**

Run: `python manage.py shell` then:
```python
from app.finanzas_personales.models import CategoriaPersonal
print(CategoriaPersonal.__tablename__)
```
Expected: `categorias_personales`. Exit shell.

- [ ] **Step 4: Commit**

```bash
git add app/finanzas_personales/routes.py app/__init__.py
git commit -m "feat(finanzas-personales): add REST routes and register blueprint"
```

---

## Task 6: Backend tests — models + isolation

**Files:**
- Create: `tests/test_finanzas_personales_models.py`
- Create: `tests/test_finanzas_personales_isolation.py`

- [ ] **Step 1: Write models test**

```python
# tests/test_finanzas_personales_models.py
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso, IngresoPersonal, GastoPersonal,
)


def test_can_create_and_query_models(app, tenant_and_user):
    tenant, user = tenant_and_user
    with app.app_context():
        cat = CategoriaPersonal(
            tenant_id=tenant.id, user_id=user.id,
            nombre="Comida", icon="utensils", color="#f59e0b", orden=1,
        )
        fuente = FuenteIngreso(
            tenant_id=tenant.id, user_id=user.id,
            nombre="Salario", icon="briefcase", orden=1,
        )
        db.session.add_all([cat, fuente])
        db.session.commit()

        gasto = GastoPersonal(
            tenant_id=tenant.id, user_id=user.id,
            fecha=date(2026, 4, 15), categoria_id=cat.id,
            concepto="Súper", monto=Decimal("123.45"),
        )
        ingreso = IngresoPersonal(
            tenant_id=tenant.id, user_id=user.id,
            fecha=date(2026, 4, 1), fuente_id=fuente.id,
            concepto="Salario abril", monto=Decimal("22000.00"),
        )
        db.session.add_all([gasto, ingreso])
        db.session.commit()

        assert GastoPersonal.query.count() == 1
        assert IngresoPersonal.query.first().monto == Decimal("22000.00")


def test_unique_categoria_nombre_per_user(app, tenant_and_user):
    tenant, user = tenant_and_user
    with app.app_context():
        db.session.add(CategoriaPersonal(
            tenant_id=tenant.id, user_id=user.id, nombre="Dup", icon="x", color="#000",
        ))
        db.session.commit()

        db.session.add(CategoriaPersonal(
            tenant_id=tenant.id, user_id=user.id, nombre="Dup", icon="x", color="#000",
        ))
        try:
            db.session.commit()
            assert False, "Expected IntegrityError"
        except Exception:
            db.session.rollback()
```

- [ ] **Step 2: Run models tests**

Run: `pytest tests/test_finanzas_personales_models.py -v`
Expected: 2 passed.

- [ ] **Step 3: Write isolation test**

```python
# tests/test_finanzas_personales_isolation.py
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.auth.models import Tenant, User, TENANT_STATUS_ACTIVE
from app.finanzas_personales.models import GastoPersonal, CategoriaPersonal


def test_user_cannot_see_other_users_gastos_in_same_tenant(app, client, tenant_and_user):
    tenant, user_a = tenant_and_user
    with app.app_context():
        user_b = User(
            tenant_id=tenant.id, email="b@test.com", name="User B", role="admin",
        )
        user_b.set_password("pwd123456")
        db.session.add(user_b)
        db.session.commit()
        cat = CategoriaPersonal(
            tenant_id=tenant.id, user_id=user_b.id, nombre="X", icon="x", color="#000",
        )
        db.session.add(cat)
        db.session.commit()
        db.session.add(GastoPersonal(
            tenant_id=tenant.id, user_id=user_b.id,
            fecha=date(2026, 4, 5), categoria_id=cat.id,
            concepto="Privado de B", monto=Decimal("100"),
        ))
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com", "password": "password123",
    })
    token = resp.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/finanzas-personales/gastos?year=2026&month=4", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert all(g["concepto"] != "Privado de B" for g in body)


def test_tenant_isolation(app, client, tenant_and_user):
    tenant_a, user_a = tenant_and_user
    with app.app_context():
        tenant_b = Tenant(name="Other", slug="other", status=TENANT_STATUS_ACTIVE, is_active=True)
        db.session.add(tenant_b)
        db.session.flush()
        user_other = User(
            tenant_id=tenant_b.id, email="x@other.com", name="Other", role="admin",
        )
        user_other.set_password("pwd123456")
        db.session.add(user_other)
        db.session.commit()
        cat = CategoriaPersonal(
            tenant_id=tenant_b.id, user_id=user_other.id,
            nombre="Y", icon="y", color="#111",
        )
        db.session.add(cat)
        db.session.commit()
        db.session.add(GastoPersonal(
            tenant_id=tenant_b.id, user_id=user_other.id,
            fecha=date(2026, 4, 5), categoria_id=cat.id,
            concepto="Otro tenant", monto=Decimal("999"),
        ))
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com", "password": "password123",
    })
    token = resp.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/finanzas-personales/gastos?year=2026&month=4", headers=headers)
    assert resp.status_code == 200
    assert all(g["concepto"] != "Otro tenant" for g in resp.get_json())
```

- [ ] **Step 4: Run isolation tests**

Run: `pytest tests/test_finanzas_personales_isolation.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_finanzas_personales_models.py tests/test_finanzas_personales_isolation.py
git commit -m "test(finanzas-personales): models and tenant/user isolation"
```

---

## Task 7: Backend tests — services (dashboard summary)

**Files:**
- Create: `tests/test_finanzas_personales_services.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_finanzas_personales_services.py
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso, IngresoPersonal, GastoPersonal,
)
from app.finanzas_personales.services import (
    seed_defaults_for_user, build_dashboard_summary,
)


def test_seed_defaults_is_idempotent(app, tenant_and_user):
    tenant, user = tenant_and_user
    with app.app_context():
        seed_defaults_for_user(tenant.id, user.id)
        first = CategoriaPersonal.query.filter_by(
            tenant_id=tenant.id, user_id=user.id,
        ).count()
        assert first == 6
        seed_defaults_for_user(tenant.id, user.id)
        second = CategoriaPersonal.query.filter_by(
            tenant_id=tenant.id, user_id=user.id,
        ).count()
        assert second == 6


def test_dashboard_summary_basic(app, tenant_and_user):
    tenant, user = tenant_and_user
    with app.app_context():
        seed_defaults_for_user(tenant.id, user.id)
        comida = CategoriaPersonal.query.filter_by(
            tenant_id=tenant.id, user_id=user.id, nombre="Comida",
        ).first()
        salario = FuenteIngreso.query.filter_by(
            tenant_id=tenant.id, user_id=user.id, nombre="Salario",
        ).first()

        db.session.add_all([
            IngresoPersonal(
                tenant_id=tenant.id, user_id=user.id,
                fecha=date(2026, 4, 1), fuente_id=salario.id,
                concepto="Sueldo", monto=Decimal("10000.00"),
            ),
            GastoPersonal(
                tenant_id=tenant.id, user_id=user.id,
                fecha=date(2026, 4, 5), categoria_id=comida.id,
                concepto="Súper", monto=Decimal("2000.00"),
            ),
            GastoPersonal(
                tenant_id=tenant.id, user_id=user.id,
                fecha=date(2026, 4, 10), categoria_id=comida.id,
                concepto="Restaurante", monto=Decimal("500.00"),
            ),
        ])
        db.session.commit()

        s = build_dashboard_summary(tenant.id, user.id, 2026, 4)
        assert s["totals"]["ingresos"] == 10000.0
        assert s["totals"]["gastos"] == 2500.0
        assert s["totals"]["balance"] == 7500.0
        assert s["totals"]["ahorroPct"] == 75
        assert len(s["history6m"]) == 6
        assert len(s["byCat"]) == 1
        assert s["byCat"][0]["label"] == "Comida"
        assert s["byCat"][0]["value"] == 2500.0
        assert s["byCat"][0]["pct"] == 100
        assert len(s["recent"]) == 3


def test_dashboard_excludes_other_months(app, tenant_and_user):
    tenant, user = tenant_and_user
    with app.app_context():
        seed_defaults_for_user(tenant.id, user.id)
        comida = CategoriaPersonal.query.filter_by(
            tenant_id=tenant.id, user_id=user.id, nombre="Comida",
        ).first()
        db.session.add(GastoPersonal(
            tenant_id=tenant.id, user_id=user.id,
            fecha=date(2026, 3, 30), categoria_id=comida.id,
            concepto="Marzo", monto=Decimal("1000"),
        ))
        db.session.add(GastoPersonal(
            tenant_id=tenant.id, user_id=user.id,
            fecha=date(2026, 4, 1), categoria_id=comida.id,
            concepto="Abril", monto=Decimal("2000"),
        ))
        db.session.commit()

        abr = build_dashboard_summary(tenant.id, user.id, 2026, 4)
        assert abr["totals"]["gastos"] == 2000.0
        mar = build_dashboard_summary(tenant.id, user.id, 2026, 3)
        assert mar["totals"]["gastos"] == 1000.0
```

- [ ] **Step 2: Run service tests**

Run: `pytest tests/test_finanzas_personales_services.py -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_finanzas_personales_services.py
git commit -m "test(finanzas-personales): dashboard summary aggregation"
```

---

## Task 8: Backend tests — routes happy path

**Files:**
- Create: `tests/test_finanzas_personales_routes.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_finanzas_personales_routes.py
def test_dashboard_seeds_categories_and_returns_zeros(client, auth_headers):
    resp = client.get("/api/v1/finanzas-personales/dashboard?year=2026&month=4", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["totals"]["ingresos"] == 0
    assert data["totals"]["gastos"] == 0

    cats = client.get("/api/v1/finanzas-personales/categorias", headers=auth_headers).get_json()
    assert len(cats) == 6
    assert {c["nombre"] for c in cats} >= {"Comida", "Transporte", "Vivienda"}


def test_create_gasto_then_appears_in_dashboard(client, auth_headers):
    cats = client.get("/api/v1/finanzas-personales/categorias", headers=auth_headers).get_json()
    comida = next(c for c in cats if c["nombre"] == "Comida")

    resp = client.post(
        "/api/v1/finanzas-personales/gastos",
        json={
            "fecha": "2026-04-12", "categoria_id": comida["id"],
            "concepto": "Test gasto", "monto": "350.50",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["monto"] == "350.50"

    dash = client.get(
        "/api/v1/finanzas-personales/dashboard?year=2026&month=4",
        headers=auth_headers,
    ).get_json()
    assert dash["totals"]["gastos"] == 350.5
    assert dash["byCat"][0]["label"] == "Comida"


def test_create_ingreso_with_fuente(client, auth_headers):
    fuentes = client.get("/api/v1/finanzas-personales/fuentes", headers=auth_headers).get_json()
    salario = next(f for f in fuentes if f["nombre"] == "Salario")

    resp = client.post(
        "/api/v1/finanzas-personales/ingresos",
        json={
            "fecha": "2026-04-01", "fuente_id": salario["id"],
            "concepto": "Sueldo", "monto": "22000.00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    dash = client.get(
        "/api/v1/finanzas-personales/dashboard?year=2026&month=4",
        headers=auth_headers,
    ).get_json()
    assert dash["totals"]["ingresos"] == 22000.0


def test_dashboard_requires_year_and_month(client, auth_headers):
    resp = client.get("/api/v1/finanzas-personales/dashboard", headers=auth_headers)
    assert resp.status_code == 400


def test_unauthenticated_blocked(client):
    resp = client.get("/api/v1/finanzas-personales/dashboard?year=2026&month=4")
    assert resp.status_code == 401


def test_meta_crud(client, auth_headers):
    create = client.post(
        "/api/v1/finanzas-personales/metas",
        json={
            "label": "Vacaciones", "icon": "plane", "color": "#0891b2",
            "monto_objetivo": "60000.00", "monto_actual": "5000.00",
            "fecha_objetivo": "2026-12-31",
        },
        headers=auth_headers,
    )
    assert create.status_code == 201
    meta_id = create.get_json()["id"]

    update = client.put(
        f"/api/v1/finanzas-personales/metas/{meta_id}",
        json={"monto_actual": "10000.00"},
        headers=auth_headers,
    )
    assert update.status_code == 200
    assert update.get_json()["monto_actual"] == "10000.00"

    listing = client.get("/api/v1/finanzas-personales/metas", headers=auth_headers).get_json()
    assert len(listing) == 1

    delete = client.delete(
        f"/api/v1/finanzas-personales/metas/{meta_id}", headers=auth_headers,
    )
    assert delete.status_code == 200
```

- [ ] **Step 2: Run route tests**

Run: `pytest tests/test_finanzas_personales_routes.py -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_finanzas_personales_routes.py
git commit -m "test(finanzas-personales): routes happy path + auth"
```

---

## Task 9: Move React prototype into static, create api.jsx

**Files:**
- Create: `app/static/js/finanzas_personales/Atoms.jsx` (copied verbatim)
- Create: `app/static/js/finanzas_personales/Charts.jsx` (copied verbatim)
- Create: `app/static/js/finanzas_personales/api.jsx` (new)

- [ ] **Step 1: Create the static directory and copy `Atoms.jsx` and `Charts.jsx`**

```bash
mkdir -p app/static/js/finanzas_personales
cp "finanzas/personal_finance/Atoms.jsx" "app/static/js/finanzas_personales/Atoms.jsx"
cp "finanzas/personal_finance/Charts.jsx" "app/static/js/finanzas_personales/Charts.jsx"
```

- [ ] **Step 2: Create `api.jsx` (replaces `data.jsx` mocks)**

```jsx
// app/static/js/finanzas_personales/api.jsx
// Tiny fetch wrapper that reuses the JWT from localStorage.

const FP_BASE = '/api/v1/finanzas-personales';

async function fpRequest(path, options = {}) {
  const token = localStorage.getItem('token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(FP_BASE + path, { ...options, headers });
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || JSON.stringify(body.errors || body) || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

const FP = {
  listCategorias: () => fpRequest('/categorias'),
  createCategoria: (data) => fpRequest('/categorias', { method: 'POST', body: JSON.stringify(data) }),
  updateCategoria: (id, data) => fpRequest('/categorias/' + id, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCategoria: (id) => fpRequest('/categorias/' + id, { method: 'DELETE' }),

  listFuentes: () => fpRequest('/fuentes'),
  createFuente: (data) => fpRequest('/fuentes', { method: 'POST', body: JSON.stringify(data) }),

  createIngreso: (data) => fpRequest('/ingresos', { method: 'POST', body: JSON.stringify(data) }),
  createGasto: (data) => fpRequest('/gastos', { method: 'POST', body: JSON.stringify(data) }),
  deleteIngreso: (id) => fpRequest('/ingresos/' + id, { method: 'DELETE' }),
  deleteGasto: (id) => fpRequest('/gastos/' + id, { method: 'DELETE' }),

  dashboard: (year, month) => fpRequest(`/dashboard?year=${year}&month=${month}`),
  movimientos: (year, month, kind) => {
    const q = new URLSearchParams({ year, month });
    if (kind) q.set('kind', kind);
    return fpRequest('/movimientos?' + q.toString());
  },
  categoriaDetalle: (catId, year, month) =>
    fpRequest(`/categorias/${catId}/detalle?year=${year}&month=${month}`),

  listPresupuestos: () => fpRequest('/presupuestos'),
  upsertPresupuesto: (data) => fpRequest('/presupuestos', { method: 'POST', body: JSON.stringify(data) }),

  listMetas: () => fpRequest('/metas'),
  createMeta: (data) => fpRequest('/metas', { method: 'POST', body: JSON.stringify(data) }),
  updateMeta: (id, data) => fpRequest('/metas/' + id, { method: 'PUT', body: JSON.stringify(data) }),
  deleteMeta: (id) => fpRequest('/metas/' + id, { method: 'DELETE' }),
};

window.FP = FP;
```

- [ ] **Step 3: Commit**

```bash
git add app/static/js/finanzas_personales/Atoms.jsx app/static/js/finanzas_personales/Charts.jsx app/static/js/finanzas_personales/api.jsx
git commit -m "feat(finanzas-personales): static atoms/charts + API client"
```

---

## Task 10: Port Shell.jsx for the static path

**Files:**
- Create: `app/static/js/finanzas_personales/Shell.jsx`

Copy from prototype with two changes: logo path uses Flask static URL, sidebar mirrors the actual app sidebar.

- [ ] **Step 1: Write the file**

```jsx
// app/static/js/finanzas_personales/Shell.jsx
const SIDEBAR_W = 256;

function Sidebar({ active = '/finanzas-personales' }) {
  const sections = [
    { eyebrow: 'PRINCIPAL', items: [{ icon: 'layout-dashboard', label: 'Dashboard', href: '/dashboard' }] },
    { eyebrow: 'FINANZAS PERSONALES', items: [
      { icon: 'piggy-bank',     label: 'Estado de Resultados', href: '/finanzas-personales' },
      { icon: 'list',           label: 'Historial',            href: '/finanzas-personales/historial' },
      { icon: 'wallet',         label: 'Presupuestos',         href: '/finanzas-personales/presupuestos' },
      { icon: 'target',         label: 'Metas de ahorro',      href: '/finanzas-personales/metas' },
    ]},
    { eyebrow: 'CONSULTORIO', items: [
      { icon: 'calculator',  label: 'Tratamientos', href: '/tratamientos' },
      { icon: 'package',     label: 'Inventario',   href: '/inventario' },
      { icon: 'bar-chart-3', label: 'Reportes',     href: '/reportes/resumen' },
    ]},
    { eyebrow: 'SISTEMA', items: [{ icon: 'settings', label: 'Ajustes', href: '/ajustes' }] },
  ];

  return (
    <aside style={{
      position: 'fixed', top: 0, bottom: 0, left: 0, width: SIDEBAR_W,
      background: '#fff', borderRight: '1px solid #e2e8f0', zIndex: 30,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', height: 64, borderBottom: '1px solid #e2e8f0', flexShrink: 0 }}>
        <img src="/static/imagenes/02-fondoblanco.jpg.jpeg" alt="Logo" style={{ height: 32, width: 32, objectFit: 'contain', borderRadius: 6 }} />
        <span style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Dental Planning</span>
      </div>
      <div style={{ padding: '12px 12px 0 12px' }}>
        <a href="/selector" style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderRadius: 8,
          fontSize: 11, fontWeight: 600, fontFamily: 'var(--font-body)', color: '#0e7490',
          background: '#ecfeff', textDecoration: 'none', letterSpacing: '.02em',
        }}>
          <Icon name="grid-2x2" size={14} /> Cambiar de Sistema
        </a>
      </div>
      <nav style={{ flex: 1, overflowY: 'auto', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 22 }}>
        {sections.map((s) => (
          <div key={s.eyebrow}>
            <div style={{ padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'var(--font-body)' }}>{s.eyebrow}</div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
              {s.items.map((it) => {
                const isActive = it.href === active;
                return (
                  <li key={it.href}>
                    <a href={it.href} style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
                      fontSize: 14, fontWeight: 500, fontFamily: 'var(--font-body)', textDecoration: 'none',
                      color: isActive ? '#0e7490' : '#475569',
                      background: isActive ? '#ecfeff' : 'transparent',
                    }}>
                      <Icon name={it.icon} size={18} />
                      {it.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}

function Topbar({ title }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20, height: 64, background: '#fff',
      borderBottom: '1px solid #e2e8f0', marginLeft: SIDEBAR_W,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
    }}>
      <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{title}</h1>
      <button
        onClick={() => { localStorage.removeItem('token'); window.location.href = '/login'; }}
        style={{ padding: 8, borderRadius: 8, border: 'none', background: 'transparent', color: '#475569', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 13 }}>
        Cerrar sesión
      </button>
    </header>
  );
}

function PageShell({ active, title, children, onAdd }) {
  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      <Sidebar active={active} />
      <Topbar title={title} />
      <main style={{ marginLeft: SIDEBAR_W, padding: 24 }}>{children}</main>
      {onAdd && (
        <button onClick={onAdd} style={{
          position: 'fixed', bottom: 28, right: 28, width: 56, height: 56, borderRadius: 9999,
          background: '#0891b2', color: '#fff', border: 'none', cursor: 'pointer',
          boxShadow: '0 8px 24px -4px rgb(8 145 178 / 0.45)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 25,
        }} title="Agregar movimiento">
          <Icon name="plus" size={24} />
        </button>
      )}
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, PageShell, SIDEBAR_W });
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/finanzas_personales/Shell.jsx
git commit -m "feat(finanzas-personales): static Shell with sidebar/topbar"
```

---

## Task 11: Port Dashboard.jsx — fetch from API

**Files:**
- Create: `app/static/js/finanzas_personales/Dashboard.jsx`

Differences from prototype:
- `useEffect` calls `FP.dashboard(year, month)` and stores summary
- `MonthSelector` triggers re-fetch
- `byCat` items link to `/finanzas-personales/categoria/<id>`

- [ ] **Step 1: Write the file**

```jsx
// app/static/js/finanzas_personales/Dashboard.jsx
const { useEffect } = React;

function MonthSelector({ year, month, onChange }) {
  const months = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, background: '#fff', border: '1px solid #e2e8f0',
        borderRadius: 8, padding: '8px 14px', minHeight: 38, fontSize: 14, fontFamily: 'var(--font-body)',
        fontWeight: 500, color: '#164e63', cursor: 'pointer',
      }}>
        <Icon name="calendar" size={16} color="#0e7490" />
        {months[month - 1]} {year}
        <Icon name="chevron-down" size={14} color="#94a3b8" />
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 44, left: 0, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, boxShadow: '0 10px 25px -5px rgb(0 0 0 / .1)', padding: 6, zIndex: 10, minWidth: 180 }}>
          {months.map((m, i) => (
            <button key={i} onClick={() => { onChange(year, i + 1); setOpen(false); }} style={{
              display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 6,
              border: 'none', background: (i + 1) === month ? '#ecfeff' : 'transparent', color: (i + 1) === month ? '#0e7490' : '#164e63',
              fontSize: 14, fontFamily: 'var(--font-body)', cursor: 'pointer',
            }}>{m}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function InsightStrip({ insight }) {
  if (!insight) return null;
  return (
    <div style={{
      background: 'linear-gradient(90deg, #ecfeff 0%, #d1fae5 100%)',
      border: '1px solid #a7f3d0', borderRadius: 12, padding: '14px 18px',
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{ width: 40, height: 40, borderRadius: 10, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name="sparkles" size={20} color="#059669" />
      </div>
      <div style={{ flex: 1, fontSize: 14, color: '#065f46', fontFamily: 'var(--font-body)', lineHeight: 1.5 }}>
        {insight}
      </div>
    </div>
  );
}

function CategoryListItem({ cat }) {
  return (
    <a href={`/finanzas-personales/categoria/${cat.id}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid #f1f5f9', textDecoration: 'none' }}>
      <div style={{ width: 36, height: 36, borderRadius: 10, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={cat.icon} size={16} color={cat.color} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', fontFamily: 'var(--font-body)' }}>{cat.label}</div>
        <div style={{ height: 4, background: '#f1f5f9', borderRadius: 9999, marginTop: 6, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: cat.pct + '%', background: cat.color, borderRadius: 9999 }} />
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#164e63', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>{fmt(cat.value)}</div>
        <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>{cat.pct}%</div>
      </div>
    </a>
  );
}

function MovementRow({ m }) {
  const isIncome = m.kind === 'ingreso';
  const color = isIncome ? '#059669' : '#dc2626';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid #f1f5f9' }}>
      <div style={{ width: 38, height: 38, borderRadius: 10, background: (m.color || '#94a3b8') + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={m.icon || 'circle'} size={16} color={m.color || '#475569'} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: '#164e63', fontFamily: 'var(--font-body)' }}>{m.concepto}</div>
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>
          {m.label} · {new Date(m.fecha).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
        </div>
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-body)' }}>
        {isIncome ? '+' : '−'}{fmt(m.monto)}
      </div>
    </div>
  );
}

function Dashboard() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    FP.dashboard(year, month)
      .then(s => { setSummary(s); setLoading(false); window.lucide && window.lucide.createIcons(); })
      .catch(err => { console.error(err); setLoading(false); });
  }, [year, month]);

  if (loading || !summary) {
    return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)' }}>Cargando…</div>;
  }

  const t = summary.totals;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Estado de Resultados Personal</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4, fontFamily: 'var(--font-body)' }}>Resumen del mes</div>
        </div>
        <MonthSelector year={year} month={month} onChange={(y, m) => { setYear(y); setMonth(m); }} />
      </div>

      <InsightStrip insight={summary.insight} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard label="Ingresos" value={fmt(t.ingresos)} icon="trending-up"  valueColor="#065f46" sub="vs mes anterior" trend={summary.trends.ingresos} />
        <StatCard label="Gastos"   value={fmt(t.gastos)}   icon="trending-down" valueColor="#164e63" sub="vs mes anterior" trend={summary.trends.gastos} />
        <StatCard label="Balance"  value={fmt(t.balance)}  icon="wallet"        valueColor={t.balance >= 0 ? '#0e7490' : '#dc2626'} sub="ingresos − gastos" />
        <StatCard label="Ahorro"   value={t.ahorroPct + '%'} icon="piggy-bank"  valueColor="#0e7490" sub="del ingreso del mes" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Gastos por categoría</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24, padding: '12px 20px 20px' }}>
            <Donut data={summary.byCat.map(c => ({ value: c.value, color: c.color }))} size={180} />
            <div style={{ flex: 1 }}>
              <CategoryLegend data={summary.byCat.map(c => ({ label: c.label, value: c.value, color: c.color }))} />
            </div>
          </div>
        </Card>
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ingresos vs Gastos</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>Últimos 6 meses</div>
          </div>
          <div style={{ padding: '4px 14px 16px' }}>
            <BarChart data={summary.history6m} height={220} />
          </div>
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Top categorías</div>
          </div>
          <div style={{ padding: '4px 20px 16px' }}>
            {summary.byCat.slice(0, 5).map(c => <CategoryListItem key={c.id} cat={c} />)}
            {summary.byCat.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin gastos este mes</div>}
          </div>
        </Card>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Últimos movimientos</div>
            <a href="/finanzas-personales/historial" style={{ fontSize: 13, color: '#0e7490', textDecoration: 'none', fontWeight: 500 }}>Ver historial</a>
          </div>
          <div>
            {summary.recent.map(m => <MovementRow key={m.id} m={m} />)}
            {summary.recent.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin movimientos este mes</div>}
          </div>
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { Dashboard, MonthSelector, InsightStrip, CategoryListItem, MovementRow });
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/finanzas_personales/Dashboard.jsx
git commit -m "feat(finanzas-personales): API-driven Dashboard component"
```

---

## Task 12: Port AddMovementModal — POST to API

**Files:**
- Create: `app/static/js/finanzas_personales/AddMovementModal.jsx`

- [ ] **Step 1: Write the file**

```jsx
// app/static/js/finanzas_personales/AddMovementModal.jsx
function Modal({ open, onClose, title, children, maxWidth = 520 }) {
  if (!open) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, overflow: 'auto' }}>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)' }} />
      <div style={{ minHeight: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
        <div style={{ position: 'relative', background: '#fff', borderRadius: 16, boxShadow: '0 20px 25px -5px rgb(0 0 0 / 0.10), 0 8px 10px -6px rgb(0 0 0 / 0.05)', width: '100%', maxWidth }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #e2e8f0' }}>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{title}</h2>
            <button onClick={onClose} style={{ padding: 8, borderRadius: 8, border: 'none', background: 'transparent', color: '#94a3b8', cursor: 'pointer' }}>
              <Icon name="x" size={16} />
            </button>
          </div>
          <div style={{ padding: '20px 24px' }}>{children}</div>
        </div>
      </div>
    </div>
  );
}

function TypeToggle({ value, onChange }) {
  const tab = (id, label, icon, sel, color) => (
    <button onClick={() => onChange(id)} style={{
      padding: '10px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
      background: sel ? '#fff' : 'transparent', color: sel ? color : '#94a3b8',
      fontWeight: 600, fontSize: 14, fontFamily: 'var(--font-body)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
      boxShadow: sel ? '0 1px 2px 0 rgb(0 0 0 / .05)' : 'none',
    }}>
      <Icon name={icon} size={16} /> {label}
    </button>
  );
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: 4, background: '#f1f5f9', borderRadius: 10 }}>
      {tab('ingreso', 'Ingreso', 'trending-up',   value === 'ingreso', '#065f46')}
      {tab('gasto',   'Gasto',   'trending-down', value === 'gasto',   '#b91c1c')}
    </div>
  );
}

function CategoryGrid({ value, onChange, options }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
      {options.map(o => {
        const sel = value === o.id;
        return (
          <button key={o.id} onClick={() => onChange(o.id)} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
            padding: '14px 8px', borderRadius: 10, cursor: 'pointer',
            border: sel ? '2px solid #0891b2' : '1px solid #e2e8f0',
            background: sel ? '#ecfeff' : '#fff',
            color: '#164e63', fontFamily: 'var(--font-body)', fontSize: 12, fontWeight: 500,
          }}>
            <div style={{ width: 36, height: 36, borderRadius: 9999, background: (o.color || '#0891b2') + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon name={o.icon} size={18} color={o.color || '#0e7490'} />
            </div>
            {o.nombre || o.label}
          </button>
        );
      })}
    </div>
  );
}

function AddMovementModal({ open, onClose, onSaved, categorias, fuentes }) {
  const [type, setType] = useState('gasto');
  const [monto, setMonto] = useState('');
  const [catId, setCatId] = useState(null);
  const [fuenteId, setFuenteId] = useState(null);
  const [concepto, setConcepto] = useState('');
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setMonto(''); setConcepto(''); setError(null);
      setCatId(categorias && categorias[0] ? categorias[0].id : null);
      setFuenteId(fuentes && fuentes[0] ? fuentes[0].id : null);
      setFecha(new Date().toISOString().slice(0, 10));
    }
  }, [open]);

  const handleSave = async () => {
    setError(null);
    const num = parseFloat(monto);
    if (!num || num <= 0) { setError('Ingresa un monto válido'); return; }
    setSaving(true);
    try {
      if (type === 'ingreso') {
        await FP.createIngreso({
          fecha, fuente_id: fuenteId, concepto, monto: num.toFixed(2),
        });
      } else {
        await FP.createGasto({
          fecha, categoria_id: catId, concepto, monto: num.toFixed(2),
        });
      }
      onSaved && onSaved();
      onClose();
    } catch (e) {
      setError(e.message || 'No se pudo guardar');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={type === 'ingreso' ? 'Nuevo Ingreso' : 'Nuevo Gasto'}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <TypeToggle value={type} onChange={setType} />

        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 12, padding: '18px 20px' }}>
          <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)', fontWeight: 500 }}>Monto</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: type === 'ingreso' ? '#065f46' : '#b91c1c', fontFamily: 'var(--font-heading)' }}>
              {type === 'ingreso' ? '+' : '−'}$
            </span>
            <input
              value={monto} onChange={e => setMonto(e.target.value)}
              placeholder="0.00" inputMode="decimal"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none',
                       fontSize: 32, fontWeight: 700, color: '#164e63', fontFamily: 'var(--font-heading)',
                       fontVariantNumeric: 'tabular-nums' }}
            />
          </div>
        </div>

        <Field label={type === 'ingreso' ? 'Origen' : 'Categoría'}>
          <CategoryGrid
            value={type === 'ingreso' ? fuenteId : catId}
            onChange={type === 'ingreso' ? setFuenteId : setCatId}
            options={type === 'ingreso' ? (fuentes || []) : (categorias || [])}
          />
        </Field>

        <Field label="Concepto">
          <TextInput value={concepto} onChange={e => setConcepto(e.target.value)} placeholder="¿En qué fue?" />
        </Field>

        <Field label="Fecha">
          <TextInput type="date" value={fecha} onChange={e => setFecha(e.target.value)} />
        </Field>

        {error && <div style={{ color: '#dc2626', fontSize: 13, fontFamily: 'var(--font-body)' }}>{error}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, paddingTop: 8, borderTop: '1px solid #e2e8f0' }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button variant={type === 'ingreso' ? 'accent' : 'primary'} icon="check" onClick={handleSave} disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

Object.assign(window, { Modal, AddMovementModal, TypeToggle, CategoryGrid });
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/finanzas_personales/AddMovementModal.jsx
git commit -m "feat(finanzas-personales): AddMovementModal posts to API"
```

---

## Task 13: Port screens (CategoryDetail, History, Metas)

**Files:**
- Create: `app/static/js/finanzas_personales/screens.jsx`

- [ ] **Step 1: Write the file**

```jsx
// app/static/js/finanzas_personales/screens.jsx
function useMonth() {
  const today = new Date();
  return useState({ year: today.getFullYear(), month: today.getMonth() + 1 });
}

function CategoryDetail() {
  const catId = parseInt(window.FP_CATEGORY_ID, 10);
  const [{ year, month }] = useMonth();
  const [data, setData] = useState(null);
  useEffect(() => {
    FP.categoriaDetalle(catId, year, month).then(setData).catch(console.error);
  }, [catId, year, month]);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  if (!data) return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>Cargando…</div>;
  const cat = data.categoria;
  const movs = data.movimientos;
  const total = data.total;
  const budget = data.presupuesto;
  const pct = budget ? Math.min(total / budget, 1) : 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <a href="/finanzas-personales" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#0e7490', textDecoration: 'none', fontFamily: 'var(--font-body)', fontWeight: 500, marginBottom: 8 }}>
          <Icon name="arrow-left" size={14} /> Volver al resumen
        </a>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name={cat.icon} size={26} color={cat.color} />
          </div>
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>{cat.label}</div>
            <div style={{ fontSize: 13, color: '#94a3b8', fontFamily: 'var(--font-body)', marginTop: 2 }}>{movs.length} movimientos</div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', gap: 16 }}>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>GASTADO ESTE MES</div>
          <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{fmt(total)}</div>
          {budget && (
            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#475569', fontFamily: 'var(--font-body)', marginBottom: 6 }}>
                <span>Presupuesto mensual</span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt(total)} de {fmt(budget)}</span>
              </div>
              <div style={{ height: 8, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: pct * 100 + '%', background: pct > 0.9 ? '#ef4444' : pct > 0.75 ? '#f59e0b' : cat.color, borderRadius: 9999 }} />
              </div>
            </div>
          )}
        </Card>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>PROMEDIO DIARIO</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{fmt(data.promedioDiario)}</div>
        </Card>
        <Card>
          <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>GASTO MÁS GRANDE</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 8 }}>{data.max ? fmt(data.max.monto) : '—'}</div>
          {data.max && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{data.max.concepto}</div>}
        </Card>
      </div>

      <Card padding={0}>
        <div style={{ padding: '20px 20px 8px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Evolución</div>
          <div style={{ fontSize: 12, color: '#94a3b8' }}>Últimos 6 meses · {cat.label}</div>
        </div>
        <div style={{ padding: '4px 14px 20px' }}>
          <BarChart data={data.history6m} height={180} />
        </div>
      </Card>

      <Card padding={0}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Todos los movimientos</div>
        {movs.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin movimientos en esta categoría este mes</div>}
        {movs.map(m => <MovementRow key={m.id} m={m} />)}
      </Card>
    </div>
  );
}

function TransactionHistory() {
  const [{ year, month }] = useMonth();
  const [filter, setFilter] = useState(null);
  const [search, setSearch] = useState('');
  const [items, setItems] = useState([]);

  useEffect(() => {
    FP.movimientos(year, month, filter).then(setItems).catch(console.error);
  }, [year, month, filter]);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  const filtered = items.filter(m =>
    !search || m.concepto.toLowerCase().includes(search.toLowerCase()),
  );
  const groups = filtered.reduce((acc, m) => { (acc[m.fecha] ??= []).push(m); return acc; }, {});

  const Tab = ({ id, label, count }) => (
    <button onClick={() => setFilter(id)} style={{
      padding: '8px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
      background: filter === id ? '#ecfeff' : 'transparent',
      color: filter === id ? '#0e7490' : '#475569',
      fontFamily: 'var(--font-body)', fontWeight: 500, fontSize: 13,
      display: 'inline-flex', alignItems: 'center', gap: 6,
    }}>
      {label}
      <span style={{ background: filter === id ? '#cffafe' : '#f1f5f9', color: filter === id ? '#0e7490' : '#94a3b8', borderRadius: 9999, padding: '1px 8px', fontSize: 11, fontWeight: 600 }}>{count}</span>
    </button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Historial de movimientos</div>
      </div>
      <Card padding={12}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 4, padding: 4, background: '#f8fafc', borderRadius: 10 }}>
            <Tab id={null}      label="Todos"    count={items.length} />
            <Tab id="ingreso"   label="Ingresos" count={items.filter(m => m.kind === 'ingreso').length} />
            <Tab id="gasto"     label="Gastos"   count={items.filter(m => m.kind === 'gasto').length} />
          </div>
          <div style={{ flex: 1, minWidth: 220, position: 'relative' }}>
            <Icon name="search" size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar concepto..." style={{
              width: '100%', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 12px 8px 36px',
              minHeight: 38, fontSize: 14, fontFamily: 'var(--font-body)', color: '#164e63', background: '#fff', boxSizing: 'border-box', outline: 'none',
            }} />
          </div>
        </div>
      </Card>
      <Card padding={0}>
        {Object.keys(groups).length === 0 && (
          <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)', fontSize: 14 }}>
            Sin resultados
          </div>
        )}
        {Object.entries(groups).map(([d, list]) => {
          const dayTotal = list.reduce((s, m) => s + (m.kind === 'ingreso' ? m.monto : -m.monto), 0);
          const dt = new Date(d);
          return (
            <div key={d}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'capitalize' }}>
                  {dt.toLocaleDateString('es-MX', { weekday: 'long', day: '2-digit', month: 'long' })}
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: dayTotal >= 0 ? '#059669' : '#dc2626', fontVariantNumeric: 'tabular-nums' }}>
                  {dayTotal >= 0 ? '+' : '−'}{fmt(Math.abs(dayTotal))}
                </div>
              </div>
              {list.map(m => <MovementRow key={m.id} m={m} />)}
            </div>
          );
        })}
      </Card>
    </div>
  );
}

function GoalCard({ goal, onDelete }) {
  const target = parseFloat(goal.monto_objetivo);
  const actual = parseFloat(goal.monto_actual);
  const pct = target ? Math.min(actual / target, 1) : 0;
  return (
    <Card padding={0}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '20px 20px 12px' }}>
        <div style={{ width: 48, height: 48, borderRadius: 12, background: goal.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon name={goal.icon} size={22} color={goal.color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#164e63', fontFamily: 'var(--font-heading)' }}>{goal.label}</div>
          {goal.fecha_objetivo && <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>Meta para {goal.fecha_objetivo}</div>}
        </div>
        <button onClick={() => onDelete(goal.id)} style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><Icon name="trash-2" size={16} /></button>
      </div>
      <div style={{ padding: '0 20px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: '#164e63', fontFamily: 'var(--font-heading)', fontVariantNumeric: 'tabular-nums' }}>{fmt(actual)}</span>
          <span style={{ fontSize: 13, color: '#94a3b8' }}>de {fmt(target)}</span>
        </div>
        <div style={{ height: 10, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: pct * 100 + '%', background: goal.color, borderRadius: 9999 }} />
        </div>
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>{Math.round(pct * 100)}% completado</div>
      </div>
    </Card>
  );
}

function MetasScreen() {
  const [goals, setGoals] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ label: '', monto_objetivo: '', monto_actual: '0', fecha_objetivo: '', icon: 'target', color: '#059669' });

  const reload = () => FP.listMetas().then(setGoals);
  useEffect(() => { reload(); }, []);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  const submit = async () => {
    await FP.createMeta({ ...form, fecha_objetivo: form.fecha_objetivo || null });
    setShowForm(false);
    setForm({ label: '', monto_objetivo: '', monto_actual: '0', fecha_objetivo: '', icon: 'target', color: '#059669' });
    reload();
  };
  const remove = async (id) => { await FP.deleteMeta(id); reload(); };

  const totalSaved = goals.reduce((s, g) => s + parseFloat(g.monto_actual), 0);
  const totalGoal = goals.reduce((s, g) => s + parseFloat(g.monto_objetivo), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Metas de ahorro</div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4 }}>{goals.length} metas activas</div>
        </div>
        <Button variant="primary" icon="plus" onClick={() => setShowForm(true)}>Nueva meta</Button>
      </div>

      {goals.length > 0 && (
        <Card padding={0}>
          <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', alignItems: 'center', padding: 24, gap: 32 }}>
            <ProgressArc value={totalSaved} max={totalGoal || 1} sub={`de ${fmtShort(totalGoal)}`} />
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: '#94a3b8' }}>AHORRADO EN TOTAL</div>
              <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{fmt(totalSaved)}</div>
            </div>
          </div>
        </Card>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
        {goals.map(g => <GoalCard key={g.id} goal={g} onDelete={remove} />)}
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title="Nueva meta de ahorro">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Nombre"><TextInput value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} placeholder="Ej. Vacaciones" /></Field>
          <Field label="Monto objetivo"><TextInput type="number" value={form.monto_objetivo} onChange={e => setForm({ ...form, monto_objetivo: e.target.value })} placeholder="60000" /></Field>
          <Field label="Monto actual"><TextInput type="number" value={form.monto_actual} onChange={e => setForm({ ...form, monto_actual: e.target.value })} placeholder="0" /></Field>
          <Field label="Fecha objetivo (opcional)"><TextInput type="date" value={form.fecha_objetivo} onChange={e => setForm({ ...form, fecha_objetivo: e.target.value })} /></Field>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setShowForm(false)}>Cancelar</Button>
            <Button variant="primary" icon="check" onClick={submit}>Guardar</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

Object.assign(window, { CategoryDetail, TransactionHistory, MetasScreen, GoalCard });
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/finanzas_personales/screens.jsx
git commit -m "feat(finanzas-personales): port screens (CategoryDetail, History, Metas) to API"
```

---

## Task 14: Port Budgets screen

**Files:**
- Create: `app/static/js/finanzas_personales/Budgets.jsx`

- [ ] **Step 1: Write the file**

```jsx
// app/static/js/finanzas_personales/Budgets.jsx
function BudgetRow({ cat, spent, budget, onEdit }) {
  const pct = budget ? Math.min(spent / budget, 1) : 0;
  const pctNum = budget ? Math.round((spent / budget) * 100) : 0;
  const remaining = budget - spent;
  const status = pctNum >= 100 ? 'over' : pctNum >= 85 ? 'near' : 'ok';
  const color = { ok: '#059669', near: '#d97706', over: '#dc2626' }[status];
  const bg = { ok: '#d1fae5', near: '#fef3c7', over: '#fee2e2' }[status];
  const label = { ok: 'En curso', near: 'Casi al tope', over: 'Excedido' }[status];
  return (
    <div style={{ padding: '18px 20px', borderBottom: '1px solid #f1f5f9' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: cat.color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name={cat.icon} size={18} color={cat.color} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: '#164e63' }}>{cat.label}</span>
            {budget > 0 && <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 9999, background: bg, color }}>{label}</span>}
          </div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
            {budget > 0
              ? (remaining >= 0 ? `Te quedan ${fmt(remaining)} de ${fmt(budget)}` : `Excediste ${fmt(-remaining)}`)
              : 'Sin presupuesto definido'}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#164e63', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-heading)' }}>{fmt(spent)}</div>
          {budget > 0 && <div style={{ fontSize: 11, color: '#94a3b8' }}>de {fmt(budget)}</div>}
        </div>
        <button onClick={() => onEdit(cat)} style={{ marginLeft: 12, background: 'transparent', border: '1px solid #e2e8f0', borderRadius: 8, padding: 8, cursor: 'pointer', color: '#475569' }}>
          <Icon name="edit-2" size={14} />
        </button>
      </div>
      {budget > 0 && (
        <div style={{ height: 8, background: '#f1f5f9', borderRadius: 9999, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: pct * 100 + '%', background: color, borderRadius: 9999 }} />
        </div>
      )}
    </div>
  );
}

function Budgets() {
  const today = new Date();
  const [year] = useState(today.getFullYear());
  const [month] = useState(today.getMonth() + 1);
  const [summary, setSummary] = useState(null);
  const [budgets, setBudgets] = useState([]);
  const [allCats, setAllCats] = useState([]);
  const [editing, setEditing] = useState(null);
  const [amount, setAmount] = useState('');

  const reload = async () => {
    const [s, b, c] = await Promise.all([
      FP.dashboard(year, month), FP.listPresupuestos(), FP.listCategorias(),
    ]);
    setSummary(s);
    setBudgets(b);
    setAllCats(c.filter(x => x.activo));
  };
  useEffect(() => { reload(); }, []);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  if (!summary) return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8' }}>Cargando…</div>;

  const budgetByCat = {};
  for (const b of budgets) {
    const cur = budgetByCat[b.categoria_id];
    if (!cur || b.vigente_desde > cur.vigente_desde) budgetByCat[b.categoria_id] = b;
  }
  const spendByCat = Object.fromEntries(summary.byCat.map(c => [c.id, c.value]));

  const save = async () => {
    await FP.upsertPresupuesto({
      categoria_id: editing.id,
      monto_mensual: parseFloat(amount).toFixed(2),
      vigente_desde: new Date().toISOString().slice(0, 10),
    });
    setEditing(null);
    reload();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Presupuestos</div>
        <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4 }}>Define límites mensuales por categoría</div>
      </div>
      <Card padding={0}>
        {allCats.length === 0 && <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8' }}>Aún no hay categorías</div>}
        {allCats.map(c => (
          <BudgetRow
            key={c.id}
            cat={{ id: c.id, label: c.nombre, icon: c.icon, color: c.color }}
            spent={spendByCat[c.id] || 0}
            budget={budgetByCat[c.id] ? parseFloat(budgetByCat[c.id].monto_mensual) : 0}
            onEdit={cat => { setEditing(cat); setAmount(budgetByCat[cat.id] ? budgetByCat[cat.id].monto_mensual : ''); }}
          />
        ))}
      </Card>

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing ? `Presupuesto: ${editing.label}` : ''}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Monto mensual"><TextInput type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" /></Field>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button variant="primary" icon="check" onClick={save}>Guardar</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

Object.assign(window, { Budgets, BudgetRow });
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/finanzas_personales/Budgets.jsx
git commit -m "feat(finanzas-personales): Budgets screen with edit modal"
```

---

## Task 15: Single entry point `main.jsx` and per-screen mounting

**Files:**
- Create: `app/static/js/finanzas_personales/main.jsx`

The Jinja shell sets `window.FP_SCREEN` to one of `dashboard | category | history | metas | presupuestos`. `main.jsx` reads it and mounts the right screen.

- [ ] **Step 1: Write the file**

```jsx
// app/static/js/finanzas_personales/main.jsx
function App() {
  const [adding, setAdding] = useState(false);
  const [categorias, setCategorias] = useState([]);
  const [fuentes, setFuentes] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    Promise.all([FP.listCategorias(), FP.listFuentes()]).then(([c, f]) => {
      setCategorias(c.filter(x => x.activo));
      setFuentes(f.filter(x => x.activo));
    });
  }, []);
  useEffect(() => { window.lucide && window.lucide.createIcons(); });

  const screen = window.FP_SCREEN || 'dashboard';
  const titles = {
    dashboard: 'Estado de Resultados Personal',
    category: 'Detalle de categoría',
    history: 'Historial',
    metas: 'Metas de ahorro',
    presupuestos: 'Presupuestos',
  };
  const actives = {
    dashboard: '/finanzas-personales',
    category: '/finanzas-personales',
    history: '/finanzas-personales/historial',
    metas: '/finanzas-personales/metas',
    presupuestos: '/finanzas-personales/presupuestos',
  };

  let body = null;
  if (screen === 'dashboard')         body = <Dashboard          key={reloadKey} />;
  else if (screen === 'category')     body = <CategoryDetail     key={reloadKey} />;
  else if (screen === 'history')      body = <TransactionHistory key={reloadKey} />;
  else if (screen === 'metas')        body = <MetasScreen        key={reloadKey} />;
  else if (screen === 'presupuestos') body = <Budgets            key={reloadKey} />;

  return (
    <PageShell active={actives[screen]} title={titles[screen]} onAdd={() => setAdding(true)}>
      {body}
      <AddMovementModal
        open={adding}
        onClose={() => setAdding(false)}
        onSaved={() => setReloadKey(k => k + 1)}
        categorias={categorias}
        fuentes={fuentes}
      />
    </PageShell>
  );
}

ReactDOM.createRoot(document.getElementById('fp-root')).render(<App />);
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/finanzas_personales/main.jsx
git commit -m "feat(finanzas-personales): single React entry point with screen routing"
```

---

## Task 16: Jinja shell template and per-screen templates

**Files:**
- Create: `app/templates/finanzas_personales/_shell.html`
- Create: `app/templates/finanzas_personales/dashboard.html`
- Create: `app/templates/finanzas_personales/category.html`
- Create: `app/templates/finanzas_personales/history.html`
- Create: `app/templates/finanzas_personales/metas.html`
- Create: `app/templates/finanzas_personales/presupuestos.html`

The shell loads React + babel-standalone + lucide and the design-token fonts. The auth gate redirects to `/login` immediately if no token; we do NOT use `document.write` — we do an early `window.location.replace()` and `return` from an IIFE so nothing else runs.

- [ ] **Step 1: Write the shell**

```html
{# app/templates/finanzas_personales/_shell.html #}
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Finanzas Personales — Dental Planning{% endblock %}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/poppins@5.0.8/index.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/open-sans@5.0.13/index.min.css">
<style>
  :root { --font-heading: 'Poppins', system-ui, sans-serif; --font-body: 'Open Sans', system-ui, sans-serif; }
  html, body { margin: 0; padding: 0; font-family: var(--font-body); color: #164e63; background: #f8fafc; }
  html { visibility: hidden; }
</style>
<script>
  // Auth gate (no document.write — just bail before rendering anything)
  (function () {
    if (!localStorage.getItem('token')) {
      window.location.replace('/login');
      // Throw so subsequent inline scripts don't execute. The blank page stays
      // hidden because html { visibility: hidden } until we explicitly reveal.
      throw new Error('AUTH_REDIRECT');
    }
    document.documentElement.style.visibility = 'visible';
  })();
  window.FP_SCREEN = "{{ fp_screen }}";
  {% if fp_category_id is defined %}window.FP_CATEGORY_ID = "{{ fp_category_id }}";{% endif %}
</script>
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script src="https://unpkg.com/react@18.3.1/umd/react.development.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js"></script>
</head>
<body>
<div id="fp-root"></div>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Atoms.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Charts.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/api.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Shell.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/AddMovementModal.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Dashboard.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/screens.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Budgets.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/main.jsx') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Write the per-screen wrapper templates**

`app/templates/finanzas_personales/dashboard.html`:
```html
{% include "finanzas_personales/_shell.html" %}
```

`app/templates/finanzas_personales/category.html`:
```html
{% include "finanzas_personales/_shell.html" %}
```

`app/templates/finanzas_personales/history.html`:
```html
{% include "finanzas_personales/_shell.html" %}
```

`app/templates/finanzas_personales/metas.html`:
```html
{% include "finanzas_personales/_shell.html" %}
```

`app/templates/finanzas_personales/presupuestos.html`:
```html
{% include "finanzas_personales/_shell.html" %}
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/finanzas_personales/
git commit -m "feat(finanzas-personales): jinja shell + per-screen templates"
```

---

## Task 17: Frontend routes (Flask)

**Files:**
- Modify: `app/frontend/routes.py`

- [ ] **Step 1: Append the route block at the end of `app/frontend/routes.py`**

```python
# ── Finanzas Personales ─────────────────────────────────────────────────────

@frontend_bp.route("/finanzas-personales")
def finanzas_personales_dashboard():
    return render_template("finanzas_personales/dashboard.html", fp_screen="dashboard")


@frontend_bp.route("/finanzas-personales/categoria/<int:cat_id>")
def finanzas_personales_categoria(cat_id):
    return render_template(
        "finanzas_personales/category.html",
        fp_screen="category", fp_category_id=cat_id,
    )


@frontend_bp.route("/finanzas-personales/historial")
def finanzas_personales_historial():
    return render_template("finanzas_personales/history.html", fp_screen="history")


@frontend_bp.route("/finanzas-personales/metas")
def finanzas_personales_metas():
    return render_template("finanzas_personales/metas.html", fp_screen="metas")


@frontend_bp.route("/finanzas-personales/presupuestos")
def finanzas_personales_presupuestos():
    return render_template("finanzas_personales/presupuestos.html", fp_screen="presupuestos")
```

- [ ] **Step 2: Smoke test — start the dev server**

In a second terminal: `python manage.py runserver --port 5000`

- [ ] **Step 3: Verify the dashboard route renders 200**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/finanzas-personales`
Expected: `200`

(Without auth, the page will redirect client-side to `/login` — that's correct.)

- [ ] **Step 4: Stop the dev server (Ctrl+C). Commit.**

```bash
git add app/frontend/routes.py
git commit -m "feat(finanzas-personales): add /finanzas-personales/* frontend routes"
```

---

## Task 18: Add Finanzas Personales to the main sidebar

**Files:**
- Modify: `app/templates/partials/sidebar_content.html`

Insert a new "FINANZAS PERSONALES" section between "PRECIOS" and "FINANZAS" (clinic).

- [ ] **Step 1: Insert the new sidebar section**

In `app/templates/partials/sidebar_content.html`, locate the closing `</div>` of the "PRECIOS" section (around line 48) and the opening `<div>` of the "FINANZAS" section (around line 51). Insert this NEW section in between:

```html
    <div>
      <p class="px-3 mb-2 text-[11px] font-semibold tracking-wider text-text-muted uppercase font-body">FINANZAS PERSONALES</p>
      <ul class="space-y-0.5">
        <li>
          <a href="/finanzas-personales" data-nav-path="/finanzas-personales" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="piggy-bank" class="h-[18px] w-[18px] shrink-0"></i>
            Estado de Resultados
          </a>
        </li>
        <li>
          <a href="/finanzas-personales/historial" data-nav-path="/finanzas-personales/historial" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="list" class="h-[18px] w-[18px] shrink-0"></i>
            Historial
          </a>
        </li>
        <li>
          <a href="/finanzas-personales/presupuestos" data-nav-path="/finanzas-personales/presupuestos" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="wallet" class="h-[18px] w-[18px] shrink-0"></i>
            Presupuestos
          </a>
        </li>
        <li>
          <a href="/finanzas-personales/metas" data-nav-path="/finanzas-personales/metas" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="target" class="h-[18px] w-[18px] shrink-0"></i>
            Metas de ahorro
          </a>
        </li>
      </ul>
    </div>
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/partials/sidebar_content.html
git commit -m "feat(finanzas-personales): add sidebar section to clinic shell"
```

---

## Task 19: Add Finanzas Personales card to the system selector

**Files:**
- Modify: `app/templates/selector.html`

The selector currently shows two cards in `grid-cols-1 sm:grid-cols-2`. Bump to 3 columns on large screens and add the new card.

- [ ] **Step 1: Update the grid class**

In `app/templates/selector.html`, find:
```html
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-6">
```
Replace with:
```html
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
```

- [ ] **Step 2: Add the new card**

Immediately after the existing "Inventario" card's closing `</a>` (around line 72) and before the closing `</div>` of the cards grid, insert:

```html
      <!-- Finanzas Personales -->
      <a href="/finanzas-personales" id="btn-finanzas-personales"
         class="group relative bg-white/10 backdrop-blur-lg border border-white/20 rounded-2xl p-8 text-center transition-all duration-300 hover:bg-white/20 hover:scale-[1.03] hover:shadow-2xl hover:shadow-emerald-900/40 focus:outline-none focus:ring-2 focus:ring-white/40 focus:ring-offset-2 focus:ring-offset-transparent">
        <div class="absolute inset-0 rounded-2xl bg-gradient-to-br from-emerald-400/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
        <div class="relative z-10">
          <div class="w-16 h-16 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg group-hover:shadow-emerald-500/40 transition-shadow duration-300">
            <i data-lucide="piggy-bank" class="h-8 w-8 text-white"></i>
          </div>
          <h2 class="text-xl font-bold font-heading text-white mb-2">Finanzas Personales</h2>
          <p class="text-sm text-primary-200 leading-relaxed mb-6">Ingresos, gastos y metas</p>
          <span class="inline-flex items-center gap-2 text-sm font-semibold text-white/80 group-hover:text-white transition-colors duration-200">
            Acceder
            <i data-lucide="arrow-right" class="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1"></i>
          </span>
        </div>
      </a>
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/selector.html
git commit -m "feat(finanzas-personales): add card to system selector"
```

---

## Task 20: End-to-end smoke test

- [ ] **Step 1: Run the full pytest suite**

Run: `pytest -q`
Expected: all tests pass — no regressions in existing modules; new tests from Tasks 6-8 pass.

- [ ] **Step 2: Manually exercise the UI**

Start the dev server: `python manage.py runserver --port 5000`

In a browser:
1. Log in (or create an admin via `python manage.py create-admin`).
2. From `/selector` confirm the new "Finanzas Personales" card appears and is clickable.
3. Land on `/finanzas-personales` — the dashboard loads with zeros and the 6 default categories appear (each with 0 — they'll be filtered out of the donut, that's expected).
4. Click the floating `+` button — modal opens. Switch to "Gasto", type 350, pick "Comida", concepto "Test", today's date — Save. Modal closes; dashboard re-fetches; KPI "Gastos" shows 350 and the donut populates with Comida.
5. Click "Comida" in Top Categorías — `/finanzas-personales/categoria/<id>` renders with the gasto in the list.
6. Visit `/finanzas-personales/historial` — your gasto is grouped under today's date.
7. Visit `/finanzas-personales/metas` — click "Nueva meta", create one, confirm it lists.
8. Visit `/finanzas-personales/presupuestos` — for "Comida" click the edit pencil, set 5000 — progress bar appears.
9. Sidebar: from any of the above pages, the "Finanzas Personales" section shows 4 items, the active one is highlighted, and "Cambiar de Sistema" returns to the selector.

If any step fails, fix in place before continuing.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix(finanzas-personales): smoke-test corrections"
```

(Skip if no changes were needed.)

---

## Task 21: Update CLAUDE.md with the new module

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `finanzas_personales` to the modules list**

In `CLAUDE.md`, find:
```
Modules: `auth`, `catalogo`, `configuracion`, `tratamientos`, `edr`, `dashboard`, `ajustes`, `inventario`, `engine`, `frontend`.
```
Replace with:
```
Modules: `auth`, `catalogo`, `configuracion`, `tratamientos`, `edr`, `dashboard`, `ajustes`, `inventario`, `finanzas_personales`, `engine`, `frontend`.
```

Then under that paragraph add:

```
The `finanzas_personales` module tracks **per-user** personal income/expenses (categorías + fuentes are seeded on first dashboard hit). Unlike other modules it scopes data by `(tenant_id, user_id)` because two users at the same clinic keep separate personal finances. Aggregations live in `app/finanzas_personales/services.py`; the React UI lives in `app/static/js/finanzas_personales/` and is served by Jinja shells under `/finanzas-personales/*`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document finanzas_personales module in CLAUDE.md"
```

---

## Self-review checklist

- **Spec coverage:**
  - Dashboard with KPIs (Ingresos / Gastos / Balance / Ahorro %) — Task 11
  - Selector de mes — Task 11 (`MonthSelector`)
  - Pie chart por categoría — Task 11 (`Donut`)
  - Línea / barras 6 meses — Task 11 (`BarChart`)
  - Lista de últimos movimientos tipo banco — Task 11 (`MovementRow`)
  - Floating `+` button — Task 10 (`PageShell`)
  - Add modal con Ingreso/Gasto toggle, monto grande, categoría grid, fecha — Task 12
  - Detalle por categoría (Nivel 2) — Task 13 (`CategoryDetail`)
  - Historial completo — Task 13 (`TransactionHistory`)
  - Metas de ahorro — Task 13 (`MetasScreen`)
  - Presupuestos por categoría con alertas — Task 14
  - Insight automático — Task 4 (`_build_insight`)
  - Sidebar entry junto a Inventario / Sistema Contable — Task 18
  - Selector card junto a Inventario / Sistema Contable — Task 19
  - Backend tenant + user isolation — Tasks 5, 6
  - Tests — Tasks 6, 7, 8

- **Type consistency:**
  - `monto` is `Decimal` server-side (`db.Numeric`), serialized as string by Marshmallow `as_string=True`, parsed to `float` in dashboard summary, and `parseFloat` on the JS side.
  - Movement payload `{id, kind, fecha, concepto, monto, label, icon, color}` — same in `recent`, `movimientos`, `categoria_detalle.movimientos`.
  - `byCat` items `{id, label, icon, color, value, pct}` — used in `Dashboard` and `Budgets`.
  - `summary.history6m` is `[{name, ingresos, gastos}]` — matches what the prototype's `BarChart` consumes.
  - Frontend `FP_SCREEN` values: `dashboard | category | history | metas | presupuestos` — matched in `main.jsx` and in the route `render_template` calls.

- **No placeholders.** All code blocks are full implementations; no "TODO" / "fill in details" lines.

- **Auth.** All `/api/v1/finanzas-personales/*` use `@require_auth`. The middleware sets `g.current_user` and `g.tenant_id`; we read `g.current_user.id` for `user_id`.

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-29-finanzas-personales.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
