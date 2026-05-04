# Inventario — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un módulo de inventario multitenant con rastreo por ubicaciones (almacén + operatorios), lotes con caducidad, alertas de mínimo/máximo y caducidad próxima, registro de compras con historial y movimientos trazables.

**Architecture:** Nuevo módulo `app/inventario/` siguiendo el patrón del proyecto (models / schemas / routes / services). Reutiliza `Material` existente agregándole campos (`expira`, `unidad_inventario`, `en_inventario`) y relación many-to-many con `Categoria`. Ubicaciones representadas como `operatorio_id NULL = almacén`. La capa `services.py` mantiene transaccionalmente la invariante `StockUbicacion.cantidad == SUM(LoteUbicacion.cantidad_restante)`. Seed opt-in desde `materiales_master` precargado con 314 materiales nuevos del Excel.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), Marshmallow, JWT, SQLite (testing) / Postgres (prod), Jinja2 + JS vanilla (frontend), pandas + openpyxl (script de extracción del Excel), pytest.

**Spec:** [docs/superpowers/specs/2026-04-20-inventario-design.md](../specs/2026-04-20-inventario-design.md)

**Nota sobre commits:** El proyecto no está inicializado como repositorio git. Los pasos de `git commit` son opcionales — ejecutarlos solo si se inicializa git. Alternativamente, trata cada paso de "Commit" como un checkpoint.

**Nota sobre seguridad en el frontend:** Todo el JS usa `textContent` y `createElement` en vez de `innerHTML` cuando se insertan datos provenientes de la API (evita XSS por nombres de material maliciosos). Usa un helper compartido `buildRow(cells)` que crea `<td>` con `textContent`.

---

## Fase 1 — Modelo de datos y migraciones

### Task 1: Scaffold del módulo + campos de inventario en Material

**Files:**
- Create: `app/inventario/__init__.py` (vacío)
- Create: `app/inventario/models.py`
- Create: `tests/test_inventario_models.py`
- Modify: `app/catalogo/models.py` (agregar columnas)
- Modify: `app/__init__.py` (importar inventario_models)

- [ ] **Step 1: Escribir test fallido que verifica los nuevos campos**

`tests/test_inventario_models.py`:
```python
from app.catalogo.models import Material, MaterialMaster


def test_material_tiene_campos_inventario(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Guantes")
    db.session.add(m)
    db.session.commit()

    assert m.expira is True
    assert m.unidad_inventario == "pieza"
    assert m.en_inventario is False


def test_material_master_tiene_campos_inventario(app, db):
    m = MaterialMaster(nombre="Guantes", categoria="general")
    db.session.add(m)
    db.session.commit()

    assert m.expira is True
    assert m.unidad_inventario == "pieza"
```

- [ ] **Step 2: Run test — debe fallar**

```
pytest tests/test_inventario_models.py -v
```
Expected: FAIL (atributos no existen)

- [ ] **Step 3: Agregar columnas a Material y MaterialMaster**

Editar `app/catalogo/models.py`. En `MaterialMaster` (después de `categoria`):
```python
    expira = db.Column(db.Boolean, default=True, nullable=False)
    unidad_inventario = db.Column(db.String(30), default="pieza", nullable=False)
```

En `Material` (después de `unidades_paquete`):
```python
    expira = db.Column(db.Boolean, default=True, nullable=False)
    unidad_inventario = db.Column(db.String(30), default="pieza", nullable=False)
    en_inventario = db.Column(db.Boolean, default=False, nullable=False)
```

- [ ] **Step 4: Registrar el módulo en la app**

Editar `app/__init__.py`, dentro del `with app.app_context()` agregar:
```python
        from app.inventario import models as inventario_models  # noqa: F401
```

Crear archivos vacíos:
- `app/inventario/__init__.py` (vacío)
- `app/inventario/models.py` (con `from app.extensions import db` únicamente)

- [ ] **Step 5: Generar migración y aplicarla**

```
flask db migrate -m "add inventario fields to material"
flask db upgrade
```

- [ ] **Step 6: Run tests — debe pasar**

```
pytest tests/test_inventario_models.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/catalogo/models.py app/__init__.py app/inventario/ migrations/ tests/test_inventario_models.py
git commit -m "feat(inventario): scaffold module and add inventory fields to Material"
```

---

### Task 2: Modelo Categoria + relaciones M2M

**Files:**
- Modify: `app/inventario/models.py`
- Modify: `tests/test_inventario_models.py`

- [ ] **Step 1: Escribir test fallido**

Agregar a `tests/test_inventario_models.py`:
```python
from app.inventario.models import Categoria, MaterialCategoria, MaterialMasterCategoria


def test_crear_categoria(app, db):
    c = Categoria(nombre="mesa_control", descripcion="Mesa de control")
    db.session.add(c)
    db.session.commit()
    assert c.id is not None


def test_material_con_multiples_categorias(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    cat1 = Categoria(nombre="mesa_control")
    cat2 = Categoria(nombre="instrumental")
    db.session.add_all([cat1, cat2])
    db.session.flush()

    m = Material(tenant_id=tenant.id, nombre="Espejo")
    db.session.add(m)
    db.session.flush()

    db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cat1.id))
    db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cat2.id))
    db.session.commit()

    assert len(m.categorias) == 2
    nombres = sorted(c.nombre for c in m.categorias)
    assert nombres == ["instrumental", "mesa_control"]
```

- [ ] **Step 2: Run test — debe fallar**

```
pytest tests/test_inventario_models.py::test_crear_categoria -v
```
Expected: FAIL (`Categoria` no existe)

- [ ] **Step 3: Definir los modelos**

`app/inventario/models.py`:
```python
from app.extensions import db


class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    descripcion = db.Column(db.String(200))


class MaterialCategoria(db.Model):
    __tablename__ = "material_categoria"

    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.id"), primary_key=True
    )
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categorias.id"), primary_key=True
    )


class MaterialMasterCategoria(db.Model):
    __tablename__ = "material_master_categoria"

    material_master_id = db.Column(
        db.Integer, db.ForeignKey("materiales_master.id"), primary_key=True
    )
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categorias.id"), primary_key=True
    )
```

- [ ] **Step 4: Agregar relationships en Material y MaterialMaster**

Editar `app/catalogo/models.py`. Al final de `Material`:
```python
    categorias = db.relationship(
        "Categoria",
        secondary="material_categoria",
        backref="materiales",
    )
```

Al final de `MaterialMaster`:
```python
    categorias = db.relationship(
        "Categoria",
        secondary="material_master_categoria",
        backref="materiales_master",
    )
```

- [ ] **Step 5: Migrar y aplicar**

```
flask db migrate -m "add categorias and m2m with material"
flask db upgrade
```

- [ ] **Step 6: Run tests**

```
pytest tests/test_inventario_models.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/inventario/models.py app/catalogo/models.py migrations/ tests/test_inventario_models.py
git commit -m "feat(inventario): add Categoria with m2m to Material and MaterialMaster"
```

---

### Task 3: Modelo Operatorio

**Files:**
- Modify: `app/inventario/models.py`
- Modify: `tests/test_inventario_models.py`

- [ ] **Step 1: Test fallido**

Agregar:
```python
from app.inventario.models import Operatorio


def test_crear_operatorio(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    op = Operatorio(tenant_id=tenant.id, nombre="Operatorio 1", orden=1)
    db.session.add(op)
    db.session.commit()
    assert op.id is not None
    assert op.activo is True


def test_operatorio_nombre_unique_por_tenant(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    db.session.add(Operatorio(tenant_id=tenant.id, nombre="Op 1"))
    db.session.commit()
    db.session.add(Operatorio(tenant_id=tenant.id, nombre="Op 1"))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_models.py::test_crear_operatorio -v
```

- [ ] **Step 3: Agregar el modelo**

En `app/inventario/models.py`:
```python
class Operatorio(db.Model):
    __tablename__ = "operatorios"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    orden = db.Column(db.Integer, default=0, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "nombre", name="uq_tenant_operatorio"),
    )
```

- [ ] **Step 4: Migrar**

```
flask db migrate -m "add operatorios table"
flask db upgrade
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_inventario_models.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/inventario/models.py migrations/ tests/test_inventario_models.py
git commit -m "feat(inventario): add Operatorio model"
```

---

### Task 4: Modelos Lote, LoteUbicacion, StockUbicacion

**Files:**
- Modify: `app/inventario/models.py`
- Modify: `tests/test_inventario_models.py`

- [ ] **Step 1: Tests fallidos**

Agregar:
```python
from datetime import date
from app.inventario.models import Lote, LoteUbicacion, StockUbicacion
from app.catalogo.models import Material


def _mk_material(db, tenant_id, nombre="Abatelenguas"):
    m = Material(tenant_id=tenant_id, nombre=nombre, en_inventario=True)
    db.session.add(m)
    db.session.flush()
    return m


def test_crear_lote_con_caducidad(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = _mk_material(db, tenant.id)
    lote = Lote(
        tenant_id=tenant.id, material_id=m.id, cantidad_inicial=100,
        fecha_surtido=date(2026, 4, 1), fecha_caducidad=date(2027, 4, 1),
        precio_unitario=1.5,
    )
    db.session.add(lote)
    db.session.commit()
    assert lote.id is not None
    assert lote.agotado is False


def test_lote_ubicacion_y_stock_ubicacion(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = _mk_material(db, tenant.id)
    lote = Lote(
        tenant_id=tenant.id, material_id=m.id, cantidad_inicial=100,
        fecha_surtido=date(2026, 4, 1),
    )
    db.session.add(lote)
    db.session.flush()

    lu = LoteUbicacion(lote_id=lote.id, operatorio_id=None, cantidad_restante=100)
    su = StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None,
        cantidad=100, minimo=30, maximo=300,
    )
    db.session.add_all([lu, su])
    db.session.commit()
    assert lu.id is not None
    assert su.id is not None


def test_stock_ubicacion_unique(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    m = _mk_material(db, tenant.id)
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None, cantidad=0
    ))
    db.session.commit()
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None, cantidad=5
    ))
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_models.py::test_crear_lote_con_caducidad -v
```

- [ ] **Step 3: Agregar modelos**

En `app/inventario/models.py`:
```python
class Lote(db.Model):
    __tablename__ = "lotes"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    cantidad_inicial = db.Column(db.Integer, nullable=False)
    fecha_surtido = db.Column(db.Date, nullable=False)
    fecha_caducidad = db.Column(db.Date, nullable=True)
    precio_unitario = db.Column(db.Float, nullable=True)
    comentarios = db.Column(db.String(500), nullable=True)
    agotado = db.Column(db.Boolean, default=False, nullable=False)


class LoteUbicacion(db.Model):
    __tablename__ = "lote_ubicacion"

    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=False)
    operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    cantidad_restante = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("lote_id", "operatorio_id", name="uq_lote_ubicacion"),
    )


class StockUbicacion(db.Model):
    __tablename__ = "stock_ubicacion"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    cantidad = db.Column(db.Integer, default=0, nullable=False)
    minimo = db.Column(db.Integer, nullable=True)
    maximo = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "material_id", "operatorio_id",
            name="uq_stock_ubicacion",
        ),
    )
```

- [ ] **Step 4: Migrar**

```
flask db migrate -m "add lotes stock and lote_ubicacion tables"
flask db upgrade
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_inventario_models.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/inventario/models.py migrations/ tests/test_inventario_models.py
git commit -m "feat(inventario): add Lote LoteUbicacion StockUbicacion models"
```

---

### Task 5: Modelos Compra y MovimientoInventario

**Files:**
- Modify: `app/inventario/models.py`
- Modify: `tests/test_inventario_models.py`

- [ ] **Step 1: Tests fallidos**

Agregar:
```python
from datetime import datetime
from app.inventario.models import Compra, MovimientoInventario


def test_crear_compra(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, "Aguja corta")
    lote = Lote(
        tenant_id=tenant.id, material_id=m.id, cantidad_inicial=100,
        fecha_surtido=date(2026, 4, 1),
    )
    db.session.add(lote)
    db.session.flush()

    compra = Compra(
        tenant_id=tenant.id, material_id=m.id, lote_id=lote.id,
        fecha=date(2026, 4, 1), cantidad=100, precio_unitario=2.0,
        user_id=user.id, actualizo_costo_master=True,
    )
    db.session.add(compra)
    db.session.commit()
    assert compra.id is not None


def test_crear_movimiento(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, "Algodon")
    mov = MovimientoInventario(
        tenant_id=tenant.id, material_id=m.id,
        tipo="compra", cantidad=50, user_id=user.id,
        fecha=datetime.utcnow(),
    )
    db.session.add(mov)
    db.session.commit()
    assert mov.id is not None
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_models.py::test_crear_compra -v
```

