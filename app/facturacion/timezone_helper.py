"""Zona horaria de México para fechas del CFDI (SAT).

Usamos un offset FIJO de UTC-6 en lugar de ZoneInfo("America/Mexico_City"):
la Ciudad de México dejó de observar horario de verano (DST) en octubre de 2022
y es UTC-6 (CST) todo el año. Si el servidor de despliegue tuviera una versión
desactualizada de tzdata, ZoneInfo aplicaría DST en verano y la Fecha del CFDI
saldría 1 hora en el futuro, y el SAT/Finkok la rechaza
("401 - Fecha y hora de generación fuera de rango"). El offset fijo elimina esa
dependencia del sistema operativo.
"""
from datetime import datetime, timezone, timedelta

# Horario del Centro de México (CST): UTC-6 fijo, sin DST desde 2022.
MEXICO_TIMEZONE = timezone(timedelta(hours=-6))


def now_mexico():
    return datetime.now(MEXICO_TIMEZONE)


def to_mexico_time(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MEXICO_TIMEZONE)
    return dt.astimezone(MEXICO_TIMEZONE)


def get_today():
    return now_mexico().date()
