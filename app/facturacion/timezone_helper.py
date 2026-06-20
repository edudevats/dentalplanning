"""Zona horaria de México para fechas del CFDI (SAT)."""
from datetime import datetime
from zoneinfo import ZoneInfo

MEXICO_TIMEZONE = ZoneInfo("America/Mexico_City")


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
