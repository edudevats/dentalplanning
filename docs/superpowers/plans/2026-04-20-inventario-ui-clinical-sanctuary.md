# Inventario UI/UX "Clinical Sanctuary" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rediseñar las vistas de inventario (`/inventario/*`) aplicando el sistema de diseño "Clinical Sanctuary" (referencia en `gestor_de_inventario_m_dico/`) para transformar la experiencia cargada de spreadsheet actual en una interfaz editorial, calma y precisa, sin romper la API ni los modelos existentes.

**Architecture:** Trabajo exclusivamente en capa de presentación (Jinja templates + JS vanilla + tokens Tailwind). Se conservan intactos `app/inventario/models.py`, `schemas.py`, `services.py`. Se agregan **tres endpoints nuevos** en `routes.py` para los KPIs del dashboard (asset value, materials count, critical count) y el feed de movimientos recientes. Se añade un subset de tokens "Clinical Sanctuary" al `@theme` global en `base.html` (namespaced `--color-cs-*` para evitar conflictos con el palette cyan existente de otras secciones). Sidebar mantiene la estructura pero se reorganiza el grupo INVENTARIO.

**Tech Stack:** Flask + Jinja2, Tailwind v4 browser CDN, JS vanilla (sin bundler), Lucide icons, Google Fonts (Manrope + Inter añadidos), pytest (para nuevos endpoints).

**Design Spec:** [gestor_de_inventario_m_dico/clinical_ether/DESIGN.md](../../../gestor_de_inventario_m_dico/clinical_ether/DESIGN.md)

**Referencia visual:**
- Dashboard → `gestor_de_inventario_m_dico/dashboard_de_inventario/screen.png`
- Almacén → `gestor_de_inventario_m_dico/almac_n_principal/screen.png`
- Operatorios → `gestor_de_inventario_m_dico/gesti_n_de_operatorios/screen.png`
- Transferir → `gestor_de_inventario_m_dico/transferir_material/screen.png`