- [ ] **Step 3: Agregar modelos**

En `app/inventario/models.py`:
```python
class Compra(db.Model):
    __tablename__ = "compras"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Float, nullable=False)
    comentarios = db.Column(db.String(500), nullable=True)
    actualizo_costo_master = db.Column(db.Boolean, default=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class MovimientoInventario(db.Model):
    __tablename__ = "movimientos_inventario"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.id"), nullable=False)
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"), nullable=True)
    tipo = db.Column(db.String(20), nullable=False)
    origen_operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    destino_operatorio_id = db.Column(
        db.Integer, db.ForeignKey("operatorios.id"), nullable=True
    )
    cantidad = db.Column(db.Integer, nullable=False)
    fecha = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    motivo = db.Column(db.String(500), nullable=True)
```

- [ ] **Step 4: Migrar**

```
flask db migrate -m "add compras and movimientos_inventario"
flask db upgrade
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_inventario_models.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/inventario/models.py migrations/ tests/test_inventario_models.py
git commit -m "feat(inventario): add Compra and MovimientoInventario"
```

---

### Task 6: Campo `dias_alerta_caducidad` en ConfigConsultorio

**Files:**
- Modify: `app/configuracion/models.py`
- Create: `tests/test_inventario_config.py`

- [ ] **Step 1: Test fallido**

`tests/test_inventario_config.py`:
```python
from app.configuracion.models import ConfigConsultorio


def test_config_tiene_dias_alerta_caducidad(app, db, tenant_and_user):
    tenant, _ = tenant_and_user
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant.id).first()
    assert cfg.dias_alerta_caducidad == 30
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_config.py -v
```

- [ ] **Step 3: Agregar columna**

En `app/configuracion/models.py` (clase `ConfigConsultorio`):
```python
    dias_alerta_caducidad = db.Column(db.Integer, default=30, nullable=False)
```

- [ ] **Step 4: Migrar**

```
flask db migrate -m "add dias_alerta_caducidad to config"
flask db upgrade
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_inventario_config.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/configuracion/models.py migrations/ tests/test_inventario_config.py
git commit -m "feat(inventario): add dias_alerta_caducidad setting"
```

---

## Fase 2 — Capa de servicios

### Task 7: Servicio `registrar_compra`

**Files:**
- Create: `app/inventario/services.py`
- Create: `tests/test_inventario_services.py`

- [ ] **Step 1: Tests fallidos**

`tests/test_inventario_services.py`:
```python
from datetime import date
import pytest
from app.catalogo.models import Material
from app.inventario.models import (
    Operatorio, Lote, LoteUbicacion, StockUbicacion, Compra,
    MovimientoInventario,
)
from app.inventario.services import registrar_compra


def _mk_material(db, tenant_id, nombre="Guantes", costo_paquete=0, unidades_paquete=1):
    m = Material(
        tenant_id=tenant_id, nombre=nombre, en_inventario=True,
        costo_paquete=costo_paquete, unidades_paquete=unidades_paquete,
    )
    db.session.add(m)
    db.session.flush()
    return m


def test_registrar_compra_crea_lote_y_suma_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)

    compra = registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=50, precio_unitario=2.0,
        fecha_surtido=date(2026, 4, 20),
        fecha_caducidad=date(2027, 4, 20),
        operatorio_destino_id=None,
        comentarios="Compra abril",
        actualizar_costo_master=False,
    )
    db.session.commit()

    lote = Lote.query.get(compra.lote_id)
    assert lote.cantidad_inicial == 50
    assert lote.fecha_caducidad == date(2027, 4, 20)

    lu = LoteUbicacion.query.filter_by(lote_id=lote.id, operatorio_id=None).first()
    assert lu.cantidad_restante == 50

    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    assert su.cantidad == 50

    mov = MovimientoInventario.query.filter_by(lote_id=lote.id).first()
    assert mov.tipo == "compra"


def test_registrar_compra_con_actualizar_costo_master(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, costo_paquete=100, unidades_paquete=100)

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=50, precio_unitario=3.0,
        fecha_surtido=date(2026, 4, 20), fecha_caducidad=None,
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=True,
    )
    db.session.commit()
    db.session.refresh(m)
    assert m.costo_paquete == 150.0
    assert m.unidades_paquete == 50


def test_registrar_compra_sin_actualizar_no_toca_costo(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, costo_paquete=100, unidades_paquete=100)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=50, precio_unitario=3.0,
        fecha_surtido=date(2026, 4, 20), fecha_caducidad=None,
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    db.session.commit()
    db.session.refresh(m)
    assert m.costo_paquete == 100
    assert m.unidades_paquete == 100


def test_registrar_compra_material_no_expira_ignora_caducidad(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    m.expira = False
    db.session.flush()

    compra = registrar_compra(
        tenant_id=tenant.id, user_id=user.id,
        material_id=m.id, cantidad=10, precio_unitario=5.0,
        fecha_surtido=date(2026, 4, 20),
        fecha_caducidad=date(2027, 4, 20),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    db.session.commit()
    lote = Lote.query.get(compra.lote_id)
    assert lote.fecha_caducidad is None
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_services.py -v
```

- [ ] **Step 3: Implementar**

`app/inventario/services.py`:
```python
from datetime import datetime
from app.extensions import db
from app.catalogo.models import Material
from app.inventario.models import (
    Lote, LoteUbicacion, StockUbicacion, Compra, MovimientoInventario,
)


def _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_id):
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant_id, material_id=material_id, operatorio_id=operatorio_id
    ).first()
    if not su:
        su = StockUbicacion(
            tenant_id=tenant_id, material_id=material_id,
            operatorio_id=operatorio_id, cantidad=0,
        )
        db.session.add(su)
        db.session.flush()
    return su


def registrar_compra(
    *, tenant_id, user_id, material_id, cantidad, precio_unitario,
    fecha_surtido, fecha_caducidad, operatorio_destino_id,
    comentarios, actualizar_costo_master,
):
    material = Material.query.filter_by(id=material_id, tenant_id=tenant_id).first()
    if not material:
        raise ValueError("Material no existe")
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser > 0")

    caducidad = fecha_caducidad if material.expira else None

    lote = Lote(
        tenant_id=tenant_id, material_id=material_id,
        cantidad_inicial=cantidad, fecha_surtido=fecha_surtido,
        fecha_caducidad=caducidad, precio_unitario=precio_unitario,
        comentarios=comentarios,
    )
    db.session.add(lote)
    db.session.flush()

    db.session.add(LoteUbicacion(
        lote_id=lote.id, operatorio_id=operatorio_destino_id,
        cantidad_restante=cantidad,
    ))

    su = _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_destino_id)
    su.cantidad += cantidad

    compra = Compra(
        tenant_id=tenant_id, material_id=material_id, lote_id=lote.id,
        fecha=fecha_surtido, cantidad=cantidad, precio_unitario=precio_unitario,
        comentarios=comentarios, actualizo_costo_master=actualizar_costo_master,
        user_id=user_id,
    )
    db.session.add(compra)

    db.session.add(MovimientoInventario(
        tenant_id=tenant_id, material_id=material_id, lote_id=lote.id,
        tipo="compra", destino_operatorio_id=operatorio_destino_id,
        cantidad=cantidad, fecha=datetime.utcnow(), user_id=user_id,
    ))

    if actualizar_costo_master:
        material.costo_paquete = precio_unitario * cantidad
        material.unidades_paquete = cantidad

    return compra
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_services.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/services.py tests/test_inventario_services.py
git commit -m "feat(inventario): service registrar_compra"
```

---

### Task 8: Servicio `transferir` (FIFO, multi-lote)

**Files:**
- Modify: `app/inventario/services.py`
- Modify: `tests/test_inventario_services.py`

- [ ] **Step 1: Tests fallidos**

Agregar a `tests/test_inventario_services.py`:
```python
from app.inventario.services import transferir


def test_transferencia_resta_origen_suma_destino(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=20, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=date(2027, 1, 1), operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()

    transferir(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=5, lote_id=None, motivo="reabasto",
    )
    db.session.commit()

    su_alm = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    su_op = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id
    ).first()
    assert su_alm.cantidad == 15
    assert su_op.cantidad == 5


def test_transferencia_fifo_por_caducidad(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 1, 1),
        fecha_caducidad=date(2027, 12, 1), operatorio_destino_id=None,
        comentarios="A", actualizar_costo_master=False,
    )
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 2, 1),
        fecha_caducidad=date(2027, 6, 1), operatorio_destino_id=None,
        comentarios="B", actualizar_costo_master=False,
    )
    db.session.flush()

    movs = transferir(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=3, lote_id=None, motivo=None,
    )
    db.session.commit()
    lote_consumido = Lote.query.get(movs[0].lote_id)
    assert lote_consumido.comentarios == "B"


def test_transferencia_multi_lote(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=3, precio_unitario=1.0, fecha_surtido=date(2026, 1, 1),
        fecha_caducidad=date(2027, 5, 1), operatorio_destino_id=None,
        comentarios="A", actualizar_costo_master=False,
    )
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 2, 1),
        fecha_caducidad=date(2027, 10, 1), operatorio_destino_id=None,
        comentarios="B", actualizar_costo_master=False,
    )
    db.session.flush()

    movs = transferir(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        origen_operatorio_id=None, destino_operatorio_id=op.id,
        cantidad=5, lote_id=None, motivo=None,
    )
    db.session.commit()
    assert len(movs) == 2
    assert sum(mv.cantidad for mv in movs) == 5


def test_transferencia_sin_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    with pytest.raises(ValueError, match="Stock insuficiente"):
        transferir(
            tenant_id=tenant.id, user_id=user.id, material_id=m.id,
            origen_operatorio_id=None, destino_operatorio_id=op.id,
            cantidad=5, lote_id=None, motivo=None,
        )
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_services.py::test_transferencia_resta_origen_suma_destino -v
```

- [ ] **Step 3: Implementar**

Agregar a `app/inventario/services.py`:
```python
from sqlalchemy import asc, nullslast


def _lotes_disponibles(tenant_id, material_id, operatorio_id):
    material = Material.query.get(material_id)
    q = (
        db.session.query(LoteUbicacion, Lote)
        .join(Lote, LoteUbicacion.lote_id == Lote.id)
        .filter(
            Lote.tenant_id == tenant_id,
            Lote.material_id == material_id,
            LoteUbicacion.operatorio_id == operatorio_id,
            LoteUbicacion.cantidad_restante > 0,
        )
    )
    if material.expira:
        q = q.order_by(nullslast(asc(Lote.fecha_caducidad)), asc(Lote.fecha_surtido))
    else:
        q = q.order_by(asc(Lote.fecha_surtido))
    return q.all()


def transferir(
    *, tenant_id, user_id, material_id, origen_operatorio_id,
    destino_operatorio_id, cantidad, lote_id, motivo,
):
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser > 0")
    if origen_operatorio_id == destino_operatorio_id:
        raise ValueError("Origen y destino no pueden ser iguales")

    su_origen = _get_or_create_stock_ubicacion(
        tenant_id, material_id, origen_operatorio_id
    )
    if su_origen.cantidad < cantidad:
        raise ValueError(
            f"Stock insuficiente (hay {su_origen.cantidad}, piden {cantidad})"
        )

    if lote_id is not None:
        lu = LoteUbicacion.query.filter_by(
            lote_id=lote_id, operatorio_id=origen_operatorio_id
        ).first()
        if not lu or lu.cantidad_restante == 0:
            raise ValueError("Lote sin stock en la ubicación de origen")
        lote = Lote.query.get(lote_id)
        lotes = [(lu, lote)]
    else:
        lotes = _lotes_disponibles(tenant_id, material_id, origen_operatorio_id)

    movs = []
    restante = cantidad
    for lu, lote in lotes:
        if restante == 0:
            break
        tomar = min(restante, lu.cantidad_restante)
        lu.cantidad_restante -= tomar

        lu_dest = LoteUbicacion.query.filter_by(
            lote_id=lote.id, operatorio_id=destino_operatorio_id
        ).first()
        if not lu_dest:
            lu_dest = LoteUbicacion(
                lote_id=lote.id, operatorio_id=destino_operatorio_id,
                cantidad_restante=0,
            )
            db.session.add(lu_dest)
            db.session.flush()
        lu_dest.cantidad_restante += tomar

        mov = MovimientoInventario(
            tenant_id=tenant_id, material_id=material_id, lote_id=lote.id,
            tipo="transferencia",
            origen_operatorio_id=origen_operatorio_id,
            destino_operatorio_id=destino_operatorio_id,
            cantidad=tomar, fecha=datetime.utcnow(),
            user_id=user_id, motivo=motivo,
        )
        db.session.add(mov)
        movs.append(mov)
        restante -= tomar

    if restante > 0:
        raise ValueError("Stock insuficiente en lotes disponibles")

    su_origen.cantidad -= cantidad
    su_destino = _get_or_create_stock_ubicacion(
        tenant_id, material_id, destino_operatorio_id
    )
    su_destino.cantidad += cantidad

    return movs
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_services.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/services.py tests/test_inventario_services.py
git commit -m "feat(inventario): service transferir with FIFO and multi-lote"
```

