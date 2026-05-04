# Finanzas Personales Dashboard v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar vista Mes/Año al dashboard de finanzas personales con saldo acumulado anual (fondo de apertura carry-over entre años), resumen de ingreso clínica, nuevos widgets (sparkline, proyección, días de reserva, ingresos por fuente), y sidebar totalmente independiente sin links al sistema dental.

**Architecture:** Nueva tabla `saldos_iniciales` (un registro por usuario/año) persiste el fondo de apertura. El servicio `build_dashboard_summary` se extiende con 3 campos no-breaking. Una nueva función `build_dashboard_anual` calcula los 12 meses del año. El frontend añade un toggle Mes/Año: en modo año monta `DashboardAnual.jsx`; en modo mes, el `Dashboard.jsx` existente con la banda YTD nueva. El sidebar `Shell.jsx` elimina el link al dashboard clínico y agrega una sección "RESUMEN DENTAL" con el total EDR del mes.

**Tech Stack:** Flask 2.x + SQLAlchemy + Marshmallow (backend), React 18 via babel-standalone + Lucide icons + SVG charts handrolled (frontend), pytest (tests).

---

## File Map

**Crear:**
- `tests/test_finanzas_personales_services.py` — tests de services (Tasks 2–4)
- `tests/test_finanzas_personales_routes.py` — tests de endpoints (Task 5)
- `app/static/js/finanzas_personales/ViewToggle.jsx` — pill toggle Mes/Año
- `app/static/js/finanzas_personales/YearSelector.jsx` — selector de año con flechas
- `app/static/js/finanzas_personales/DashboardAnual.jsx` — vista anual completa

**Modificar:**
- `app/finanzas_personales/models.py` — añadir `SaldoInicial`
- `app/finanzas_personales/schemas.py` — añadir `SaldoInicialSchema`
- `app/finanzas_personales/services.py` — nuevas funciones helper + `build_dashboard_anual` + `cerrar_año`
- `app/finanzas_personales/routes.py` — 4 endpoints nuevos
- `app/static/js/finanzas_personales/api.jsx` — 3 métodos nuevos en `FP`
- `app/static/js/finanzas_personales/Shell.jsx` — sidebar independiente
- `app/static/js/finanzas_personales/Charts.jsx` — `LineChart` + `Sparkline`
- `app/static/js/finanzas_personales/Dashboard.jsx` — 5ta tarjeta + banda YTD + toggle
- `app/templates/finanzas_personales/_shell.html` — incluir nuevos jsx

---

## Task 1: SaldoInicial — modelo, schema y migración

**Files:**
- Modify: `app/finanzas_personales/models.py`
- Modify: `app/finanzas_personales/schemas.py`

- [ ] **Step 1: Añadir `SaldoInicial` al final de `app/finanzas_personales/models.py`**

```python
class SaldoInicial(db.Model):
    __tablename__ = "saldos_iniciales"

    id         = db.Column(db.Integer, primary_key=True)
    tenant_id  = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    año        = db.Column(db.Integer, nullable=False)
    monto      = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "user_id", "año", name="uq_saldo_inicial_user_año"),
        db.Index("ix_saldo_inicial_user", "tenant_id", "user_id"),
    )
```

- [ ] **Step 2: Añadir `SaldoInicialSchema` al final de `app/finanzas_personales/schemas.py`**

```python
class SaldoInicialSchema(Schema):
    id         = fields.Int(dump_only=True)
    año        = fields.Int(required=True, validate=validate.Range(min=2000, max=2100))
    monto      = fields.Decimal(as_string=False, places=2, load_default=0)
    created_at = fields.DateTime(dump_only=True)
```

- [ ] **Step 3: Generar y aplicar la migración**

```bash
flask db migrate -m "add saldo inicial table"
flask db upgrade
```

Verificar que se creó la tabla:
```bash
python manage.py shell
# >>> from app.finanzas_personales.models import SaldoInicial
# >>> SaldoInicial.__table__.columns.keys()
# ['id', 'tenant_id', 'user_id', 'año', 'monto', 'created_at']
```

- [ ] **Step 4: Commit**

```bash
git add app/finanzas_personales/models.py app/finanzas_personales/schemas.py migrations/
git commit -m "feat: add SaldoInicial model and schema for annual carry-over"
```

---

## Task 2: Tres campos nuevos en `build_dashboard_summary`

**Files:**
- Create: `tests/test_finanzas_personales_services.py`
- Modify: `app/finanzas_personales/services.py`

- [ ] **Step 1: Crear `tests/test_finanzas_personales_services.py` con los tests de los 3 nuevos campos**

```python
from datetime import date
import pytest
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso, IngresoPersonal, GastoPersonal, SaldoInicial,
)
from app.finanzas_personales.services import build_dashboard_summary, seed_defaults_for_user
from app.edr.models import Ingreso


def _seed(db, tenant, user):
    seed_defaults_for_user(tenant.id, user.id)
    db.session.commit()


def test_saldo_acumulado_ytd_sin_fondo_inicial(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 1, 15), concepto="Salario enero", monto=30000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 1, 20), concepto="Renta", monto=10000,
    ))
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 3, 15), concepto="Salario marzo", monto=30000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 3, 20), concepto="Gastos marzo", monto=8000,
    ))
    db.session.commit()

    summary = build_dashboard_summary(tenant.id, user.id, 2026, 3)
    # saldo_inicial=0, ingresos ene+mar=60000, gastos ene+mar=18000 => 42000
    assert summary["saldo_acumulado_ytd"] == pytest.approx(42000.0)


def test_saldo_acumulado_ytd_con_fondo_inicial(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2026, monto=100000,
    ))
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 2, 10), concepto="Salario", monto=20000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 2, 15), concepto="Gastos", monto=5000,
    ))
    db.session.commit()

    summary = build_dashboard_summary(tenant.id, user.id, 2026, 2)
    # saldo_inicial=100000, ingresos=20000, gastos=5000 => 115000
    assert summary["saldo_acumulado_ytd"] == pytest.approx(115000.0)


def test_ingreso_clinica_cero_sin_datos_edr(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.commit()
    summary = build_dashboard_summary(tenant.id, user.id, 2026, 4)
    assert summary["ingreso_clinica"] == pytest.approx(0.0)


def test_ingreso_clinica_suma_del_mes(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(Ingreso(
        tenant_id=tenant.id, fecha=date(2026, 4, 5),
        nombre_tratamiento="Limpieza", monto=2000,
    ))
    db.session.add(Ingreso(
        tenant_id=tenant.id, fecha=date(2026, 4, 20),
        nombre_tratamiento="Ortodoncia", monto=5000,
    ))
    db.session.add(Ingreso(
        tenant_id=tenant.id, fecha=date(2026, 3, 15),
        nombre_tratamiento="Otro mes", monto=9999,
    ))
    db.session.commit()
    summary = build_dashboard_summary(tenant.id, user.id, 2026, 4)
    assert summary["ingreso_clinica"] == pytest.approx(7000.0)


def test_tasa_ahorro_12m_es_lista_de_12(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.commit()
    summary = build_dashboard_summary(tenant.id, user.id, 2026, 4)
    assert len(summary["tasa_ahorro_12m"]) == 12
    assert all("name" in d and "pct" in d for d in summary["tasa_ahorro_12m"])


def test_tasa_ahorro_12m_calcula_porcentaje(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 4, 10), concepto="Salario", monto=10000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 4, 15), concepto="Gastos", monto=2000,
    ))
    db.session.commit()
    summary = build_dashboard_summary(tenant.id, user.id, 2026, 4)
    abril_entry = next(d for d in summary["tasa_ahorro_12m"] if d["name"] == "Abr")
    assert abril_entry["pct"] == 80  # (10000-2000)/10000 * 100
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
pytest tests/test_finanzas_personales_services.py -v
```

