"""Cifrado simétrico (Fernet) para los secretos del CSD: llave privada y contraseña.

La llave maestra vive en la variable de entorno FACTURACION_FERNET_KEY; nunca se
guarda en el repo ni en la base de datos. Los secretos solo se descifran en memoria
al momento de timbrar.
"""
from flask import current_app
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = current_app.config.get("FACTURACION_FERNET_KEY")
    if not key:
        raise RuntimeError(
            "FACTURACION_FERNET_KEY no está configurada; "
            "no se pueden cifrar/descifrar secretos del CSD."
        )
    return Fernet(key if isinstance(key, bytes) else key.encode())


def encrypt(data) -> bytes:
    """Cifra bytes (o str) y devuelve el token cifrado (bytes)."""
    if isinstance(data, str):
        data = data.encode()
    return _fernet().encrypt(data)


def decrypt(token) -> bytes:
    """Descifra un token producido por encrypt(); devuelve los bytes originales."""
    if isinstance(token, str):
        token = token.encode()
    return _fernet().decrypt(token)
