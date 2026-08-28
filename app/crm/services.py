"""Capa de servicios del CRM: TODAS las escrituras pasan por aquí (patrón inventario)."""
from datetime import date, timedelta
from app.extensions import db
from app.auth.models import Tenant
from app.crm.models import (
    ESTATUS_CRM, SEGUIMIENTO_TIPOS,
    Paciente, PacienteVisita, PacienteSeguimiento, PacienteEvento, CrmConfig,
)


class CrmError(Exception):
    """Error de negocio del CRM; las routes lo devuelven como 400."""


class CrmNotFound(CrmError):
    """Recurso del CRM no encontrado; las routes lo devuelven como 404."""


CAMPOS_PACIENTE = (
    "nombre", "telefono", "whatsapp", "email", "fecha_nacimiento",
    "especialista_id", "es_problematico", "notas_generales",
)


def _paciente(tenant_id, paciente_id, incluir_eliminados=False):
    q = Paciente.query.filter_by(id=paciente_id, tenant_id=tenant_id)
    if not incluir_eliminados:
        q = q.filter_by(eliminado=False)
    p = q.first()
    if not p:
        raise CrmNotFound("Paciente no encontrado")
    return p


def _validar_especialista(tenant_id, especialista_id):
    if especialista_id is None:
        return
    from app.ajustes.models import Especialista
    ok = Especialista.query.filter_by(id=especialista_id, tenant_id=tenant_id).first()
    if not ok:
        raise CrmError("Especialista no encontrado")


def get_config(tenant_id):
    cfg = CrmConfig.query.filter_by(tenant_id=tenant_id).first()
    if not cfg:
        cfg = CrmConfig(tenant_id=tenant_id, meses_inactividad=4)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def fecha_corte_inactividad(tenant_id):
    meses = get_config(tenant_id).meses_inactividad or 4
    return date.today() - timedelta(days=30 * meses)


def crm_activo(tenant_id):
    tenant = db.session.get(Tenant, tenant_id)
    return bool(tenant) and "crm" in tenant.allowed_modules


def crear_paciente(tenant_id, data, usuario_id=None):
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise CrmError("El nombre del paciente es obligatorio")
    estatus = data.get("estatus_crm") or "prospecto"
    if estatus not in ESTATUS_CRM:
        raise CrmError("Estatus inválido")
    _validar_especialista(tenant_id, data.get("especialista_id"))
    p = Paciente(
        tenant_id=tenant_id, nombre=nombre, estatus_crm=estatus,
        **{k: data.get(k) for k in CAMPOS_PACIENTE if k != "nombre" and k in data},
    )
    db.session.add(p)
    db.session.commit()
    return p


def actualizar_paciente(tenant_id, paciente_id, data, usuario_id=None):
    p = _paciente(tenant_id, paciente_id)
    if "nombre" in data and not (data.get("nombre") or "").strip():
        raise CrmError("El nombre del paciente es obligatorio")
    if "especialista_id" in data:
        _validar_especialista(tenant_id, data.get("especialista_id"))
    nuevo_estatus = data.get("estatus_crm")
    if nuevo_estatus and nuevo_estatus != p.estatus_crm:
        _registrar_cambio_estatus(p, nuevo_estatus, usuario_id)
    for k in CAMPOS_PACIENTE:
        if k in data:
            setattr(p, k, data[k])
    db.session.commit()
    return p


def eliminar_paciente(tenant_id, paciente_id):
    p = _paciente(tenant_id, paciente_id)
    p.eliminado = True
    db.session.commit()


def _registrar_cambio_estatus(p, nuevo_estatus, usuario_id):
    if nuevo_estatus not in ESTATUS_CRM:
        raise CrmError("Estatus inválido")
    db.session.add(PacienteEvento(
        tenant_id=p.tenant_id, paciente_id=p.id, tipo="cambio_estatus",
        detalle=f"{p.estatus_crm} → {nuevo_estatus}", usuario_id=usuario_id,
    ))
    p.estatus_crm = nuevo_estatus


def cambiar_estatus(tenant_id, paciente_id, nuevo_estatus, usuario_id=None):
    p = _paciente(tenant_id, paciente_id)
    if nuevo_estatus != p.estatus_crm:
        _registrar_cambio_estatus(p, nuevo_estatus, usuario_id)
    db.session.commit()
    return p