---

### Task 9: Servicio `ajustar`

**Files:**
- Modify: `app/inventario/services.py`
- Modify: `tests/test_inventario_services.py`

- [ ] **Step 1: Tests**

Agregar:
```python
from app.inventario.services import ajustar


def test_ajuste_aumenta_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()

    mov = ajustar(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        operatorio_id=None, cantidad_nueva=15, motivo="conteo",
        lote_id=None,
    )
    db.session.commit()
    assert mov.tipo == "ajuste"
    assert mov.cantidad == 5
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    assert su.cantidad == 15


def test_ajuste_reduce_stock(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()
    mov = ajustar(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        operatorio_id=None, cantidad_nueva=3, motivo="merma",
        lote_id=None,
    )
    db.session.commit()
    assert mov.cantidad == -7
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_services.py::test_ajuste_aumenta_stock -v
```

- [ ] **Step 3: Implementar**

Agregar a `app/inventario/services.py`:
```python
def ajustar(
    *, tenant_id, user_id, material_id, operatorio_id, cantidad_nueva,
    motivo, lote_id,
):
    if cantidad_nueva < 0:
        raise ValueError("cantidad_nueva no puede ser negativa")
    if not motivo:
        raise ValueError("motivo es requerido")

    su = _get_or_create_stock_ubicacion(tenant_id, material_id, operatorio_id)
    delta = cantidad_nueva - su.cantidad
    if delta == 0:
        raise ValueError("Ajuste sin cambio real")

    su.cantidad = cantidad_nueva

    if lote_id:
        lu = LoteUbicacion.query.filter_by(
            lote_id=lote_id, operatorio_id=operatorio_id
        ).first()
        if lu:
            lu.cantidad_restante = max(0, lu.cantidad_restante + delta)

    mov = MovimientoInventario(
        tenant_id=tenant_id, material_id=material_id, lote_id=lote_id,
        tipo="ajuste",
        origen_operatorio_id=operatorio_id if delta < 0 else None,
        destino_operatorio_id=operatorio_id if delta > 0 else None,
        cantidad=delta, fecha=datetime.utcnow(),
        user_id=user_id, motivo=motivo,
    )
    db.session.add(mov)
    return mov
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_services.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/services.py tests/test_inventario_services.py
git commit -m "feat(inventario): service ajustar for manual stock corrections"
```

---

### Task 10: Servicio `calcular_alertas`

**Files:**
- Modify: `app/inventario/services.py`
- Modify: `tests/test_inventario_services.py`

- [ ] **Step 1: Tests**

Agregar:
```python
from datetime import timedelta
from app.inventario.services import calcular_alertas


def test_alerta_stock_bajo_independiente_por_ubicacion(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id, "Guantes")
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()

    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=5, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.flush()
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    su.minimo = 10
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id,
        cantidad=0, minimo=1,
    ))
    db.session.commit()

    alertas = calcular_alertas(tenant_id=tenant.id)
    assert len(alertas["bajo"]) == 2


def test_alerta_caducidad_respeta_config(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    from app.configuracion.models import ConfigConsultorio
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant.id).first()
    cfg.dias_alerta_caducidad = 30
    db.session.flush()
    hoy = date.today()
    m = _mk_material(db, tenant.id)
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=hoy,
        fecha_caducidad=hoy + timedelta(days=15),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=hoy,
        fecha_caducidad=hoy + timedelta(days=90),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    db.session.commit()
    alertas = calcular_alertas(tenant_id=tenant.id)
    assert len(alertas["caducidad"]) == 1


def test_material_no_expira_sin_alerta_caducidad(app, db, tenant_and_user):
    tenant, user = tenant_and_user
    m = _mk_material(db, tenant.id)
    m.expira = False
    db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1.0, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    alertas = calcular_alertas(tenant_id=tenant.id)
    assert len(alertas["caducidad"]) == 0
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_services.py::test_alerta_stock_bajo_independiente_por_ubicacion -v
```

- [ ] **Step 3: Implementar**

Agregar a `app/inventario/services.py`:
```python
from datetime import date, timedelta
from app.configuracion.models import ConfigConsultorio
from app.inventario.models import Operatorio


def _ubicacion_nombre(tenant_id, operatorio_id):
    if operatorio_id is None:
        return "Almacén"
    op = Operatorio.query.filter_by(id=operatorio_id, tenant_id=tenant_id).first()
    return op.nombre if op else "Desconocida"


def _stock_total_lote(lote_id):
    total = (
        db.session.query(db.func.coalesce(db.func.sum(LoteUbicacion.cantidad_restante), 0))
        .filter(LoteUbicacion.lote_id == lote_id)
        .scalar()
    )
    return total or 0


def calcular_alertas(*, tenant_id):
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    dias = cfg.dias_alerta_caducidad if cfg else 30
    limite = date.today() + timedelta(days=dias)

    stocks = StockUbicacion.query.filter_by(tenant_id=tenant_id).all()
    bajo, alto = [], []
    for su in stocks:
        material = Material.query.get(su.material_id)
        base = {
            "material_id": su.material_id,
            "material_nombre": material.nombre,
            "operatorio_id": su.operatorio_id,
            "ubicacion": _ubicacion_nombre(tenant_id, su.operatorio_id),
            "cantidad": su.cantidad,
        }
        if su.minimo is not None and su.cantidad <= su.minimo:
            bajo.append({**base, "minimo": su.minimo})
        if su.maximo is not None and su.cantidad >= su.maximo:
            alto.append({**base, "maximo": su.maximo})

    caducidad = []
    lotes = (
        db.session.query(Lote, Material)
        .join(Material, Lote.material_id == Material.id)
        .filter(
            Lote.tenant_id == tenant_id,
            Lote.agotado == False,  # noqa: E712
            Lote.fecha_caducidad.isnot(None),
            Lote.fecha_caducidad <= limite,
            Material.expira == True,  # noqa: E712
        ).all()
    )
    for lote, material in lotes:
        caducidad.append({
            "lote_id": lote.id,
            "material_id": material.id,
            "material_nombre": material.nombre,
            "fecha_caducidad": lote.fecha_caducidad.isoformat(),
            "cantidad_restante": _stock_total_lote(lote.id),
        })

    return {"bajo": bajo, "alto": alto, "caducidad": caducidad}
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_services.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/services.py tests/test_inventario_services.py
git commit -m "feat(inventario): service calcular_alertas"
```

---

## Fase 3 — API (schemas y rutas)

### Task 11: Schemas Marshmallow

**Files:**
- Create: `app/inventario/schemas.py`

- [ ] **Step 1: Crear**

`app/inventario/schemas.py`:
```python
from marshmallow import Schema, fields, validate


class CategoriaSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    descripcion = fields.Str(allow_none=True)


class OperatorioSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    orden = fields.Int(load_default=0)
    activo = fields.Bool(load_default=True)


class UmbralesUbicacionSchema(Schema):
    operatorio_id = fields.Int(allow_none=True)
    minimo = fields.Int(allow_none=True)
    maximo = fields.Int(allow_none=True)


class MaterialInventarioSchema(Schema):
    id = fields.Int(dump_only=True)
    nombre = fields.Str(required=True)
    categorias = fields.List(fields.Int(), load_default=[])
    expira = fields.Bool(load_default=True)
    unidad_inventario = fields.Str(load_default="pieza")
    en_inventario = fields.Bool(load_default=True)
    umbrales = fields.List(fields.Nested(UmbralesUbicacionSchema), load_default=[])


class CompraSchema(Schema):
    id = fields.Int(dump_only=True)
    material_id = fields.Int(required=True)
    cantidad = fields.Int(required=True, validate=validate.Range(min=1))
    precio_unitario = fields.Float(required=True, validate=validate.Range(min=0))
    fecha_surtido = fields.Date(required=True)
    fecha_caducidad = fields.Date(allow_none=True)
    no_caduca = fields.Bool(load_default=False)
    operatorio_destino_id = fields.Int(allow_none=True, load_default=None)
    comentarios = fields.Str(allow_none=True)
    actualizar_costo_master = fields.Bool(load_default=True)


class TransferenciaSchema(Schema):
    material_id = fields.Int(required=True)
    origen_operatorio_id = fields.Int(allow_none=True)
    destino_operatorio_id = fields.Int(allow_none=True)
    cantidad = fields.Int(required=True, validate=validate.Range(min=1))
    lote_id = fields.Int(allow_none=True, load_default=None)
    motivo = fields.Str(allow_none=True)


class AjusteSchema(Schema):
    material_id = fields.Int(required=True)
    operatorio_id = fields.Int(allow_none=True)
    cantidad_nueva = fields.Int(required=True, validate=validate.Range(min=0))
    motivo = fields.Str(required=True, validate=validate.Length(min=1))
    lote_id = fields.Int(allow_none=True, load_default=None)


class ImportMasterInventarioSchema(Schema):
    master_ids = fields.List(fields.Int(), required=True)
```

- [ ] **Step 2: Commit**

```bash
git add app/inventario/schemas.py
git commit -m "feat(inventario): marshmallow schemas"
```

---

### Task 12: Blueprint + rutas de operatorios

**Files:**
- Create: `app/inventario/routes.py`
- Modify: `app/__init__.py`
- Create: `tests/test_inventario_routes_operatorios.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_operatorios.py`:
```python
def test_listar_operatorios_vacio(client, auth_headers):
    resp = client.get("/api/v1/inventario/operatorios", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_crear_operatorio(client, auth_headers):
    resp = client.post(
        "/api/v1/inventario/operatorios",
        json={"nombre": "Op Infantil", "orden": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["nombre"] == "Op Infantil"


def test_no_borrar_operatorio_con_stock(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import Operatorio, StockUbicacion
    tenant, _ = tenant_and_user
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add(op); db.session.flush()
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.flush()
    db.session.add(StockUbicacion(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=op.id, cantidad=5
    ))
    db.session.commit()

    resp = client.delete(
        f"/api/v1/inventario/operatorios/{op.id}", headers=auth_headers
    )
    assert resp.status_code == 409
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_operatorios.py -v
```

- [ ] **Step 3: Implementar routes**

`app/inventario/routes.py`:
```python
from flask import Blueprint, request, jsonify, g
from marshmallow import ValidationError
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.inventario.models import Operatorio, StockUbicacion
from app.inventario.schemas import OperatorioSchema

inventario_bp = Blueprint("inventario", __name__, url_prefix="/api/v1/inventario")


@inventario_bp.route("/operatorios", methods=["GET"])
@require_auth
def listar_operatorios():
    ops = Operatorio.query.filter_by(tenant_id=g.tenant_id).order_by(
        Operatorio.orden, Operatorio.nombre
    ).all()
    return jsonify(OperatorioSchema(many=True).dump(ops))


@inventario_bp.route("/operatorios", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_operatorio():
    try:
        data = OperatorioSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    op = Operatorio(tenant_id=g.tenant_id, **data)
    db.session.add(op)
    db.session.commit()
    return jsonify(OperatorioSchema().dump(op)), 201


@inventario_bp.route("/operatorios/<int:op_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_operatorio(op_id):
    op = Operatorio.query.filter_by(id=op_id, tenant_id=g.tenant_id).first_or_404()
    try:
        data = OperatorioSchema(partial=True).load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    for k, v in data.items():
        setattr(op, k, v)
    db.session.commit()
    return jsonify(OperatorioSchema().dump(op))


@inventario_bp.route("/operatorios/<int:op_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def eliminar_operatorio(op_id):
    op = Operatorio.query.filter_by(id=op_id, tenant_id=g.tenant_id).first_or_404()
    tiene_stock = StockUbicacion.query.filter(
        StockUbicacion.tenant_id == g.tenant_id,
        StockUbicacion.operatorio_id == op_id,
        StockUbicacion.cantidad > 0,
    ).first()
    if tiene_stock:
        return jsonify({
            "error": "Operatorio tiene stock; transfiere antes de borrar"
        }), 409
    db.session.delete(op)
    db.session.commit()
    return jsonify({"message": "Operatorio eliminado"})
```