**Reglas del design system (resumen operativo):**
- Prohibido `border: 1px solid` para separar contenido. Usar cambios de `background-color` entre capas.
- Paleta jerarquizada: `surface` (#f7f9fb, base) → `surface_container` (#e8eff3, sectioning) → `surface_container_lowest` (#ffffff, cards activas).
- Primary `#005db6`, primary_dim `#0051a1`. NO verde de éxito — usar variantes primary. Error `#9f403d` / error_container a 30% opacity para alertas críticas.
- Display (headlines grandes) → Manrope. Body/utility → Inter.
- `rounded-lg` (0.5rem) para cards grandes. Nunca `none` o `sm` para contenedores principales.
- Tablas sin divisores: filas separadas por 8px de whitespace; hover = fondo `surface_container_low`.
- Text color `#2a3439` (on_surface) — nunca negro puro.
- Transiciones hover: mínimo 200ms ease-in-out.

**Nota sobre seguridad frontend:** Todo el JS nuevo usa `textContent`, `createElement` y `setAttribute` — **nunca `innerHTML`** (para evitar XSS con nombres de materiales maliciosos). Reutiliza helpers en `app/static/js/inventario/dom.js` (`addCell`, `makeOption`, `makeLink`, `clearChildren`). Para insertar iconos Lucide, crear el elemento `<i>` con `createElement` y `setAttribute("data-lucide", name)`, luego llamar a `lucide.createIcons()`.

**Nota sobre commits:** El proyecto no está inicializado como git. Cada paso "Commit" es un checkpoint opcional — si git está disponible, ejecutar; si no, tratar como hito de verificación manual.

---

## Fase 0 — Tokens de diseño y scaffolding

### Task 0.1: Añadir tokens Clinical Sanctuary al tema global

**Files:**
- Modify: `app/templates/base.html` (bloque `@theme` dentro de `<style type="text/tailwindcss">`)

**Contexto:** El proyecto ya usa tokens Tailwind custom (`--color-primary-*` = cyan). NO los tocamos — añadimos una paleta paralela prefijada `--color-cs-*` (Clinical Sanctuary) que usaremos solo en las 4 vistas de inventario. También agregamos `--font-cs-display` y `--font-cs-body`.

- [ ] **Step 1: Añadir import de Manrope + Inter al `<head>` de base.html**

Localizar en `app/templates/base.html` la línea con el link a Open Sans/Poppins y añadir inmediatamente después:

```html
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Añadir tokens `--color-cs-*` y fuentes al `@theme`**

Dentro del bloque `@theme { ... }` en `base.html`, al final (después de `--font-body`), añadir:

```css
      /* Clinical Sanctuary — Inventario */
      --color-cs-primary:         #005db6;
      --color-cs-primary-dim:     #0051a1;
      --color-cs-primary-container: #d5e3f7;
      --color-cs-on-primary:      #ffffff;
      --color-cs-on-primary-container: #001c3b;

      --color-cs-surface:              #f7f9fb;
      --color-cs-surface-bright:       #ffffff;
      --color-cs-surface-container-lowest: #ffffff;
      --color-cs-surface-container-low:    #f1f5f9;
      --color-cs-surface-container:    #e8eff3;
      --color-cs-surface-container-high: #dde6ec;

      --color-cs-on-surface:      #2a3439;
      --color-cs-on-surface-var:  #475569;
      --color-cs-outline:         #8a9199;
      --color-cs-outline-variant: #c1c7cd;

      --color-cs-error:           #9f403d;
      --color-cs-error-container: #fe8983;
      --color-cs-on-error-container: #410002;

      --font-cs-display: 'Manrope', system-ui, sans-serif;
      --font-cs-body:    'Inter', system-ui, sans-serif;
```

- [ ] **Step 3: Verificar manualmente que Tailwind genera las clases**

Arrancar el servidor:
```bash
python run.py
```
Abrir `http://localhost:5000/inventario`, abrir DevTools y ejecutar en consola:
```js
getComputedStyle(document.documentElement).getPropertyValue('--color-cs-primary').trim()
```
Expected: `#005db6`

Si el valor aparece, las clases `bg-cs-primary`, `text-cs-on-surface`, `font-cs-display` etc. ya están disponibles.

- [ ] **Step 4: Commit**

```bash
git add app/templates/base.html
git commit -m "feat(inventario): add Clinical Sanctuary design tokens to global theme"
```

---

### Task 0.2: Crear helper JS compartido para las vistas CS

**Files:**
- Create: `app/static/js/inventario/cs_shared.js`

**Contexto:** Módulo con utilidades reutilizables entre las 4 vistas CS: formato de moneda/números compactos, tiempo relativo, constructor de "status chip" y helper de iconos Lucide (para evitar innerHTML).

- [ ] **Step 1: Escribir el archivo**

`app/static/js/inventario/cs_shared.js`:
```javascript
// Utilities shared by the Clinical Sanctuary inventory views.
window.csShared = (function () {
  function currency(v) {
    if (v == null) return "—";
    if (v >= 1_000_000) return "$" + (v / 1_000_000).toFixed(2) + "M";
    if (v >= 1_000)     return "$" + (v / 1_000).toFixed(1)  + "K";
    return "$" + Number(v).toFixed(0);
  }

  function compactNumber(v) {
    if (v == null) return "—";
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
    if (v >= 1_000)     return (v / 1_000).toFixed(1)     + "k";
    return String(v);
  }

  function timeAgo(iso) {
    const then = new Date(iso);
    const diff = (Date.now() - then.getTime()) / 1000;
    if (diff < 60)      return Math.floor(diff)          + " secs ago";
    if (diff < 3600)    return Math.floor(diff / 60)     + " mins ago";
    if (diff < 86400)   return Math.floor(diff / 3600)   + " hours ago";
    return Math.floor(diff / 86400) + " days ago";
  }

  function statusChip(label, variant) {
    // variant: "stable" | "low" | "expiring" | "expired"
    const span = document.createElement("span");
    const tone = {
      stable:   "bg-cs-primary-container text-cs-on-primary-container",
      low:      "bg-cs-error-container/30 text-cs-error",
      expiring: "bg-cs-error-container/30 text-cs-error",
      expired:  "bg-cs-error-container/30 text-cs-error",
    }[variant] || "bg-cs-surface-container text-cs-on-surface-var";
    span.className = "inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold " + tone;
    span.textContent = label;
    return span;
  }

  // Safe Lucide icon constructor — creates <i data-lucide="...">. Call
  // lucide.createIcons() afterwards to hydrate it.
  function lucideIcon(name, extraClasses) {
    const i = document.createElement("i");
    i.setAttribute("data-lucide", name);
    i.className = extraClasses || "h-4 w-4";
    return i;
  }

  // Initials helper for avatar badges.
  function initials(nombre) {
    return (nombre || "")
      .split(/\s+/)
      .map(w => w[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }

  return { currency, compactNumber, timeAgo, statusChip, lucideIcon, initials };
})();
```

- [ ] **Step 2: Commit**

```bash
git add app/static/js/inventario/cs_shared.js
git commit -m "feat(inventario): add Clinical Sanctuary shared JS helpers"
```

---

### Task 0.3: Crear layout específico de inventario

**Files:**
- Create: `app/templates/inventario/_layout_cs.html`
- Create: `app/templates/inventario/_sidebar_cs.html`

**Contexto:** Las 4 vistas de inventario comparten chrome: topbar con búsqueda + Live indicator, sidebar con el grupo INVENTARIO destacado, botón "Transfer" prominente. Extraemos en un layout propio que hereda de `base.html` (no de `layout.html`, porque el topbar del Clinical Sanctuary es distinto — sin campana de notificaciones, con search global, botón Transfer degradado, etc.).

- [ ] **Step 1: Crear el sidebar partial**

`app/templates/inventario/_sidebar_cs.html`:
```html
<div class="flex flex-col h-full p-4">

  <div class="px-2 mb-6">
    <h2 class="font-cs-display text-lg font-bold text-cs-on-surface leading-tight">Inventory Central</h2>
    <p class="text-xs text-cs-on-surface-var mt-0.5" style="letter-spacing: 0.05rem;">Precision Management</p>
  </div>

  <a href="/inventario/compras" class="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold shadow-sm hover:opacity-95 transition-opacity mb-6">
    <i data-lucide="plus" class="h-4 w-4"></i>
    New Entry
  </a>

  <nav class="flex-1 space-y-0.5">
    <a href="/inventario" data-nav-path="/inventario" class="cs-nav-link flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-cs-on-surface-var transition-colors">
      <i data-lucide="layout-dashboard" class="h-[18px] w-[18px] shrink-0"></i>
      Dashboard
    </a>
    <a href="/inventario/almacen" data-nav-path="/inventario/almacen" class="cs-nav-link flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-cs-on-surface-var transition-colors">
      <i data-lucide="warehouse" class="h-[18px] w-[18px] shrink-0"></i>
      Main Warehouse
    </a>
    <a href="/inventario/operatorios" data-nav-path="/inventario/operatorios" class="cs-nav-link flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-cs-on-surface-var transition-colors">
      <i data-lucide="briefcase-medical" class="h-[18px] w-[18px] shrink-0"></i>
      Operatories
    </a>
    <a href="/inventario/movimientos" data-nav-path="/inventario/movimientos" class="cs-nav-link flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-cs-on-surface-var transition-colors">
      <i data-lucide="file-text" class="h-[18px] w-[18px] shrink-0"></i>
      Inventory Reports
    </a>
  </nav>

  <div class="mt-auto pt-4 space-y-0.5">
    <a href="/ajustes" class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-cs-on-surface-var hover:bg-cs-surface-container transition-colors">
      <i data-lucide="settings" class="h-[18px] w-[18px] shrink-0"></i>
      Settings
    </a>
    <a href="/dashboard" class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-cs-on-surface-var hover:bg-cs-surface-container transition-colors">
      <i data-lucide="arrow-left-circle" class="h-[18px] w-[18px] shrink-0"></i>
      Volver a Dental Planning
    </a>

    <div class="mt-3 flex items-center gap-3 px-3 py-2.5 rounded-lg bg-cs-surface-container-lowest">
      <div class="w-9 h-9 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-sm font-semibold font-cs-display shrink-0">
        <span data-user-initials>??</span>
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-semibold text-cs-on-surface truncate" data-user-name>Usuario</p>
        <p class="text-xs text-cs-on-surface-var truncate">View Profile</p>
      </div>
    </div>
  </div>
</div>

<style>
  .cs-nav-link:hover { background-color: var(--color-cs-surface-container); color: var(--color-cs-on-surface); }
  .cs-nav-link.active {
    background-color: var(--color-cs-surface-container-lowest);
    color: var(--color-cs-primary);
    font-weight: 600;
    box-shadow: inset 3px 0 0 0 var(--color-cs-primary);
  }
</style>
```

- [ ] **Step 2: Crear el layout**

`app/templates/inventario/_layout_cs.html`:
```html
{% extends "base.html" %}
{% block body %}
<div class="min-h-screen bg-cs-surface font-cs-body text-cs-on-surface">

  <div id="sidebar-overlay" class="fixed inset-0 bg-black/30 z-40 lg:hidden hidden"></div>

  <aside class="hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:w-64 bg-cs-surface-container-low z-30">
    {% include "inventario/_sidebar_cs.html" %}
  </aside>

  <aside id="mobile-sidebar" class="fixed inset-y-0 left-0 w-64 bg-cs-surface-container-low z-50 flex flex-col transform -translate-x-full transition-transform duration-200 ease-in-out lg:hidden">
    {% include "inventario/_sidebar_cs.html" %}
    <button id="sidebar-close" class="absolute top-4 right-4 p-1 rounded-lg text-cs-on-surface-var hover:text-cs-on-surface transition-colors cursor-pointer" aria-label="Cerrar menu">
      <i data-lucide="x" class="h-5 w-5"></i>
    </button>
  </aside>

  <header class="sticky top-0 z-20 h-16 backdrop-blur-xl bg-cs-surface-bright/80 lg:ml-64">
    <div class="flex items-center justify-between h-full px-4 lg:px-8 gap-4">
      <div class="flex items-center gap-3 flex-1 max-w-xl">
        <button id="sidebar-toggle" class="p-2 rounded-lg text-cs-on-surface-var hover:bg-cs-surface-container transition-colors cursor-pointer lg:hidden" aria-label="Abrir menu">
          <i data-lucide="menu" class="h-5 w-5"></i>
        </button>
        <div class="relative flex-1">
          <i data-lucide="search" class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-cs-outline"></i>
          <input id="cs-global-search" type="text" placeholder="Search inventory..." class="w-full pl-10 pr-3 py-2 rounded-lg bg-cs-surface-container text-sm placeholder:text-cs-outline focus:outline-none focus:ring-2 focus:ring-cs-primary/30 transition-all" />
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="hidden md:inline-flex items-center gap-2 text-xs font-medium text-cs-on-surface-var px-3">
          <span class="w-2 h-2 rounded-full bg-cs-primary animate-cs-pulse"></span>
          Live Updates Active
        </span>
        <a href="/inventario/transferir" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold shadow-sm hover:opacity-95 transition-opacity">
          <i data-lucide="arrow-right-left" class="h-4 w-4"></i>
          Transfer
        </a>
      </div>
    </div>
  </header>

  <main class="lg:ml-64 p-4 lg:p-10 max-w-7xl">
    {% block cs_content %}{% endblock %}
  </main>
</div>

{% block scripts %}{% endblock %}

<script>
  lucide.createIcons();
  if (typeof setActiveNav === 'function') setActiveNav();
  if (typeof initMobileSidebar === 'function') initMobileSidebar();
  if (!Auth.check()) { /* redirected */ }
  else if (typeof loadUserInfo === 'function') loadUserInfo();
</script>

<style>
  @keyframes cs-pulse {
    0%, 100% { opacity: 1.0; }
    50%      { opacity: 0.4; }
  }
  .animate-cs-pulse { animation: cs-pulse 2s ease-in-out infinite; }
</style>
{% endblock %}
```

- [ ] **Step 3: Verificar que el archivo parsea sin errores**

El layout todavía no está usado por ninguna ruta; su validación real ocurre en Task 2.1. Ejecutar:
```bash
python -c "from app import create_app; a = create_app(); print('OK')"
```
Expected: `OK` (sin error de Jinja).

- [ ] **Step 4: Commit**

```bash
git add app/templates/inventario/_layout_cs.html app/templates/inventario/_sidebar_cs.html
git commit -m "feat(inventario): add Clinical Sanctuary layout + sidebar partial"
```

---

## Fase 1 — Endpoints backend para dashboard KPIs

### Task 1.1: Endpoint `/dashboard` con KPIs consolidados

**Files:**
- Modify: `app/inventario/routes.py`
- Modify: `app/inventario/services.py` (añadir helper `calcular_kpis_dashboard`)
- Test: `tests/test_inventario_dashboard.py`

**Contexto:** El dashboard mockup exige 3 KPIs: Total Asset Value (sum of `lote_ubicacion.cantidad_restante * lote.precio_unitario` por tenant), Active Materials (count de Material con `en_inventario=True`), Critical Attention (count de materiales con stock < mínimo). Todo filtrado por `tenant_id`. Un solo endpoint para evitar N requests.

- [ ] **Step 1: Escribir el test fallido**

`tests/test_inventario_dashboard.py`:
```python
from datetime import date
from app.catalogo.models import Material
from app.inventario.models import Lote, LoteUbicacion, StockUbicacion


def test_dashboard_kpis_returns_aggregates(app, db, tenant_and_user, auth_headers, client):
    tenant, _user = tenant_and_user

    m1 = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    m2 = Material(tenant_id=tenant.id, nombre="Lidocaína", en_inventario=True)
    m3 = Material(tenant_id=tenant.id, nombre="Oculto", en_inventario=False)
    db.session.add_all([m1, m2, m3]); db.session.flush()

    lote = Lote(tenant_id=tenant.id, material_id=m1.id, cantidad_inicial=100,
                fecha_surtido=date.today(), precio_unitario=5.0)
    db.session.add(lote); db.session.flush()
    db.session.add(LoteUbicacion(lote_id=lote.id, operatorio_id=None, cantidad_restante=100))
    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=m1.id,
                                  operatorio_id=None, cantidad=100, minimo=150))
    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=m2.id,
                                  operatorio_id=None, cantidad=50, minimo=10))
    db.session.commit()

    r = client.get("/api/v1/inventario/dashboard", headers=auth_headers)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_asset_value"] == 500.0        # 100 * 5.0
    assert data["active_materials"] == 2             # m3 excluded
    assert data["critical_items"] == 1               # only m1 below minimum
```

- [ ] **Step 2: Run test — debe fallar**

```bash
pytest tests/test_inventario_dashboard.py::test_dashboard_kpis_returns_aggregates -v
```
Expected: FAIL — 404 (endpoint no existe).

- [ ] **Step 3: Añadir helper en `services.py`**

Al final de `app/inventario/services.py` añadir:
```python
def calcular_kpis_dashboard(tenant_id):
    from app.catalogo.models import Material
    from app.inventario.models import Lote, LoteUbicacion, StockUbicacion

    asset_value = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(LoteUbicacion.cantidad_restante * Lote.precio_unitario),
                0.0,
            )
        )
        .join(Lote, Lote.id == LoteUbicacion.lote_id)
        .filter(Lote.tenant_id == tenant_id, Lote.agotado.is_(False))
        .scalar()
    )

    active_materials = (
        db.session.query(db.func.count(Material.id))
        .filter(Material.tenant_id == tenant_id, Material.en_inventario.is_(True))
        .scalar()
    )

    critical_rows = (
        db.session.query(StockUbicacion.material_id)
        .filter(
            StockUbicacion.tenant_id == tenant_id,
            StockUbicacion.minimo.isnot(None),
            StockUbicacion.cantidad < StockUbicacion.minimo,
        )
        .distinct()
        .all()
    )

    return {
        "total_asset_value": float(asset_value or 0),
        "active_materials": int(active_materials or 0),
        "critical_items": len(critical_rows),
    }
```

- [ ] **Step 4: Añadir el endpoint en `routes.py`**

Al final de `app/inventario/routes.py` añadir:
```python
from app.inventario.services import calcular_kpis_dashboard as _kpis


@inventario_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard_kpis():
    return jsonify(_kpis(tenant_id=g.tenant_id))
```

- [ ] **Step 5: Run test — debe pasar**

```bash
pytest tests/test_inventario_dashboard.py::test_dashboard_kpis_returns_aggregates -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/inventario/routes.py app/inventario/services.py tests/test_inventario_dashboard.py
git commit -m "feat(inventario): add /dashboard endpoint with asset value, active materials, critical items"
```

---

### Task 1.2: Endpoint `/operatorios/distribucion`

**Files:**
- Modify: `app/inventario/routes.py`
- Test: `tests/test_inventario_dashboard.py`

**Contexto:** La card "Operatory Distribution" necesita por cada operatorio activo: `id`, `nombre`, `total_units` (sum de StockUbicacion.cantidad), `status` (`stable` si todos los stocks están OK, `restock_needed` si al menos uno está debajo del mínimo).

- [ ] **Step 1: Escribir el test fallido**

Añadir a `tests/test_inventario_dashboard.py`:
```python
def test_operatory_distribution(app, db, tenant_and_user, auth_headers, client):
    tenant, _user = tenant_and_user
    from app.inventario.models import Operatorio, StockUbicacion
    from app.catalogo.models import Material

    op1 = Operatorio(tenant_id=tenant.id, nombre="Alpha", orden=1, activo=True)
    op2 = Operatorio(tenant_id=tenant.id, nombre="Beta", orden=2, activo=True)
    db.session.add_all([op1, op2]); db.session.flush()

    mat = Material(tenant_id=tenant.id, nombre="Gasa", en_inventario=True)
    db.session.add(mat); db.session.flush()

    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=mat.id,
                                  operatorio_id=op1.id, cantidad=1240, minimo=100))
    db.session.add(StockUbicacion(tenant_id=tenant.id, material_id=mat.id,
                                  operatorio_id=op2.id, cantidad=50, minimo=100))
    db.session.commit()

    r = client.get("/api/v1/inventario/operatorios/distribucion", headers=auth_headers)
    assert r.status_code == 200
    body = r.get_json()
    by_name = {row["nombre"]: row for row in body}
    assert by_name["Alpha"]["total_units"] == 1240
    assert by_name["Alpha"]["status"] == "stable"
    assert by_name["Beta"]["total_units"] == 50
    assert by_name["Beta"]["status"] == "restock_needed"
```

- [ ] **Step 2: Run — debe fallar**

```bash
pytest tests/test_inventario_dashboard.py::test_operatory_distribution -v
```
Expected: FAIL (404).

- [ ] **Step 3: Añadir el endpoint**

En `app/inventario/routes.py`:
```python
@inventario_bp.route("/operatorios/distribucion", methods=["GET"])
@require_auth
def operatorios_distribucion():
    ops = Operatorio.query.filter_by(
        tenant_id=g.tenant_id, activo=True
    ).order_by(Operatorio.orden, Operatorio.nombre).all()

    result = []
    for op in ops:
        stocks = StockUbicacion.query.filter_by(
            tenant_id=g.tenant_id, operatorio_id=op.id
        ).all()
        total = sum(s.cantidad for s in stocks)
        needs_restock = any(
            s.minimo is not None and s.cantidad < s.minimo for s in stocks
        )
        result.append({
            "id": op.id,
            "nombre": op.nombre,
            "total_units": int(total),
            "status": "restock_needed" if needs_restock else "stable",
        })
    return jsonify(result)
```

- [ ] **Step 4: Run — debe pasar**

```bash
pytest tests/test_inventario_dashboard.py::test_operatory_distribution -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_dashboard.py
git commit -m "feat(inventario): add /operatorios/distribucion endpoint"
```

---

### Task 1.3: Endpoint `/movimientos/recientes`

**Files:**
- Modify: `app/inventario/routes.py`
- Test: `tests/test_inventario_dashboard.py`

**Contexto:** El feed "Recent Transfers" del dashboard muestra los últimos 5 movimientos con `material_nombre`, `origen_nombre`, `destino_nombre`, `cantidad`, `tipo` y `fecha`.

- [ ] **Step 1: Escribir el test**

Añadir a `tests/test_inventario_dashboard.py`:
```python
def test_movimientos_recientes(app, db, tenant_and_user, auth_headers, client):
    from datetime import datetime
    from app.catalogo.models import Material
    from app.inventario.models import MovimientoInventario, Operatorio

    tenant, user = tenant_and_user
    op = Operatorio(tenant_id=tenant.id, nombre="Alpha", orden=1, activo=True)
    mat = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    db.session.add_all([op, mat]); db.session.flush()

    mv = MovimientoInventario(
        tenant_id=tenant.id, material_id=mat.id, tipo="compra",
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=150, fecha=datetime.utcnow(), user_id=user.id,
    )
    db.session.add(mv); db.session.commit()

    r = client.get("/api/v1/inventario/movimientos/recientes", headers=auth_headers)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["material_nombre"] == "Guantes"
    assert items[0]["destino_nombre"] == "Alpha"
    assert items[0]["cantidad"] == 150
    assert items[0]["tipo"] == "compra"
```

- [ ] **Step 2: Run — debe fallar**

```bash
pytest tests/test_inventario_dashboard.py::test_movimientos_recientes -v
```
Expected: FAIL (404).

- [ ] **Step 3: Añadir el endpoint**

En `routes.py`:
```python
@inventario_bp.route("/movimientos/recientes", methods=["GET"])
@require_auth
def movimientos_recientes():
    movs = (
        MovimientoInventario.query.filter_by(tenant_id=g.tenant_id)
        .order_by(MovimientoInventario.fecha.desc()).limit(5).all()
    )
    if not movs:
        return jsonify([])

    mat_ids = {mv.material_id for mv in movs}
    op_ids = {mv.origen_operatorio_id for mv in movs if mv.origen_operatorio_id}
    op_ids |= {mv.destino_operatorio_id for mv in movs if mv.destino_operatorio_id}

    mats = {m.id: m.nombre for m in Material.query.filter(Material.id.in_(mat_ids)).all()}
    ops = {o.id: o.nombre for o in Operatorio.query.filter(Operatorio.id.in_(op_ids)).all()} if op_ids else {}

    return jsonify([{
        "id": mv.id, "tipo": mv.tipo, "cantidad": mv.cantidad,
        "fecha": mv.fecha.isoformat(),
        "material_id": mv.material_id,
        "material_nombre": mats.get(mv.material_id, ""),
        "origen_nombre": ops.get(mv.origen_operatorio_id, "Almacén") if mv.origen_operatorio_id else "Almacén",
        "destino_nombre": ops.get(mv.destino_operatorio_id, "Almacén") if mv.destino_operatorio_id else "Almacén",
    } for mv in movs])
```

- [ ] **Step 4: Run — toda la suite debe pasar**

```bash
pytest tests/test_inventario_dashboard.py -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_dashboard.py
git commit -m "feat(inventario): add /movimientos/recientes endpoint"
```

---

## Fase 2 — Dashboard redesign

### Task 2.1: Reescribir `dashboard.html` al estilo Clinical Sanctuary

**Files:**
- Modify: `app/templates/inventario/dashboard.html` (reescritura completa)

**Contexto:** El dashboard actual es una tabla + botones. El nuevo es un overview editorial: título "Overview", 3 KPI cards, card grande "Operatory Distribution", feed "Recent Transfers". La tabla de materiales se mueve a `/inventario/almacen` (Task 3.1).

- [ ] **Step 1: Reemplazar el contenido completo de `dashboard.html`**

```html
{% extends "inventario/_layout_cs.html" %}
{% block title %}Dashboard — Inventory Central{% endblock %}
{% block cs_content %}

<div class="space-y-8">

  <div class="flex items-start justify-between gap-4">
    <div>
      <h1 class="font-cs-display text-4xl font-bold text-cs-on-surface tracking-tight">Overview</h1>
      <p class="mt-1.5 text-sm text-cs-on-surface-var">Real-time inventory metrics across all facilities.</p>
    </div>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <article class="relative p-6 rounded-lg bg-cs-surface-container-lowest">
      <div class="flex items-start justify-between">
        <p class="text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var">Total Asset Value</p>
        <span class="inline-flex items-center justify-center w-9 h-9 rounded-md bg-cs-primary-container text-cs-on-primary-container">
          <i data-lucide="landmark" class="h-4 w-4"></i>
        </span>
      </div>
      <p class="mt-4 font-cs-display text-4xl font-bold text-cs-on-surface" data-kpi="asset-value">—</p>
      <p class="mt-2 text-xs font-medium text-cs-primary" data-kpi="asset-delta"></p>
    </article>

    <article class="relative p-6 rounded-lg bg-cs-surface-container-lowest">
      <div class="flex items-start justify-between">
        <p class="text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var">Active Materials</p>
        <span class="inline-flex items-center justify-center w-9 h-9 rounded-md bg-cs-surface-container text-cs-on-surface-var">
          <i data-lucide="layers" class="h-4 w-4"></i>
        </span>
      </div>
      <p class="mt-4 font-cs-display text-4xl font-bold text-cs-on-surface" data-kpi="active-count">—</p>
      <p class="mt-2 text-xs text-cs-on-surface-var" data-kpi="active-sub">—</p>
    </article>

    <article class="relative p-6 rounded-lg bg-cs-error-container/30">
      <div class="flex items-start justify-between">
        <p class="text-xs font-semibold uppercase tracking-widest text-cs-error">Critical Attention</p>
        <span class="inline-flex items-center justify-center w-9 h-9 rounded-md bg-cs-error-container/50 text-cs-error">
          <i data-lucide="triangle-alert" class="h-4 w-4"></i>
        </span>
      </div>
      <p class="mt-4 font-cs-display text-4xl font-bold text-cs-error" data-kpi="critical-count">—</p>
      <p class="mt-2 text-xs font-medium text-cs-error" data-kpi="critical-sub">Items below minimum threshold</p>
      <a href="/inventario/almacen?filtro=bajo" class="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-cs-error">Review Items <i data-lucide="arrow-right" class="h-3 w-3"></i></a>
    </article>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
    <section class="lg:col-span-2 p-6 rounded-lg bg-cs-surface-container">
      <div class="flex items-center justify-between mb-5">
        <h2 class="font-cs-display text-lg font-semibold text-cs-on-surface">Operatory Distribution</h2>
        <a href="/inventario/operatorios" class="text-xs font-semibold text-cs-primary inline-flex items-center gap-1">View Details <i data-lucide="arrow-up-right" class="h-3 w-3"></i></a>
      </div>
      <ul id="cs-operatory-list" class="space-y-2"></ul>
    </section>

    <section class="p-6 rounded-lg bg-cs-surface-container-lowest">
      <div class="flex items-center justify-between mb-5">
        <h2 class="font-cs-display text-lg font-semibold text-cs-on-surface">Recent Transfers</h2>
        <i data-lucide="arrow-left-right" class="h-4 w-4 text-cs-on-surface-var"></i>
      </div>
      <ul id="cs-recent-feed" class="space-y-4"></ul>
      <a href="/inventario/movimientos" class="mt-6 block text-center py-2.5 rounded-md bg-cs-primary-container text-cs-on-primary-container text-sm font-semibold hover:bg-cs-primary-container/80 transition-colors">View Full Log</a>
    </section>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_shared.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_dashboard.js') }}"></script>
{% endblock %}
```

- [ ] **Step 2: Iniciar servidor y verificar**

```bash
python run.py
```
Abrir `http://localhost:5000/inventario`. Expected: header "Overview" en Manrope, 3 KPI cards con placeholders "—", sidebar CS a la izquierda, topbar con search + Transfer.

- [ ] **Step 3: Commit**

```bash
git add app/templates/inventario/dashboard.html
git commit -m "feat(inventario): redesign dashboard with Clinical Sanctuary layout"
```

---

### Task 2.2: Poblar KPIs y feeds del dashboard con `cs_dashboard.js`

**Files:**
- Create: `app/static/js/inventario/cs_dashboard.js`

**Contexto:** Hace 3 fetches a los endpoints de Fase 1 y pinta los KPIs, la distribución de operatorios y el feed reciente. Usa helpers de `cs_shared.js` (incluido `lucideIcon` para evitar `innerHTML`).

- [ ] **Step 1: Escribir el script**

```javascript
(async function () {
  const { currency, compactNumber, timeAgo, statusChip, lucideIcon, initials } = window.csShared;
  const { clearChildren } = window.invDom;

  async function loadKpis() {
    const kpis = await invApi.get("/dashboard");
    document.querySelector('[data-kpi="asset-value"]').textContent = currency(kpis.total_asset_value);
    document.querySelector('[data-kpi="active-count"]').textContent = compactNumber(kpis.active_materials);
    document.querySelector('[data-kpi="active-sub"]').textContent = "Across all categories";
    document.querySelector('[data-kpi="critical-count"]').textContent = String(kpis.critical_items);
    document.querySelector('[data-kpi="critical-sub"]').textContent =
      kpis.critical_items === 0 ? "All items within threshold" : "Items below minimum threshold";
  }

  async function loadOperatoryDistribution() {
    const rows = await invApi.get("/operatorios/distribucion");
    const list = document.getElementById("cs-operatory-list");
    clearChildren(list);
    if (rows.length === 0) {
      const li = document.createElement("li");
      li.className = "text-sm text-cs-on-surface-var py-3 px-4";
      li.textContent = "No operatories yet.";
      list.appendChild(li);
      return;
    }
    rows.forEach((op, idx) => {
      const li = document.createElement("li");
      li.className = "flex items-center gap-4 p-4 rounded-md bg-cs-surface-container-lowest hover:bg-cs-surface-container-low transition-colors duration-200 cursor-pointer";
      li.addEventListener("click", () => { window.location.href = "/inventario/operatorios#" + op.id; });

      const badge = document.createElement("div");
      badge.className = "w-10 h-10 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-xs font-semibold font-cs-display shrink-0";
      badge.textContent = "O" + String(idx + 1).padStart(2, "0");

      const info = document.createElement("div");
      info.className = "flex-1 min-w-0";
      const title = document.createElement("p");
      title.className = "text-sm font-semibold text-cs-on-surface truncate";
      title.textContent = op.nombre;
      const subtitle = document.createElement("p");
      subtitle.className = "text-xs text-cs-on-surface-var truncate";
      subtitle.textContent = "Operatory";
      info.append(title, subtitle);

      const units = document.createElement("div");
      units.className = "text-right shrink-0";
      const unitsVal = document.createElement("p");
      unitsVal.className = "text-sm font-semibold text-cs-on-surface tabular-nums";
      unitsVal.textContent = compactNumber(op.total_units);
      const unitsLabel = document.createElement("p");
      unitsLabel.className = "text-[10px] uppercase tracking-widest text-cs-on-surface-var";
      unitsLabel.textContent = "Units";
      units.append(unitsVal, unitsLabel);

      const chip = statusChip(
        op.status === "stable" ? "Stable" : "Restock Needed",
        op.status === "stable" ? "stable"  : "low",
      );

      li.append(badge, info, units, chip);
      list.appendChild(li);
    });
  }

  async function loadRecentFeed() {
    const items = await invApi.get("/movimientos/recientes");
    const feed = document.getElementById("cs-recent-feed");
    clearChildren(feed);
    if (items.length === 0) {
      const li = document.createElement("li");
      li.className = "text-sm text-cs-on-surface-var";
      li.textContent = "No recent movements.";
      feed.appendChild(li);
      return;
    }
    items.forEach((mv) => {
      const li = document.createElement("li");
      li.className = "flex items-start gap-3";

      const iconWrap = document.createElement("div");
      iconWrap.className = "w-9 h-9 rounded-md bg-cs-surface-container text-cs-on-surface-var flex items-center justify-center shrink-0 mt-0.5";
      const iconName = {
        compra: "truck",
        transferencia: "arrow-right-left",
        ajuste: "sliders-horizontal",
      }[mv.tipo] || "package";
      iconWrap.appendChild(lucideIcon(iconName, "h-4 w-4"));

      const body = document.createElement("div");
      body.className = "flex-1 min-w-0";
      const title = document.createElement("p");
      title.className = "text-sm font-semibold text-cs-on-surface";
      let label;
      if (mv.tipo === "compra")         label = "Incoming Shipment";
      else if (mv.tipo === "ajuste")    label = "Stock Adjustment";
      else                              label = "Transfer: " + mv.destino_nombre;
      title.textContent = label;

      const detail = document.createElement("p");
      detail.className = "text-xs text-cs-on-surface-var mt-0.5";
      detail.textContent = mv.cantidad + "× " + mv.material_nombre;

      const when = document.createElement("p");
      when.className = "text-[10px] uppercase tracking-widest text-cs-on-surface-var mt-1";
      when.textContent = timeAgo(mv.fecha);

      body.append(title, detail, when);
      li.append(iconWrap, body);
      feed.appendChild(li);
    });
    if (window.lucide) lucide.createIcons();
  }

  try {
    await Promise.all([loadKpis(), loadOperatoryDistribution(), loadRecentFeed()]);
  } catch (err) {
    console.error("Dashboard load failed:", err);
  }
})();
```

- [ ] **Step 2: Verificar datos en navegador**

Si la DB está vacía, sembrar con:
```bash
python manage.py shell
```
```python
from app.extensions import db
from app.catalogo.models import Material
from app.inventario.models import Operatorio, StockUbicacion
# ajustar tenant_id a uno existente
db.session.add(Operatorio(tenant_id=1, nombre="Operatorio Alpha", orden=1, activo=True))
db.session.add(Operatorio(tenant_id=1, nombre="Operatorio Beta", orden=2, activo=True))
m = Material(tenant_id=1, nombre="Test Material", en_inventario=True)
db.session.add(m); db.session.flush()
db.session.add(StockUbicacion(tenant_id=1, material_id=m.id, operatorio_id=None, cantidad=100, minimo=10))
db.session.commit()
exit()
```
Recargar `/inventario`. Expected: "Active Materials" ≥ 1, lista de operatorios poblada.

- [ ] **Step 3: Commit**

```bash
git add app/static/js/inventario/cs_dashboard.js
git commit -m "feat(inventario): wire Clinical Sanctuary dashboard data loading"
```

---

## Fase 3 — Vista "Almacén Principal"

### Task 3.1: Crear ruta `/inventario/almacen`, template y JS

**Files:**
- Modify: `app/frontend/routes.py`
- Create: `app/templates/inventario/almacen.html`
- Create: `app/static/js/inventario/cs_almacen.js`

**Contexto:** El "Main Warehouse" reemplaza funcionalmente la tabla del dashboard viejo. Muestra 3 KPI cards contextuales (Total Value, Low Stock Alerts, Expiring Soon) + tabla de materiales con avatar de iniciales, stock actual, min/max, status chip, expiración y acciones.

- [ ] **Step 1: Añadir ruta Flask**

En `app/frontend/routes.py`:
```python
@frontend_bp.route("/inventario/almacen")
def inventario_almacen():
    return render_template("inventario/almacen.html")
```

- [ ] **Step 2: Crear el template**

`app/templates/inventario/almacen.html`:
```html
{% extends "inventario/_layout_cs.html" %}
{% block title %}Main Warehouse — Inventory Central{% endblock %}
{% block cs_content %}

<div class="space-y-8">

  <div class="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
    <div>
      <h1 class="font-cs-display text-4xl font-bold text-cs-on-surface tracking-tight">Main Warehouse</h1>
      <p class="mt-1.5 text-sm text-cs-on-surface-var max-w-xl">Manage and monitor primary inventory levels, expiration dates, and critical stock thresholds.</p>
    </div>
    <div class="flex items-center gap-2">
      <a href="/inventario/transferir" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cs-surface-container text-cs-on-surface text-sm font-semibold hover:bg-cs-surface-container-high transition-colors">
        <i data-lucide="arrow-right-left" class="h-4 w-4"></i>
        Transfer to Operatory
      </a>
      <a href="/inventario/compras" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold shadow-sm hover:opacity-95 transition-opacity">
        <i data-lucide="plus" class="h-4 w-4"></i>
        Add Material
      </a>
    </div>
  </div>

  <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
    <div class="p-5 rounded-lg bg-cs-surface-container-lowest">
      <p class="text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var">Total Value</p>
      <p class="mt-3 font-cs-display text-3xl font-bold text-cs-on-surface" data-kpi="total-value">—</p>
    </div>
    <div class="p-5 rounded-lg bg-cs-surface-container-lowest">
      <p class="text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var">Low Stock Alerts</p>
      <p class="mt-3 font-cs-display text-3xl font-bold text-cs-error" data-kpi="low-count">—</p>
      <p class="mt-1 text-xs text-cs-on-surface-var">Require immediate restock</p>
    </div>
    <div class="p-5 rounded-lg bg-cs-surface-container-lowest">
      <p class="text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var">Expiring Soon</p>
      <p class="mt-3 font-cs-display text-3xl font-bold text-cs-on-surface" data-kpi="exp-count">—</p>
      <p class="mt-1 text-xs text-cs-on-surface-var">Within next 30 days</p>
    </div>
  </div>

  <section class="p-6 rounded-lg bg-cs-surface-container-lowest">
    <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 mb-5">
      <div class="relative flex-1">
        <i data-lucide="search" class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-cs-outline"></i>
        <input id="cs-search" placeholder="Filter materials..." class="w-full pl-10 pr-3 py-2 rounded-md bg-cs-surface-container text-sm placeholder:text-cs-outline focus:outline-none focus:ring-2 focus:ring-cs-primary/30" />
      </div>
      <select id="cs-categoria" class="rounded-md bg-cs-surface-container px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cs-primary/30">
        <option value="">All categories</option>
      </select>
      <select id="cs-alerta" class="rounded-md bg-cs-surface-container px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cs-primary/30">
        <option value="">All statuses</option>
        <option value="bajo">Low stock</option>
        <option value="alto">Over stock</option>
        <option value="caduca">Expiring</option>
      </select>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full">
        <thead>
          <tr class="text-left">
            <th class="py-3 pr-4 text-[11px] font-semibold uppercase tracking-widest text-cs-on-surface-var">Material Name</th>
            <th class="py-3 px-4 text-[11px] font-semibold uppercase tracking-widest text-cs-on-surface-var text-right">Current Stock</th>
            <th class="py-3 px-4 text-[11px] font-semibold uppercase tracking-widest text-cs-on-surface-var text-right">Min / Max</th>
            <th class="py-3 px-4 text-[11px] font-semibold uppercase tracking-widest text-cs-on-surface-var">Status</th>
            <th class="py-3 px-4 text-[11px] font-semibold uppercase tracking-widest text-cs-on-surface-var">Expiration</th>
            <th class="py-3 pl-4 text-[11px] font-semibold uppercase tracking-widest text-cs-on-surface-var text-right">Actions</th>
          </tr>
        </thead>
        <tbody id="cs-almacen-body"></tbody>
      </table>
      <p id="cs-almacen-empty" class="hidden py-8 text-center text-sm text-cs-on-surface-var">No materials match the current filters.</p>
    </div>

    <p id="cs-almacen-footer" class="mt-4 text-xs text-cs-on-surface-var"></p>
  </section>

</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_shared.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_almacen.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Escribir `cs_almacen.js`**

```javascript
(async function () {
  const { currency, statusChip, lucideIcon, initials } = window.csShared;
  const { clearChildren, makeOption } = window.invDom;

  const tbody    = document.getElementById("cs-almacen-body");
  const emptyMsg = document.getElementById("cs-almacen-empty");
  const footer   = document.getElementById("cs-almacen-footer");
  const search   = document.getElementById("cs-search");
  const catSel   = document.getElementById("cs-categoria");
  const alertSel = document.getElementById("cs-alerta");

  async function loadKpis() {
    const [kpis, alertas] = await Promise.all([
      invApi.get("/dashboard"),
      invApi.get("/alertas/resumen"),
    ]);
    document.querySelector('[data-kpi="total-value"]').textContent = currency(kpis.total_asset_value);
    document.querySelector('[data-kpi="low-count"]').textContent   = String(alertas.bajo);
    document.querySelector('[data-kpi="exp-count"]').textContent   = String(alertas.caducidad);
  }

  async function loadCategories() {
    const cats = await invApi.get("/categorias");
    cats.forEach(c => catSel.appendChild(makeOption(c.nombre, c.nombre)));
  }

  function buildQuery() {
    const p = new URLSearchParams();
    if (search.value)   p.set("busqueda", search.value);
    if (catSel.value)   p.set("categoria", catSel.value);
    return "/materiales?" + p;
  }

  function rowFor(m) {
    const tr = document.createElement("tr");
    tr.className = "group transition-colors duration-200 cursor-pointer hover:bg-cs-surface-container-low";
    tr.addEventListener("click", () => { window.location.href = "/inventario/material/" + m.id; });

    const tdMat = document.createElement("td");
    tdMat.className = "py-4 pr-4";
    const wrap = document.createElement("div");
    wrap.className = "flex items-center gap-3";
    const avatar = document.createElement("div");
    avatar.className = "w-9 h-9 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-xs font-semibold font-cs-display shrink-0";
    avatar.textContent = initials(m.nombre);
    const meta = document.createElement("div");
    const name = document.createElement("p");
    name.className = "text-sm font-semibold text-cs-on-surface";
    name.textContent = m.nombre;
    const sku = document.createElement("p");
    sku.className = "text-xs text-cs-on-surface-var";
    sku.textContent = "SKU: " + m.id;
    meta.append(name, sku);
    wrap.append(avatar, meta);
    tdMat.appendChild(wrap);

    const tdStock = document.createElement("td");
    tdStock.className = "py-4 px-4 text-right text-sm font-semibold text-cs-on-surface tabular-nums";
    tdStock.textContent = String(m.total_global) + " " + (m.unidad_inventario || "");

    const tdMinMax = document.createElement("td");
    tdMinMax.className = "py-4 px-4 text-right text-xs text-cs-on-surface-var tabular-nums";
    tdMinMax.textContent = "—";

    const tdStatus = document.createElement("td");
    tdStatus.className = "py-4 px-4";
    tdStatus.appendChild(statusChip("In Stock", "stable"));

    const tdExp = document.createElement("td");
    tdExp.className = "py-4 px-4 text-xs text-cs-on-surface-var";
    tdExp.textContent = m.expira ? "Varies by lot" : "N/A";

    const tdActions = document.createElement("td");
    tdActions.className = "py-4 pl-4 text-right";
    const btn = document.createElement("button");
    btn.className = "p-2 rounded-md text-cs-on-surface-var hover:text-cs-primary hover:bg-cs-primary-container transition-colors opacity-0 group-hover:opacity-100";
    btn.setAttribute("aria-label", "Editar material");
    btn.appendChild(lucideIcon("pencil", "h-4 w-4"));
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      window.location.href = "/inventario/material/" + m.id;
    });
    tdActions.appendChild(btn);

    tr.append(tdMat, tdStock, tdMinMax, tdStatus, tdExp, tdActions);
    return tr;
  }

  async function load() {
    const mats = await invApi.get(buildQuery());
    clearChildren(tbody);
    if (mats.length === 0) {
      emptyMsg.classList.remove("hidden");
      footer.textContent = "";
    } else {
      emptyMsg.classList.add("hidden");
      mats.forEach(m => tbody.appendChild(rowFor(m)));
      footer.textContent = "Showing " + mats.length + " of " + mats.length + " results";
    }
    if (window.lucide) lucide.createIcons();
  }

  [catSel, alertSel].forEach(el => el.addEventListener("change", load));
  search.addEventListener("input", () => setTimeout(load, 200));

  const url = new URL(window.location);
  if (url.searchParams.get("filtro")) {
    alertSel.value = url.searchParams.get("filtro");
  }

  await loadCategories();
  await Promise.all([loadKpis(), load()]);
})();
```

- [ ] **Step 4: Verificar en navegador**

Ir a `http://localhost:5000/inventario/almacen`. Expected:
- Header + 3 KPI cards + tabla
- Hover en fila cambia fondo (sin líneas divisoras)
- Chip "In Stock" en azul, no verde
- Click en fila va al detalle del material

