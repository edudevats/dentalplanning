# Finanzas Personales — Dashboard v2 Design

**Date:** 2026-05-03  
**Status:** Approved  
**Scope:** Dashboard rediseñado con vista Mes/Año, saldo acumulado anual con fondo de apertura, resumen de ingresos clínica, y sidebar independiente.

---

## 1. Contexto y objetivos

El módulo `finanzas_personales` ya existe y funciona (ingresos, gastos, categorías, presupuestos, metas). El problema actual:

- El sidebar enlaza a `/dashboard` (clínica), brincando al usuario fuera del sistema
- No hay vista anual ni acumulado de saldo
- No hay resumen de ingresos del consultorio en el contexto personal
- Faltan varios widgets de valor (fuentes de ingreso, tasa de ahorro, proyección)

**Objetivos de esta iteración:**
1. Hacer el sistema completamente independiente (navegación propia)
2. Agregar saldo acumulado anual con fondo de apertura carry-over entre años
3. Toggle Mes / Año en el dashboard
4. Resumen del ingreso clínico como tarjeta simple en vista mensual
5. Nuevos widgets: ingresos por fuente, sparkline tasa de ahorro, proyección de cierre, días de reserva

---

## 2. Modelo de datos

### Nueva tabla: `saldos_iniciales`

```sql
CREATE TABLE saldos_iniciales (
    id          INTEGER PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    año         INTEGER NOT NULL,
    monto       NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL,
    UNIQUE (tenant_id, user_id, año)
);
CREATE INDEX ix_saldo_inicial_user ON saldos_iniciales (tenant_id, user_id);
```

**Regla de negocio:** El monto puede ser positivo (sobrante del año anterior) o negativo (deuda arrastrada). Si no existe un registro para el año en curso, se asume `monto = 0`.

### Modelo SQLAlchemy: `SaldoInicial` en `app/finanzas_personales/models.py`

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

---

## 3. Backend

### 3.1 Cambios en `services.py`

#### `build_dashboard_summary` — nuevos campos en el response

Agrega 3 campos al dict existente (no rompe nada):

| Campo nuevo | Descripción |
|---|---|
| `saldo_acumulado_ytd` | `saldo_inicial_año + ingresos YTD - gastos YTD` hasta fin del mes seleccionado |
| `ingreso_clinica` | Suma de `Ingreso.monto` (modelo `app.edr.models`) del mismo mes/año y tenant (0 si no hay datos EDR) |
| `tasa_ahorro_12m` | Lista de 12 dicts `{name, pct}` — porcentaje de ahorro de cada mes (0 si sin ingresos) |

#### Nueva función: `build_dashboard_anual(tenant_id, user_id, year) -> dict`

```
saldo_inicial        ← SaldoInicial donde año=year (0 si no existe)
ingresos_anuales     ← SUM(IngresoPersonal.monto) de ene-dic del año
gastos_anuales       ← SUM(GastoPersonal.monto) de ene-dic del año
balance_anual        ← ingresos_anuales - gastos_anuales
saldo_acumulado      ← saldo_inicial + balance_anual
ahorro_pct_anual     ← (balance_anual / ingresos_anuales * 100) si ingresos > 0 else 0

proyeccion_cierre:
  meses_transcurridos = meses con al menos un movimiento en el año
  si meses_transcurridos > 0:
    ritmo_mensual = balance_anual / meses_transcurridos
    meses_restantes = 12 - mes_actual
    proyeccion = saldo_acumulado + ritmo_mensual * meses_restantes
  else:
    proyeccion = saldo_acumulado

dias_reserva:
  gasto_diario_promedio = gastos_anuales / dias_transcurridos_en_año
  si gasto_diario_promedio > 0:
    dias_reserva = saldo_acumulado / gasto_diario_promedio
  else:
    dias_reserva = null

history12m: por cada mes enero-diciembre:
  {name, ingresos, gastos, balance, saldo_acum}
  meses con datos: saldo_acum[mes] = saldo_inicial + sum(balances mes 1..mes)
  meses futuros (sin movimientos): ingresos=null, gastos=null, balance=null, saldo_acum=null
  El frontend dibuja la línea punteada de proyección interpolando desde el último saldo_acum real hasta proyeccion_cierre

by_fuente: igual a by_cat pero para IngresoPersonal agrupado por FuenteIngreso
```

