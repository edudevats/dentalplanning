import os
from flask import Flask
from app.config import config_by_name
from app.extensions import db, migrate, jwt, cors


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.catalogo.routes import catalogo_bp
    from app.configuracion.routes import config_bp
    from app.tratamientos.routes import tratamientos_bp
    from app.edr.routes import edr_bp
    from app.dashboard.routes import dashboard_bp
    from app.ajustes.routes import ajustes_bp
    from app.frontend.routes import frontend_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(tratamientos_bp)
    app.register_blueprint(edr_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ajustes_bp)
    app.register_blueprint(frontend_bp)

    # Error handlers
    from app.middleware.error_handlers import register_error_handlers
    register_error_handlers(app)

    # Import all models so they're registered with SQLAlchemy
    with app.app_context():
        from app.auth import models as auth_models  # noqa: F401
        from app.catalogo import models as catalogo_models  # noqa: F401
        from app.configuracion import models as config_models  # noqa: F401
        from app.tratamientos import models as tx_models  # noqa: F401
        from app.edr import models as edr_models  # noqa: F401
        from app.ajustes import models as ajustes_models  # noqa: F401

    # Health check
    @app.route("/api/v1/health")
    def health():
        return {"status": "ok", "app": "DentalSaaS"}

    return app
