import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 2592000))
    )
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    RATELIMIT_ENABLED = True
    CLIP_API_KEY = os.getenv("CLIP_API_KEY", "")
    CLIP_SECRET_KEY = os.getenv("CLIP_SECRET_KEY", "")
    CLIP_WEBHOOK_SECRET = os.getenv("CLIP_WEBHOOK_SECRET", "")
    CLIP_BASE_URL = os.getenv("CLIP_BASE_URL", "https://api.payclip.com")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://www.dentalplanning.mx")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "USER_MAIL")
    SMTP_PASS = os.getenv("SMTP_PASS", "PASS_MAIL")
    SMTP_FROM = os.getenv("SMTP_FROM", "alertas@dentalplanning.mx")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    BILLING_GRACE_DAYS = int(os.getenv("BILLING_GRACE_DAYS", "3"))
    # Llave maestra (Fernet) para cifrar secretos del CSD. NUNCA en el repo ni en la BD.
    FACTURACION_FERNET_KEY = os.getenv("FACTURACION_FERNET_KEY", "")
    # Finkok (PAC para timbrado de CFDI). FINKOK_PASSWORD es el token/contraseña.
    # FINKOK_ENVIRONMENT: "test" (sandbox de pruebas) o "production".
    FINKOK_USERNAME = os.getenv("FINKOK_USERNAME", "")
    FINKOK_PASSWORD = os.getenv("FINKOK_PASSWORD", "")
    FINKOK_ENVIRONMENT = os.getenv("FINKOK_ENVIRONMENT", "test")


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///dental_saas.db"
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=300)
    RATELIMIT_ENABLED = False
    FACTURACION_FERNET_KEY = "8-ANfoQdltt99PyJ-wSEMA_n6fVz7QT0QtKNoGt1liE="


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def init_app(cls, app):
        """Validate required secrets at boot time."""
        for key in ("SECRET_KEY", "JWT_SECRET_KEY", "FACTURACION_FERNET_KEY"):
            if not os.environ.get(key):
                raise RuntimeError(
                    f"CRITICAL: {key} environment variable is required "
                    f"in production. Set it before starting the app."
                )
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
        app.config["JWT_SECRET_KEY"] = os.environ["JWT_SECRET_KEY"]
        app.config["FACTURACION_FERNET_KEY"] = os.environ["FACTURACION_FERNET_KEY"]


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