Esperado: `AttributeError` o `KeyError` — `saldo_acumulado_ytd`, `ingreso_clinica`, `tasa_ahorro_12m` no existen en el response.

- [ ] **Step 3: Añadir los imports necesarios al inicio de `app/finanzas_personales/services.py`**

Al inicio del archivo, después de `from app.finanzas_personales.models import (...)`, añadir:

```python
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso,
    IngresoPersonal, GastoPersonal,
    PresupuestoCategoria, SaldoInicial,
)
from app.edr.models import Ingreso
from calendar import isleap
```

- [ ] **Step 4: Añadir las tres funciones helper antes de `build_dashboard_summary` en `services.py`**

```python
def _saldo_acumulado_ytd(tenant_id: int, user_id: int, year: int, month: int) -> float:
    si = SaldoInicial.query.filter_by(tenant_id=tenant_id, user_id=user_id, año=year).first()
    saldo_inicial = _money(si.monto) if si else 0.0
    ytd_start = date(year, 1, 1)
    ytd_end = _month_bounds(year, month)[1]
    ingresos = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= ytd_start, IngresoPersonal.fecha <= ytd_end,
    ).scalar())
    gastos = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= ytd_start, GastoPersonal.fecha <= ytd_end,
    ).scalar())
    return saldo_inicial + ingresos - gastos


def _ingreso_clinica(tenant_id: int, year: int, month: int) -> float:
    start, end = _month_bounds(year, month)
    return _money(db.session.query(func.coalesce(func.sum(Ingreso.monto), 0)).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.fecha >= start, Ingreso.fecha <= end,
    ).scalar())


def _tasa_ahorro_12m(tenant_id: int, user_id: int, year: int, month: int) -> list:
    month_names_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                      "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    months_back = []
    yy, mm = year, month
    for _ in range(12):
        months_back.append((yy, mm))
        yy, mm = _prev_month(yy, mm)
    months_back.reverse()
    result = []
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
        pct = round(((i - g) / i) * 100) if i > 0 else 0
        result.append({"name": month_names_es[mm - 1], "pct": pct})
    return result
```

- [ ] **Step 5: Añadir los 3 nuevos campos al final de `build_dashboard_summary`, antes del `return`**

Localizar el `return {` al final de `build_dashboard_summary` y añadir los campos al dict:

```python
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
        "saldo_acumulado_ytd": _saldo_acumulado_ytd(tenant_id, user_id, year, month),
        "ingreso_clinica": _ingreso_clinica(tenant_id, year, month),
        "tasa_ahorro_12m": _tasa_ahorro_12m(tenant_id, user_id, year, month),
    }
```

- [ ] **Step 6: Ejecutar tests y verificar que pasan**

```bash
pytest tests/test_finanzas_personales_services.py -v
```

Esperado: 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/finanzas_personales/services.py tests/test_finanzas_personales_services.py
git commit -m "feat: extend dashboard_summary with ytd balance, clinic income, and savings rate"
```

---

## Task 3: `build_dashboard_anual`

**Files:**
- Modify: `tests/test_finanzas_personales_services.py` (añadir tests)
- Modify: `app/finanzas_personales/services.py` (nueva función)

- [ ] **Step 1: Añadir tests de `build_dashboard_anual` al archivo de tests**

```python
from app.finanzas_personales.services import build_dashboard_anual


def test_dashboard_anual_sin_datos(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    result = build_dashboard_anual(tenant.id, user.id, 2026)
    assert result["year"] == 2026
    assert result["saldo_inicial"] == pytest.approx(0.0)
    assert result["totales"]["ingresos"] == pytest.approx(0.0)
    assert result["totales"]["gastos"] == pytest.approx(0.0)
    assert result["saldo_acumulado"] == pytest.approx(0.0)
    assert len(result["history12m"]) == 12
    assert result["by_fuente"] == []


def test_dashboard_anual_con_fondo_inicial(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2026, monto=100000,
    ))
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 1, 10), concepto="Salario", monto=30000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2026, 1, 15), concepto="Renta", monto=10000,
    ))
    db.session.commit()

    result = build_dashboard_anual(tenant.id, user.id, 2026)
    assert result["saldo_inicial"] == pytest.approx(100000.0)
    assert result["totales"]["ingresos"] == pytest.approx(30000.0)
    assert result["totales"]["gastos"] == pytest.approx(10000.0)
    # saldo_acumulado = 100000 + 30000 - 10000 = 120000
    assert result["saldo_acumulado"] == pytest.approx(120000.0)


def test_dashboard_anual_history12m_saldo_acumulado_progresivo(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2025, monto=50000,
    ))
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2025, 1, 5), concepto="Ene", monto=20000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2025, 1, 10), concepto="Ene", monto=5000,
    ))
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2025, 2, 5), concepto="Feb", monto=20000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2025, 2, 10), concepto="Feb", monto=8000,
    ))
    db.session.commit()

    result = build_dashboard_anual(tenant.id, user.id, 2025)
    ene = result["history12m"][0]
    feb = result["history12m"][1]
    # ene: saldo_acum = 50000 + 15000 = 65000
    assert ene["name"] == "Ene"
    assert ene["saldo_acum"] == pytest.approx(65000.0)
    # feb: saldo_acum = 65000 + 12000 = 77000
    assert feb["name"] == "Feb"
    assert feb["saldo_acum"] == pytest.approx(77000.0)