**Response completo `build_dashboard_anual`:**
```json
{
  "year": 2026,
  "saldo_inicial": 100000.0,
  "totales": {
    "ingresos": 0.0, "gastos": 0.0, "balance": 0.0, "ahorroPct": 0
  },
  "saldo_acumulado": 100000.0,
  "proyeccion_cierre": 100000.0,
  "dias_reserva": null,
  "history12m": [
    {"name": "Ene", "ingresos": 30000, "gastos": 20000, "balance": 10000, "saldo_acum": 110000},
    {"name": "Feb", "ingresos": null, "gastos": null, "balance": null, "saldo_acum": null}
  ],
  "by_fuente": [
    {"id": 1, "label": "Salario", "icon": "briefcase", "color": "#0891b2", "value": 25000, "pct": 83}
  ]
}
```

#### Nueva función: `cerrar_año(tenant_id, user_id, year) -> SaldoInicial`

Calcula el balance total del `year`, crea el registro `SaldoInicial` para `year+1`. Lanza `ValueError` si ya existe un `SaldoInicial` para `year+1` (protección contra doble cierre, sin importar el monto). El usuario puede sobrescribir manualmente via `POST /saldo-inicial`.

### 3.2 Nuevos endpoints en `routes.py`

| Método | Path | Descripción |
|---|---|---|
| `GET` | `/api/v1/finanzas-personales/dashboard/anual?year=Y` | Llama `build_dashboard_anual` |
| `POST` | `/api/v1/finanzas-personales/saldo-inicial` | Crea/actualiza `SaldoInicial` manualmente (body: `{año, monto}`) |
| `GET` | `/api/v1/finanzas-personales/saldo-inicial?year=Y` | Lee el saldo inicial de un año |
| `POST` | `/api/v1/finanzas-personales/cerrar-año` | Llama `cerrar_año` (body: `{año}`) |

---

## 4. Frontend

### 4.1 Sidebar (`Shell.jsx`) — navegación independiente

**Eliminar:** sección "PRINCIPAL" con enlace a `/dashboard`.

**Nueva estructura del sidebar:**

```
FINANZAS PERSONALES
  Estado de Resultados   /finanzas-personales
  Historial              /finanzas-personales/historial
  Presupuestos           /finanzas-personales/presupuestos
  Metas de ahorro        /finanzas-personales/metas

RESUMEN DENTAL             (sección colapsable, default: expandida)
  [tarjeta inline]  Ingresos del consultorio este mes: $X
  [enlace]          Ver ingresos completos → /ingresos  (badge "cambia sistema")

SISTEMA
  Ajustes            /ajustes
  Cambiar de Sistema /selector
```

La tarjeta inline "Ingresos del consultorio" carga el dato del endpoint mensual ampliado (`ingreso_clinica`). Si falla el fetch, muestra "---" sin error visible.

### 4.2 Dashboard — toggle Mes / Año

Nuevo componente `ViewToggle` en la cabecera (junto al `MonthSelector`/`YearSelector`):

```jsx
<ViewToggle value={view} onChange={setView} />
// view: 'mes' | 'año'
```

Cuando `view === 'año'`, el `MonthSelector` se reemplaza por un `YearSelector` (solo número de año, flechas ← →).

### 4.3 Vista Mes — cambios al `Dashboard.jsx` existente

**Fila de tarjetas:** pasa de 4 a 5 columnas en pantallas ≥1280px; en 1024-1279px se muestra 2+3.

| Tarjeta | Valor | Color/icono |
|---|---|---|
| Ingresos | igual que hoy | verde |
| Gastos | igual que hoy | neutral |
| Balance | igual que hoy | azul/rojo |
| Ahorro % | igual que hoy | azul |
| **Clínica este mes** | `ingreso_clinica` | gris azulado, icono `building-2` |

**Nueva banda "Posición financiera del año"** — después del InsightStrip:

```
┌─────────────────────────────────────────────────────────────────┐
│ Fondo inicial: $100,000  +  Ingresos YTD: $X  −  Gastos YTD: $X  =  Saldo: $X  [sparkline]
└─────────────────────────────────────────────────────────────────┘
```
Color del saldo: verde si > 0, rojo si < 0. El sparkline (12 puntos, tasa de ahorro mensual) se dibuja con el componente `Sparkline` nuevo en `Charts.jsx`.

**Sin cambios al resto** (donut, barra 6m, top categorías, últimos movimientos).

### 4.4 Vista Año — nuevo componente `DashboardAnual.jsx`