- [ ] **Step 5: Commit**

```bash
git add app/frontend/routes.py app/templates/inventario/almacen.html app/static/js/inventario/cs_almacen.js
git commit -m "feat(inventario): add Main Warehouse view with Clinical Sanctuary styling"
```

---

## Fase 4 — Operatory Management redesign

### Task 4.1: Rediseñar `operatorios.html` + `cs_operatorios.js`

**Files:**
- Modify: `app/templates/inventario/operatorios.html` (reescritura completa)
- Create: `app/static/js/inventario/cs_operatorios.js`

**Contexto:** Grid de cards de operatorios con % stock, al seleccionar uno abre panel derecho con inventario por item. Incluye modal para crear nuevos operatorios (CRUD preservado).

- [ ] **Step 1: Reescribir `operatorios.html`**

```html
{% extends "inventario/_layout_cs.html" %}
{% block title %}Operatories — Inventory Central{% endblock %}
{% block cs_content %}

<div class="space-y-8">

  <div class="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
    <div>
      <h1 class="font-cs-display text-4xl font-bold text-cs-on-surface tracking-tight">
        Operatory <span class="text-cs-on-surface-var font-normal">Management</span>
      </h1>
      <p class="mt-1.5 text-sm text-cs-on-surface-var max-w-xl">Monitor real-time inventory dispersion across clinical spaces. Select an operatory to view detailed stock levels.</p>
    </div>
    <div class="flex items-center gap-2">
      <span class="inline-flex items-center gap-2 text-xs font-medium text-cs-on-surface-var px-3">
        <span class="w-2 h-2 rounded-full bg-cs-primary animate-cs-pulse"></span>
        Live Sync Active
      </span>
      <button id="cs-new-operatory" class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-cs-surface-container text-cs-on-surface text-sm font-semibold hover:bg-cs-surface-container-high transition-colors">
        <i data-lucide="plus" class="h-4 w-4"></i>
        Nuevo
      </button>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">

    <section class="lg:col-span-2 p-6 rounded-lg bg-cs-surface-container">
      <h2 class="font-cs-display text-base font-semibold text-cs-on-surface mb-4">Active Spaces</h2>
      <ul id="cs-ops-grid" class="grid grid-cols-1 sm:grid-cols-2 gap-3"></ul>
    </section>

    <aside id="cs-op-detail" class="p-6 rounded-lg bg-cs-surface-container-lowest hidden">
      <div class="flex items-start justify-between mb-5">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-cs-primary">Selected</p>
          <h3 id="cs-op-detail-name" class="font-cs-display text-2xl font-bold text-cs-on-surface mt-1"></h3>
          <p class="text-xs text-cs-on-surface-var mt-0.5">Operatory Inventory Detail</p>
        </div>
        <button id="cs-op-detail-close" class="p-1 rounded text-cs-on-surface-var hover:text-cs-on-surface" aria-label="Cerrar">
          <i data-lucide="x" class="h-4 w-4"></i>
        </button>
      </div>

      <div class="flex gap-2 mb-5">
        <a href="/inventario/transferir" class="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-gradient-to-br from-cs-primary to-cs-primary-dim text-cs-on-primary text-sm font-semibold">
          <i data-lucide="refresh-cw" class="h-4 w-4"></i> Restock Request
        </a>
        <button class="inline-flex items-center gap-2 px-3 py-2 rounded-md bg-cs-surface-container text-cs-on-surface text-sm font-semibold">
          <i data-lucide="scan-line" class="h-4 w-4"></i> Scan Item
        </button>
      </div>

      <div class="flex items-center justify-between text-[10px] font-semibold uppercase tracking-widest text-cs-on-surface-var mb-2 px-2">
        <span>Material</span>
        <span class="flex gap-6"><span>In Room</span><span>Whse</span></span>
      </div>
      <ul id="cs-op-detail-items" class="space-y-2"></ul>
    </aside>

  </div>
</div>

<div id="cs-op-modal" class="hidden fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
  <form id="cs-op-form" class="bg-cs-surface-container-lowest rounded-lg p-6 w-full max-w-md space-y-4">
    <h2 class="font-cs-display text-xl font-bold text-cs-on-surface">Nuevo operatorio</h2>
    <label class="block">
      <span class="block text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var mb-1.5">Nombre</span>
      <input name="nombre" required class="w-full rounded-md bg-cs-surface-container px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cs-primary/30" />
    </label>
    <label class="block">
      <span class="block text-xs font-semibold uppercase tracking-widest text-cs-on-surface-var mb-1.5">Orden</span>
      <input name="orden" type="number" value="0" class="w-full rounded-md bg-cs-surface-container px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cs-primary/30" />
    </label>
    <div class="flex justify-end gap-2 pt-2">
      <button type="button" id="cs-op-cancel" class="px-4 py-2 rounded-md bg-cs-surface-container text-cs-on-surface text-sm font-semibold">Cancelar</button>
      <button type="submit" class="px-4 py-2 rounded-md bg-cs-primary text-cs-on-primary text-sm font-semibold">Crear</button>
    </div>
  </form>
</div>

{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_shared.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_operatorios.js') }}"></script>
{% endblock %}
```