def test_dashboard_anual_by_fuente(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    fuente = FuenteIngreso.query.filter_by(
        tenant_id=tenant.id, user_id=user.id, nombre="Salario"
    ).first()
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2025, 3, 1), fuente_id=fuente.id, concepto="Salario", monto=15000,
    ))
    db.session.commit()
    result = build_dashboard_anual(tenant.id, user.id, 2025)
    assert len(result["by_fuente"]) >= 1
    salario = next(f for f in result["by_fuente"] if f["label"] == "Salario")
    assert salario["value"] == pytest.approx(15000.0)
    assert salario["pct"] == 100
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
pytest tests/test_finanzas_personales_services.py::test_dashboard_anual_sin_datos -v
```

Esperado: `ImportError` o `AttributeError` — `build_dashboard_anual` no existe aún.

- [ ] **Step 3: Añadir `build_dashboard_anual` a `services.py`**

Añadir después de `build_dashboard_summary`:

```python
def build_dashboard_anual(tenant_id: int, user_id: int, year: int) -> dict:
    today = date.today()
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    si = SaldoInicial.query.filter_by(tenant_id=tenant_id, user_id=user_id, año=year).first()
    saldo_inicial = _money(si.monto) if si else 0.0

    ingresos_anuales = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= year_start, IngresoPersonal.fecha <= year_end,
    ).scalar())
    gastos_anuales = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= year_start, GastoPersonal.fecha <= year_end,
    ).scalar())

    balance_anual = ingresos_anuales - gastos_anuales
    saldo_acumulado = saldo_inicial + balance_anual
    ahorro_pct = round((balance_anual / ingresos_anuales) * 100) if ingresos_anuales else 0

    # Proyección de cierre
    meses_con_datos = 0
    for mes in range(1, 13):
        ms, me = _month_bounds(year, mes)
        if ms > today:
            break
        has_mov = (
            db.session.query(IngresoPersonal.id).filter(
                IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
                IngresoPersonal.fecha >= ms, IngresoPersonal.fecha <= me,
            ).first() or
            db.session.query(GastoPersonal.id).filter(
                GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
                GastoPersonal.fecha >= ms, GastoPersonal.fecha <= me,
            ).first()
        )
        if has_mov:
            meses_con_datos += 1

    if meses_con_datos > 0:
        ritmo = balance_anual / meses_con_datos
        mes_actual = today.month if today.year == year else 12
        proyeccion_cierre = round(saldo_acumulado + ritmo * (12 - mes_actual), 2)
    else:
        proyeccion_cierre = round(saldo_acumulado, 2)

    # Días de reserva
    if today.year == year:
        dias_transcurridos = (today - year_start).days + 1
    else:
        dias_transcurridos = 366 if isleap(year) else 365
    gasto_diario = gastos_anuales / dias_transcurridos if dias_transcurridos > 0 else 0
    dias_reserva = round(saldo_acumulado / gasto_diario) if (gasto_diario > 0 and saldo_acumulado > 0) else None

    # History 12 meses con saldo acumulado progresivo
    month_names_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                      "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    history12m = []
    saldo_corriente = saldo_inicial
    for mes in range(1, 13):
        ms, me = _month_bounds(year, mes)
        if ms > today:
            history12m.append({
                "name": month_names_es[mes - 1],
                "ingresos": None, "gastos": None, "balance": None, "saldo_acum": None,
            })
        else:
            i = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
                IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
                IngresoPersonal.fecha >= ms, IngresoPersonal.fecha <= me,
            ).scalar())
            g = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
                GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
                GastoPersonal.fecha >= ms, GastoPersonal.fecha <= me,
            ).scalar())
            b = i - g
            saldo_corriente += b
            history12m.append({
                "name": month_names_es[mes - 1],
                "ingresos": i, "gastos": g, "balance": b, "saldo_acum": saldo_corriente,
            })

    # By fuente
    fuente_colors = ["#0891b2", "#059669", "#8b5cf6", "#f59e0b", "#ec4899"]
    fuente_rows = db.session.query(
        FuenteIngreso.id, FuenteIngreso.nombre, FuenteIngreso.icon,
        func.coalesce(func.sum(IngresoPersonal.monto), 0),
    ).outerjoin(
        IngresoPersonal,
        (IngresoPersonal.fuente_id == FuenteIngreso.id)
        & (IngresoPersonal.fecha >= year_start) & (IngresoPersonal.fecha <= year_end)
        & (IngresoPersonal.tenant_id == tenant_id) & (IngresoPersonal.user_id == user_id),
    ).filter(
        FuenteIngreso.tenant_id == tenant_id,
        FuenteIngreso.user_id == user_id,
        FuenteIngreso.activo.is_(True),
    ).group_by(FuenteIngreso.id).all()

    by_fuente = []
    for idx, (fid, nombre, icon, suma) in enumerate(fuente_rows):
        v = _money(suma)
        if v <= 0:
            continue
        by_fuente.append({
            "id": fid, "label": nombre, "icon": icon,
            "color": fuente_colors[idx % len(fuente_colors)],
            "value": v,
            "pct": round((v / ingresos_anuales) * 100) if ingresos_anuales else 0,
        })
    by_fuente.sort(key=lambda f: f["value"], reverse=True)

    return {
        "year": year,
        "saldo_inicial": saldo_inicial,
        "totales": {
            "ingresos": ingresos_anuales,
            "gastos": gastos_anuales,
            "balance": balance_anual,
            "ahorroPct": ahorro_pct,
        },
        "saldo_acumulado": saldo_acumulado,
        "proyeccion_cierre": proyeccion_cierre,
        "dias_reserva": dias_reserva,
        "history12m": history12m,
        "by_fuente": by_fuente,
    }
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
pytest tests/test_finanzas_personales_services.py -k "anual" -v
```

Esperado: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/finanzas_personales/services.py tests/test_finanzas_personales_services.py
git commit -m "feat: add build_dashboard_anual service function"
```

---

## Task 4: `cerrar_año`

**Files:**
- Modify: `tests/test_finanzas_personales_services.py`
- Modify: `app/finanzas_personales/services.py`

- [ ] **Step 1: Añadir tests de `cerrar_año`**

```python
from app.finanzas_personales.services import cerrar_año
import pytest


def test_cerrar_año_crea_saldo_siguiente(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2024, monto=50000,
    ))
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2024, 6, 1), concepto="Salario", monto=120000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2024, 6, 15), concepto="Gastos", monto=80000,
    ))
    db.session.commit()

    nuevo = cerrar_año(tenant.id, user.id, 2024)
    # 50000 (fondo 2024) + 120000 (ingresos) - 80000 (gastos) = 90000
    assert nuevo.año == 2025
    assert float(nuevo.monto) == pytest.approx(90000.0)

    saved = SaldoInicial.query.filter_by(
        tenant_id=tenant.id, user_id=user.id, año=2025
    ).first()
    assert saved is not None
    assert float(saved.monto) == pytest.approx(90000.0)


def test_cerrar_año_sin_fondo_inicial_usa_cero(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2023, 3, 1), concepto="Ingreso", monto=60000,
    ))
    db.session.add(GastoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2023, 3, 15), concepto="Gasto", monto=40000,
    ))
    db.session.commit()

    nuevo = cerrar_año(tenant.id, user.id, 2023)
    # 0 (sin fondo) + 60000 - 40000 = 20000
    assert nuevo.año == 2024
    assert float(nuevo.monto) == pytest.approx(20000.0)


def test_cerrar_año_no_sobreescribe_existente(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2026, monto=99999,
    ))
    db.session.commit()

    with pytest.raises(ValueError, match="2026"):
        cerrar_año(tenant.id, user.id, 2025)
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
pytest tests/test_finanzas_personales_services.py -k "cerrar" -v
```

Esperado: `ImportError` — `cerrar_año` no existe.

- [ ] **Step 3: Añadir `cerrar_año` a `services.py`**