def agregar_visita(tenant_id, paciente_id, fecha, motivo=None, ingreso_id=None, usuario_id=None):
    p = _paciente(tenant_id, paciente_id)
    v = PacienteVisita(
        tenant_id=tenant_id, paciente_id=p.id, fecha=fecha,
        motivo=motivo, ingreso_id=ingreso_id, created_by=usuario_id,
    )
    db.session.add(v)
    db.session.commit()
    return v


def agregar_seguimiento(tenant_id, paciente_id, tipo, fecha_programada, notas=None, usuario_id=None):
    if tipo not in SEGUIMIENTO_TIPOS:
        raise CrmError("Tipo de seguimiento inválido")
    p = _paciente(tenant_id, paciente_id)
    s = PacienteSeguimiento(
        tenant_id=tenant_id, paciente_id=p.id, tipo=tipo,
        fecha_programada=fecha_programada, notas=notas, created_by=usuario_id,
    )
    db.session.add(s)
    db.session.commit()
    return s


def completar_seguimiento(tenant_id, seguimiento_id):
    s = PacienteSeguimiento.query.filter_by(
        id=seguimiento_id, tenant_id=tenant_id
    ).first()
    if not s:
        raise CrmNotFound("Seguimiento no encontrado")
    s.completado = True
    s.fecha_completado = date.today()
    db.session.commit()
    return s


def agregar_nota(tenant_id, paciente_id, texto, usuario_id=None):
    texto = (texto or "").strip()
    if not texto:
        raise CrmError("La nota no puede estar vacía")
    p = _paciente(tenant_id, paciente_id)
    e = PacienteEvento(
        tenant_id=tenant_id, paciente_id=p.id, tipo="nota",
        detalle=texto, usuario_id=usuario_id,
    )
    db.session.add(e)
    db.session.commit()
    return e


# ── Hooks del EDR (SIN commit: participan en la transacción del caller) ──

def _motivo_de(hermanos):
    """El motivo de la visita: los tratamientos del grupo, uno tras otro."""
    nombres = [h.nombre_tratamiento for h in hermanos if h.nombre_tratamiento]
    return " + ".join(nombres) if nombres else "Tratamiento"


def sincronizar_visita_ingreso(ingreso):
    """Crea/actualiza la visita ligada al GRUPO del ingreso. Llamar tras flush.

    La visita es del paciente, no del renglón: una visita por grupo, anclada al
    primer ingreso. Buscarla por cualquier hermano —y no solo por `ingreso.id`—
    es lo que evita que editar la segunda línea abra una visita duplicada.
    """
    from app.edr.services import hermanos_de_visita
    hermanos = hermanos_de_visita(ingreso)
    ids = [h.id for h in hermanos]
    visita = PacienteVisita.query.filter(
        PacienteVisita.tenant_id == ingreso.tenant_id,
        PacienteVisita.ingreso_id.in_(ids),
    ).first()

    if not ingreso.paciente_id:
        if visita:
            db.session.delete(visita)
        return

    p = Paciente.query.filter_by(
        id=ingreso.paciente_id, tenant_id=ingreso.tenant_id, eliminado=False
    ).first()
    if not p:
        raise CrmError("Paciente no encontrado en el CRM")

    ancla = hermanos[0]
    motivo = _motivo_de(hermanos)
    if visita:
        visita.paciente_id = p.id
        visita.fecha = ancla.fecha
        visita.motivo = motivo
    else:
        db.session.add(PacienteVisita(
            tenant_id=ingreso.tenant_id, paciente_id=p.id,
            fecha=ancla.fecha, motivo=motivo, ingreso_id=ancla.id,
        ))


