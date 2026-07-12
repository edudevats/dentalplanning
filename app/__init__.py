import os
from flask import Flask
from app.config import config_by_name
from app.extensions import db, migrate, jwt, cors


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    config_cls = config_by_name[config_name]
    app.config.from_object(config_cls)

    # Let config classes run boot-time validation (e.g. secret checks)
    if hasattr(config_cls, "init_app"):
        config_cls.init_app(app)

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={
        r"/api/*": {"origins": app.config.get("CORS_ORIGINS", ["*"])}
    })

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.catalogo.routes import catalogo_bp
    from app.configuracion.routes import config_bp
    from app.tratamientos.routes import tratamientos_bp
    from app.edr.routes import edr_bp
    from app.dashboard.routes import dashboard_bp
    from app.ajustes.routes import ajustes_bp
    from app.inventario.routes import inventario_bp
    from app.finanzas_personales.routes import finanzas_personales_bp
    from app.superadmin.routes import superadmin_bp
    from app.clip.routes import clip_bp
    from app.frontend.routes import frontend_bp
    from app.facturacion.routes import facturacion_bp
    from app.portal.routes import portal_bp
    from app.crm.routes import crm_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(tratamientos_bp)
    app.register_blueprint(edr_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ajustes_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(finanzas_personales_bp)
    app.register_blueprint(superadmin_bp)
    app.register_blueprint(clip_bp)
    app.register_blueprint(frontend_bp)
    app.register_blueprint(facturacion_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(crm_bp)

    # Error handlers
    from app.middleware.error_handlers import register_error_handlers
    register_error_handlers(app)

    # Instrumentación opt-in de tiempos de respuesta (PROFILE_REQUESTS=1)
    from app.middleware.profiling import init_profiling
    init_profiling(app)

    # Import all models so they're registered with SQLAlchemy
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
        from app.facturacion import models as facturacion_models  # noqa: F401
        from app.crm import models as crm_models  # noqa: F401

    # Health check
    @app.route("/api/v1/health")
    def health():
        return {"status": "ok", "app": "Dental Planning"}

    from app.inventario.cli import inventario_cli
    app.cli.add_command(inventario_cli)

    from app.clip.cli import billing_cli
    app.cli.add_command(billing_cli)

    return app