```python
def cerrar_año(tenant_id: int, user_id: int, year: int) -> "SaldoInicial":
    existing = SaldoInicial.query.filter_by(
        tenant_id=tenant_id, user_id=user_id, año=year + 1,
    ).first()
    if existing:
        raise ValueError(
            f"Ya existe un saldo inicial para {year + 1}. "
            "Use el endpoint POST /saldo-inicial para sobrescribirlo manualmente."
        )

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    ingresos = _money(db.session.query(func.coalesce(func.sum(IngresoPersonal.monto), 0)).filter(
        IngresoPersonal.tenant_id == tenant_id, IngresoPersonal.user_id == user_id,
        IngresoPersonal.fecha >= year_start, IngresoPersonal.fecha <= year_end,
    ).scalar())
    gastos = _money(db.session.query(func.coalesce(func.sum(GastoPersonal.monto), 0)).filter(
        GastoPersonal.tenant_id == tenant_id, GastoPersonal.user_id == user_id,
        GastoPersonal.fecha >= year_start, GastoPersonal.fecha <= year_end,
    ).scalar())

    si_actual = SaldoInicial.query.filter_by(
        tenant_id=tenant_id, user_id=user_id, año=year
    ).first()
    saldo_apertura = _money(si_actual.monto) if si_actual else 0.0

    nuevo = SaldoInicial(
        tenant_id=tenant_id,
        user_id=user_id,
        año=year + 1,
        monto=saldo_apertura + ingresos - gastos,
    )
    db.session.add(nuevo)
    db.session.commit()
    return nuevo
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

```bash
pytest tests/test_finanzas_personales_services.py -k "cerrar" -v
```

Esperado: 3 tests PASS.

- [ ] **Step 5: Correr toda la suite de services**

```bash
pytest tests/test_finanzas_personales_services.py -v
```

Esperado: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add app/finanzas_personales/services.py tests/test_finanzas_personales_services.py
git commit -m "feat: add cerrar_año service with carry-over balance"
```

---

## Task 5: Cuatro endpoints nuevos

**Files:**
- Create: `tests/test_finanzas_personales_routes.py`
- Modify: `app/finanzas_personales/routes.py`
- Modify: `app/finanzas_personales/schemas.py` (DashboardQuerySchema needs year-only variant)

- [ ] **Step 1: Crear `tests/test_finanzas_personales_routes.py`**

```python
from datetime import date
import pytest
from app.finanzas_personales.models import (
    IngresoPersonal, GastoPersonal, SaldoInicial,
)
from app.finanzas_personales.services import seed_defaults_for_user


def _seed(client, auth_headers, db, tenant, user):
    seed_defaults_for_user(tenant.id, user.id)
    db.session.commit()


def test_dashboard_mensual_incluye_nuevos_campos(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    resp = client.get("/api/v1/finanzas-personales/dashboard?year=2026&month=3",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "saldo_acumulado_ytd" in data
    assert "ingreso_clinica" in data
    assert "tasa_ahorro_12m" in data
    assert len(data["tasa_ahorro_12m"]) == 12


def test_dashboard_anual_endpoint(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    resp = client.get("/api/v1/finanzas-personales/dashboard/anual?year=2026",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["year"] == 2026
    assert "saldo_inicial" in data
    assert "totales" in data
    assert "saldo_acumulado" in data
    assert "proyeccion_cierre" in data
    assert "history12m" in data
    assert len(data["history12m"]) == 12
    assert "by_fuente" in data


def test_dashboard_anual_año_invalido(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    resp = client.get("/api/v1/finanzas-personales/dashboard/anual?year=abc",
                      headers=auth_headers)
    assert resp.status_code == 400


def test_get_saldo_inicial_sin_datos(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    resp = client.get("/api/v1/finanzas-personales/saldo-inicial?year=2026",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["año"] == 2026
    assert data["monto"] == 0.0
    assert data["exists"] is False


def test_upsert_saldo_inicial_crea_nuevo(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    resp = client.post("/api/v1/finanzas-personales/saldo-inicial",
                       json={"año": 2026, "monto": 50000},
                       headers=auth_headers)
    assert resp.status_code == 201
    data = resp.get_json()
    assert float(data["monto"]) == pytest.approx(50000.0)


def test_upsert_saldo_inicial_actualiza_existente(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2026, monto=10000,
    ))
    db.session.commit()
    resp = client.post("/api/v1/finanzas-personales/saldo-inicial",
                       json={"año": 2026, "monto": 75000},
                       headers=auth_headers)
    assert resp.status_code == 201
    assert float(resp.get_json()["monto"]) == pytest.approx(75000.0)


def test_cerrar_año_endpoint_ok(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    db.session.add(IngresoPersonal(
        tenant_id=tenant.id, user_id=user.id,
        fecha=date(2024, 5, 1), concepto="X", monto=10000,
    ))
    db.session.commit()
    resp = client.post("/api/v1/finanzas-personales/cerrar-año",
                       json={"año": 2024},
                       headers=auth_headers)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["año_siguiente"] == 2025
    assert data["monto"] == pytest.approx(10000.0)


def test_cerrar_año_endpoint_conflicto(app, client, db, tenant_and_user, auth_headers):
    tenant, user = tenant_and_user
    _seed(client, auth_headers, db, tenant, user)
    db.session.add(SaldoInicial(
        tenant_id=tenant.id, user_id=user.id, año=2025, monto=99,
    ))
    db.session.commit()
    resp = client.post("/api/v1/finanzas-personales/cerrar-año",
                       json={"año": 2024},
                       headers=auth_headers)
    assert resp.status_code == 409
```

- [ ] **Step 2: Ejecutar y verificar que falla**

```bash
pytest tests/test_finanzas_personales_routes.py -v
```

Esperado: 404 / AttributeError — los endpoints no existen.

- [ ] **Step 3: Actualizar los imports en `routes.py`**

Reemplazar el bloque de imports en `app/finanzas_personales/routes.py`:

```python
from flask import Blueprint, request, jsonify, g
from datetime import date
from marshmallow import ValidationError

from app.extensions import db
from app.middleware.tenant import require_auth
from app.finanzas_personales.models import (
    CategoriaPersonal, FuenteIngreso,
    IngresoPersonal, GastoPersonal,
    PresupuestoCategoria, MetaAhorro, SaldoInicial,
)
from app.finanzas_personales.schemas import (
    CategoriaPersonalSchema, FuenteIngresoSchema,
    IngresoPersonalSchema, GastoPersonalSchema,
    PresupuestoCategoriaSchema, MetaAhorroSchema,
    DashboardQuerySchema, SaldoInicialSchema,
)
from app.finanzas_personales.services import (
    seed_defaults_for_user, build_dashboard_summary,
    list_movements, build_category_detail, _month_bounds,
    build_dashboard_anual, cerrar_año,
)
```

- [ ] **Step 4: Añadir los 4 endpoints nuevos a `routes.py`** (al final, antes de los endpoints de metas)

