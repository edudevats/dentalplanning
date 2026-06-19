"""Validación y parseo de un CSD (Certificado de Sello Digital) con satcfdi."""
from datetime import datetime
from satcfdi.models import Signer
from satcfdi.models.certificate import CertificateType


class CSDInvalido(Exception):
    """El CSD no se pudo cargar/validar, o no es un CSD (p. ej. es una FIEL)."""


def validar_csd(cer_bytes: bytes, key_bytes: bytes, password: str) -> dict:
    """Carga y valida un CSD. Devuelve metadatos del certificado.

    Lanza CSDInvalido si la contraseña no corresponde, si la llave no casa con el
    certificado, o si el certificado es una e.firma (FIEL) en vez de un CSD.
    """
    try:
        signer = Signer.load(
            certificate=cer_bytes, key=key_bytes, password=password
        )
    except Exception as e:  # satcfdi lanza distintas excepciones según el fallo
        raise CSDInvalido(
            f"No se pudo cargar el CSD (contraseña o archivos inválidos): {e}"
        )

    if signer.type != CertificateType.CSD:
        raise CSDInvalido(
            "El archivo es una e.firma (FIEL), no un CSD. "
            "Sube tu Certificado de Sello Digital."
        )

    not_before = signer.certificate.get_notBefore().decode()  # 'YYYYMMDDHHMMSSZ'
    not_after = signer.certificate.get_notAfter().decode()
    return {
        "rfc": str(signer.rfc),
        "razon_social": signer.legal_name,
        "no_certificado": signer.certificate_number,
        "valido_desde": datetime.strptime(not_before, "%Y%m%d%H%M%SZ"),
        "valido_hasta": datetime.strptime(not_after, "%Y%m%d%H%M%SZ"),
    }
