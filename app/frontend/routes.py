from flask import render_template, redirect, url_for
from . import frontend_bp


@frontend_bp.route('/')
def index():
    return redirect(url_for('frontend.selector'))


@frontend_bp.route('/selector')
def selector():
    return render_template('selector.html')


@frontend_bp.route('/login')
def login():
    return render_template('auth/login.html')


@frontend_bp.route('/register')
def register():
    return render_template('auth/register.html')


@frontend_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', page='dashboard')


@frontend_bp.route('/tratamientos')
def tratamientos():
    return render_template('precios/list.html', page='tratamientos')


@frontend_bp.route('/tratamientos/nuevo')
def tratamiento_nuevo():
    return render_template('precios/form.html', page='tratamientos', tratamiento_id=None)


@frontend_bp.route('/tratamientos/<int:tratamiento_id>')
def tratamiento_detail(tratamiento_id):
    return render_template('precios/detail.html', page='tratamientos', tratamiento_id=tratamiento_id)


@frontend_bp.route('/tratamientos/<int:tratamiento_id>/editar')
def tratamiento_editar(tratamiento_id):
    return render_template('precios/form.html', page='tratamientos', tratamiento_id=tratamiento_id)


@frontend_bp.route('/materiales')
def materiales():
    return render_template('catalogo/materiales.html', page='materiales')


@frontend_bp.route('/ingresos')
def ingresos():
    return render_template('edr/ingresos.html', page='ingresos')


@frontend_bp.route('/gastos')
def gastos():
    return render_template('edr/gastos.html', page='gastos')


@frontend_bp.route('/pagos-doctores')
def pagos_doctores():
    return render_template('edr/pagos_doctores.html', page='pagos-doctores')


@frontend_bp.route('/reportes/resumen')
def reportes_resumen():
    return render_template('reportes/resumen.html', page='reportes/resumen')


@frontend_bp.route('/reportes/trimestral')
def reportes_trimestral():
    return redirect(url_for('frontend.reportes_resumen'))


@frontend_bp.route('/reportes/distribucion')
def reportes_distribucion():
    return redirect(url_for('frontend.reportes_resumen'))


@frontend_bp.route('/reportes/marketing')
def reportes_marketing():
    return render_template('reportes/marketing.html', page='reportes/marketing')


@frontend_bp.route('/ajustes')
def ajustes():
    return render_template('ajustes/index.html', page='ajustes')


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


@frontend_bp.route("/inventario/almacen")
def inventario_almacen():
    return render_template("inventario/almacen.html")


@frontend_bp.route("/inventario/transferir")
def inventario_transferir():
    return render_template("inventario/transferir.html")


# ── Panel Super-Admin ───────────────────────────────────────────────────────

@frontend_bp.route("/admin")
@frontend_bp.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin/dashboard.html")


@frontend_bp.route("/admin/tenants")
def admin_tenants():
    return render_template("admin/tenants.html")


@frontend_bp.route("/admin/tenants/<int:tenant_id>")
def admin_tenant_detail(tenant_id):
    return render_template("admin/tenant_detail.html", tenant_id=tenant_id)


@frontend_bp.route("/admin/pagos")
def admin_pagos():
    return render_template("admin/pagos.html")


@frontend_bp.route("/admin/planes")
def admin_planes():
    return render_template("admin/planes.html")
