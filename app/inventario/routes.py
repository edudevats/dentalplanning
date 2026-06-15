from flask import Blueprint, request, jsonify, g
from marshmallow import ValidationError
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.middleware.tenant import require_auth, require_role
from app.catalogo.models import Material, MaterialMaster
from app.inventario.models import (
    Categoria, Compra, Lote, LoteUbicacion, MaterialCategoria,
    MovimientoInventario, Operatorio, StockUbicacion,
)
from app.inventario.schemas import (
    AjusteSchema, CategoriaSchema, CompraSchema,
    ImportMasterInventarioSchema, MaterialInventarioSchema,
    OperatorioEstadoSchema, OperatorioSchema, TransferenciaSchema,
)
from app.inventario.services import (
    _get_or_create_stock_ubicacion, _inicializar_stock_material, ajustar,
    calcular_alertas, calcular_kpis_dashboard, registrar_compra, transferir,
)

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
    db.session.flush()
    # Stock=0 para todos los materiales del tenant (fuente unica).
    for m in Material.query.filter_by(tenant_id=g.tenant_id).all():
        _get_or_create_stock_ubicacion(g.tenant_id, m.id, op.id)
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
    nuevo_nombre = data.get("nombre")
    if nuevo_nombre and nuevo_nombre != op.nombre:
        existe = Operatorio.query.filter(
            Operatorio.tenant_id == g.tenant_id,
            Operatorio.nombre == nuevo_nombre,
            Operatorio.id != op.id,
        ).first()
        if existe:
            return jsonify({"error": f'Ya existe un operatorio con el nombre "{nuevo_nombre}"'}), 409
    for k, v in data.items():
        setattr(op, k, v)
    db.session.commit()
    return jsonify(OperatorioSchema().dump(op))


@inventario_bp.route("/operatorios/<int:op_id>/estado", methods=["PUT"])
@require_auth
@require_role("admin", "editor")
def cambiar_estado_operatorio(op_id):
    op = Operatorio.query.filter_by(id=op_id, tenant_id=g.tenant_id).first_or_404()
    try:
        data = OperatorioEstadoSchema().load(request.get_json() or {})
    except ValidationError as e:
        return jsonify({"errors": e.messages}), 400
    op.estado = data["estado"]
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


def _serializar_lista(m, total_global):
    return {
        "id": m.id, "nombre": m.nombre,
        "expira": m.expira, "unidad_inventario": m.unidad_inventario,
        "categorias": [c.nombre for c in m.categorias],
        "total_global": int(total_global),
    }


@inventario_bp.route("/materiales", methods=["GET"])
@require_auth
def listar_materiales_inv():
    # Fuente unica: el catalogo del tenant. No filtramos por en_inventario;
    # todo material listado en /materiales debe aparecer aqui con su stock.
    categoria = request.args.get("categoria")
    busqueda = request.args.get("busqueda")
    # selectinload de categorias: se leen por cada material al serializar.
    q = Material.query.options(
        selectinload(Material.categorias)
    ).filter_by(tenant_id=g.tenant_id)
    if categoria:
        q = q.join(Material.categorias).filter(Categoria.nombre == categoria)
    if busqueda:
        q = q.filter(Material.nombre.ilike(f"%{busqueda}%"))
    materiales = q.order_by(Material.nombre).all()

    # Total de stock por material en UNA consulta agrupada (antes: un SUM por
    # cada material -> N+1).
    totales = dict(
        db.session.query(
            StockUbicacion.material_id,
            db.func.coalesce(db.func.sum(StockUbicacion.cantidad), 0),
        )
        .filter(StockUbicacion.tenant_id == g.tenant_id)
        .group_by(StockUbicacion.material_id)
        .all()
    )
    return jsonify([
        _serializar_lista(m, totales.get(m.id, 0)) for m in materiales
    ])


@inventario_bp.route("/materiales/<int:material_id>", methods=["GET"])
@require_auth
def inspeccionar_material(material_id):
    m = Material.query.filter_by(
        id=material_id, tenant_id=g.tenant_id,
    ).first_or_404()
    stocks = StockUbicacion.query.filter_by(
        tenant_id=g.tenant_id, material_id=m.id
    ).all()
    lotes = Lote.query.filter_by(
        tenant_id=g.tenant_id, material_id=m.id, agotado=False
    ).all()
    # Ubicaciones de TODOS los lotes en una sola consulta (antes: una por lote).
    lus_por_lote = {}
    lote_ids = [lote.id for lote in lotes]
    if lote_ids:
        for lu in LoteUbicacion.query.filter(
            LoteUbicacion.lote_id.in_(lote_ids)
        ).all():
            lus_por_lote.setdefault(lu.lote_id, []).append(lu)
    lote_data = []
    for lote in lotes:
        lus = lus_por_lote.get(lote.id, [])
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
    _inicializar_stock_material(g.tenant_id, m.id)
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

    # Politica auto-sync: en_inventario se ignora aqui (siempre True).
    for field in ("expira", "unidad_inventario", "nombre"):
        if field in data:
            setattr(m, field, data[field])

    if not m.en_inventario:
        m.en_inventario = True
        _inicializar_stock_material(g.tenant_id, m.id)

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


@inventario_bp.route("/master-disponibles", methods=["GET"])
@require_auth
def master_disponibles():
    subq = db.session.query(Material.master_id).filter(
        Material.tenant_id == g.tenant_id,
        Material.master_id.isnot(None),
    )
    # selectinload de categorias: se leen por cada master al serializar.
    q = MaterialMaster.query.options(
        selectinload(MaterialMaster.categorias)
    ).filter(~MaterialMaster.id.in_(subq))
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


@inventario_bp.route("/dashboard", methods=["GET"])
@require_auth
def dashboard_kpis():
    return jsonify(calcular_kpis_dashboard(tenant_id=g.tenant_id))


@inventario_bp.route("/operatorios/distribucion", methods=["GET"])
@require_auth
def operatorios_distribucion():
    ops = Operatorio.query.filter_by(
        tenant_id=g.tenant_id, estado="activo"
    ).order_by(Operatorio.orden, Operatorio.nombre).all()

    if not ops:
        return jsonify([])

    op_ids = [op.id for op in ops]
    stocks_by_op: dict[int, list] = {op.id: [] for op in ops}
    for s in StockUbicacion.query.filter(
        StockUbicacion.tenant_id == g.tenant_id,
        StockUbicacion.operatorio_id.in_(op_ids),
    ).all():
        stocks_by_op[s.operatorio_id].append(s)

    result = []
    for op in ops:
        stocks = stocks_by_op[op.id]
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


@inventario_bp.route("/movimientos/recientes", methods=["GET"])
@require_auth
def movimientos_recientes():
    movs = (
        MovimientoInventario.query.filter_by(tenant_id=g.tenant_id)
        .order_by(MovimientoInventario.fecha.desc()).limit(5).all()
    )
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
                _inicializar_stock_material(g.tenant_id, existente.id)
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
        _inicializar_stock_material(g.tenant_id, m.id)
        importados += 1

    db.session.commit()
    return jsonify({"importados": importados}), 201
