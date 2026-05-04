# Módulo Inventario — Diseño

**Fecha:** 2026-04-20
**Estado:** Aprobado para implementación
**Referencia origen:** `Inventario smile studio.xlsx` (hojas MESA DE CONTROL e INSTRUMENTAL, 324 materiales únicos)

## Propósito

Añadir un módulo de inventario multitenant que permita al consultorio dental:
- Rastrear existencias de materiales en almacén y en cada operatorio.
- Definir mínimos y máximos independientes por ubicación para generar alertas de stock bajo / alto.
- Registrar compras con lotes y fechas de caducidad, con alertas de vencimiento próximo.
- Distinguir materiales que caducan de los que no.
- Registrar transferencias entre ubicaciones y ajustes manuales con trazabilidad completa.
- Importar opt-in desde un catálogo maestro precargado con los materiales del Excel.

## Decisiones acordadas

| # | Tema | Decisión |
|---|------|----------|
| 1 | Relación con catálogo existente | Un solo catálogo unificado (`materiales`) + categorías. El mismo material sirve para pricing engine e inventario. |
| 2 | Caducidad | Por lotes. Cada compra crea un lote con su propia fecha. La pantalla de inspección muestra los lotes con su caducidad por ubicación. Flag `expira` por material (instrumental y similares no caducan). |
| 3a | Operatorios | Entidad global por tenant. El usuario los crea/renombra/borra. Cualquier material puede tener stock en cualquier operatorio. |
| 3b | Movimientos | Botón "Transferir" (origen → destino) + ajuste manual para conteos físicos. Ambos registran historial. |
| 4 | Mín/Máx | Independientes por ubicación (almacén y cada operatorio). Un material puede existir sólo en un operatorio si su caducidad es muy corta para almacén. |
| 5 | Alertas | Panel dentro del módulo + tarjeta resumen en dashboard principal (`X bajos · Y altos · Z por caducar`). Días de anticipación de caducidad configurable por tenant (default 30). |
| 6 | Compras | Formulario único: crea lote, suma stock a ubicación destino y registra compra en historial. Checkbox "actualizar costo del material" marcado por default. |
| 7 | Categorías | Many-to-many. Un material puede ser `mesa_control` Y `instrumental`. Categorías globales fijas iniciales: `mesa_control`, `instrumental`, `general`. |
| 8 | Import | Opt-in. El tenant abre "Agregar al inventario" y elige del catálogo maestro. Nada se auto-copia. |
| 9 | Seed | Sólo los 314 materiales nuevos. 10 ya existen en master y no se duplican (verificación por nombre case-insensitive). |

## Arquitectura

Módulo nuevo `app/inventario/` siguiendo el patrón del proyecto:

```
app/inventario/
  __init__.py
  models.py
  schemas.py
  routes.py
  services.py      ← lógica transaccional (compras, transferencias)
```

- Frontend servido por `app/frontend/routes.py` (nuevas rutas Jinja2 con JS vanilla que consume `/api/v1/inventario/...`).
- Tenant isolation: todas las queries filtran por `g.tenant_id`. Decoradores `@require_auth` y `@require_role`.
- Ajuste del tenant (`app/ajustes`): se añade `dias_alerta_caducidad` (int, default 30).
- Sin impacto en el pricing engine existente. El material sigue teniendo `costo_paquete` / `unidades_paquete`; solo se modifican si el usuario marca el checkbox en una compra.

## Modelo de datos