```python
# ── Dashboard anual ────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/dashboard/anual", methods=["GET"])
@require_auth
def dashboard_anual():
    tenant_id, user_id = _scope()
    try:
        year = int(request.args.get("year", date.today().year))
        if not (2000 <= year <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"errors": {"year": ["Año inválido"]}}), 400
    seed_defaults_for_user(tenant_id, user_id)
    return jsonify(build_dashboard_anual(tenant_id, user_id, year))


# ── Saldo inicial ──────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/saldo-inicial", methods=["GET"])
@require_auth
def get_saldo_inicial():
    tenant_id, user_id = _scope()
    try:
        year = int(request.args.get("year", date.today().year))
        if not (2000 <= year <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"errors": {"year": ["Año inválido"]}}), 400
    si = SaldoInicial.query.filter_by(tenant_id=tenant_id, user_id=user_id, año=year).first()
    if not si:
        return jsonify({"año": year, "monto": 0.0, "exists": False})
    return jsonify({**SaldoInicialSchema().dump(si), "exists": True})


@finanzas_personales_bp.route("/saldo-inicial", methods=["POST"])
@require_auth
def upsert_saldo_inicial():
    tenant_id, user_id = _scope()
    data = request.get_json() or {}
    try:
        año = int(data.get("año", 0))
        monto = float(data.get("monto", 0))
        if not (2000 <= año <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"errors": {"año": ["Año o monto inválido"]}}), 400
    si = SaldoInicial.query.filter_by(tenant_id=tenant_id, user_id=user_id, año=año).first()
    if si:
        si.monto = monto
    else:
        si = SaldoInicial(tenant_id=tenant_id, user_id=user_id, año=año, monto=monto)
        db.session.add(si)
    db.session.commit()
    return jsonify(SaldoInicialSchema().dump(si)), 201


# ── Cierre de año ──────────────────────────────────────────────────────────

@finanzas_personales_bp.route("/cerrar-año", methods=["POST"])
@require_auth
def cerrar_año_endpoint():
    tenant_id, user_id = _scope()
    data = request.get_json() or {}
    try:
        año = int(data.get("año", 0))
        if not (2000 <= año <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"errors": {"año": ["Año inválido"]}}), 400
    try:
        nuevo = cerrar_año(tenant_id, user_id, año)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"año_siguiente": año + 1, "monto": float(nuevo.monto)}), 201
```

- [ ] **Step 5: Ejecutar y verificar que pasan**

```bash
pytest tests/test_finanzas_personales_routes.py -v
```

Esperado: todos PASS.

- [ ] **Step 6: Correr toda la suite de tests**

```bash
pytest -v
```

Esperado: todos PASS (incluyendo los tests existentes de otros módulos).

- [ ] **Step 7: Commit**

```bash
git add app/finanzas_personales/routes.py tests/test_finanzas_personales_routes.py
git commit -m "feat: add annual dashboard, saldo-inicial, and cerrar-año endpoints"
```

---

## Task 6: `api.jsx` — tres métodos nuevos

**Files:**
- Modify: `app/static/js/finanzas_personales/api.jsx`

- [ ] **Step 1: Añadir los tres métodos al objeto `FP` antes del cierre `};`**

```js
  dashboardAnual: (year) => fpRequest(`/dashboard/anual?year=${year}`),
  getSaldoInicial: (year) => fpRequest(`/saldo-inicial?year=${year}`),
  upsertSaldoInicial: (año, monto) =>
    fpRequest('/saldo-inicial', { method: 'POST', body: JSON.stringify({ año, monto }) }),
  cerrarAño: (año) =>
    fpRequest('/cerrar-año', { method: 'POST', body: JSON.stringify({ año }) }),
```

- [ ] **Step 2: Verificar que el servidor levanta sin error**

```bash
python manage.py runserver --port 5000
```

Abrir `http://localhost:5000/finanzas-personales` — debe cargar sin error de consola JS.

- [ ] **Step 3: Commit**

```bash
git add app/static/js/finanzas_personales/api.jsx
git commit -m "feat: add dashboardAnual, saldoInicial, cerrarAño to FP api client"
```

---

## Task 7: `Shell.jsx` — sidebar independiente

**Files:**
- Modify: `app/static/js/finanzas_personales/Shell.jsx`

- [ ] **Step 1: Reemplazar el contenido completo de `Shell.jsx`**

```jsx
const SIDEBAR_W = 256;

function ClinicIncomeWidget() {
  const [amount, setAmount] = React.useState(null);
  React.useEffect(() => {
    const today = new Date();
    FP.dashboard(today.getFullYear(), today.getMonth() + 1)
      .then(s => setAmount(s.ingreso_clinica))
      .catch(() => {});
  }, []);
  return (
    <div style={{
      margin: '4px 0', padding: '10px 12px', background: '#f8fafc',
      borderRadius: 8, border: '1px solid #e2e8f0',
    }}>
      <div style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)', marginBottom: 2 }}>
        Ingresos consultorio (este mes)
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: '#164e63', fontFamily: 'var(--font-body)' }}>
        {amount === null ? '---' : fmt(amount)}
      </div>
    </div>
  );
}

function Sidebar({ active = '/finanzas-personales' }) {
  const [dentalOpen, setDentalOpen] = useState(true);

  const fpItems = [
    { icon: 'piggy-bank',  label: 'Estado de Resultados', href: '/finanzas-personales' },
    { icon: 'list',        label: 'Historial',             href: '/finanzas-personales/historial' },
    { icon: 'wallet',      label: 'Presupuestos',          href: '/finanzas-personales/presupuestos' },
    { icon: 'target',      label: 'Metas de ahorro',       href: '/finanzas-personales/metas' },
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
        {/* FINANZAS PERSONALES */}
        <div>
          <div style={{ padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'var(--font-body)' }}>
            Finanzas Personales
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {fpItems.map(it => {
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

        {/* RESUMEN DENTAL */}
        <div>
          <button
            onClick={() => setDentalOpen(o => !o)}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              width: '100%', padding: '0 12px', marginBottom: dentalOpen ? 8 : 0,
              fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8',
              textTransform: 'uppercase', fontFamily: 'var(--font-body)',
              background: 'transparent', border: 'none', cursor: 'pointer',
            }}
          >
            Resumen Dental
            <Icon name={dentalOpen ? 'chevron-up' : 'chevron-down'} size={12} color="#94a3b8" />
          </button>
          {dentalOpen && (
            <div style={{ padding: '0 4px' }}>
              <ClinicIncomeWidget />
              <a href="/ingresos" style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', marginTop: 4,
                borderRadius: 8, fontSize: 13, fontWeight: 500, fontFamily: 'var(--font-body)',
                color: '#475569', textDecoration: 'none',
              }}>
                <Icon name="external-link" size={14} color="#94a3b8" />
                Ver ingresos completos
                <span style={{ fontSize: 10, background: '#fef9c3', color: '#92400e', borderRadius: 4, padding: '1px 5px', marginLeft: 'auto' }}>
                  cambia sistema
                </span>
              </a>
            </div>
          )}
        </div>

        {/* SISTEMA */}
        <div>
          <div style={{ padding: '0 12px', marginBottom: 8, fontSize: 11, fontWeight: 600, letterSpacing: '.06em', color: '#94a3b8', textTransform: 'uppercase', fontFamily: 'var(--font-body)' }}>
            Sistema
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            <li>
              <a href="/ajustes" style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 8,
                fontSize: 14, fontWeight: 500, fontFamily: 'var(--font-body)', textDecoration: 'none',
                color: '/ajustes' === active ? '#0e7490' : '#475569',
                background: '/ajustes' === active ? '#ecfeff' : 'transparent',
              }}>
                <Icon name="settings" size={18} />Ajustes
              </a>
            </li>
          </ul>
        </div>
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
        Cerrar sesion
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

- [ ] **Step 2: Verificar en el navegador**

Abrir `http://localhost:5000/finanzas-personales`. Verificar:
- El sidebar NO tiene el enlace "Dashboard" de la clínica
- Aparece la sección "RESUMEN DENTAL" colapsable
- El widget muestra "---" o el monto de la clínica
- El enlace "Ver ingresos completos" tiene el badge amarillo "cambia sistema"