- [ ] **Step 2: Escribir `cs_operatorios.js`**

```javascript
(async function () {
  const { statusChip, lucideIcon, initials } = window.csShared;
  const { clearChildren } = window.invDom;

  const grid       = document.getElementById("cs-ops-grid");
  const detail     = document.getElementById("cs-op-detail");
  const detailName = document.getElementById("cs-op-detail-name");
  const itemsUl    = document.getElementById("cs-op-detail-items");
  const modal      = document.getElementById("cs-op-modal");
  const form       = document.getElementById("cs-op-form");

  let distribucion = [];

  function cardFor(op) {
    const li = document.createElement("li");
    const pct = op.total_units > 0
      ? Math.min(100, Math.round((op.total_units / Math.max(op.total_units, 1000)) * 100))
      : 0;
    li.className = "p-4 rounded-lg bg-cs-surface-container-lowest cursor-pointer transition-all duration-200 hover:bg-cs-surface-container-low";
    li.dataset.opId = op.id;

    const head = document.createElement("div");
    head.className = "flex items-start justify-between mb-4";

    const nameWrap = document.createElement("div");
    const iconWrap = document.createElement("div");
    iconWrap.className = "w-9 h-9 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center mb-2";
    iconWrap.appendChild(lucideIcon("briefcase-medical", "h-4 w-4"));
    const name = document.createElement("p");
    name.className = "text-sm font-semibold text-cs-on-surface";
    name.textContent = op.nombre;
    const sub = document.createElement("p");
    sub.className = "text-xs text-cs-on-surface-var";
    sub.textContent = "Clinical Suite";
    nameWrap.append(iconWrap, name, sub);

    const chip = statusChip(
      op.status === "stable" ? "Ready" : "Low Stock",
      op.status === "stable" ? "stable" : "low",
    );
    head.append(nameWrap, chip);

    const stats = document.createElement("p");
    stats.className = "text-[10px] uppercase tracking-widest text-cs-on-surface-var mb-1.5";
    stats.textContent = "Stock Level";

    const bar = document.createElement("div");
    bar.className = "h-1.5 w-full rounded-full bg-cs-surface-container overflow-hidden";
    const fill = document.createElement("div");
    fill.className = "h-full rounded-full bg-cs-primary";
    fill.style.width = pct + "%";
    bar.appendChild(fill);

    const pctLabel = document.createElement("p");
    pctLabel.className = "mt-1.5 text-xs font-semibold text-cs-on-surface tabular-nums";
    pctLabel.textContent = pct + "%";

    li.append(head, stats, bar, pctLabel);
    li.addEventListener("click", () => selectOperatory(op));
    return li;
  }

  function setActiveCard(opId) {
    grid.querySelectorAll("li").forEach(li => {
      if (li.dataset.opId == String(opId)) {
        li.classList.add("bg-cs-surface-bright");
        li.style.outline = "2px solid var(--color-cs-primary)";
      } else {
        li.style.outline = "none";
        li.classList.remove("bg-cs-surface-bright");
      }
    });
  }

  async function selectOperatory(op) {
    setActiveCard(op.id);
    detail.classList.remove("hidden");
    detailName.textContent = op.nombre;

    clearChildren(itemsUl);
    const skeleton = document.createElement("li");
    skeleton.className = "text-xs text-cs-on-surface-var py-3";
    skeleton.textContent = "Loading inventory…";
    itemsUl.appendChild(skeleton);

    const mats = await invApi.get("/materiales");
    const details = await Promise.all(
      mats.slice(0, 30).map(m => invApi.get("/materiales/" + m.id))
    );

    clearChildren(itemsUl);
    let any = false;
    details.forEach(m => {
      const here = (m.stock_por_ubicacion || []).find(s => s.operatorio_id === op.id);
      const whse = (m.stock_por_ubicacion || []).find(s => s.operatorio_id === null);
      if (!here || here.cantidad === 0) return;
      any = true;

      const li = document.createElement("li");
      li.className = "flex items-center gap-3 p-3 rounded-md bg-cs-surface-container";

      const av = document.createElement("div");
      av.className = "w-8 h-8 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center text-[10px] font-semibold";
      av.textContent = initials(m.nombre);

      const info = document.createElement("div");
      info.className = "flex-1 min-w-0";
      const n = document.createElement("p");
      n.className = "text-sm font-semibold text-cs-on-surface truncate";
      n.textContent = m.nombre;
      const sku = document.createElement("p");
      sku.className = "text-[10px] text-cs-on-surface-var";
      sku.textContent = "SKU " + m.id;
      info.append(n, sku);

      const inRoom = document.createElement("span");
      inRoom.className = "text-xs font-semibold text-cs-on-surface tabular-nums w-12 text-right";
      inRoom.textContent = String(here.cantidad);

      const warehouse = document.createElement("span");
      warehouse.className = "text-xs text-cs-on-surface-var tabular-nums w-12 text-right";
      warehouse.textContent = whse ? String(whse.cantidad) : "0";

      li.append(av, info, inRoom, warehouse);
      itemsUl.appendChild(li);
    });

    if (!any) {
      const li = document.createElement("li");
      li.className = "text-xs text-cs-on-surface-var py-3";
      li.textContent = "No stock in this operatory yet.";
      itemsUl.appendChild(li);
    }
  }

  async function loadOps() {
    distribucion = await invApi.get("/operatorios/distribucion");
    clearChildren(grid);
    distribucion.forEach(op => grid.appendChild(cardFor(op)));
    if (window.lucide) lucide.createIcons();

    const hash = window.location.hash.replace("#", "");
    if (hash) {
      const op = distribucion.find(o => String(o.id) === hash);
      if (op) selectOperatory(op);
    }
  }

  document.getElementById("cs-op-detail-close").addEventListener("click", () => {
    detail.classList.add("hidden");
  });

  document.getElementById("cs-new-operatory").addEventListener("click", () => {
    modal.classList.remove("hidden");
  });
  document.getElementById("cs-op-cancel").addEventListener("click", () => {
    modal.classList.add("hidden");
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    try {
      await invApi.post("/operatorios", {
        nombre: fd.get("nombre"),
        orden: parseInt(fd.get("orden") || "0"),
      });
      modal.classList.add("hidden");
      form.reset();
      await loadOps();
    } catch (err) { alert(err.message); }
  });

  await loadOps();
})();
```

