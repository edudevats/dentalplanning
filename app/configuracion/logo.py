"""Logo del consultorio: fuente única para todo el que lo necesite.

Vive en `ConfigConsultorio` porque es un dato de la clínica, no de sus datos
fiscales: lo usan el ticket impreso, el PDF del CFDI, el portal de
autofacturación y las cotizaciones.
"""
import base64
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func

from app.configuracion.models import ConfigConsultorio
from app.extensions import db

# Normalizamos al subir para que el BLOB siempre quede chico (sin riesgo de
# truncado en BD) y se vea consistente en todos los consumidores.
LOGO_MAX_PX = 512          # lado mayor; suficiente para mostrarlo a 80-220px (incl. retina)
LOGO_MAX_UPLOAD = 8 * 1024 * 1024  # tope del archivo de entrada antes de decodificar


def procesar_logo(raw):
    """Valida que sea imagen, la reescala a LOGO_MAX_PX y la devuelve como PNG.

    Conserva la transparencia. Lanza ValueError si no es una imagen válida.
    """
    try:
        img = Image.open(BytesIO(raw))
        img.load()  # fuerza el decode real → valida que no esté corrupta
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("archivo no es una imagen válida")
    # Conserva canal alfa si lo tiene; si no, RGB plano
    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.thumbnail((LOGO_MAX_PX, LOGO_MAX_PX), Image.LANCZOS)  # mantiene proporción
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def logo_bytes(tenant_id):
    """Bytes del logo del tenant, o None si no tiene."""
    cfg = ConfigConsultorio.query.filter_by(tenant_id=tenant_id).first()
    if not cfg or not cfg.logo:
        return None
    return bytes(cfg.logo)


def logo_b64(tenant_id):
    """Logo como base64 (para el agente de impresión y los data: URI)."""
    data = logo_bytes(tenant_id)
    return base64.b64encode(data).decode("ascii") if data else None


def logo_version(tenant_id):
    """Longitud en bytes, para cache-busting. No carga el BLOB.

    Cambia cuando el consultorio sube otro logo, así el navegador no se queda
    con el viejo.
    """
    return db.session.query(
        func.length(ConfigConsultorio.logo)
    ).filter_by(tenant_id=tenant_id).scalar() or ""


def logo_mime(data):
    """Detecta el tipo de imagen por los bytes mágicos (no guardamos el tipo)."""
    if data[:8].startswith(b"\x89PNG"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"