- [ ] **Step 3: Commit**

```bash
git add app/static/js/finanzas_personales/Shell.jsx
git commit -m "feat: make finanzas personales sidebar fully independent"
```

---

## Task 8: `ViewToggle.jsx` y `YearSelector.jsx`

**Files:**
- Create: `app/static/js/finanzas_personales/ViewToggle.jsx`
- Create: `app/static/js/finanzas_personales/YearSelector.jsx`

- [ ] **Step 1: Crear `ViewToggle.jsx`**

```jsx
function ViewToggle({ value, onChange }) {
  return (
    <div style={{
      display: 'inline-flex', background: '#f1f5f9', borderRadius: 8, padding: 3, gap: 0,
    }}>
      {['mes', 'año'].map(v => (
        <button
          key={v}
          onClick={() => onChange(v)}
          style={{
            padding: '6px 18px', borderRadius: 6, border: 'none', cursor: 'pointer',
            fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
            background: value === v ? '#fff' : 'transparent',
            color: value === v ? '#0e7490' : '#64748b',
            boxShadow: value === v ? '0 1px 3px rgb(0 0 0 / .1)' : 'none',
            transition: 'all .15s',
          }}
        >
          {v === 'mes' ? 'Mes' : 'Año'}
        </button>
      ))}
    </div>
  );
}

Object.assign(window, { ViewToggle });
```

- [ ] **Step 2: Crear `YearSelector.jsx`**

```jsx
function YearSelector({ year, onChange }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '4px 8px',
    }}>
      <button
        onClick={() => onChange(year - 1)}
        style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: '4px 6px', color: '#475569', borderRadius: 4 }}
      >
        <Icon name="chevron-left" size={16} />
      </button>
      <span style={{
        fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-body)',
        color: '#164e63', minWidth: 44, textAlign: 'center',
      }}>
        {year}
      </span>
      <button
        onClick={() => onChange(year + 1)}
        style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: '4px 6px', color: '#475569', borderRadius: 4 }}
      >
        <Icon name="chevron-right" size={16} />
      </button>
    </div>
  );
}

Object.assign(window, { YearSelector });
```

- [ ] **Step 3: Commit**

```bash
git add app/static/js/finanzas_personales/ViewToggle.jsx app/static/js/finanzas_personales/YearSelector.jsx
git commit -m "feat: add ViewToggle and YearSelector components"
```

---

## Task 9: `Charts.jsx` — `LineChart` y `Sparkline`

**Files:**
- Modify: `app/static/js/finanzas_personales/Charts.jsx`

- [ ] **Step 1: Añadir `Sparkline` y `LineChart` al final de `Charts.jsx`, antes de `Object.assign(window, ...)`**

```jsx
function Sparkline({ data, width = 120, height = 32, color = '#0e7490' }) {
  if (!data || data.length < 2) return null;
  const values = data.map(d => d.pct);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 2 - ((v - min) / range) * (height - 8);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

function LineChart({ data, height = 240 }) {
  // data: [{name, saldo_acum: number|null}]
  const W = 520, H = height, PL = 72, PR = 16, PT = 12, PB = 28;
  const chartW = W - PL - PR;
  const chartH = H - PT - PB;

  const realData = data.filter(d => d.saldo_acum !== null);
  if (realData.length === 0) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: 13, fontFamily: 'var(--font-body)' }}>
        Sin datos para mostrar
      </div>
    );
  }

  const values = realData.map(d => d.saldo_acum);
  const minV = Math.min(...values, 0);
  const maxV = Math.max(...values, 0);
  const range = maxV - minV || 1;

  const toX = (i) => PL + (i / 11) * chartW;
  const toY = (v) => PT + chartH - ((v - minV) / range) * chartH;
  const zeroY = toY(0);

  const realPath = data
    .map((d, i) => (d.saldo_acum !== null ? `${i === 0 || data[i - 1].saldo_acum === null ? 'M' : 'L'} ${toX(i)} ${toY(d.saldo_acum)}` : null))
    .filter(Boolean)
    .join(' ');

  const fmtY = (v) => {
    const a = Math.abs(v);
    if (a >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
    if (a >= 1000) return '$' + (v / 1000).toFixed(0) + 'k';
    return '$' + Math.round(v);
  };

  const yTicks = [minV, minV + range * 0.5, maxV].map(v => Math.round(v));

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible', display: 'block' }}>
      {/* Grid y zero line */}
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PL} y1={toY(v)} x2={W - PR} y2={toY(v)} stroke="#f1f5f9" strokeWidth={1} />
          <text x={PL - 6} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="#94a3b8" fontFamily="var(--font-body)">
            {fmtY(v)}
          </text>
        </g>
      ))}
      <line x1={PL} y1={zeroY} x2={W - PR} y2={zeroY} stroke="#e2e8f0" strokeWidth={1} strokeDasharray="4 2" />

      {/* Real line */}
      <path d={realPath} fill="none" stroke="#0891b2" strokeWidth={2} strokeLinejoin="round" />

      {/* Data points */}
      {data.map((d, i) => d.saldo_acum !== null && (
        <circle key={i} cx={toX(i)} cy={toY(d.saldo_acum)} r={3} fill="#0891b2" />
      ))}

      {/* Month labels */}
      {data.map((d, i) => (
        <text key={i} x={toX(i)} y={H - 4} textAnchor="middle" fontSize={9} fill="#94a3b8" fontFamily="var(--font-body)">
          {d.name}
        </text>
      ))}
    </svg>
  );
}
```

- [ ] **Step 2: Añadir `Sparkline` y `LineChart` al `Object.assign` existente**

Localizar la línea `Object.assign(window, { ... })` al final de `Charts.jsx` y agregar `Sparkline, LineChart` a ese objeto.

- [ ] **Step 3: Verificar que no hay errores de consola**

Refrescar `http://localhost:5000/finanzas-personales` y verificar consola JS sin errores.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/finanzas_personales/Charts.jsx
git commit -m "feat: add Sparkline and LineChart to Charts.jsx"
```

---

## Task 10: `Dashboard.jsx` — 5ta tarjeta, banda YTD y toggle

**Files:**
- Modify: `app/static/js/finanzas_personales/Dashboard.jsx`

- [ ] **Step 1: Reemplazar el componente `Dashboard` completo en `Dashboard.jsx`**

```jsx
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

