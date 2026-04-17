from flask import render_template, redirect, url_for
from . import frontend_bp


@frontend_bp.route('/')
def index():
    return redirect(url_for('frontend.dashboard'))


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
