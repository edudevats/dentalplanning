"""Cliente SOAP para el Web Service de Registro de Clientes de Finkok.

Registra/edita/consulta el RFC emisor de un tenant bajo la cuenta del socio de
negocios (reseller). satcfdi no cubre este WSDL, así que armamos el envelope
SOAP 1.1 a mano y lo enviamos con requests, igual que el patrón interno de
satcfdi. Sin dependencias nuevas.

Doc: https://wiki.finkok.com/en/home/webservices/registro_de_clientes
"""
import base64
import logging

import requests
from lxml import etree

from app.facturacion.xml_safety import assert_safe_xml

logger = logging.getLogger(__name__)

_NS_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
_NS_REG = "http://facturacion.finkok.com/registration"

_ENDPOINTS = {
    "TEST": "https://demo-facturacion.finkok.com/servicios/soap/registration",
    "PRODUCTION": "https://facturacion.finkok.com/servicios/soap/registration",
}
_TIMEOUT = 30


class RegistroFinkokError(Exception):
    """Falla de red/HTTP al hablar con el WS de registro de Finkok."""


def _endpoint(environment):
    env = (environment or "TEST").upper()
    # Acepta "test"/"production" (config) y "TEST"/"PRODUCTION".
    if env not in _ENDPOINTS:
        env = "PRODUCTION" if env.startswith("PROD") else "TEST"
    return _ENDPOINTS[env]


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _envelope(operation, campos):
    """Arma el envelope SOAP 1.1; campos = lista de (nombre, valor) en orden.

    Todo se califica en el namespace de registro (elementFormDefault=qualified).
    """
    nsmap = {"soapenv": _NS_ENV, "reg": _NS_REG}
    env = etree.Element(etree.QName(_NS_ENV, "Envelope"), nsmap=nsmap)
    body = etree.SubElement(env, etree.QName(_NS_ENV, "Body"))
    op = etree.SubElement(body, etree.QName(_NS_REG, operation))
    for nombre, valor in campos:
        el = etree.SubElement(op, etree.QName(_NS_REG, nombre))
        el.text = "" if valor is None else str(valor)
    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def _post(operation, envelope, environment):
    """Envía el envelope y devuelve el árbol XML de la respuesta (validado XXE)."""
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{operation}"',
    }
    logger.debug("Finkok registration %s -> %s", operation, _endpoint(environment))
    try:
        resp = requests.post(
            _endpoint(environment), data=envelope, headers=headers,
            timeout=_TIMEOUT, verify=True,
        )
    except requests.RequestException as e:
        raise RegistroFinkokError(f"Error de conexión con Finkok: {e}")
    if resp.status_code != 200:
        raise RegistroFinkokError(f"Finkok respondió HTTP {resp.status_code}")
    try:
        assert_safe_xml(resp.content)  # respuesta no confiable
        return etree.fromstring(resp.content)
    except RegistroFinkokError:
        raise
    except Exception as e:
        raise RegistroFinkokError(f"Respuesta inválida de Finkok: {e}")


def _first_text(root, local_name):
    hits = root.xpath(f"//*[local-name()=$n]", n=local_name)
    return hits[0].text if hits else None


def _child_text(el, local_name):
    hits = el.xpath(f".//*[local-name()=$n]", n=local_name)
    return hits[0].text if hits else None


def _as_int(value):
    if value is None:
        return None
    value = value.strip()
    return int(value) if value.lstrip("-").isdigit() else None


def _result(root):
    """Extrae {success, message} de un RegistrationResult (add/edit)."""
    success = (_first_text(root, "success") or "").strip().lower() == "true"
    return {"success": success, "message": _first_text(root, "message") or ""}


def agregar_cliente(rfc, cer_bytes, key_bytes, passphrase, *,
                    username, password, environment, type_user="O", coupon=""):
    """Da de alta el RFC bajo la cuenta del socio (método add)."""
    envelope = _envelope("add", [
        ("reseller_username", username),
        ("reseller_password", password),
        ("taxpayer_id", rfc),
        ("type_user", type_user),
        ("coupon", coupon),
        ("added", ""),
        ("cer", _b64(cer_bytes)),
        ("key", _b64(key_bytes)),
        ("passphrase", passphrase),
    ])
    try:
        return _result(_post("add", envelope, environment))
    except RegistroFinkokError as e:
        return {"success": False, "message": str(e)}


def editar_cliente(rfc, cer_bytes, key_bytes, passphrase, *,
                   username, password, environment, status="A"):
    """Edita el cliente (método edit): status A/S y/o reemplazo de CSD."""
    envelope = _envelope("edit", [
        ("reseller_username", username),
        ("reseller_password", password),
        ("taxpayer_id", rfc),
        ("status", status),
        ("cer", _b64(cer_bytes)),
        ("key", _b64(key_bytes)),
        ("passphrase", passphrase),
    ])
    try:
        return _result(_post("edit", envelope, environment))
    except RegistroFinkokError as e:
        return {"success": False, "message": str(e)}


def consultar_cliente(rfc, *, username, password, environment):
    """Consulta el estado del RFC (método get)."""
    envelope = _envelope("get", [
        ("reseller_username", username),
        ("reseller_password", password),
        ("taxpayer_id", rfc),
    ])
    vacio = {"success": False, "status": None, "counter": None,
             "credit": None, "message": ""}
    try:
        root = _post("get", envelope, environment)
    except RegistroFinkokError as e:
        return {**vacio, "message": str(e)}
    # getResult -> users[ResellerUser{status,counter,taxpayer_id,credit}]
    for user in root.xpath("//*[local-name()='ResellerUser']"):
        if (_child_text(user, "taxpayer_id") or "").strip().upper() == rfc.strip().upper():
            return {
                "success": True,
                "status": _child_text(user, "status"),
                "counter": _as_int(_child_text(user, "counter")),
                "credit": _as_int(_child_text(user, "credit")),
                "message": _first_text(root, "message") or "",
            }
    return {**vacio, "message": _first_text(root, "message") or "RFC no encontrado"}