- [ ] **Step 3: Verificar en navegador**

Ir a `/inventario/operatorios`. Expected:
- Header + grid de cards
- Click en card abre panel derecho con items
- "Nuevo" abre modal; crear un operatorio lo añade

- [ ] **Step 4: Commit**

```bash
git add app/templates/inventario/operatorios.html app/static/js/inventario/cs_operatorios.js
git commit -m "feat(inventario): redesign operatories view with Clinical Sanctuary grid + detail panel"
```

---

## Fase 5 — Página standalone "Material Transfer"

### Task 5.1: Crear ruta, template y JS de transferir

**Files:**
- Modify: `app/frontend/routes.py`
- Create: `app/templates/inventario/transferir.html`
- Create: `app/static/js/inventario/cs_transferir.js`

**Contexto:** Layout 2 columnas: izquierda formulario (Origin → Destination, material search, cantidad), derecha panel "Live Inventory Data" con impact en vivo. Al cambiar material/cantidad el panel derecho se actualiza sin submit.

- [ ] **Step 1: Añadir ruta**

En `app/frontend/routes.py`:
```python
@frontend_bp.route("/inventario/transferir")
def inventario_transferir():
    return render_template("inventario/transferir.html")
```

- [ ] **Step 2: Crear template**

`app/templates/inventario/transferir.html`:
```html
{% extends "inventario/_layout_cs.html" %}
{% block title %}Material Transfer — Inventory Central{% endblock %}
{% block cs_content %}

<div class="grid grid-cols-1 lg:grid-cols-5 gap-4 max-w-6xl">

  <section class="lg:col-span-3 p-8 rounded-lg bg-cs-surface-container-lowest">

    <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-cs-primary mb-2">
      <i data-lucide="arrow-right-left" class="h-4 w-4"></i>
      Inventory Action
    </div>
    <h1 class="font-cs-display text-4xl font-bold text-cs-on-surface tracking-tight">Material Transfer</h1>
    <p class="mt-1.5 text-sm text-cs-on-surface-var">Allocate stock from central holding to specific operational zones.</p>

    <div class="mt-8 p-4 rounded-lg bg-cs-surface-container flex items-center gap-3">
      <div class="flex-1 p-4 rounded-md bg-cs-surface-container-lowest">
        <p class="text-[10px] font-semibold uppercase tracking-widest text-cs-on-surface-var">Origin</p>
        <div class="mt-2 flex items-center gap-3">
          <div class="w-10 h-10 rounded-md bg-cs-surface-container text-cs-on-surface-var flex items-center justify-center">
            <i data-lucide="warehouse" class="h-5 w-5"></i>
          </div>
          <div class="flex-1 min-w-0">
            <select id="cs-origen" class="w-full text-sm font-semibold text-cs-on-surface bg-transparent focus:outline-none cursor-pointer">
              <option value="">Main Warehouse</option>
            </select>
            <p class="text-[10px] text-cs-on-surface-var">Central storage</p>
          </div>
        </div>
      </div>
      <i data-lucide="arrow-right" class="h-5 w-5 text-cs-on-surface-var shrink-0"></i>
      <div class="flex-1 p-4 rounded-md bg-cs-surface-container-lowest">
        <p class="text-[10px] font-semibold uppercase tracking-widest text-cs-primary">Destination Target</p>
        <div class="mt-2 flex items-center gap-3">
          <div class="w-10 h-10 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center">
            <i data-lucide="briefcase-medical" class="h-5 w-5"></i>
          </div>
          <div class="flex-1 min-w-0">
            <select id="cs-destino" class="w-full text-sm font-semibold text-cs-on-surface bg-transparent focus:outline-none cursor-pointer">
              <option value="">Selecciona operatorio</option>
            </select>
            <p class="text-[10px] text-cs-on-surface-var">Operatory</p>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-6">
      <label class="block text-sm font-semibold text-cs-on-surface mb-2">Select Material</label>
      <div class="relative">
        <i data-lucide="search" class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-cs-outline"></i>
        <input id="cs-mat-search" type="text" placeholder="Search by name or SKU..." class="w-full pl-10 pr-3 py-3 rounded-md bg-cs-surface-container text-sm focus:outline-none focus:ring-2 focus:ring-cs-primary/30" />
        <ul id="cs-mat-suggest" class="hidden absolute z-10 left-0 right-0 mt-1 max-h-64 overflow-y-auto rounded-md bg-cs-surface-container-lowest shadow-lg"></ul>
      </div>
      <div id="cs-mat-selected" class="hidden mt-2 p-3 rounded-md bg-cs-surface-container flex items-center gap-3">
        <div class="w-10 h-10 rounded-md bg-cs-primary-container text-cs-on-primary-container flex items-center justify-center">
          <i data-lucide="pill" class="h-5 w-5"></i>
        </div>
        <div class="flex-1 min-w-0">
          <p id="cs-mat-name" class="text-sm font-semibold text-cs-on-surface"></p>
          <p id="cs-mat-sku" class="text-xs text-cs-on-surface-var"></p>
        </div>
        <button type="button" id="cs-mat-clear" class="text-xs font-medium text-cs-on-surface-var hover:text-cs-on-surface inline-flex items-center gap-1">
          <i data-lucide="x" class="h-3 w-3"></i> Change
        </button>
      </div>
    </div>

    <div class="mt-6">
      <label class="block text-sm font-semibold text-cs-on-surface mb-2">Transfer Quantity</label>
      <div class="flex items-center gap-4">
        <div class="inline-flex items-center rounded-md bg-cs-surface-container">
          <button type="button" id="cs-qty-minus" class="p-3 text-cs-on-surface-var hover:text-cs-on-surface" aria-label="Restar">
            <i data-lucide="minus" class="h-4 w-4"></i>
          </button>
          <input id="cs-qty" type="number" min="1" value="1" class="w-20 text-center text-lg font-semibold font-cs-display bg-transparent focus:outline-none tabular-nums" />
          <button type="button" id="cs-qty-plus" class="p-3 text-cs-on-surface-var hover:text-cs-on-surface" aria-label="Sumar">
            <i data-lucide="plus" class="h-4 w-4"></i>
          </button>
        </div>
        <span id="cs-qty-units" class="text-sm text-cs-on-surface-var">Units</span>
      </div>
    </div>

    <div class="mt-6">
      <label class="block text-sm font-semibold text-cs-on-surface mb-2">Motivo (opcional)</label>
      <input id="cs-motivo" type="text" placeholder="Restock, reposición, emergencia..." class="w-full px-3 py-2.5 rounded-md bg-cs-surface-container text-sm focus:outline-none focus:ring-2 focus:ring-cs-primary/30" />
    </div>
  </section>

  <aside class="lg:col-span-2 p-6 rounded-lg bg-cs-surface flex flex-col">
    <div class="flex items-center justify-between mb-5">
      <div class="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-cs-primary">
        <span class="w-2 h-2 rounded-full bg-cs-primary animate-cs-pulse"></span>
        Live Inventory Data
      </div>
      <a href="/inventario/almacen" class="text-cs-on-surface-var hover:text-cs-on-surface" aria-label="Cerrar">
        <i data-lucide="x" class="h-4 w-4"></i>
      </a>
    </div>

    <div class="mb-5">
      <p class="text-xs font-semibold text-cs-on-surface mb-2">Origin Impact</p>
      <div class="p-4 rounded-md bg-cs-surface-container-lowest">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-cs-on-surface-var">Current Stock</span>
          <span id="cs-impact-current" class="font-cs-display text-2xl font-bold text-cs-on-surface tabular-nums">—</span>
        </div>
        <div class="mt-3 h-1.5 rounded-full bg-cs-surface-container overflow-hidden">
          <div id="cs-impact-bar" class="h-full bg-cs-primary transition-all duration-300" style="width: 100%"></div>
        </div>
        <div class="mt-3 flex items-center justify-between text-xs">
          <span class="text-cs-on-surface-var">Post-Transfer</span>
          <span id="cs-impact-post" class="font-semibold text-cs-primary tabular-nums">—</span>
        </div>
      </div>
    </div>

    <div class="mb-auto">
      <p class="text-xs font-semibold text-cs-on-surface mb-2">Destination Target</p>
      <div class="p-4 rounded-md bg-cs-surface-container-lowest">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-md bg-cs-surface-container text-cs-on-surface-var flex items-center justify-center">
            <i data-lucide="archive" class="h-4 w-4"></i>
          </div>
          <div class="flex-1">
            <p id="cs-dest-title" class="text-sm font-semibold text-cs-on-surface">—</p>
            <p class="text-xs text-cs-on-surface-var">Sufficient storage available for incoming transfer.</p>
          </div>
        </div>
        <div class="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-cs-primary-container text-cs-on-primary-container text-xs font-semibold">
          <i data-lucide="check-circle-2" class="h-3 w-3"></i>
          Clear for Transfer
        </div>
      </div>
    </div>

    <div class="mt-6 space-y-2">
      <button id="cs-confirm" class="w-full inline-flex items-center justify-center gap-2 py-3 rounded-md bg-cs-primary text-cs-on-primary font-semibold text-sm hover:bg-cs-primary-dim transition-colors">
        Confirm Transfer <i data-lucide="arrow-right" class="h-4 w-4"></i>
      </button>
      <button type="button" class="w-full py-2 text-cs-primary text-sm font-semibold hover:underline">Save as Draft</button>
      <p id="cs-error" class="hidden text-xs font-medium text-cs-error text-center"></p>
    </div>
  </aside>
</div>

{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_shared.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/cs_transferir.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Escribir `cs_transferir.js`**

```javascript
(async function () {
  const { makeOption, clearChildren } = window.invDom;

  const origenSel  = document.getElementById("cs-origen");
  const destinoSel = document.getElementById("cs-destino");
  const destTitle  = document.getElementById("cs-dest-title");
  const matSearch  = document.getElementById("cs-mat-search");
  const matSuggest = document.getElementById("cs-mat-suggest");
  const matSelected= document.getElementById("cs-mat-selected");
  const matName    = document.getElementById("cs-mat-name");
  const matSku     = document.getElementById("cs-mat-sku");
  const qtyInput   = document.getElementById("cs-qty");
  const qtyUnits   = document.getElementById("cs-qty-units");
  const impactCurr = document.getElementById("cs-impact-current");
  const impactPost = document.getElementById("cs-impact-post");
  const impactBar  = document.getElementById("cs-impact-bar");
  const confirmBtn = document.getElementById("cs-confirm");
  const errorEl    = document.getElementById("cs-error");

  let operatorios = [];
  let materiales  = [];
  let selectedMat = null;
  const detailCache = {};

  async function init() {
    const [ops, mats] = await Promise.all([
      invApi.get("/operatorios"),
      invApi.get("/materiales"),
    ]);
    operatorios = ops;
    materiales = mats;

    ops.forEach(op => {
      origenSel.appendChild(makeOption(op.id, op.nombre));
      destinoSel.appendChild(makeOption(op.id, op.nombre));
    });

    origenSel.addEventListener("change", refreshImpact);
    destinoSel.addEventListener("change", () => {
      const op = operatorios.find(o => String(o.id) === destinoSel.value);
      destTitle.textContent = op ? op.nombre + " Capacity" : "Main Warehouse Capacity";
    });

    matSearch.addEventListener("input", onSearch);
    document.getElementById("cs-mat-clear").addEventListener("click", clearSelection);

    document.getElementById("cs-qty-minus").addEventListener("click", () => {
      qtyInput.value = Math.max(1, parseInt(qtyInput.value || "1") - 1);
      refreshImpact();
    });
    document.getElementById("cs-qty-plus").addEventListener("click", () => {
      qtyInput.value = parseInt(qtyInput.value || "1") + 1;
      refreshImpact();
    });
    qtyInput.addEventListener("input", refreshImpact);

    confirmBtn.addEventListener("click", submit);
  }

  function onSearch() {
    const q = matSearch.value.trim().toLowerCase();
    if (!q) { matSuggest.classList.add("hidden"); return; }
    const matches = materiales.filter(m => m.nombre.toLowerCase().includes(q)).slice(0, 8);
    clearChildren(matSuggest);
    matches.forEach(m => {
      const li = document.createElement("li");
      li.className = "px-4 py-2.5 text-sm hover:bg-cs-surface-container cursor-pointer";
      li.textContent = m.nombre;
      li.addEventListener("click", () => selectMaterial(m));
      matSuggest.appendChild(li);
    });
    matSuggest.classList.toggle("hidden", matches.length === 0);
  }

  async function selectMaterial(m) {
    selectedMat = m;
    matSelected.classList.remove("hidden");
    matName.textContent = m.nombre;
    matSku.textContent = "SKU: " + m.id;
    qtyUnits.textContent = "Units (" + (m.unidad_inventario || "pz") + ")";
    matSuggest.classList.add("hidden");
    matSearch.value = m.nombre;
    await refreshImpact();
  }

  function clearSelection() {
    selectedMat = null;
    matSelected.classList.add("hidden");
    matSearch.value = "";
    impactCurr.textContent = "—";
    impactPost.textContent = "—";
    impactBar.style.width = "100%";
  }

  async function fetchDetail(matId) {
    if (!detailCache[matId]) {
      detailCache[matId] = await invApi.get("/materiales/" + matId);
    }
    return detailCache[matId];
  }

  async function refreshImpact() {
    if (!selectedMat) return;
    const det = await fetchDetail(selectedMat.id);
    const origenId = origenSel.value ? parseInt(origenSel.value) : null;
    const row = (det.stock_por_ubicacion || []).find(s => s.operatorio_id === origenId);
    const current = row ? row.cantidad : 0;
    const qty = Math.max(0, parseInt(qtyInput.value || "0"));
    const post = Math.max(0, current - qty);
    impactCurr.textContent = String(current);
    impactPost.textContent = String(post);
    impactBar.style.width = (current > 0 ? Math.round((post / current) * 100) : 0) + "%";
    if (qty > current) {
      impactBar.style.backgroundColor = "var(--color-cs-error)";
    } else {
      impactBar.style.backgroundColor = "var(--color-cs-primary)";
    }
  }

  async function submit() {
    errorEl.classList.add("hidden");
    if (!selectedMat) { showErr("Selecciona un material."); return; }
    if (!destinoSel.value) { showErr("Selecciona destino."); return; }
    const body = {
      material_id: selectedMat.id,
      origen_operatorio_id: origenSel.value ? parseInt(origenSel.value) : null,
      destino_operatorio_id: parseInt(destinoSel.value),
      cantidad: parseInt(qtyInput.value || "0"),
      motivo: document.getElementById("cs-motivo").value || null,
    };
    try {
      await invApi.post("/transferencias", body);
      window.location.href = "/inventario?transfer=ok";
    } catch (err) {
      showErr(err.message || "Error al transferir");
    }
  }

  function showErr(msg) {
    errorEl.textContent = msg;
    errorEl.classList.remove("hidden");
  }

  await init();
})();
```

- [ ] **Step 4: Probar flujo end-to-end**

1. Ir a `/inventario/transferir`
2. Seleccionar destino (un operatorio) → título del panel destino cambia
3. Buscar material → autocomplete aparece → seleccionar
4. Cambiar cantidad con +/- → Current Stock y Post-Transfer se actualizan en vivo
5. Si cantidad excede stock → barra se pone roja
6. Click "Confirm Transfer" → redirect a dashboard

- [ ] **Step 5: Commit**

```bash
git add app/frontend/routes.py app/templates/inventario/transferir.html app/static/js/inventario/cs_transferir.js
git commit -m "feat(inventario): add standalone Material Transfer page with live impact panel"
```

---

## Fase 6 — Navegación y verificación final

### Task 6.1: Actualizar sidebar global

**Files:**
- Modify: `app/templates/partials/sidebar_content.html`

**Contexto:** El sidebar global (no el CS) tiene un grupo INVENTARIO que necesita incluir las nuevas rutas "Almacén" y "Transferir".

- [ ] **Step 1: Reemplazar el bloque INVENTARIO del sidebar global**

En `app/templates/partials/sidebar_content.html`, reemplazar el `<div>` cuyo header es "INVENTARIO" por:
```html
    <div>
      <p class="px-3 mb-2 text-[11px] font-semibold tracking-wider text-text-muted uppercase font-body">INVENTARIO</p>
      <ul class="space-y-0.5">
        <li>
          <a href="/inventario" data-nav-path="/inventario" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="layout-dashboard" class="h-[18px] w-[18px] shrink-0"></i>
            Dashboard
          </a>
        </li>
        <li>
          <a href="/inventario/almacen" data-nav-path="/inventario/almacen" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="warehouse" class="h-[18px] w-[18px] shrink-0"></i>
            Almacén
          </a>
        </li>
        <li>
          <a href="/inventario/operatorios" data-nav-path="/inventario/operatorios" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="briefcase-medical" class="h-[18px] w-[18px] shrink-0"></i>
            Operatorios
          </a>
        </li>
        <li>
          <a href="/inventario/transferir" data-nav-path="/inventario/transferir" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="arrow-left-right" class="h-[18px] w-[18px] shrink-0"></i>
            Transferir
          </a>
        </li>
        <li>
          <a href="/inventario/compras" data-nav-path="/inventario/compras" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="shopping-cart" class="h-[18px] w-[18px] shrink-0"></i>
            Compras
          </a>
        </li>
        <li>
          <a href="/inventario/movimientos" data-nav-path="/inventario/movimientos" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium font-body transition-colors duration-150 text-text-secondary hover:bg-surface-hover hover:text-text-primary">
            <i data-lucide="arrow-right-left" class="h-[18px] w-[18px] shrink-0"></i>
            Movimientos
          </a>
        </li>
      </ul>
    </div>
