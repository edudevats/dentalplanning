"""
Timezone helper utilities for the SAT application.
Ensures all datetime operations use Mexico City timezone.
"""
from datetime import datetime
import sys

# Handle Python version compatibility for timezone support
if sys.version_info >= (3, 9):
    from zoneinfo import ZoneInfo
else:
    from backports.zoneinfo import ZoneInfo


# Mexico City timezone
MEXICO_TIMEZONE = ZoneInfo("America/Mexico_City")


# Monkeypatch satcfdi's incorrect timezone mappings
# satcfdi maps 'Tiempo del Pacífico' to 'America/La_Paz' (Bolivia, UTC-4!)
# and 'Tiempo del Noroeste' to 'America/Matamoros' (UTC-6)
try:
    import satcfdi.transform as _sat_transform
    _sat_transform.HUSO_HORARIOS['Tiempo del Pacífico'] = 'America/Mazatlan'
    _sat_transform.HUSO_HORARIOS['Tiempo del Noroeste'] = 'America/Tijuana'
except Exception:
    pass



def now_mexico():
    """
    Get current datetime in Mexico City timezone.
    
    Returns:
        datetime: Current datetime with Mexico City timezone
    """
    return datetime.now(MEXICO_TIMEZONE)


def to_mexico_time(dt):
    """
    Convert a datetime object to Mexico City timezone.
    
    Args:
        dt: datetime object (naive or aware)
        
    Returns:
        datetime: Datetime in Mexico City timezone
    """
    if dt is None:
        return None
        
    # If naive, assume it's already in Mexico timezone
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MEXICO_TIMEZONE)
    
    # If aware, convert to Mexico timezone
    return dt.astimezone(MEXICO_TIMEZONE)


def get_today():
    """
    Get today's date in Mexico City timezone.
    
    Returns:
        date: Today's date in Mexico timezone
    """
    return now_mexico().date()