def eliminar_visita_ingreso(tenant_id, ingreso_id):
    """Suelta al ingreso de su visita antes de borrarlo.

    Si era el que la anclaba y quedan hermanos, la visita no se va con él: se
    re-ancla al siguiente y su motivo se recalcula sin el tratamiento borrado.
    Si no era el ancla, la visita del grupo se queda donde está, pero su
    motivo igual nombraba este tratamiento y debe recalcularse sin él. Sólo
    desaparece cuando se fue el último del grupo.
    """
    from app.edr.models import Ingreso
    from app.edr.services import hermanos_de_visita

    # hermanos_de_visita ya devuelve [ingreso] cuando visita_uid es NULL, así
    # que no hace falta comprobarlo aparte: sólo se necesita que el ingreso
    # exista (db.session.get puede devolver None).
    ingreso = db.session.get(Ingreso, ingreso_id)
    restantes = []
    if ingreso:
        restantes = [h for h in hermanos_de_visita(ingreso) if h.id != ingreso_id]

    visita = PacienteVisita.query.filter_by(
        tenant_id=tenant_id, ingreso_id=ingreso_id
    ).first()
    if visita:
        if not restantes:
            db.session.delete(visita)
            return
        visita.ingreso_id = restantes[0].id
        visita.fecha = restantes[0].fecha
        visita.motivo = _motivo_de(restantes)
        return

    # El ingreso borrado no anclaba la visita (era un hermano). La visita del
    # grupo, si existe, sigue en su renglón de siempre — pero su motivo
    # mencionaba este tratamiento, así que hay que recalcularlo sin él.
    if not restantes:
        return
    visita_grupo = PacienteVisita.query.filter(
        PacienteVisita.tenant_id == tenant_id,
        PacienteVisita.ingreso_id.in_([h.id for h in restantes]),
    ).first()
    if visita_grupo:
        visita_grupo.motivo = _motivo_de(restantes)


# ── Importación CSV / XLSX ──

CAMPOS_IMPORT = ("nombre", "telefono", "whatsapp", "email", "estatus")


def _celda_a_texto(c):
    """Normaliza una celda de xlsx a texto; evita '5511111111.0' en teléfonos numéricos."""
    if c is None:
        return ""
    if isinstance(c, float) and c.is_integer():
        return str(int(c))
    return str(c).strip()


def parsear_archivo_pacientes(file_storage):
    """Devuelve list[dict] con claves CAMPOS_IMPORT a partir de un CSV o XLSX."""
    nombre_archivo = (file_storage.filename or "").lower()
    if nombre_archivo.endswith(".csv"):
        import csv, io
        texto = file_storage.read().decode("utf-8-sig", errors="replace")
        lector = csv.DictReader(io.StringIO(texto))
        encabezados = [h.strip().lower() for h in (lector.fieldnames or [])]
        filas_raw = [
            {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
            for fila in lector
        ]
    elif nombre_archivo.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(file_storage, read_only=True)
        hoja = wb.active
        iterador = hoja.iter_rows(values_only=True)
        primera = next(iterador, None)
        encabezados = [str(c or "").strip().lower() for c in (primera or [])]
        filas_raw = []
        for row in iterador:
            filas_raw.append({
                encabezados[i]: _celda_a_texto(c)
                for i, c in enumerate(row) if i < len(encabezados)
            })
        wb.close()
    else:
        raise CrmError("Formato no soportado; sube un archivo .csv o .xlsx")

    if "nombre" not in encabezados:
        raise CrmError("El archivo debe tener una columna 'nombre'")

    return [
        {campo: fila.get(campo, "") for campo in CAMPOS_IMPORT}
        for fila in filas_raw
        if any((fila.get(campo) or "") for campo in CAMPOS_IMPORT)
    ]


def preview_importacion(tenant_id, filas):
    telefonos = {
        t for (t,) in db.session.query(Paciente.telefono).filter(
            Paciente.tenant_id == tenant_id, Paciente.eliminado.is_(False),
            Paciente.telefono.isnot(None), Paciente.telefono != "",
        )
    }
    nombres = {
        n.strip().lower() for (n,) in db.session.query(Paciente.nombre).filter(
            Paciente.tenant_id == tenant_id, Paciente.eliminado.is_(False),
        )
    }

    vistos_tel = set()
    vistos_nombre = set()

    resultado = []
    for fila in filas:
        advertencias = []
        valida = bool((fila.get("nombre") or "").strip())
        if not valida:
            advertencias.append("Fila sin nombre; no se importará")
        else:
            telefono = fila.get("telefono") or ""
            nombre_norm = fila["nombre"].strip().lower()
            if telefono and telefono in telefonos:
                advertencias.append("Ya existe un paciente con este teléfono")
            elif telefono and telefono in vistos_tel:
                advertencias.append("Duplicado dentro del archivo (teléfono)")
            if nombre_norm in nombres:
                advertencias.append("Ya existe un paciente con este nombre")
            elif nombre_norm in vistos_nombre:
                advertencias.append("Duplicado dentro del archivo (nombre)")
            if telefono:
                vistos_tel.add(telefono)
            vistos_nombre.add(nombre_norm)
        estatus = (fila.get("estatus") or "").strip().lower()
        if estatus and estatus not in ESTATUS_CRM:
            advertencias.append(f"Estatus '{estatus}' desconocido; se usará 'prospecto'")
        resultado.append({**fila, "advertencias": advertencias, "valida": valida})

    return {
        "filas": resultado,
        "total": len(resultado),
        "validas": sum(1 for f in resultado if f["valida"]),
    }


def importar_pacientes(tenant_id, filas, usuario_id=None):
    if not isinstance(filas, list) or not all(isinstance(f, dict) for f in filas):
        raise CrmError("Formato de filas inválido")
    creados = 0
    for fila in filas:
        nombre = (fila.get("nombre") or "").strip()
        if not nombre:
            continue
        estatus = (fila.get("estatus") or "").strip().lower()
        db.session.add(Paciente(
            tenant_id=tenant_id,
            nombre=nombre,
            telefono=(fila.get("telefono") or "") or None,
            whatsapp=(fila.get("whatsapp") or "") or None,
            email=(fila.get("email") or "") or None,
            estatus_crm=estatus if estatus in ESTATUS_CRM else "prospecto",
        ))
        creados += 1
    db.session.commit()  # atómico: o entran todos o ninguno
    return creados


# ── Vinculación con ingresos históricos del EDR ──

def sugerencias_edr(tenant_id):
    from sqlalchemy import func
    from app.edr.models import Ingreso

    filas = db.session.query(
        func.trim(Ingreso.paciente).label("nombre"),
        func.count(Ingreso.id),
        func.max(Ingreso.fecha),
    ).filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.paciente_id.is_(None),
        Ingreso.paciente.isnot(None),
        func.trim(Ingreso.paciente) != "",
    ).group_by(func.trim(Ingreso.paciente)).all()

    existentes = {
        (p.nombre or "").strip().lower(): p.id
        for p in Paciente.query.filter_by(tenant_id=tenant_id, eliminado=False)
    }
    return [
        {
            "nombre": nombre,
            "num_ingresos": num,
            "ultima_fecha": ultima.isoformat() if ultima else None,
            "paciente_existente_id": existentes.get(nombre.strip().lower()),
        }
        for nombre, num, ultima in sorted(filas, key=lambda f: f[0].lower())
    ]


