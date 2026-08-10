from flask import render_template, redirect, url_for, request
from . import frontend_bp


@frontend_bp.route('/')
def index():
    return redirect(url_for('frontend.selector'))


@frontend_bp.route('/selector')
def selector():
    return render_template('selector.html')


@frontend_bp.route('/login')
def login():
    return render_template('auth/login.html', public_page=True)


@frontend_bp.route('/register')
def register():
    return render_template('auth/register.html', public_page=True)


@frontend_bp.route('/registro-exitoso')
def registro_exitoso():
    return render_template('auth/registro_exitoso.html', public_page=True)


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


@frontend_bp.route('/facturas')
def facturas():
    return render_template('facturas/list.html', page='facturas')


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


@frontend_bp.route("/admin/tenants/<int:tenant_id>/reportes")
def admin_tenant_reportes(tenant_id):
    # Garantiza el contexto as_tenant en la URL para que app.js lo propague en cada GET
    if request.args.get("as_tenant") != str(tenant_id):
        return redirect(url_for("frontend.admin_tenant_reportes",
                                tenant_id=tenant_id, as_tenant=tenant_id))
    return render_template("admin/tenant_reportes.html", tenant_id=tenant_id)


@frontend_bp.route("/admin/tenants/<int:tenant_id>/reportes/marketing")
def admin_tenant_reportes_marketing(tenant_id):
    if request.args.get("as_tenant") != str(tenant_id):
        return redirect(url_for("frontend.admin_tenant_reportes_marketing",
                                tenant_id=tenant_id, as_tenant=tenant_id))
    return render_template("admin/tenant_reportes_marketing.html", tenant_id=tenant_id)


@frontend_bp.route("/admin/pagos")
def admin_pagos():
    return render_template("admin/pagos.html")


@frontend_bp.route("/admin/planes")
def admin_planes():
    return render_template("admin/planes.html")


@frontend_bp.route("/admin/solicitudes")
def admin_solicitudes():
    return render_template("admin/solicitudes.html")


@frontend_bp.route("/admin/auditoria")
def admin_auditoria():
    return render_template("admin/auditoria.html")


# Finanzas Personales

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


# ── CRM de Pacientes ──

@frontend_bp.route("/crm")
def crm_kanban():
    return render_template("crm/kanban.html", crm_screen="kanban")


@frontend_bp.route("/crm/pendientes")
def crm_pendientes():
    return render_template("crm/pendientes.html", crm_screen="pendientes")


@frontend_bp.route("/crm/importar")
def crm_importar():
    return render_template("crm/importar.html", crm_screen="importar")


@frontend_bp.route("/cotizaciones")
def cobranza_cotizaciones():
    return render_template(
        "cobranza/cotizaciones.html", crm_screen="cotizaciones",
    )