function YTDBand({ saldoAcumuladoYtd, tasaAhorro12m }) {
  const saldoColor = saldoAcumuladoYtd >= 0 ? '#0e7490' : '#dc2626';
  return (
    <div style={{
      background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12,
      padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon name="calendar-range" size={16} color="#64748b" />
        <span style={{ fontSize: 12, color: '#64748b', fontFamily: 'var(--font-body)' }}>Posición del año</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: saldoColor, fontFamily: 'var(--font-body)' }}>
          Saldo acumulado: {fmt(saldoAcumuladoYtd)}
        </span>
        <span style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>
          (ingresos − gastos desde enero + fondo inicial)
        </span>
      </div>
      {tasaAhorro12m && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: '#94a3b8', fontFamily: 'var(--font-body)' }}>Ahorro 12m</span>
          <Sparkline data={tasaAhorro12m} width={100} height={28} color="#0891b2" />
        </div>
      )}
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

function DashboardMes({ year, month, onChangeDate }) {
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
  const clinicColor = '#475569';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <InsightStrip insight={summary.insight} />

      <YTDBand saldoAcumuladoYtd={summary.saldo_acumulado_ytd} tasaAhorro12m={summary.tasa_ahorro_12m} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16 }}>
        <StatCard label="Ingresos"      value={fmt(t.ingresos)}           icon="trending-up"   valueColor="#065f46" sub="vs mes anterior" trend={summary.trends.ingresos} />
        <StatCard label="Gastos"        value={fmt(t.gastos)}             icon="trending-down" valueColor="#164e63" sub="vs mes anterior" trend={summary.trends.gastos} />
        <StatCard label="Balance"       value={fmt(t.balance)}            icon="wallet"        valueColor={t.balance >= 0 ? '#0e7490' : '#dc2626'} sub="ingresos − gastos" />
        <StatCard label="Ahorro"        value={t.ahorroPct + '%'}         icon="piggy-bank"    valueColor="#0e7490" sub="del ingreso del mes" />
        <StatCard label="Clínica (mes)" value={fmt(summary.ingreso_clinica || 0)} icon="building-2" valueColor={clinicColor} sub="ingresos consultorio" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Gastos por categoria</div>
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
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>Ultimos 6 meses</div>
          </div>
          <div style={{ padding: '4px 14px 16px' }}>
            <BarChart data={summary.history6m} height={220} />
          </div>
        </Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Top categorias</div>
          </div>
          <div style={{ padding: '4px 20px 16px' }}>
            {summary.byCat.slice(0, 5).map(c => <CategoryListItem key={c.id} cat={c} />)}
            {summary.byCat.length === 0 && <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin gastos este mes</div>}
          </div>
        </Card>
        <Card padding={0}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ultimos movimientos</div>
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

function Dashboard() {
  const today = new Date();
  const [view, setView] = useState('mes');
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63' }}>
            {view === 'mes' ? 'Estado de Resultados Personal' : 'Resumen Anual'}
          </div>
          <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 4, fontFamily: 'var(--font-body)' }}>
            {view === 'mes' ? 'Resumen del mes' : 'Balance acumulado del año'}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ViewToggle value={view} onChange={setView} />
          {view === 'mes'
            ? <MonthSelector year={year} month={month} onChange={(y, m) => { setYear(y); setMonth(m); }} />
            : <YearSelector year={year} onChange={setYear} />
          }
        </div>
      </div>

      {view === 'mes'
        ? <DashboardMes year={year} month={month} />
        : <DashboardAnual year={year} />
      }
    </div>
  );
}

Object.assign(window, { Dashboard, MonthSelector, InsightStrip, CategoryListItem, MovementRow, DashboardMes });
```

- [ ] **Step 2: Verificar en navegador**

Abrir `http://localhost:5000/finanzas-personales`. Verificar:
- Toggle "Mes / Año" aparece en la cabecera
- En vista Mes: aparece la 5ta tarjeta "Clínica (mes)" y la banda YTD con sparkline
- El toggle a "Año" no debe romper (aunque `DashboardAnual` no exista aún, debe mostrar `undefined` sin crash — se verifica en Task 11)

- [ ] **Step 3: Commit**

```bash
git add app/static/js/finanzas_personales/Dashboard.jsx
git commit -m "feat: add view toggle, clinic card, YTD band to monthly dashboard"
```

---

## Task 11: `DashboardAnual.jsx`

**Files:**
- Create: `app/static/js/finanzas_personales/DashboardAnual.jsx`

- [ ] **Step 1: Crear `DashboardAnual.jsx`**