Editar `app/__init__.py`:
```python
    from app.inventario.routes import inventario_bp
    ...
    app.register_blueprint(inventario_bp)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_operatorios.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py app/__init__.py tests/test_inventario_routes_operatorios.py
git commit -m "feat(inventario): operatorios API"
```

---

### Task 13: Rutas de categorías

**Files:**
- Modify: `app/inventario/routes.py`
- Create: `tests/test_inventario_routes_categorias.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_categorias.py`:
```python
def test_listar_categorias(client, auth_headers, db):
    from app.inventario.models import Categoria
    db.session.add_all([
        Categoria(nombre="mesa_control"),
        Categoria(nombre="instrumental"),
    ])
    db.session.commit()

    resp = client.get("/api/v1/inventario/categorias", headers=auth_headers)
    assert resp.status_code == 200
    nombres = sorted(c["nombre"] for c in resp.get_json())
    assert "mesa_control" in nombres
    assert "instrumental" in nombres
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_categorias.py -v
```

- [ ] **Step 3: Añadir routes**

En `app/inventario/routes.py`:
```python
from app.inventario.models import Categoria
from app.inventario.schemas import CategoriaSchema


@inventario_bp.route("/categorias", methods=["GET"])
@require_auth
def listar_categorias():
    cats = Categoria.query.order_by(Categoria.nombre).all()
    return jsonify(CategoriaSchema(many=True).dump(cats))


@inventario_bp.route("/categorias", methods=["POST"])
@require_auth
@require_role("admin")
def crear_categoria():
    try:
        data = CategoriaSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    if Categoria.query.filter_by(nombre=data["nombre"]).first():
        return jsonify({"error": "Categoría ya existe"}), 409
    cat = Categoria(**data)
    db.session.add(cat)
    db.session.commit()
    return jsonify(CategoriaSchema().dump(cat)), 201
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_categorias.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_routes_categorias.py
git commit -m "feat(inventario): categorias API"
```

---

### Task 14: Rutas de compras

**Files:**
- Modify: `app/inventario/routes.py`
- Create: `tests/test_inventario_routes_compras.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_compras.py`:
```python
def test_registrar_compra_endpoint(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    db.session.add(m); db.session.commit()

    resp = client.post(
        "/api/v1/inventario/compras",
        json={
            "material_id": m.id, "cantidad": 50, "precio_unitario": 2.5,
            "fecha_surtido": "2026-04-20", "fecha_caducidad": "2027-04-20",
            "actualizar_costo_master": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["cantidad"] == 50


def test_viewer_no_puede_registrar_compra(client, db, tenant_and_user):
    from app.auth.models import User
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    v = User(tenant_id=tenant.id, email="v@t.com", name="V", role="viewer")
    v.set_password("password123")
    db.session.add(v)
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.commit()

    login = client.post("/api/v1/auth/login", json={
        "email": "v@t.com", "password": "password123",
    })
    headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}
    resp = client.post(
        "/api/v1/inventario/compras",
        json={
            "material_id": m.id, "cantidad": 1, "precio_unitario": 1,
            "fecha_surtido": "2026-04-20", "actualizar_costo_master": False,
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_listar_compras(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.commit()
    client.post("/api/v1/inventario/compras", json={
        "material_id": m.id, "cantidad": 5, "precio_unitario": 1,
        "fecha_surtido": "2026-04-20", "actualizar_costo_master": False,
    }, headers=auth_headers)
    resp = client.get("/api/v1/inventario/compras", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_compras.py -v
```

- [ ] **Step 3: Implementar**

En `app/inventario/routes.py`:
```python
from app.inventario.models import Compra
from app.inventario.schemas import CompraSchema
from app.inventario.services import registrar_compra


@inventario_bp.route("/compras", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def registrar_compra_endpoint():
    try:
        data = CompraSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    caducidad = None if data.get("no_caduca") else data.get("fecha_caducidad")
    try:
        compra = registrar_compra(
            tenant_id=g.tenant_id, user_id=g.current_user.id,
            material_id=data["material_id"], cantidad=data["cantidad"],
            precio_unitario=data["precio_unitario"],
            fecha_surtido=data["fecha_surtido"],
            fecha_caducidad=caducidad,
            operatorio_destino_id=data.get("operatorio_destino_id"),
            comentarios=data.get("comentarios"),
            actualizar_costo_master=data["actualizar_costo_master"],
        )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
    return jsonify({
        "id": compra.id, "material_id": compra.material_id,
        "cantidad": compra.cantidad, "precio_unitario": compra.precio_unitario,
        "fecha": compra.fecha.isoformat(), "lote_id": compra.lote_id,
    }), 201


@inventario_bp.route("/compras", methods=["GET"])
@require_auth
def listar_compras():
    material_id = request.args.get("material_id", type=int)
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    q = Compra.query.filter_by(tenant_id=g.tenant_id)
    if material_id:
        q = q.filter_by(material_id=material_id)
    if fecha_desde:
        q = q.filter(Compra.fecha >= fecha_desde)
    if fecha_hasta:
        q = q.filter(Compra.fecha <= fecha_hasta)
    compras = q.order_by(Compra.fecha.desc()).all()
    return jsonify([{
        "id": c.id, "material_id": c.material_id, "cantidad": c.cantidad,
        "precio_unitario": c.precio_unitario, "fecha": c.fecha.isoformat(),
        "comentarios": c.comentarios, "lote_id": c.lote_id,
    } for c in compras])
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_compras.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_routes_compras.py
git commit -m "feat(inventario): compras API"
```

---

### Task 15: Rutas de transferencias, ajustes, movimientos

**Files:**
- Modify: `app/inventario/routes.py`
- Create: `tests/test_inventario_routes_movimientos.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_movimientos.py`:
```python
from datetime import date


def _seed(db, tenant_id, user_id, cantidad=20):
    from app.catalogo.models import Material
    from app.inventario.models import Operatorio
    from app.inventario.services import registrar_compra
    m = Material(tenant_id=tenant_id, nombre="Alg", en_inventario=True)
    db.session.add(m); db.session.flush()
    op = Operatorio(tenant_id=tenant_id, nombre="Op 1")
    db.session.add(op); db.session.flush()
    registrar_compra(
        tenant_id=tenant_id, user_id=user_id, material_id=m.id,
        cantidad=cantidad, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    return m, op


def test_transferencia(client, auth_headers, db, tenant_and_user):
    tenant, user = tenant_and_user
    m, op = _seed(db, tenant.id, user.id)
    resp = client.post(
        "/api/v1/inventario/transferencias",
        json={
            "material_id": m.id, "origen_operatorio_id": None,
            "destino_operatorio_id": op.id, "cantidad": 5, "motivo": "r",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_transferencia_sin_stock_409(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import Operatorio
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    op = Operatorio(tenant_id=tenant.id, nombre="Op 1")
    db.session.add_all([m, op]); db.session.commit()
    resp = client.post(
        "/api/v1/inventario/transferencias",
        json={
            "material_id": m.id, "origen_operatorio_id": None,
            "destino_operatorio_id": op.id, "cantidad": 5, "motivo": None,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_ajuste(client, auth_headers, db, tenant_and_user):
    tenant, user = tenant_and_user
    m, _ = _seed(db, tenant.id, user.id, cantidad=10)
    resp = client.post(
        "/api/v1/inventario/ajustes",
        json={
            "material_id": m.id, "operatorio_id": None,
            "cantidad_nueva": 7, "motivo": "conteo",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_listar_movimientos(client, auth_headers, db, tenant_and_user):
    tenant, user = tenant_and_user
    _seed(db, tenant.id, user.id)
    resp = client.get("/api/v1/inventario/movimientos", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) >= 1
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_movimientos.py -v
```

- [ ] **Step 3: Implementar**

En `app/inventario/routes.py`:
```python
from app.inventario.models import MovimientoInventario
from app.inventario.schemas import TransferenciaSchema, AjusteSchema
from app.inventario.services import transferir, ajustar


@inventario_bp.route("/transferencias", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def transferir_endpoint():
    try:
        data = TransferenciaSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    try:
        movs = transferir(
            tenant_id=g.tenant_id, user_id=g.current_user.id,
            material_id=data["material_id"],
            origen_operatorio_id=data.get("origen_operatorio_id"),
            destino_operatorio_id=data.get("destino_operatorio_id"),
            cantidad=data["cantidad"],
            lote_id=data.get("lote_id"),
            motivo=data.get("motivo"),
        )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        msg = str(e)
        code = 409 if "Stock insuficiente" in msg else 400
        return jsonify({"error": msg}), code
    return jsonify({"movimientos": [mv.id for mv in movs]}), 201


@inventario_bp.route("/ajustes", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def ajustar_endpoint():
    try:
        data = AjusteSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    try:
        mov = ajustar(
            tenant_id=g.tenant_id, user_id=g.current_user.id,
            material_id=data["material_id"],
            operatorio_id=data.get("operatorio_id"),
            cantidad_nueva=data["cantidad_nueva"],
            motivo=data["motivo"],
            lote_id=data.get("lote_id"),
        )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": mov.id, "delta": mov.cantidad}), 201


@inventario_bp.route("/movimientos", methods=["GET"])
@require_auth
def listar_movimientos():
    material_id = request.args.get("material_id", type=int)
    tipo = request.args.get("tipo")
    q = MovimientoInventario.query.filter_by(tenant_id=g.tenant_id)
    if material_id:
        q = q.filter_by(material_id=material_id)
    if tipo:
        q = q.filter_by(tipo=tipo)
    movs = q.order_by(MovimientoInventario.fecha.desc()).limit(500).all()
    return jsonify([{
        "id": mv.id, "tipo": mv.tipo, "material_id": mv.material_id,
        "lote_id": mv.lote_id,
        "origen_operatorio_id": mv.origen_operatorio_id,
        "destino_operatorio_id": mv.destino_operatorio_id,
        "cantidad": mv.cantidad, "fecha": mv.fecha.isoformat(),
        "motivo": mv.motivo,
    } for mv in movs])
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_movimientos.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_routes_movimientos.py
git commit -m "feat(inventario): transferencias ajustes movimientos API"
```

---

### Task 16: Rutas de alertas

**Files:**
- Modify: `app/inventario/routes.py`
- Create: `tests/test_inventario_routes_alertas.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_alertas.py`:
```python
from datetime import date, timedelta


def test_alertas_endpoint(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import StockUbicacion
    from app.inventario.services import registrar_compra
    tenant, user = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=2, precio_unitario=1, fecha_surtido=date.today(),
        fecha_caducidad=date.today() + timedelta(days=10),
        operatorio_destino_id=None, comentarios=None,
        actualizar_costo_master=False,
    )
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id
    ).first()
    su.minimo = 5
    db.session.commit()

    resp = client.get("/api/v1/inventario/alertas", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["bajo"]) == 1
    assert len(data["caducidad"]) == 1


def test_alertas_resumen(client, auth_headers):
    resp = client.get("/api/v1/inventario/alertas/resumen", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"bajo", "alto", "caducidad"}
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_alertas.py -v
```

- [ ] **Step 3: Implementar**

En `app/inventario/routes.py`:
```python
from app.inventario.services import calcular_alertas


@inventario_bp.route("/alertas", methods=["GET"])
@require_auth
def alertas_endpoint():
    return jsonify(calcular_alertas(tenant_id=g.tenant_id))


@inventario_bp.route("/alertas/resumen", methods=["GET"])
@require_auth
def alertas_resumen():
    a = calcular_alertas(tenant_id=g.tenant_id)
    return jsonify({
        "bajo": len(a["bajo"]),
        "alto": len(a["alto"]),
        "caducidad": len(a["caducidad"]),
    })
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_alertas.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_routes_alertas.py
git commit -m "feat(inventario): alertas endpoints"
```

---

### Task 17: Rutas de materiales en inventario

