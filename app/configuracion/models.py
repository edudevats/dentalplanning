from datetime import datetime, timezone
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from app.extensions import db


class ConfigConsultorio(db.Model):
    __tablename__ = "config_consultorio"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), unique=True, nullable=False
    )
    gastos_fijos = db.Column(db.Float, default=0)
    horas_lunes = db.Column(db.Float, default=8)
    horas_martes = db.Column(db.Float, default=8)
    horas_miercoles = db.Column(db.Float, default=8)
    horas_jueves = db.Column(db.Float, default=8)
    horas_viernes = db.Column(db.Float, default=8)
    horas_sabado = db.Column(db.Float, default=0)
    horas_domingo = db.Column(db.Float, default=0)
    numero_unidades = db.Column(db.Integer, default=1)
    dias_alerta_caducidad = db.Column(db.Integer, default=30, nullable=False)
    # Tasa de impuesto SOLO informativa (estimación de impuestos a pagar).
    # No se resta de la utilidad ni se usa en ningún otro cálculo de la app.
    tasa_impuesto_pct = db.Column(db.Float, default=0, nullable=False)
    # Diferencia en pesos que el corte de caja tolera sin exigir comentario.
    # Default 0: cualquier descuadre, aunque sea de un peso, pide explicación.
    tolerancia_corte_caja = db.Column(db.Float, nullable=False, default=0,
                                      server_default="0")
    # Logo de la clínica. Vive aquí (y no en ConfiguracionFiscal) porque lo usan
    # el ticket impreso, el CFDI, el portal de autofacturación y las
    # cotizaciones. Se lee siempre vía app/configuracion/logo.py.
    # MySQL mapea LargeBinary a BLOB (máx 64KB) y truncaría logos grandes;
    # MEDIUMBLOB sube el límite a 16MB. SQLite (tests) ignora la variante.
    logo = db.Column(db.LargeBinary().with_variant(MEDIUMBLOB(), "mysql"))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def horas_semana(self):
        return (
            self.horas_lunes
            + self.horas_martes
            + self.horas_miercoles
            + self.horas_jueves
            + self.horas_viernes
            + self.horas_sabado
            + self.horas_domingo
        )

    @property
    def horas_mes(self):
        return self.horas_semana * 4

    @property
    def costo_hora(self):
        if self.horas_mes > 0 and self.numero_unidades > 0:
            return self.gastos_fijos / self.horas_mes / self.numero_unidades
        return 0

    @property
    def costo_operario_hora(self):
        if self.horas_mes > 0:
            return self.gastos_fijos / self.horas_mes
        return 0