```

- [ ] **Step 2: Verificar**

Ir a `/dashboard` (el global). Expected: sidebar muestra 6 items bajo INVENTARIO, todos navegan a las nuevas rutas CS.

- [ ] **Step 3: Commit**

```bash
git add app/templates/partials/sidebar_content.html
git commit -m "chore(inventario): update global sidebar with new inventory routes"
```

---

### Task 6.2: Verificación end-to-end

**Files:** ninguno — verificación visual y de tests.

- [ ] **Step 1: Iniciar dev server**

```bash
python run.py
```

- [ ] **Step 2: Recorrer cada vista contra su mockup**

1. `/inventario` ← `gestor_de_inventario_m_dico/dashboard_de_inventario/screen.png`
2. `/inventario/almacen` ← `gestor_de_inventario_m_dico/almac_n_principal/screen.png`
3. `/inventario/operatorios` ← `gestor_de_inventario_m_dico/gesti_n_de_operatorios/screen.png`
4. `/inventario/transferir` ← `gestor_de_inventario_m_dico/transferir_material/screen.png`

Para cada una: comparar layout, tipografía, paleta, espaciado. Tomar screenshots si hay herramientas de preview disponibles.

- [ ] **Step 3: Correr la suite de tests**

```bash
pytest
```
Expected: todos PASS, incluyendo los 3 nuevos de `tests/test_inventario_dashboard.py`.

- [ ] **Step 4: Checklist de compliance con DESIGN.md**

Revisar manualmente cada vista CS contra las reglas:
- [ ] Ningún `border: 1px solid` separando cards (solo shifts de background)
- [ ] Headlines en Manrope (`font-cs-display`); body en Inter (`font-cs-body`)
- [ ] Status chips "In Stock" en azul (primary_container), no verde
- [ ] Tablas sin divisores horizontales — separación por padding y hover
- [ ] Texto principal en `#2a3439` (on_surface), no negro puro
- [ ] `rounded-lg` en cards grandes, nunca `sm`/`none`
- [ ] Transiciones hover con duration ≥200ms