**Fila de tarjetas anuales (4):**

| Tarjeta | Valor |
|---|---|
| Ingresos del año | totales.ingresos |
| Gastos del año | totales.gastos |
| Saldo acumulado | saldo_acumulado (verde/rojo) |
| Proyección cierre | proyeccion_cierre con icono `trending-up/down` |

**Gráfica de saldo acumulado** (nuevo `LineChart` en `Charts.jsx`):
- Eje X: 12 meses
- Línea sólida: meses con datos reales
- Línea punteada: meses futuros (proyección lineal)
- Línea de referencia horizontal en Y=0 (para ver cuándo el saldo cruza el cero)

**Tabla de 12 meses:**
```
Mes | Ingresos | Gastos | Balance | Saldo Acumulado
```
Meses sin datos: celdas grises. Mes actual: fondo azul claro. Meses futuros: texto gris.

**Donut de ingresos por fuente** (reutiliza componente `Donut` + `CategoryLegend` de `Charts.jsx`).

**Botón "Cerrar año":**
- Visible cuando: el año seleccionado es el año actual y es diciembre, O el año seleccionado es un año pasado
- Al hacer clic: modal de confirmación con el monto calculado
- Al confirmar: POST `/cerrar-año`, luego recarga el dashboard del año siguiente

**Card "Días de reserva"** (si `dias_reserva !== null`):
> "Con tu saldo actual de $X puedes cubrir **N días** de gastos a tu ritmo actual."

### 4.5 Nuevos archivos

| Archivo | Contenido |
|---|---|
| `DashboardAnual.jsx` | Componente vista anual completo |
| `YearSelector.jsx` | Selector de año con flechas (reutilizable) |
| `ViewToggle.jsx` | Pill toggle Mes/Año |

### 4.6 Archivos modificados

| Archivo | Cambio |
|---|---|
| `Shell.jsx` | Nuevo sidebar sin link `/dashboard`, con sección RESUMEN DENTAL |
| `Dashboard.jsx` | 5ta tarjeta + banda YTD + sparkline; lógica del toggle carga `DashboardAnual` |
| `Charts.jsx` | `+LineChart`, `+Sparkline` |
| `api.jsx` | `+FP.dashboardAnual(year)`, `+FP.saldoInicial(year)`, `+FP.cerrarAño(año)` |
| `_shell.html` | Agrega `DashboardAnual.jsx`, `YearSelector.jsx`, `ViewToggle.jsx` |

---

## 5. Migración de base de datos

Una migración nueva: `add_saldo_inicial_table`.

No hay cambios destructivos. Las tablas existentes no se modifican.

---

## 6. Flujo de cierre de año

```
1. Usuario abre dashboard en vista Año con year=2025
2. Hace clic en "Cerrar año 2025"
3. Modal: "El balance de 2025 es +$100,000. Este monto se transferirá como fondo inicial de 2026. ¿Confirmar?"
4. POST /cerrar-año { año: 2025 }
5. Backend: calcula balance 2025, crea SaldoInicial(año=2026, monto=100000)
6. Frontend: redirige a dashboard Año 2026
7. Dashboard 2026 muestra fondo inicial $100,000 como punto de partida de la gráfica
```

Si el usuario ya tiene datos en 2026 (ingresos/gastos registrados) pero sin `SaldoInicial`, el saldo acumulado empieza en 0. El cierre lo puede hacer retroactivamente en cualquier momento.

---

## 7. Lo que NO cambia

- Modelos existentes: sin cambios
- Endpoints existentes: solo se amplía el response de `GET /dashboard` con 3 campos extra
- Pantallas existentes: historial, presupuestos, metas, categoría — sin cambios
- Lógica FEFO/FIFO del inventario — sin relación con este módulo
- Tests existentes: todos deben seguir pasando

---

## 8. Tests nuevos requeridos

| Archivo | Casos |
|---|---|
| `test_finanzas_personales_services.py` | `test_saldo_acumulado_con_fondo_inicial`, `test_saldo_acumulado_sin_fondo_inicial`, `test_cerrar_año_crea_saldo_siguiente`, `test_cerrar_año_no_sobreescribe_existente`, `test_proyeccion_cierre`, `test_dias_reserva` |
| `test_finanzas_personales_routes.py` | `test_dashboard_anual_endpoint`, `test_saldo_inicial_crud`, `test_cerrar_año_endpoint`, `test_dashboard_mensual_incluye_nuevos_campos` |