```python
class Categoria(db.Model):
    __tablename__ = "categorias"
    id = Integer PK
    nombre = String(50) unique
    descripcion = String(200)
    # Global (sin tenant_id). Seed inicial: mesa_control, instrumental, general.

class MaterialCategoria(db.Model):     # M2M
    material_id = FK(materiales.id)
    categoria_id = FK(categorias.id)
    PK(material_id, categoria_id)

class MaterialMasterCategoria(db.Model):   # M2M para master catalog
    material_master_id = FK(materiales_master.id)
    categoria_id = FK(categorias.id)
    PK(material_master_id, categoria_id)

# Ampliación de Material y MaterialMaster (migración):
#   + expira: Boolean default True
#   + unidad_inventario: String(30) default "pieza"
#   + en_inventario: Boolean default False   (solo Material del tenant)

class Operatorio(db.Model):
    id = Integer PK
    tenant_id = FK(tenants.id)
    nombre = String(100)
    orden = Integer default 0
    activo = Boolean default True
    UNIQUE(tenant_id, nombre)

class Lote(db.Model):
    id = Integer PK
    tenant_id = FK(tenants.id)
    material_id = FK(materiales.id)
    cantidad_inicial = Integer
    fecha_surtido = Date
    fecha_caducidad = Date nullable   # NULL si material.expira=False
    precio_unitario = Float nullable
    comentarios = String(500) nullable
    agotado = Boolean default False

class LoteUbicacion(db.Model):
    id = Integer PK
    lote_id = FK(lotes.id)
    operatorio_id = FK(operatorios.id) nullable    # NULL = almacén
    cantidad_restante = Integer
    UNIQUE(lote_id, operatorio_id)

class StockUbicacion(db.Model):
    # Agregado de stock por ubicación, con umbrales.
    id = Integer PK
    tenant_id = FK(tenants.id)
    material_id = FK(materiales.id)
    operatorio_id = FK(operatorios.id) nullable    # NULL = almacén
    cantidad = Integer default 0
    minimo = Integer nullable
    maximo = Integer nullable
    UNIQUE(tenant_id, material_id, operatorio_id)

class Compra(db.Model):
    id = Integer PK
    tenant_id = FK(tenants.id)
    material_id = FK(materiales.id)
    lote_id = FK(lotes.id)
    fecha = Date
    cantidad = Integer
    precio_unitario = Float
    comentarios = String(500) nullable
    actualizo_costo_master = Boolean default False
    user_id = FK(users.id)

class MovimientoInventario(db.Model):
    id = Integer PK
    tenant_id = FK(tenants.id)
    material_id = FK(materiales.id)
    lote_id = FK(lotes.id) nullable
    tipo = Enum("compra", "transferencia", "ajuste")
    origen_operatorio_id = FK(operatorios.id) nullable    # NULL = almacén (o sin origen si compra)
    destino_operatorio_id = FK(operatorios.id) nullable
    cantidad = Integer
    fecha = DateTime
    user_id = FK(users.id)
    motivo = String(500) nullable
```

**Invariantes mantenidas por la capa de servicio (`services.py`):**
- `StockUbicacion.cantidad == SUM(LoteUbicacion.cantidad_restante WHERE same operatorio_id, material_id)`.
- Toda modificación de stock (compra, transferencia, ajuste) es transaccional y crea un `MovimientoInventario`.
- Un `Lote` se marca `agotado=True` cuando todas sus `LoteUbicacion` suman 0; no se borra.
- Una `Compra` siempre crea un `Lote` nuevo (no se suma a lotes existentes para preservar trazabilidad de precio y caducidad).
- `operatorio_id = NULL` representa almacén consistentemente en `Lote Ubicacion`, `StockUbicacion`, `MovimientoInventario`.

## API (`/api/v1/inventario`)

Todos los endpoints usan `@require_auth`. Escritura requiere `admin` o `editor`; `viewer` es solo lectura.

### Operatorios
- `GET /operatorios` — lista
- `POST /operatorios` — crear `{ nombre, orden? }`
- `PUT /operatorios/<id>` — `{ nombre?, orden?, activo? }`
- `DELETE /operatorios/<id>` — falla con 409 si tiene stock > 0 en alguna `StockUbicacion`.