**Files:**
- Modify: `app/inventario/routes.py`
- Create: `tests/test_inventario_routes_materiales.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_materiales.py`:
```python
from datetime import date


def test_listar_materiales(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.services import registrar_compra
    tenant, user = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Guantes", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=10, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()

    resp = client.get("/api/v1/inventario/materiales", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["total_global"] == 10


def test_no_lista_sin_en_inventario(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    db.session.add(Material(tenant_id=tenant.id, nombre="SoloPricing", en_inventario=False))
    db.session.commit()
    resp = client.get("/api/v1/inventario/materiales", headers=auth_headers)
    assert len(resp.get_json()) == 0


def test_inspeccionar(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.services import registrar_compra
    tenant, user = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Aguja", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=tenant.id, user_id=user.id, material_id=m.id,
        cantidad=20, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=date(2027, 1, 1), operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    resp = client.get(
        f"/api/v1/inventario/materiales/{m.id}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["lotes"]) == 1
    assert len(data["stock_por_ubicacion"]) == 1


def test_isolation_material(client, auth_headers, db, tenant_and_user):
    from app.auth.models import Tenant
    from app.catalogo.models import Material
    otro = Tenant(name="Otro", slug="otro")
    db.session.add(otro); db.session.flush()
    m = Material(tenant_id=otro.id, nombre="Ajeno", en_inventario=True)
    db.session.add(m); db.session.commit()
    resp = client.get(f"/api/v1/inventario/materiales/{m.id}", headers=auth_headers)
    assert resp.status_code == 404


def test_actualizar_umbrales(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import Material
    from app.inventario.models import StockUbicacion
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="X", en_inventario=True)
    db.session.add(m); db.session.commit()
    resp = client.put(
        f"/api/v1/inventario/materiales/{m.id}",
        json={
            "expira": False, "unidad_inventario": "caja",
            "umbrales": [{"operatorio_id": None, "minimo": 5, "maximo": 30}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    su = StockUbicacion.query.filter_by(
        tenant_id=tenant.id, material_id=m.id, operatorio_id=None
    ).first()
    assert su.minimo == 5 and su.maximo == 30
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_materiales.py -v
```

- [ ] **Step 3: Implementar**

En `app/inventario/routes.py`:
```python
from app.catalogo.models import Material, MaterialMaster
from app.inventario.models import Lote, LoteUbicacion, MaterialCategoria
from app.inventario.schemas import (
    MaterialInventarioSchema, ImportMasterInventarioSchema,
)
from app.inventario.services import _get_or_create_stock_ubicacion


def _serializar_lista(m):
    total = (
        db.session.query(db.func.coalesce(db.func.sum(StockUbicacion.cantidad), 0))
        .filter_by(tenant_id=m.tenant_id, material_id=m.id)
        .scalar()
    ) or 0
    return {
        "id": m.id, "nombre": m.nombre,
        "expira": m.expira, "unidad_inventario": m.unidad_inventario,
        "categorias": [c.nombre for c in m.categorias],
        "total_global": int(total),
    }


@inventario_bp.route("/materiales", methods=["GET"])
@require_auth
def listar_materiales_inv():
    categoria = request.args.get("categoria")
    busqueda = request.args.get("busqueda")
    q = Material.query.filter_by(tenant_id=g.tenant_id, en_inventario=True)
    if categoria:
        q = q.join(Material.categorias).filter(Categoria.nombre == categoria)
    if busqueda:
        q = q.filter(Material.nombre.ilike(f"%{busqueda}%"))
    materiales = q.order_by(Material.nombre).all()
    return jsonify([_serializar_lista(m) for m in materiales])


@inventario_bp.route("/materiales/<int:material_id>", methods=["GET"])
@require_auth
def inspeccionar_material(material_id):
    m = Material.query.filter_by(
        id=material_id, tenant_id=g.tenant_id, en_inventario=True
    ).first_or_404()
    stocks = StockUbicacion.query.filter_by(
        tenant_id=g.tenant_id, material_id=m.id
    ).all()
    lotes = Lote.query.filter_by(
        tenant_id=g.tenant_id, material_id=m.id, agotado=False
    ).all()
    lote_data = []
    for lote in lotes:
        lus = LoteUbicacion.query.filter_by(lote_id=lote.id).all()
        lote_data.append({
            "id": lote.id,
            "fecha_surtido": lote.fecha_surtido.isoformat(),
            "fecha_caducidad": lote.fecha_caducidad.isoformat() if lote.fecha_caducidad else None,
            "cantidad_inicial": lote.cantidad_inicial,
            "precio_unitario": lote.precio_unitario,
            "comentarios": lote.comentarios,
            "ubicaciones": [
                {"operatorio_id": lu.operatorio_id, "cantidad_restante": lu.cantidad_restante}
                for lu in lus if lu.cantidad_restante > 0
            ],
        })
    return jsonify({
        "id": m.id, "nombre": m.nombre,
        "expira": m.expira, "unidad_inventario": m.unidad_inventario,
        "categorias": [{"id": c.id, "nombre": c.nombre} for c in m.categorias],
        "stock_por_ubicacion": [{
            "operatorio_id": s.operatorio_id, "cantidad": s.cantidad,
            "minimo": s.minimo, "maximo": s.maximo,
        } for s in stocks],
        "lotes": lote_data,
    })


@inventario_bp.route("/materiales", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def crear_material_inv():
    try:
        data = MaterialInventarioSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    if Material.query.filter_by(tenant_id=g.tenant_id, nombre=data["nombre"]).first():
        return jsonify({"error": "Ya existe"}), 409
    m = Material(
        tenant_id=g.tenant_id, nombre=data["nombre"],
        expira=data["expira"], unidad_inventario=data["unidad_inventario"],
        en_inventario=True,
    )
    db.session.add(m); db.session.flush()
    for cid in data.get("categorias", []):
        db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cid))
    for u in data.get("umbrales", []):
        su = _get_or_create_stock_ubicacion(g.tenant_id, m.id, u.get("operatorio_id"))
        su.minimo = u.get("minimo")
        su.maximo = u.get("maximo")
    db.session.commit()
    return jsonify({"id": m.id, "nombre": m.nombre}), 201


@inventario_bp.route("/materiales/<int:material_id>", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def actualizar_material_inv(material_id):
    m = Material.query.filter_by(id=material_id, tenant_id=g.tenant_id).first_or_404()
    try:
        data = MaterialInventarioSchema(partial=True).load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    for field in ("expira", "unidad_inventario", "en_inventario", "nombre"):
        if field in data:
            setattr(m, field, data[field])

    if "categorias" in data:
        MaterialCategoria.query.filter_by(material_id=m.id).delete()
        for cid in data["categorias"]:
            db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cid))

    for u in data.get("umbrales", []):
        su = _get_or_create_stock_ubicacion(g.tenant_id, m.id, u.get("operatorio_id"))
        if "minimo" in u:
            su.minimo = u["minimo"]
        if "maximo" in u:
            su.maximo = u["maximo"]

    db.session.commit()
    return jsonify({"id": m.id})
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_materiales.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_routes_materiales.py
git commit -m "feat(inventario): materiales listado inspeccion y umbrales"
```

---

### Task 18: Importación desde master

**Files:**
- Modify: `app/inventario/routes.py`
- Create: `tests/test_inventario_routes_importar.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_routes_importar.py`:
```python
def test_master_disponibles(client, auth_headers, db):
    from app.catalogo.models import MaterialMaster
    db.session.add_all([
        MaterialMaster(nombre="A", categoria="general"),
        MaterialMaster(nombre="B", categoria="general"),
    ])
    db.session.commit()
    resp = client.get("/api/v1/inventario/master-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


def test_importar(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import MaterialMaster, Material
    tenant, _ = tenant_and_user
    a = MaterialMaster(nombre="A", categoria="general")
    b = MaterialMaster(nombre="B", categoria="general")
    db.session.add_all([a, b]); db.session.commit()
    resp = client.post(
        "/api/v1/inventario/materiales/importar-master",
        json={"master_ids": [a.id, b.id]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    count = Material.query.filter_by(tenant_id=tenant.id, en_inventario=True).count()
    assert count == 2


def test_importar_no_duplica(client, auth_headers, db, tenant_and_user):
    from app.catalogo.models import MaterialMaster, Material
    tenant, _ = tenant_and_user
    master = MaterialMaster(nombre="A", categoria="general")
    db.session.add(master); db.session.flush()
    db.session.add(Material(
        tenant_id=tenant.id, nombre="A", master_id=master.id, en_inventario=False
    ))
    db.session.commit()
    client.post(
        "/api/v1/inventario/materiales/importar-master",
        json={"master_ids": [master.id]},
        headers=auth_headers,
    )
    mats = Material.query.filter_by(tenant_id=tenant.id, nombre="A").all()
    assert len(mats) == 1
    assert mats[0].en_inventario is True
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_routes_importar.py -v
```

- [ ] **Step 3: Implementar**

En `app/inventario/routes.py`:
```python
@inventario_bp.route("/master-disponibles", methods=["GET"])
@require_auth
def master_disponibles():
    subq = db.session.query(Material.master_id).filter(
        Material.tenant_id == g.tenant_id,
        Material.master_id.isnot(None),
        Material.en_inventario == True,  # noqa: E712
    )
    q = MaterialMaster.query.filter(~MaterialMaster.id.in_(subq))
    categoria = request.args.get("categoria")
    busqueda = request.args.get("busqueda")
    if categoria:
        q = q.join(MaterialMaster.categorias).filter(Categoria.nombre == categoria)
    if busqueda:
        q = q.filter(MaterialMaster.nombre.ilike(f"%{busqueda}%"))
    masters = q.order_by(MaterialMaster.nombre).all()
    return jsonify([{
        "id": m.id, "nombre": m.nombre,
        "expira": m.expira, "unidad_inventario": m.unidad_inventario,
        "categorias": [c.nombre for c in m.categorias],
    } for m in masters])


@inventario_bp.route("/materiales/importar-master", methods=["POST"])
@require_auth
@require_role("admin", "editor")
def importar_master_inv():
    try:
        data = ImportMasterInventarioSchema().load(request.get_json())
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400

    masters = MaterialMaster.query.filter(
        MaterialMaster.id.in_(data["master_ids"])
    ).all()

    importados = 0
    for master in masters:
        existente = Material.query.filter_by(
            tenant_id=g.tenant_id, nombre=master.nombre
        ).first()
        if existente:
            if not existente.en_inventario:
                existente.en_inventario = True
                importados += 1
            continue
        m = Material(
            tenant_id=g.tenant_id, master_id=master.id, nombre=master.nombre,
            expira=master.expira, unidad_inventario=master.unidad_inventario,
            en_inventario=True,
        )
        db.session.add(m); db.session.flush()
        for cat in master.categorias:
            db.session.add(MaterialCategoria(material_id=m.id, categoria_id=cat.id))
        importados += 1

    db.session.commit()
    return jsonify({"importados": importados}), 201
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_routes_importar.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/inventario/routes.py tests/test_inventario_routes_importar.py
git commit -m "feat(inventario): importar master into tenant inventory"
```

---

## Fase 4 — Seed desde el Excel

### Task 19: Script de extracción

**Files:**
- Create: `scripts/extract_inventario_seed.py`
- Create: `seed_data/inventario_materiales.json`

- [ ] **Step 1: Crear script**

`scripts/extract_inventario_seed.py`:
```python
"""Lee Inventario smile studio.xlsx y emite seed_data/inventario_materiales.json.

Uso:
    python scripts/extract_inventario_seed.py "Inventario smile studio.xlsx"
"""
import json
import sys
from pathlib import Path
import pandas as pd

NO_EXPIRA = {"no", "NO", "No"}


def _extraer_hoja(xlsx_path, sheet):
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
    out = {}
    for _, row in df.iloc[7:].iterrows():
        nombre = row[0]
        if pd.isna(nombre):
            continue
        nombre = str(nombre).strip()
        if not nombre:
            continue
        cad_val = row[6]
        no_expira = (
            not pd.isna(cad_val) and str(cad_val).strip() in NO_EXPIRA
        )
        out[nombre.upper()] = {"expira": not no_expira}
    return out


def main():
    if len(sys.argv) < 2:
        print("Uso: extract_inventario_seed.py <archivo.xlsx>")
        sys.exit(1)
    xlsx = sys.argv[1]
    mesa = _extraer_hoja(xlsx, "MESA DE CONTROL")
    inst = _extraer_hoja(xlsx, "INSTRUMENTAL")

    todos = {}
    for nombre, info in mesa.items():
        todos[nombre] = {
            "nombre": nombre, "expira": info["expira"],
            "unidad_inventario": "pieza",
            "categorias": ["mesa_control"],
        }
    for nombre, info in inst.items():
        if nombre in todos:
            if "instrumental" not in todos[nombre]["categorias"]:
                todos[nombre]["categorias"].append("instrumental")
            todos[nombre]["expira"] = todos[nombre]["expira"] and info["expira"]
        else:
            todos[nombre] = {
                "nombre": nombre, "expira": info["expira"],
                "unidad_inventario": "pieza",
                "categorias": ["instrumental"],
            }

    salida = sorted(todos.values(), key=lambda m: m["nombre"])
    out = Path("seed_data/inventario_materiales.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {out} con {len(salida)} materiales")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Ejecutar**

```
python scripts/extract_inventario_seed.py "Inventario smile studio.xlsx"
```
Expected: `Escrito seed_data/inventario_materiales.json con 324 materiales`

- [ ] **Step 3: Verificar**

```
python -c "import json; d = json.load(open('seed_data/inventario_materiales.json', encoding='utf-8')); print(len(d), d[0])"
```
Expected: `324 {...}`

- [ ] **Step 4: Commit**

```bash
git add scripts/extract_inventario_seed.py seed_data/inventario_materiales.json
git commit -m "feat(inventario): seed extraction script and JSON output"
```

---

### Task 20: CLI `flask inventario seed`

**Files:**
- Create: `app/inventario/cli.py`
- Modify: `app/__init__.py`
- Create: `tests/test_inventario_seed.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_seed.py`:
```python
def test_seed_inserta_categorias_y_materiales(app, db, tmp_path):
    from app.inventario.cli import run_seed
    from app.inventario.models import Categoria
    from app.catalogo.models import MaterialMaster
    import json

    seed_file = tmp_path / "inv.json"
    seed_file.write_text(json.dumps([
        {"nombre": "ABATELENGUAS", "expira": True, "unidad_inventario": "pieza",
         "categorias": ["mesa_control", "instrumental"]},
        {"nombre": "GUANTES", "expira": True, "unidad_inventario": "caja",
         "categorias": ["mesa_control"]},
    ]), encoding="utf-8")

    run_seed(str(seed_file))

    cats = {c.nombre for c in Categoria.query.all()}
    assert {"mesa_control", "instrumental", "general"} <= cats

    nombres = {m.nombre for m in MaterialMaster.query.all()}
    assert "ABATELENGUAS" in nombres
    assert "GUANTES" in nombres