- [ ] **Step 5: Commit final**

```bash
git commit --allow-empty -m "chore(inventario): Clinical Sanctuary redesign complete"
```

---

## Resumen de archivos afectados

**Creados:**
- `app/templates/inventario/_layout_cs.html`
- `app/templates/inventario/_sidebar_cs.html`
- `app/templates/inventario/almacen.html`
- `app/templates/inventario/transferir.html`
- `app/static/js/inventario/cs_shared.js`
- `app/static/js/inventario/cs_dashboard.js`
- `app/static/js/inventario/cs_almacen.js`
- `app/static/js/inventario/cs_operatorios.js`
- `app/static/js/inventario/cs_transferir.js`
- `tests/test_inventario_dashboard.py`

**Modificados:**
- `app/templates/base.html` (tokens CS + fonts)
- `app/templates/inventario/dashboard.html` (reescrito)
- `app/templates/inventario/operatorios.html` (reescrito)
- `app/templates/partials/sidebar_content.html` (items de inventario)
- `app/frontend/routes.py` (2 rutas nuevas: `/inventario/almacen`, `/inventario/transferir`)
- `app/inventario/routes.py` (3 endpoints: `/dashboard`, `/operatorios/distribucion`, `/movimientos/recientes`)
- `app/inventario/services.py` (helper `calcular_kpis_dashboard`)

**Intactos (fuera de scope — rediseñables en plan futuro):**
- Todos los modelos, schemas y el resto de endpoints del backend
- Vistas `compras.html`, `movimientos.html`, `importar.html`, `material.html`