### Materiales
- `GET /materiales` — lista con totales y alertas. Query: `categoria`, `alerta=bajo|alto|caduca`, `busqueda`.
- `GET /materiales/<id>` — inspección completa: stock por ubicación, lotes activos con caducidad por ubicación, últimos N movimientos.
- `POST /materiales` — crea material propio con `en_inventario=True`.
- `PUT /materiales/<id>` — actualiza categorías, flag `expira`, `unidad_inventario`, y umbrales `{ ubicacion: {minimo, maximo} }`.
- `POST /materiales/importar-master` — body `{ master_ids: [...] }`. Copia a `materiales` del tenant con `en_inventario=True`. Idempotente (si ya existe, ignora).
- `GET /master-disponibles` — lista materiales del master que el tenant aún no tiene en su catálogo.

### Compras y lotes
- `POST /compras` — body `{ material_id, cantidad, precio_unitario, fecha_surtido, fecha_caducidad?, no_caduca, ubicacion_destino_id?, comentarios?, actualizar_costo_master }`. Transaccional: crea `Lote`, `LoteUbicacion`, suma `StockUbicacion`, crea `Compra` y `MovimientoInventario(tipo="compra")`. Si `actualizar_costo_master=True`, actualiza `Material.costo_paquete = precio_unitario * cantidad` y `Material.unidades_paquete = cantidad`.
- `GET /compras` — historial con filtros `fecha_desde`, `fecha_hasta`, `material_id`.
- `GET /materiales/<id>/lotes` — lotes activos con detalle.

### Transferencias y ajustes
- `POST /transferencias` — body `{ material_id, origen_operatorio_id, destino_operatorio_id, cantidad, lote_id?, motivo? }`. Si `lote_id` se omite, consume FIFO: por `fecha_caducidad` ascendente si el material expira; por `fecha_surtido` ascendente si no expira. Puede consumir varios lotes en un solo llamado si uno no alcanza; genera un `MovimientoInventario` por lote consumido. Falla 409 si no hay stock suficiente en origen.
- `POST /ajustes` — body `{ material_id, operatorio_id, lote_id?, cantidad_nueva, motivo }`. Calcula delta y registra `MovimientoInventario(tipo="ajuste")`.
- `GET /movimientos` — historial con filtros.

### Alertas
- `GET /alertas` — `{ bajo: [...], alto: [...], caducidad: [...] }`. Cada item con `material`, `ubicacion`, `cantidad_actual`, `umbral` (o `fecha_caducidad`).
- `GET /alertas/resumen` — contadores `{ bajo: int, alto: int, caducidad: int }` para el badge del dashboard principal.

Criterios:
- **Bajo:** `StockUbicacion.cantidad <= StockUbicacion.minimo` (ignora si `minimo` es NULL).
- **Alto:** `StockUbicacion.cantidad >= StockUbicacion.maximo` (ignora si `maximo` es NULL).
- **Caducidad:** `Lote.fecha_caducidad <= today + tenant.dias_alerta_caducidad` AND `Lote.agotado=False` AND material.`expira=True`.

### Categorías
- `GET /categorias` — lista.
- `POST /categorias` — admin únicamente (para ampliaciones futuras).

## Frontend (Jinja2 + JS vanilla)

Rutas en `app/frontend/routes.py`:

- `/inventario` — dashboard con tabla tipo Excel (material, categoría, almacén, cada operatorio como columna, total global, caducidad más próxima, alertas). Filtros: chips de categorías, búsqueda, toggle "solo con alerta". Semáforo: rojo=bajo, naranja=alto, amarillo=por caducar. Acciones: **+ Registrar compra**, **↔ Transferir**, **+ Agregar material**.
- `/inventario/material/<id>` — inspección. Cabecera editable (categorías, `expira`, unidad, mín/máx por ubicación). Tabla **Lotes activos** (fecha surtido, caducidad o "no caduca", cantidad restante por ubicación, precio, comentarios). Tabla **Stock por ubicación**. Pestaña **Historial** con movimientos del material.
- `/inventario/compras` — historial de compras + botón "Registrar compra".
- `/inventario/movimientos` — historial de transferencias y ajustes.
- `/inventario/operatorios` — gestión CRUD.
- `/inventario/importar` — pantalla opt-in paginada con búsqueda y filtro por categoría para copiar del master.

**Modales clave:**

