"""Número de expediente del paciente: formato, reglas y asignación.

Dos formatos por clínica: "letra" (A000245 = letra + 6 dígitos) y "numerico"
(0000245 = 7 dígitos). El contador (`CrmConfig.expediente_siguiente`) es único
por clínica y lo comparten todas las letras. Nada aquí hace commit.
"""
import re

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.crm.models import CrmConfig, Paciente, PacienteEvento
from app.crm.services import CrmError, CrmForbidden, get_config

FORMATOS = ("letra", "numerico")
CONTADOR_INICIAL = 100
MAX_REINTENTOS = 5

_RE_LETRA = re.compile(r"^([A-Z])(\d{1,6})$")
_RE_NUMERICO = re.compile(r"^\d{1,7}$")
_RE_BUSQUEDA_LETRA = re.compile(r"^([A-Za-z])(\d{1,6})$")
_RE_BUSQUEDA_NUMERICA = re.compile(r"^\d{1,7}$")


def es_admin(usuario):
    return usuario.role == "admin" or bool(usuario.is_superuser)


def letras_de(cfg):
    return [x for x in (cfg.expediente_letras or "").split(",") if x]


def codigo_de_busqueda(texto):
    """Código completo al que apunta lo que se teclea en un buscador, o None.

    "a245" -> "A000245" y "245" -> "0000245": quien busca no teclea los ceros
    ni la mayúscula. Si el texto no parece un expediente devuelve None.
    """
    t = (texto or "").strip()
    m = _RE_BUSQUEDA_LETRA.match(t)
    if m:
        return formatear("letra", int(m.group(2)), m.group(1))
    if _RE_BUSQUEDA_NUMERICA.match(t):
        return formatear("numerico", int(t))
    return None


def formatear(formato, numero, letra=None):
    if formato == "letra":
        return f"{(letra or '').upper()}{numero:06d}"
    return f"{numero:07d}"


def _requiere_formato(cfg):
    if cfg.expediente_formato not in FORMATOS:
        raise CrmError("El admin aún no configura los expedientes")


def normalizar_manual(cfg, texto):
    """Devuelve (expediente, numero) ya con ceros/mayúscula, o lanza CrmError."""
    _requiere_formato(cfg)
    t = str(texto if texto is not None else "").strip().upper()
    if cfg.expediente_formato == "letra":
        m = _RE_LETRA.match(t)
        if not m:
            raise CrmError("El expediente debe ser una letra y hasta 6 dígitos, por ejemplo A000245")
        letra, numero = m.group(1), int(m.group(2))
        if letra not in letras_de(cfg):
            raise CrmError(f"La letra {letra} no está permitida en esta clínica")
    else:
        if not _RE_NUMERICO.match(t):
            raise CrmError("El expediente debe tener hasta 7 dígitos, por ejemplo 0000245")
        letra, numero = None, int(t)
    if numero < 1:
        raise CrmError("El número de expediente debe ser mayor que cero")
    return formatear(cfg.expediente_formato, numero, letra), numero


def siguiente_libre(tenant_id, cfg):
    """Primer número >= contador que ningún paciente del tenant (incluso eliminado) usa."""
    inicio = cfg.expediente_siguiente or CONTADOR_INICIAL
    usados = {
        n for (n,) in db.session.query(Paciente.expediente_numero).filter(
            Paciente.tenant_id == tenant_id,
            Paciente.expediente_numero >= inicio,
        )
    }
    n = inicio
    while n in usados:
        n += 1
    return n


def _evento(p, anterior, nuevo, usuario):
    db.session.add(PacienteEvento(
        tenant_id=p.tenant_id, paciente_id=p.id, tipo="expediente",
        detalle=f"{anterior or '—'} → {nuevo or '—'}",
        usuario_id=getattr(usuario, "id", None),
    ))


def _duplicado(expediente):
    return CrmError(f"El expediente {expediente} ya lo tiene otro paciente")