def test_seed_no_duplica(app, db, tmp_path):
    from app.inventario.cli import run_seed
    from app.catalogo.models import MaterialMaster
    import json

    db.session.add(MaterialMaster(nombre="alcohol", categoria="general"))
    db.session.commit()

    seed_file = tmp_path / "inv.json"
    seed_file.write_text(json.dumps([
        {"nombre": "ALCOHOL", "expira": True, "unidad_inventario": "pieza",
         "categorias": ["mesa_control"]},
    ]), encoding="utf-8")

    run_seed(str(seed_file))
    count = MaterialMaster.query.filter(
        db.func.upper(MaterialMaster.nombre) == "ALCOHOL"
    ).count()
    assert count == 1
```

- [ ] **Step 2: Run — debe fallar**

```
pytest tests/test_inventario_seed.py -v
```

- [ ] **Step 3: Implementar**

`app/inventario/cli.py`:
```python
import json
import click
from flask.cli import AppGroup
from app.extensions import db
from app.catalogo.models import MaterialMaster
from app.inventario.models import Categoria, MaterialMasterCategoria

inventario_cli = AppGroup("inventario", help="Comandos del módulo inventario")

CATEGORIAS_BASE = [
    ("mesa_control", "Materiales de la mesa de control"),
    ("instrumental", "Instrumental dental"),
    ("general", "Uso general"),
]


def _get_or_create_cat(nombre, desc=""):
    cat = Categoria.query.filter_by(nombre=nombre).first()
    if not cat:
        cat = Categoria(nombre=nombre, descripcion=desc)
        db.session.add(cat); db.session.flush()
    return cat


