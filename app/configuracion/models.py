from datetime import datetime, timezone
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