1. **Registrar compra:** autocomplete de material (link a "crear nuevo" si no existe), cantidad, precio unitario, fecha surtido, toggle "no caduca" / fecha caducidad, comentarios, selector de ubicación destino (default Almacén), checkbox **"Actualizar costo del material con este precio"** marcado por default.
2. **Transferir:** material (autocomplete), cantidad, origen, destino, motivo opcional, selector de lote opcional (default FIFO por caducidad).

**Dashboard principal (`/dashboard`)** — modificación:
- Tarjeta nueva "Inventario" consumiendo `GET /alertas/resumen`, con links a `/inventario?alerta=bajo|alto|caduca`.

## Seed e importación

**Script one-shot** `scripts/extract_inventario_seed.py`:
- Lee `Inventario smile studio.xlsx`, toma la unión de nombres de MESA DE CONTROL e INSTRUMENTAL.
- Filtra contra `materiales_master` existente (comparación case-insensitive) → 314 nuevos.
- Infere `expira=False` cuando la columna Caducidad del Excel es "NO" (todas las hojas), `True` en otro caso.
- Infere `categorias` según en qué hoja aparece el material.
- Emite `seed_data/inventario_materiales.json`.

**Seeder** se ejecuta en la migración o vía `flask seed inventario`:
- Crea las 3 categorías globales si no existen.
- Inserta los 314 materiales nuevos en `materiales_master` con sus categorías.
- **NO modifica** materiales ya existentes; solo agrega.

Import del tenant: opt-in vía `POST /materiales/importar-master` desde la pantalla `/inventario/importar`.

## Migraciones (Alembic)

1. `add_inventario_fields_to_material` — columnas `expira`, `unidad_inventario`, `en_inventario` en `materiales` y `materiales_master`.
2. `create_categorias_tables` — `categorias`, `material_categoria`, `material_master_categoria`. Inserta seed de 3 categorías.
3. `create_operatorios` — tabla `operatorios`.
4. `create_inventario_stock_tables` — `lotes`, `lote_ubicacion`, `stock_ubicacion`, `compras`, `movimientos_inventario`.
5. `add_dias_alerta_caducidad_to_ajustes` — columna en tabla de configuración del tenant (default 30).

## Pruebas (`tests/test_inventario.py`)

Usan fixtures existentes de `conftest.py` (`tenant_and_user`, `auth_headers`). Cubren:

- `test_crear_operatorio`
- `test_no_borrar_operatorio_con_stock`
- `test_registrar_compra_crea_lote_y_suma_stock`
- `test_registrar_compra_con_checkbox_actualiza_costo_paquete`
- `test_registrar_compra_sin_checkbox_no_toca_costo`
- `test_transferencia_resta_origen_suma_destino`
- `test_transferencia_fifo_toma_lote_mas_proximo_a_vencer`
- `test_transferencia_falla_si_no_hay_stock_suficiente`
- `test_ajuste_manual_registra_movimiento`
- `test_alertas_stock_bajo_por_ubicacion` (almacén y operatorios independientes)
- `test_alertas_stock_alto_por_ubicacion`
- `test_alertas_caducidad_respeta_dias_configurados`
- `test_material_no_expira_no_genera_alerta_caducidad`
- `test_tenant_no_ve_inventario_de_otro_tenant`
- `test_viewer_no_puede_registrar_compra`
- `test_editor_puede_registrar_compra`
- `test_importar_master_no_duplica_si_ya_existe`
- `test_inspeccion_devuelve_lotes_con_caducidad_por_ubicacion`
- `test_lote_agotado_no_aparece_en_alertas_caducidad`
- `test_stockubicacion_consistente_con_suma_de_loteubicacion`

## Fuera de alcance (para otro spec si se requiere)

- Envío de alertas por correo / notificaciones push.
- Importación automática del Excel completo con stock inicial (se puede hacer con un comando CLI opcional fuera de este spec).
- Códigos de barras / etiquetas QR.
- Órdenes de compra y proveedores.
- Reportes avanzados (consumo por tratamiento, costos mensuales, etc.).