def run_seed(seed_path):
    for nombre, desc in CATEGORIAS_BASE:
        _get_or_create_cat(nombre, desc)

    with open(seed_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    existentes = {
        m.nombre.strip().upper(): m for m in MaterialMaster.query.all()
    }

    nuevos = 0
    for item in items:
        key = item["nombre"].strip().upper()
        if key in existentes:
            continue
        master = MaterialMaster(
            nombre=item["nombre"],
            expira=item.get("expira", True),
            unidad_inventario=item.get("unidad_inventario", "pieza"),
            categoria="general",
        )
        db.session.add(master); db.session.flush()
        for cat_nombre in item.get("categorias", []):
            cat = _get_or_create_cat(cat_nombre)
            db.session.add(MaterialMasterCategoria(
                material_master_id=master.id, categoria_id=cat.id
            ))
        existentes[key] = master
        nuevos += 1

    db.session.commit()
    click.echo(f"Seed completado: {nuevos} materiales nuevos agregados.")
    return nuevos


@inventario_cli.command("seed")
@click.argument("seed_path", default="seed_data/inventario_materiales.json")
def seed_cmd(seed_path):
    run_seed(seed_path)
```

Editar `app/__init__.py`, al final de `create_app` antes de `return app`:
```python
    from app.inventario.cli import inventario_cli
    app.cli.add_command(inventario_cli)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_inventario_seed.py -v
```
Expected: PASS

- [ ] **Step 5: Ejecutar el seed real**

```
flask inventario seed
```
Expected: `Seed completado: 314 materiales nuevos agregados.` (o cerca)

- [ ] **Step 6: Commit**

```bash
git add app/inventario/cli.py app/__init__.py tests/test_inventario_seed.py
git commit -m "feat(inventario): seed CLI to load master catalog"
```

---

## Fase 5 — Frontend

**Nota:** Todo el JS usa un helper `setText(el, value)` y `addCell(tr, value)` para insertar datos de la API con `textContent`, nunca `innerHTML`. La única vez que se usa HTML literal es al definir la estructura estática (headers, modales) dentro de los templates Jinja2, que son contenido confiable del servidor.

### Task 21: Rutas frontend y templates stub

**Files:**
- Modify: `app/frontend/routes.py`
- Create: 6 templates en `app/frontend/templates/inventario/`

- [ ] **Step 1: Añadir rutas**

En `app/frontend/routes.py`:
```python
@frontend_bp.route("/inventario")
def inventario_dashboard():
    return render_template("inventario/dashboard.html")


@frontend_bp.route("/inventario/material/<int:material_id>")
def inventario_material(material_id):
    return render_template("inventario/material.html", material_id=material_id)


@frontend_bp.route("/inventario/compras")
def inventario_compras():
    return render_template("inventario/compras.html")


@frontend_bp.route("/inventario/movimientos")
def inventario_movimientos():
    return render_template("inventario/movimientos.html")


@frontend_bp.route("/inventario/operatorios")
def inventario_operatorios():
    return render_template("inventario/operatorios.html")


@frontend_bp.route("/inventario/importar")
def inventario_importar():
    return render_template("inventario/importar.html")
```

- [ ] **Step 2: Crear templates**

`app/frontend/templates/inventario/dashboard.html`:
```html
{% extends "base.html" %}
{% block title %}Inventario{% endblock %}
{% block content %}
<div id="inventario-app">
  <h1>Inventario</h1>
  <div class="toolbar">
    <input id="busqueda" placeholder="Buscar material..." />
    <select id="filtro-categoria"><option value="">Todas</option></select>
    <select id="filtro-alerta">
      <option value="">Sin filtro</option>
      <option value="bajo">Stock bajo</option>
      <option value="alto">Stock alto</option>
      <option value="caduca">Por caducar</option>
    </select>
    <button id="btn-compra">+ Registrar compra</button>
    <button id="btn-transferir">Transferir</button>
    <a href="/inventario/importar" class="btn">+ Agregar material</a>
  </div>
  <table id="tabla-inventario">
    <thead><tr>
      <th>Material</th><th>Categorías</th><th>Total</th>
    </tr></thead>
    <tbody></tbody>
  </table>
  <div id="modal-compra" class="modal hidden"></div>
  <div id="modal-transferir" class="modal hidden"></div>
</div>
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dashboard.js') }}"></script>
{% endblock %}
```

`app/frontend/templates/inventario/material.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="material-app" data-material-id="{{ material_id }}">
  <a href="/inventario">Volver</a>
  <h1 id="material-nombre"></h1>
  <section id="umbrales"></section>
  <section id="lotes"></section>
  <section id="historial"></section>
</div>
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/material.js') }}"></script>
{% endblock %}
```

`app/frontend/templates/inventario/compras.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="compras-app">
  <h1>Registro de compras</h1>
  <button id="btn-nueva-compra">+ Nueva compra</button>
  <table id="tabla-compras">
    <thead><tr><th>Fecha</th><th>Material</th><th>Cantidad</th>
    <th>Precio</th><th>Comentarios</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="modal-compra" class="modal hidden">
    <form id="form-compra">
      <h2>Registrar compra</h2>
      <label>Material <select name="material_id" required></select></label>
      <label>Cantidad <input name="cantidad" type="number" min="1" required /></label>
      <label>Precio unitario <input name="precio_unitario" type="number" step="0.01" required /></label>
      <label>Fecha surtido <input name="fecha_surtido" type="date" required /></label>
      <label>Ubicación destino
        <select name="operatorio_destino_id">
          <option value="">Almacén</option>
        </select>
      </label>
      <label><input type="checkbox" name="no_caduca" /> No caduca</label>
      <label>Fecha caducidad <input name="fecha_caducidad" type="date" /></label>
      <label>Comentarios <textarea name="comentarios"></textarea></label>
      <label>
        <input type="checkbox" name="actualizar_costo_master" checked />
        Actualizar costo del material
      </label>
      <button type="submit">Guardar</button>
      <button type="button" id="cancelar-compra">Cancelar</button>
    </form>
  </div>
</div>
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/compras.js') }}"></script>
{% endblock %}
```

`app/frontend/templates/inventario/movimientos.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="mov-app">
  <h1>Historial de movimientos</h1>
  <select id="filtro-tipo">
    <option value="">Todos</option>
    <option value="compra">Compras</option>
    <option value="transferencia">Transferencias</option>
    <option value="ajuste">Ajustes</option>
  </select>
  <table id="tabla-mov">
    <thead><tr>
      <th>Fecha</th><th>Tipo</th><th>Material</th>
      <th>Origen</th><th>Destino</th><th>Cantidad</th><th>Motivo</th>
    </tr></thead><tbody></tbody>
  </table>
</div>
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/movimientos.js') }}"></script>
{% endblock %}
```

`app/frontend/templates/inventario/operatorios.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="op-app">
  <h1>Operatorios</h1>
  <form id="form-nuevo-op">
    <input name="nombre" placeholder="Nombre" required />
    <input name="orden" type="number" placeholder="Orden" />
    <button type="submit">Crear</button>
  </form>
  <ul id="lista-op"></ul>
</div>
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/operatorios.js') }}"></script>
{% endblock %}
```

`app/frontend/templates/inventario/importar.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="importar-app">
  <h1>Agregar materiales al inventario</h1>
  <input id="busqueda" placeholder="Buscar..." />
  <select id="filtro-cat">
    <option value="">Todas</option>
    <option value="mesa_control">Mesa de control</option>
    <option value="instrumental">Instrumental</option>
  </select>
  <table id="tabla-master">
    <thead><tr>
      <th><input type="checkbox" id="seleccionar-todo" /></th>
      <th>Nombre</th><th>Categorías</th>
    </tr></thead><tbody></tbody>
  </table>
  <button id="btn-importar">Importar seleccionados</button>
</div>
<script src="{{ url_for('static', filename='js/inventario/api.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/dom.js') }}"></script>
<script src="{{ url_for('static', filename='js/inventario/importar.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Smoke test**

```
python run.py &
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/inventario
```
Expected: `200` o redirección al login.

- [ ] **Step 4: Commit**

```bash
git add app/frontend/routes.py app/frontend/templates/inventario/
git commit -m "feat(inventario): frontend routes and templates"
```

---

### Task 22: Helpers JS compartidos (api + DOM seguro)

**Files:**
- Create: `app/static/js/inventario/api.js`
- Create: `app/static/js/inventario/dom.js`

- [ ] **Step 1: api.js**

`app/static/js/inventario/api.js`:
```javascript
const BASE = "/api/v1/inventario";

function authHeaders() {
  const token = localStorage.getItem("access_token");
  return {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/json",
  };
}

async function req(method, path, body) {
  const opts = { method, headers: authHeaders() };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ error: r.statusText }));
    throw new Error(err.error || JSON.stringify(err.errors || err));
  }
  if (r.status === 204) return null;
  return r.json();
}

window.invApi = {
  get: (p) => req("GET", p),
  post: (p, b) => req("POST", p, b),
  put: (p, b) => req("PUT", p, b),
  del: (p) => req("DELETE", p),
};
```

- [ ] **Step 2: dom.js (helpers seguros, sin innerHTML con datos)**

`app/static/js/inventario/dom.js`:
```javascript
/**
 * Helpers de DOM que usan textContent para evitar XSS.
 * Los datos de la API nunca se inyectan como HTML.
 */
function setText(sel, value) {
  const el = typeof sel === "string" ? document.querySelector(sel) : sel;
  if (el) el.textContent = value == null ? "" : String(value);
}

function addCell(tr, value) {
  const td = document.createElement("td");
  td.textContent = value == null ? "" : String(value);
  tr.appendChild(td);
  return td;
}

function addCellNode(tr, node) {
  const td = document.createElement("td");
  td.appendChild(node);
  tr.appendChild(td);
  return td;
}

function buildRow(values) {
  const tr = document.createElement("tr");
  values.forEach(v => addCell(tr, v));
  return tr;
}

function clearChildren(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function makeOption(value, label) {
  const o = document.createElement("option");
  o.value = value == null ? "" : String(value);
  o.textContent = label;
  return o;
}

function makeLink(href, label) {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = label;
  return a;
}

window.invDom = {
  setText, addCell, addCellNode, buildRow, clearChildren,
  makeOption, makeLink,
};
```

- [ ] **Step 3: Commit**

```bash
git add app/static/js/inventario/api.js app/static/js/inventario/dom.js
git commit -m "feat(inventario): js helpers (api + safe DOM)"
```

---

### Task 23: JS del dashboard de inventario

**Files:**
- Create: `app/static/js/inventario/dashboard.js`

- [ ] **Step 1: Crear**

`app/static/js/inventario/dashboard.js`:
```javascript
(async function () {
  const { setText, addCell, addCellNode, clearChildren, makeOption, makeLink } = window.invDom;
  const tbody = document.querySelector("#tabla-inventario tbody");
  const filtroCat = document.getElementById("filtro-categoria");
  const filtroAlerta = document.getElementById("filtro-alerta");
  const busqueda = document.getElementById("busqueda");

  async function cargarCategorias() {
    const cats = await invApi.get("/categorias");
    cats.forEach(c => filtroCat.appendChild(makeOption(c.nombre, c.nombre)));
  }

  function buildUrl() {
    const params = new URLSearchParams();
    if (busqueda.value) params.set("busqueda", busqueda.value);
    if (filtroCat.value) params.set("categoria", filtroCat.value);
    if (filtroAlerta.value) params.set("alerta", filtroAlerta.value);
    return "/materiales?" + params;
  }

  async function cargar() {
    const mats = await invApi.get(buildUrl());
    clearChildren(tbody);
    mats.forEach(m => {
      const tr = document.createElement("tr");
      addCellNode(tr, makeLink("/inventario/material/" + m.id, m.nombre));
      addCell(tr, (m.categorias || []).join(", "));
      addCell(tr, m.total_global);
      tbody.appendChild(tr);
    });
  }

  [filtroCat, filtroAlerta].forEach(el => el.addEventListener("change", cargar));
  busqueda.addEventListener("input", () => setTimeout(cargar, 200));

  document.getElementById("btn-compra").addEventListener("click", () => {
    window.location.href = "/inventario/compras";
  });

  // Modal transferir (Task 25 complementa este handler)
  document.getElementById("btn-transferir").addEventListener("click", () => {
    window.location.href = "/inventario/movimientos";
  });

  await cargarCategorias();
  await cargar();
})();
```

- [ ] **Step 2: Smoke manual**

Visitar `/inventario` tras hacer login. Debe renderizar tabla (vacía o con materiales).

- [ ] **Step 3: Commit**

```bash
git add app/static/js/inventario/dashboard.js
git commit -m "feat(inventario): dashboard js"
```

---

### Task 24: JS de compras, operatorios, movimientos, material, importar

**Files:**
- Create: `app/static/js/inventario/compras.js`
- Create: `app/static/js/inventario/operatorios.js`
- Create: `app/static/js/inventario/movimientos.js`
- Create: `app/static/js/inventario/material.js`
- Create: `app/static/js/inventario/importar.js`

- [ ] **Step 1: compras.js**

`app/static/js/inventario/compras.js`:
```javascript
(async function () {
  const { addCell, clearChildren, makeOption } = window.invDom;
  const tbody = document.querySelector("#tabla-compras tbody");
  const modal = document.getElementById("modal-compra");
  const form = document.getElementById("form-compra");

  async function llenarSelects() {
    const [mats, ops] = await Promise.all([
      invApi.get("/materiales"), invApi.get("/operatorios"),
    ]);
    const selM = form.querySelector('[name="material_id"]');
    clearChildren(selM);
    mats.forEach(m => selM.appendChild(makeOption(m.id, m.nombre)));
    const selO = form.querySelector('[name="operatorio_destino_id"]');
    // Quitar operatorios previos (conservar opción "Almacén" con value="")
    [...selO.querySelectorAll('option:not([value=""])')].forEach(o => o.remove());
    ops.forEach(op => selO.appendChild(makeOption(op.id, op.nombre)));
  }

  async function cargar() {
    const compras = await invApi.get("/compras");
    clearChildren(tbody);
    compras.forEach(c => {
      const tr = document.createElement("tr");
      addCell(tr, c.fecha);
      addCell(tr, c.material_id);
      addCell(tr, c.cantidad);
      addCell(tr, c.precio_unitario);
      addCell(tr, c.comentarios || "");
      tbody.appendChild(tr);
    });
  }

  document.getElementById("btn-nueva-compra").addEventListener("click", () => {
    modal.classList.remove("hidden");
  });
  document.getElementById("cancelar-compra").addEventListener("click", () => {
    modal.classList.add("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      material_id: parseInt(fd.get("material_id")),
      cantidad: parseInt(fd.get("cantidad")),
      precio_unitario: parseFloat(fd.get("precio_unitario")),
      fecha_surtido: fd.get("fecha_surtido"),
      fecha_caducidad: fd.get("fecha_caducidad") || null,
      no_caduca: fd.get("no_caduca") === "on",
      operatorio_destino_id: fd.get("operatorio_destino_id")
        ? parseInt(fd.get("operatorio_destino_id")) : null,
      comentarios: fd.get("comentarios") || null,
      actualizar_costo_master: fd.get("actualizar_costo_master") === "on",
    };
    try {
      await invApi.post("/compras", body);
      modal.classList.add("hidden");
      form.reset();
      await cargar();
    } catch (err) {
      alert("Error: " + err.message);
    }
  });

  await Promise.all([llenarSelects(), cargar()]);
})();
```

- [ ] **Step 2: operatorios.js**

`app/static/js/inventario/operatorios.js`:
```javascript
(async function () {
  const { clearChildren } = window.invDom;
  const lista = document.getElementById("lista-op");
  const form = document.getElementById("form-nuevo-op");

  async function cargar() {
    const ops = await invApi.get("/operatorios");
    clearChildren(lista);
    ops.forEach(op => {
      const li = document.createElement("li");
      li.textContent = op.nombre + " (orden " + op.orden + ") ";
      const btn = document.createElement("button");
      btn.textContent = "Borrar";
      btn.addEventListener("click", async () => {
        try {
          await invApi.del("/operatorios/" + op.id);
          cargar();
        } catch (err) {
          alert(err.message);
        }
      });
      li.appendChild(btn);
      lista.appendChild(li);
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    await invApi.post("/operatorios", {
      nombre: fd.get("nombre"),
      orden: parseInt(fd.get("orden") || "0"),
    });
    form.reset();
    cargar();
  });

  await cargar();
})();
```

- [ ] **Step 3: movimientos.js**

`app/static/js/inventario/movimientos.js`:
```javascript
(async function () {
  const { addCell, clearChildren } = window.invDom;
  const tbody = document.querySelector("#tabla-mov tbody");
  const filtro = document.getElementById("filtro-tipo");

  async function cargar() {
    const params = filtro.value ? "?tipo=" + filtro.value : "";
    const movs = await invApi.get("/movimientos" + params);
    clearChildren(tbody);
    movs.forEach(mv => {
      const tr = document.createElement("tr");
      addCell(tr, mv.fecha.slice(0, 16).replace("T", " "));
      addCell(tr, mv.tipo);
      addCell(tr, mv.material_id);
      addCell(tr, mv.origen_operatorio_id == null ? "Almacén" : mv.origen_operatorio_id);
      addCell(tr, mv.destino_operatorio_id == null ? "Almacén" : mv.destino_operatorio_id);
      addCell(tr, mv.cantidad);
      addCell(tr, mv.motivo || "");
      tbody.appendChild(tr);
    });
  }

  filtro.addEventListener("change", cargar);
  await cargar();
})();
```

- [ ] **Step 4: material.js**

`app/static/js/inventario/material.js`:
```javascript
(async function () {
  const { setText, addCell, clearChildren } = window.invDom;
  const app = document.getElementById("material-app");
  const id = app.dataset.materialId;
  const data = await invApi.get("/materiales/" + id);

  setText("#material-nombre", data.nombre);

  const umb = document.getElementById("umbrales");
  clearChildren(umb);
  const h2 = document.createElement("h2");
  h2.textContent = "Stock y umbrales por ubicación";
  umb.appendChild(h2);

  const tabla = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Ubicación", "Cantidad", "Mínimo", "Máximo"].forEach(h => {
    const th = document.createElement("th");
    th.textContent = h;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  const tbody = document.createElement("tbody");
  tabla.appendChild(thead);
  tabla.appendChild(tbody);

  data.stock_por_ubicacion.forEach(s => {
    const tr = document.createElement("tr");
    addCell(tr, s.operatorio_id == null ? "Almacén" : s.operatorio_id);
    addCell(tr, s.cantidad);
    ["minimo", "maximo"].forEach(campo => {
      const td = document.createElement("td");
      const inp = document.createElement("input");
      inp.type = "number";
      inp.value = s[campo] == null ? "" : s[campo];
      inp.dataset.op = s.operatorio_id == null ? "" : String(s.operatorio_id);
      inp.dataset.campo = campo;
      td.appendChild(inp);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  umb.appendChild(tabla);

  const btnGuardar = document.createElement("button");
  btnGuardar.textContent = "Guardar umbrales";
  btnGuardar.addEventListener("click", async () => {
    const byOp = {};
    tabla.querySelectorAll("input").forEach(inp => {
      const key = inp.dataset.op || "null";
      if (!byOp[key]) {
        byOp[key] = {
          operatorio_id: inp.dataset.op ? parseInt(inp.dataset.op) : null,
        };
      }
      byOp[key][inp.dataset.campo] = inp.value === "" ? null : parseInt(inp.value);
    });
    await invApi.put("/materiales/" + id, { umbrales: Object.values(byOp) });
    alert("Umbrales actualizados");
  });
  umb.appendChild(btnGuardar);

  // Lotes
  const lotesEl = document.getElementById("lotes");
  clearChildren(lotesEl);
  const h3 = document.createElement("h2");
  h3.textContent = "Lotes activos";
  lotesEl.appendChild(h3);
  if (data.lotes.length === 0) {
    const p = document.createElement("p");
    p.textContent = "Sin lotes activos";
    lotesEl.appendChild(p);
  } else {
    const tl = document.createElement("table");
    const trh = document.createElement("tr");
    ["Surtido", "Caducidad", "Precio", "Ubicaciones"].forEach(h => {
      const th = document.createElement("th");
      th.textContent = h;
      trh.appendChild(th);
    });
    const thd = document.createElement("thead");
    thd.appendChild(trh);
    tl.appendChild(thd);
    const tbl = document.createElement("tbody");
    data.lotes.forEach(lt => {
      const tr = document.createElement("tr");
      addCell(tr, lt.fecha_surtido);
      addCell(tr, lt.fecha_caducidad || "No caduca");
      addCell(tr, lt.precio_unitario == null ? "" : lt.precio_unitario);
      const ubics = lt.ubicaciones.map(u =>
        (u.operatorio_id == null ? "Almacén" : u.operatorio_id) + ": " + u.cantidad_restante
      ).join(", ");
      addCell(tr, ubics);
      tbl.appendChild(tr);
    });
    tl.appendChild(tbl);
    lotesEl.appendChild(tl);
  }

  // Historial
  const hist = document.getElementById("historial");
  clearChildren(hist);
  const hh = document.createElement("h2");
  hh.textContent = "Historial";
  hist.appendChild(hh);
  const movs = await invApi.get("/movimientos?material_id=" + id);
  const mt = document.createElement("table");
  const mthd = document.createElement("thead");
  const mtr = document.createElement("tr");
  ["Fecha", "Tipo", "Origen", "Destino", "Cantidad", "Motivo"].forEach(h => {
    const th = document.createElement("th");
    th.textContent = h;
    mtr.appendChild(th);
  });
  mthd.appendChild(mtr);
  mt.appendChild(mthd);
  const mtbl = document.createElement("tbody");
  movs.forEach(mv => {
    const tr = document.createElement("tr");
    addCell(tr, mv.fecha.slice(0, 16).replace("T", " "));
    addCell(tr, mv.tipo);
    addCell(tr, mv.origen_operatorio_id == null ? "—" : mv.origen_operatorio_id);
    addCell(tr, mv.destino_operatorio_id == null ? "—" : mv.destino_operatorio_id);
    addCell(tr, mv.cantidad);
    addCell(tr, mv.motivo || "");
    mtbl.appendChild(tr);
  });
  mt.appendChild(mtbl);
  hist.appendChild(mt);
})();
```

- [ ] **Step 5: importar.js**

`app/static/js/inventario/importar.js`:
```javascript
(async function () {
  const { addCell, addCellNode, clearChildren } = window.invDom;
  const tbody = document.querySelector("#tabla-master tbody");
  const busq = document.getElementById("busqueda");
  const filtro = document.getElementById("filtro-cat");
  const btn = document.getElementById("btn-importar");
  const selAll = document.getElementById("seleccionar-todo");

  async function cargar() {
    const params = new URLSearchParams();
    if (busq.value) params.set("busqueda", busq.value);
    if (filtro.value) params.set("categoria", filtro.value);
    const masters = await invApi.get("/master-disponibles?" + params);
    clearChildren(tbody);
    masters.forEach(m => {
      const tr = document.createElement("tr");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = String(m.id);
      cb.classList.add("sel");
      addCellNode(tr, cb);
      addCell(tr, m.nombre);
      addCell(tr, (m.categorias || []).join(", "));
      tbody.appendChild(tr);
    });
  }

  busq.addEventListener("input", () => setTimeout(cargar, 200));
  filtro.addEventListener("change", cargar);
  selAll.addEventListener("change", () => {
    document.querySelectorAll(".sel").forEach(c => c.checked = selAll.checked);
  });
  btn.addEventListener("click", async () => {
    const ids = [...document.querySelectorAll(".sel:checked")]
      .map(c => parseInt(c.value));
    if (ids.length === 0) return alert("Selecciona al menos uno");
    const r = await invApi.post("/materiales/importar-master", { master_ids: ids });
    alert(r.importados + " materiales importados");
    await cargar();
  });

  await cargar();
})();
```

- [ ] **Step 6: Smoke manual**

Probar cada página:
- `/inventario/operatorios`
- `/inventario/compras`
- `/inventario/movimientos`
- `/inventario/material/<id>`
- `/inventario/importar`

- [ ] **Step 7: Commit**

```bash
git add app/static/js/inventario/
git commit -m "feat(inventario): JS for all module pages using safe DOM"
```

---

### Task 25: Modal Transferir en el dashboard

**Files:**
- Modify: `app/frontend/templates/inventario/dashboard.html`
- Modify: `app/static/js/inventario/dashboard.js`

- [ ] **Step 1: Agregar modal al template**

Dentro de `dashboard.html`, reemplazar la línea `<div id="modal-transferir" class="modal hidden"></div>` por:
```html
<div id="modal-transferir" class="modal hidden">
  <form id="form-transferir">
    <h2>Transferir</h2>
    <label>Material <select name="material_id" required></select></label>
    <label>Origen
      <select name="origen_operatorio_id">
        <option value="">Almacén</option>
      </select>
    </label>
    <label>Destino
      <select name="destino_operatorio_id">
        <option value="">Almacén</option>
      </select>
    </label>
    <label>Cantidad <input name="cantidad" type="number" min="1" required /></label>
    <label>Motivo <input name="motivo" /></label>
    <button type="submit">Transferir</button>
    <button type="button" id="cancelar-transferir">Cancelar</button>
  </form>
</div>
```

- [ ] **Step 2: Actualizar dashboard.js**

Reemplazar el handler de `btn-transferir` (que redirigía) por la lógica del modal. Agregar al final del IIFE en `dashboard.js`:
```javascript
const { makeOption } = window.invDom;
const modalT = document.getElementById("modal-transferir");
const formT = document.getElementById("form-transferir");

async function prefillTransferir() {
  const [mats, ops] = await Promise.all([
    invApi.get("/materiales"), invApi.get("/operatorios"),
  ]);
  const selMat = formT.querySelector('[name="material_id"]');
  while (selMat.firstChild) selMat.removeChild(selMat.firstChild);
  mats.forEach(m => selMat.appendChild(makeOption(m.id, m.nombre)));
  ["origen_operatorio_id", "destino_operatorio_id"].forEach(name => {
    const sel = formT.querySelector('[name="' + name + '"]');
    // Conservar la opción "Almacén" (value vacío)
    [...sel.querySelectorAll('option:not([value=""])')].forEach(o => o.remove());
    ops.forEach(op => sel.appendChild(makeOption(op.id, op.nombre)));
  });
}

document.getElementById("btn-transferir").onclick = async () => {
  await prefillTransferir();
  modalT.classList.remove("hidden");
};
document.getElementById("cancelar-transferir").addEventListener("click", () => {
  modalT.classList.add("hidden");
});
formT.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(formT);
  const body = {
    material_id: parseInt(fd.get("material_id")),
    origen_operatorio_id: fd.get("origen_operatorio_id")
      ? parseInt(fd.get("origen_operatorio_id")) : null,
    destino_operatorio_id: fd.get("destino_operatorio_id")
      ? parseInt(fd.get("destino_operatorio_id")) : null,
    cantidad: parseInt(fd.get("cantidad")),
    motivo: fd.get("motivo") || null,
  };
  try {
    await invApi.post("/transferencias", body);
    modalT.classList.add("hidden"); formT.reset();
    await cargar();
  } catch (err) {
    alert(err.message);
  }
});
```

- [ ] **Step 3: Smoke manual**

En `/inventario`, abrir modal, transferir.

- [ ] **Step 4: Commit**

```bash
git add app/frontend/templates/inventario/dashboard.html app/static/js/inventario/dashboard.js
git commit -m "feat(inventario): transferir modal on dashboard"
```

---

### Task 26: Tarjeta de alertas en el dashboard principal

**Files:**
- Modify: template del dashboard principal (en `app/frontend/templates/`)
- Create: `app/static/js/dashboard_inventario_card.js`

- [ ] **Step 1: Localizar el template**

```
ls app/frontend/templates/
```
Identificar el archivo del dashboard principal (p.ej. `dashboard.html` o `index.html`).

- [ ] **Step 2: Agregar tarjeta al template**

Dentro de la sección de tarjetas, agregar:
```html
<a class="card card-inventario" href="/inventario" id="card-inventario">
  <h3>Inventario</h3>
  <div class="metrics">
    <span><strong id="inv-bajo">–</strong> bajos</span>
    <span><strong id="inv-alto">–</strong> altos</span>
    <span><strong id="inv-caduca">–</strong> por caducar</span>
  </div>
</a>
<script src="{{ url_for('static', filename='js/dashboard_inventario_card.js') }}"></script>
```

- [ ] **Step 3: Crear JS**

`app/static/js/dashboard_inventario_card.js`:
```javascript
(async function () {
  const token = localStorage.getItem("access_token");
  const r = await fetch("/api/v1/inventario/alertas/resumen", {
    headers: { "Authorization": "Bearer " + token },
  });
  if (!r.ok) return;
  const data = await r.json();
  document.getElementById("inv-bajo").textContent = String(data.bajo);
  document.getElementById("inv-alto").textContent = String(data.alto);
  document.getElementById("inv-caduca").textContent = String(data.caducidad);
})();
```

- [ ] **Step 4: Smoke manual**

Visitar `/dashboard`. La tarjeta debe mostrar los 3 contadores.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/templates/ app/static/js/dashboard_inventario_card.js
git commit -m "feat(inventario): dashboard card with alert summary"
```

---

## Fase 6 — Integración y aislamiento

### Task 27: Tests end-to-end y aislamiento multitenant

**Files:**
- Create: `tests/test_inventario_isolation.py`

- [ ] **Step 1: Tests**

`tests/test_inventario_isolation.py`:
```python
from datetime import date


def test_operatorio_de_otro_tenant_no_aparece(client, auth_headers, db, tenant_and_user):
    from app.auth.models import Tenant
    from app.inventario.models import Operatorio
    otro = Tenant(name="Otro", slug="otro")
    db.session.add(otro); db.session.flush()
    db.session.add(Operatorio(tenant_id=otro.id, nombre="Op Ajeno"))
    db.session.commit()
    resp = client.get("/api/v1/inventario/operatorios", headers=auth_headers)
    nombres = [o["nombre"] for o in resp.get_json()]
    assert "Op Ajeno" not in nombres


def test_compra_de_otro_tenant_no_aparece(client, auth_headers, db, tenant_and_user):
    from app.auth.models import Tenant, User
    from app.catalogo.models import Material
    from app.inventario.services import registrar_compra
    otro = Tenant(name="Otro", slug="otro")
    db.session.add(otro); db.session.flush()
    u = User(tenant_id=otro.id, email="o@o.com", name="o", role="admin")
    u.set_password("password12345")
    db.session.add(u); db.session.flush()
    m = Material(tenant_id=otro.id, nombre="Ajeno", en_inventario=True)
    db.session.add(m); db.session.flush()
    registrar_compra(
        tenant_id=otro.id, user_id=u.id, material_id=m.id,
        cantidad=5, precio_unitario=1, fecha_surtido=date(2026, 4, 1),
        fecha_caducidad=None, operatorio_destino_id=None,
        comentarios=None, actualizar_costo_master=False,
    )
    db.session.commit()
    resp = client.get("/api/v1/inventario/compras", headers=auth_headers)
    assert resp.get_json() == []


def test_flujo_completo(client, auth_headers, db, tenant_and_user):
    """compra → umbrales → transferencia → alerta baja."""
    from app.catalogo.models import Material
    tenant, _ = tenant_and_user
    m = Material(tenant_id=tenant.id, nombre="Flujo", en_inventario=True)
    db.session.add(m); db.session.commit()

    op_resp = client.post(
        "/api/v1/inventario/operatorios",
        json={"nombre": "Op 1"}, headers=auth_headers,
    )
    op_id = op_resp.get_json()["id"]

    cad = (date.today().replace(year=date.today().year + 1)).isoformat()
    client.post("/api/v1/inventario/compras", json={
        "material_id": m.id, "cantidad": 10, "precio_unitario": 2,
        "fecha_surtido": "2026-04-20", "fecha_caducidad": cad,
        "actualizar_costo_master": False,
    }, headers=auth_headers)

    client.put("/api/v1/inventario/materiales/" + str(m.id), json={
        "umbrales": [
            {"operatorio_id": None, "minimo": 3, "maximo": 50},
            {"operatorio_id": op_id, "minimo": 5, "maximo": None},
        ],
    }, headers=auth_headers)

    client.post("/api/v1/inventario/transferencias", json={
        "material_id": m.id, "origen_operatorio_id": None,
        "destino_operatorio_id": op_id, "cantidad": 4,
    }, headers=auth_headers)

    alertas = client.get(
        "/api/v1/inventario/alertas", headers=auth_headers
    ).get_json()
    bajo_op = [a for a in alertas["bajo"] if a["operatorio_id"] == op_id]
    assert len(bajo_op) == 1
    assert bajo_op[0]["cantidad"] == 4
    assert bajo_op[0]["minimo"] == 5
```

- [ ] **Step 2: Run**

```
pytest tests/test_inventario_isolation.py -v
```
Expected: PASS

- [ ] **Step 3: Suite completa**

```
pytest -v
```
Expected: Todos los tests pasan.

- [ ] **Step 4: Commit**

```bash
git add tests/test_inventario_isolation.py
git commit -m "test(inventario): end-to-end and tenant isolation"
```

---

## Verificación final

- [ ] Migraciones se aplican limpio en un DB vacío: `flask db upgrade`
- [ ] Seed funciona: `flask inventario seed` reporta ~314 materiales nuevos
- [ ] Suite completa pasa: `pytest -v`
- [ ] Flujo manual en browser:
  - Login como admin
  - `/inventario/importar` → importar 3-5 materiales del master
  - `/inventario/operatorios` → crear "Op 1"
  - `/inventario/compras` → registrar una compra en almacén
  - `/inventario` → ver stock, abrir modal "Transferir", llevar 3 unidades a "Op 1"
  - `/inventario/material/<id>` → ver lotes, ubicaciones, editar mín/máx por ubicación
  - `/dashboard` → tarjeta de inventario con 3 contadores