def vincular_paciente_edr(tenant_id, nombre, usuario_id=None):
    from sqlalchemy import func
    from app.edr.models import Ingreso
    from app.edr.services import hermanos_de_visita

    nombre = (nombre or "").strip()
    if not nombre:
        raise CrmError("Falta el nombre a vincular")

    paciente = Paciente.query.filter(
        Paciente.tenant_id == tenant_id, Paciente.eliminado.is_(False),
        func.lower(Paciente.nombre) == nombre.lower(),
    ).first()
    if not paciente:
        paciente = Paciente(tenant_id=tenant_id, nombre=nombre, estatus_crm="activo")
        db.session.add(paciente)
        db.session.flush()

    ingresos = Ingreso.query.filter(
        Ingreso.tenant_id == tenant_id,
        Ingreso.paciente_id.is_(None),
        func.trim(Ingreso.paciente) == nombre,
    ).all()

    con_visita = {
        v.ingreso_id for v in PacienteVisita.query.filter(
            PacienteVisita.tenant_id == tenant_id,
            PacienteVisita.ingreso_id.isnot(None),
        )
    }

    # Una visita por GRUPO (visita_uid), no por renglón: llamar a
    # sincronizar_visita_ingreso por cada ingreso deja que ella misma se
    # encargue de encontrar/reancarlar la visita del grupo por cualquiera de
    # sus hermanos, así que basta con no repetir el mismo grupo dos veces en
    # esta pasada. hermanos_de_visita ya devuelve [ingreso] cuando
    # visita_uid es NULL, así que un ingreso suelto sigue siendo su propio
    # grupo de uno — eso preserva el comportamiento previo para el caso sin
    # agrupar.
    visitas_creadas = 0
    grupos_vistos = set()
    for i in ingresos:
        i.paciente_id = paciente.id
        clave_grupo = i.visita_uid or ("__ingreso__", i.id)
        if clave_grupo in grupos_vistos:
            continue
        grupos_vistos.add(clave_grupo)

        hermanos = hermanos_de_visita(i)
        ya_tenia_visita = any(h.id in con_visita for h in hermanos)
        sincronizar_visita_ingreso(i)
        if not ya_tenia_visita:
            visitas_creadas += 1

    db.session.commit()
    return {
        "paciente_id": paciente.id,
        "ingresos_vinculados": len(ingresos),
        "visitas_creadas": visitas_creadas,
    }