```jsx
const { useEffect: useEffectAnual } = React;

function CerrarAñoModal({ year, monto, onConfirm, onCancel }) {
  const montoFmt = monto >= 0 ? `+${fmt(monto)}` : `−${fmt(Math.abs(monto))}`;
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgb(0 0 0 / .4)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{ background: '#fff', borderRadius: 16, padding: 32, maxWidth: 420, width: '90%', boxShadow: '0 20px 60px -10px rgb(0 0 0 / .25)' }}>
        <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-heading)', color: '#164e63', marginBottom: 12 }}>
          Cerrar año {year}
        </div>
        <div style={{ fontSize: 14, color: '#475569', fontFamily: 'var(--font-body)', lineHeight: 1.6, marginBottom: 24 }}>
          El saldo acumulado de <strong>{year}</strong> es <strong style={{ color: monto >= 0 ? '#059669' : '#dc2626' }}>{montoFmt}</strong>.
          Este monto se transferirá como fondo inicial del año <strong>{year + 1}</strong>. ¿Confirmar?
        </div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button onClick={onCancel} style={{
            padding: '10px 20px', borderRadius: 8, border: '1px solid #e2e8f0',
            background: '#fff', color: '#475569', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 14,
          }}>Cancelar</button>
          <button onClick={onConfirm} style={{
            padding: '10px 20px', borderRadius: 8, border: 'none',
            background: '#0891b2', color: '#fff', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 600,
          }}>Confirmar cierre</button>
        </div>
      </div>
    </div>
  );
}

function DashboardAnual({ year }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [cerrando, setCerrando] = useState(false);

  useEffectAnual(() => {
    setLoading(true);
    FP.dashboardAnual(year)
      .then(d => { setData(d); setLoading(false); window.lucide && window.lucide.createIcons(); })
      .catch(err => { console.error(err); setLoading(false); });
  }, [year]);

  if (loading || !data) {
    return <div style={{ padding: 60, textAlign: 'center', color: '#94a3b8', fontFamily: 'var(--font-body)' }}>Cargando…</div>;
  }

  const today = new Date();
  const canClose = (year < today.getFullYear()) || (year === today.getFullYear() && today.getMonth() === 11);

  const handleCerrar = () => {
    setCerrando(true);
    FP.cerrarAño(year)
      .then(() => { window.location.href = `/finanzas-personales?view=año&year=${year + 1}`; })
      .catch(err => { alert(err.message); setCerrando(false); });
  };

  const t = data.totales;
  const saldoColor = data.saldo_acumulado >= 0 ? '#0e7490' : '#dc2626';
  const proyColor = data.proyeccion_cierre >= 0 ? '#059669' : '#dc2626';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {showModal && (
        <CerrarAñoModal
          year={year}
          monto={data.saldo_acumulado}
          onConfirm={handleCerrar}
          onCancel={() => setShowModal(false)}
        />
      )}

      {/* Tarjetas anuales */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        <StatCard label="Ingresos del año"   value={fmt(t.ingresos)}            icon="trending-up"   valueColor="#065f46" sub={`ahorro ${t.ahorroPct}%`} />
        <StatCard label="Gastos del año"     value={fmt(t.gastos)}              icon="trending-down" valueColor="#164e63" sub="total anual" />
        <StatCard label="Saldo acumulado"    value={fmt(data.saldo_acumulado)}  icon="wallet"        valueColor={saldoColor} sub={`desde $${(data.saldo_inicial/1000).toFixed(0)}k fondo inicial`} />
        <StatCard label="Proyección cierre"  value={fmt(data.proyeccion_cierre)} icon="target"       valueColor={proyColor} sub="a ritmo actual" />
      </div>

      {/* Días de reserva */}
      {data.dias_reserva !== null && (
        <div style={{
          background: '#ecfeff', border: '1px solid #a5f3fc', borderRadius: 12,
          padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <Icon name="shield-check" size={20} color="#0e7490" />
          <span style={{ fontSize: 14, color: '#164e63', fontFamily: 'var(--font-body)' }}>
            Con tu saldo actual puedes cubrir <strong>{data.dias_reserva} días</strong> de gastos a tu ritmo actual.
          </span>
        </div>
      )}

      {/* Gráfica de saldo acumulado */}
      <Card padding={0}>
        <div style={{ padding: '20px 20px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Saldo acumulado {year}</div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2, fontFamily: 'var(--font-body)' }}>
              Fondo inicial: {fmt(data.saldo_inicial)}
            </div>
          </div>
          {canClose && (
            <button
              onClick={() => setShowModal(true)}
              disabled={cerrando}
              style={{
                padding: '8px 16px', borderRadius: 8, border: '1px solid #0891b2',
                background: '#fff', color: '#0891b2', cursor: 'pointer',
                fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 500,
              }}
            >
              Cerrar año {year}
            </button>
          )}
        </div>
        <div style={{ padding: '8px 16px 20px' }}>
          <LineChart data={data.history12m} height={220} />
        </div>
      </Card>

      {/* Tabla 12 meses + donut por fuente */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 20 }}>
        <Card padding={0}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>
            Detalle mensual {year}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                  {['Mes', 'Ingresos', 'Gastos', 'Balance', 'Saldo Acum.'].map(h => (
                    <th key={h} style={{ padding: '10px 16px', textAlign: h === 'Mes' ? 'left' : 'right', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.history12m.map((row, i) => {
                  const isFuture = row.ingresos === null;
                  const isCurrentMonth = !isFuture && i === (new Date().getMonth());
                  const style = {
                    color: isFuture ? '#cbd5e1' : '#164e63',
                    background: isCurrentMonth ? '#f0f9ff' : 'transparent',
                    borderBottom: '1px solid #f1f5f9',
                  };
                  return (
                    <tr key={i} style={style}>
                      <td style={{ padding: '10px 16px', fontWeight: isCurrentMonth ? 600 : 400 }}>{row.name}</td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', color: isFuture ? '#cbd5e1' : '#059669' }}>
                        {isFuture ? '---' : fmt(row.ingresos)}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', color: isFuture ? '#cbd5e1' : '#dc2626' }}>
                        {isFuture ? '---' : fmt(row.gastos)}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', color: isFuture ? '#cbd5e1' : (row.balance >= 0 ? '#059669' : '#dc2626') }}>
                        {isFuture ? '---' : (row.balance >= 0 ? '+' : '−') + fmt(Math.abs(row.balance))}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 600, color: isFuture ? '#cbd5e1' : (row.saldo_acum >= 0 ? '#0e7490' : '#dc2626') }}>
                        {isFuture ? '---' : fmt(row.saldo_acum)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card padding={0}>
          <div style={{ padding: '20px 20px 8px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, fontFamily: 'var(--font-heading)', color: '#164e63' }}>Ingresos por fuente</div>
          </div>
          {data.by_fuente.length > 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '12px 20px 20px' }}>
              <Donut data={data.by_fuente.map(f => ({ value: f.value, color: f.color }))} size={160} />
              <div style={{ flex: 1 }}>
                <CategoryLegend data={data.by_fuente.map(f => ({ label: f.label, value: f.value, color: f.color }))} />
              </div>
            </div>
          ) : (
            <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Sin ingresos registrados en {year}</div>
          )}
        </Card>
      </div>
    </div>
  );
}

Object.assign(window, { DashboardAnual, CerrarAñoModal });
```

- [ ] **Step 2: Verificar en navegador**

Abrir `http://localhost:5000/finanzas-personales`, cambiar al toggle "Año". Verificar:
- Tarjetas anuales muestran los valores (todos en 0 si no hay datos)
- La gráfica `LineChart` renderiza sin error
- La tabla de 12 meses aparece (meses futuros en gris)
- El donut de fuentes muestra "Sin ingresos" si no hay datos

- [ ] **Step 3: Commit**

```bash
git add app/static/js/finanzas_personales/DashboardAnual.jsx
git commit -m "feat: add annual dashboard view with cumulative balance chart and 12-month table"
```

---

## Task 12: `_shell.html` — incluir nuevos jsx

**Files:**
- Modify: `app/templates/finanzas_personales/_shell.html`

- [ ] **Step 1: Añadir las tres líneas de script después de `Charts.jsx` en `_shell.html`**

```html
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Atoms.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Charts.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/ViewToggle.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/YearSelector.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/api.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Shell.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/AddMovementModal.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Dashboard.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/DashboardAnual.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/screens.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/Budgets.jsx') }}"></script>
<script type="text/babel" src="{{ url_for('static', filename='js/finanzas_personales/main.jsx') }}"></script>
```

- [ ] **Step 2: Verificación final completa**

Abrir el servidor y probar el flujo completo:

1. `http://localhost:5000/finanzas-personales` — dashboard mes carga sin error
2. Toggle a "Año" — dashboard anual carga
3. `http://localhost:5000/finanzas-personales/historial` — sidebar muestra sección RESUMEN DENTAL, no tiene link "Dashboard" de clínica
4. `http://localhost:5000/finanzas-personales/presupuestos` — sidebar correcto
5. Consola JS sin errores en ninguna página

- [ ] **Step 3: Correr suite completa de tests**

```bash
pytest -v
```

Esperado: todos PASS.

- [ ] **Step 4: Commit final**

```bash
git add app/templates/finanzas_personales/_shell.html
git commit -m "feat: wire all new finanzas personales jsx files into shell template"
```