def aplicar(p, cfg, cambio, usuario):
    """Asigna, cambia o quita el expediente de `p`. Sin commit; hace flush.

    cambio: {"modo": "auto", "letra": "A"?} | {"modo": "manual", "valor": "a245"}
            | {"modo": "quitar"}
    Asignar el primero lo puede hacer cualquier usuario; cambiarlo o quitarlo, solo el admin.
    """
    modo = cambio.get("modo")
    if modo not in ("auto", "manual", "quitar"):
        raise CrmError("Modo de expediente inválido")
    anterior = p.expediente
    if anterior and not es_admin(usuario):
        raise CrmForbidden("Solo el administrador puede cambiar o quitar un expediente")

    if modo == "quitar":
        if anterior is None:
            return
        p.expediente = None
        p.expediente_numero = None
        _evento(p, anterior, None, usuario)
        db.session.flush()
        return

    _requiere_formato(cfg)

    if modo == "manual":
        nuevo, numero = normalizar_manual(cfg, cambio.get("valor"))
        if nuevo == anterior:
            return
        otro = Paciente.query.filter(
            Paciente.tenant_id == p.tenant_id, Paciente.expediente == nuevo,
            Paciente.id != p.id,
        ).first()
        if otro:
            raise _duplicado(nuevo)
        try:
            with db.session.begin_nested():
                p.expediente, p.expediente_numero = nuevo, numero
                db.session.flush()
        except IntegrityError:  # carrera con otro alta del mismo código
            raise _duplicado(nuevo)
        _evento(p, anterior, nuevo, usuario)
        db.session.flush()
        return

    # auto
    letra = None
    if cfg.expediente_formato == "letra":
        letra = cambio.get("letra")
        if letra is not None and not isinstance(letra, str):
            raise CrmError("Elige una letra de expediente válida")
        letra = (letra or "").strip().upper()
        letras = letras_de(cfg)
        if not letra and len(letras) == 1:
            letra = letras[0]
        if letra not in letras:
            raise CrmError("Elige una letra de expediente válida")
    # Dos altas simultáneas con letras distintas no pueden tomar el mismo número:
    # se serializan sobre la fila de config (SQLite ignora FOR UPDATE; no importa).
    # populate_existing relee el contador por si otro alta lo movió mientras esperábamos.
    CrmConfig.query.filter_by(tenant_id=p.tenant_id).with_for_update().populate_existing().one()
    for _ in range(MAX_REINTENTOS):
        numero = siguiente_libre(p.tenant_id, cfg)
        nuevo = formatear(cfg.expediente_formato, numero, letra)
        try:
            with db.session.begin_nested():
                p.expediente, p.expediente_numero = nuevo, numero
                db.session.flush()
        except IntegrityError:
            # Otro alta tomó el código entre la lectura y la escritura: seguir adelante.
            cfg.expediente_siguiente = max(cfg.expediente_siguiente or 0, numero + 1)
            continue
        cfg.expediente_siguiente = numero + 1
        _evento(p, anterior, nuevo, usuario)
        db.session.flush()
        return
    raise CrmError("No se pudo asignar un expediente libre, intenta de nuevo")


def configurar(tenant_id, formato, letras):
    """Guarda formato y letras del tenant (sin commit), respetando lo ya asignado."""
    if formato not in FORMATOS:
        raise CrmError("Formato de expediente inválido")
    cfg = get_config(tenant_id)
    nuevas = []
    if formato == "letra":
        for x in letras or []:
            x = (x or "").strip().upper()
            if not re.fullmatch(r"[A-Z]", x):
                raise CrmError(f"Letra inválida: {x or 'vacía'}")
            if x not in nuevas:
                nuevas.append(x)
        if not nuevas:
            raise CrmError("Indica al menos una letra para los expedientes")

    base = Paciente.query.filter(
        Paciente.tenant_id == tenant_id, Paciente.expediente.isnot(None),
    )
    if cfg.expediente_formato and formato != cfg.expediente_formato and base.count():
        raise CrmError("No se puede cambiar el formato: ya hay pacientes con expediente")
    if cfg.expediente_formato == "letra" and formato == "letra":
        for quitada in set(letras_de(cfg)) - set(nuevas):
            if base.filter(Paciente.expediente.like(f"{quitada}%")).count():
                raise CrmError(f"No se puede quitar la letra {quitada}: ya hay pacientes con ella")

    cfg.expediente_formato = formato
    cfg.expediente_letras = ",".join(nuevas) if formato == "letra" else None
    db.session.flush()
    return cfg
