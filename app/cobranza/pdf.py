"""Generación de PDFs de cotización y estado de cuenta."""
import re
import unicodedata

from flask import render_template


def _sanitizar(texto):
    plano = unicodedata.normalize("NFKD", texto or "")
    plano = plano.encode("ascii", "ignore").decode("ascii")
    plano = re.sub(r"[^A-Za-z0-9]+", "-", plano)
    return plano.strip("-")


def nombre_archivo(cot, sufijo=""):
    principal = max(cot.conceptos, key=lambda c: c.importe, default=None)
    concepto = _sanitizar(
        principal.descripcion if principal else "Cotizacion",
    )
    paciente = _sanitizar(
        cot.paciente.nombre if cot.paciente else "Paciente",
    )
    partes = [
        parte for parte in (_sanitizar(sufijo), concepto, paciente) if parte
    ]
    return "-".join(partes) + ".pdf"


def _contexto_clinica(cot):
    from app.auth.models import Tenant
    from app.configuracion.logo import logo_b64, logo_bytes, logo_mime
    from app.extensions import db
    from app.facturacion.models import ConfiguracionFiscal, Sucursal

    fiscal = ConfiguracionFiscal.query.filter_by(
        tenant_id=cot.tenant_id,
    ).first()
    tenant = db.session.get(Tenant, cot.tenant_id)
    sucursal = None
    if cot.sucursal_id:
        sucursal = Sucursal.query.filter_by(
            id=cot.sucursal_id, tenant_id=cot.tenant_id,
        ).first()

    logo_data_uri = None
    crudo = logo_bytes(cot.tenant_id)
    if crudo:
        logo_data_uri = (
            f"data:{logo_mime(crudo)};base64,{logo_b64(cot.tenant_id)}"
        )
    return {
        "clinica_nombre": (
            getattr(fiscal, "razon_social", None)
            or (tenant.name if tenant else "")
            or "Consultorio"
        ),
        "logo": logo_data_uri,
        "sucursal": sucursal,
    }


def _render_pdf(plantilla, **contexto):
    import weasyprint
    html = render_template(plantilla, **contexto)
    return weasyprint.HTML(string=html).write_pdf()


def _filas_cotizacion(cot):
    if cot.programados:
        return [
            {
                "numero": p.numero,
                "etiqueta": (
                    "Anticipo" if p.numero == 0 else f"Pago {p.numero}"
                ),
                "fecha": p.fecha_vencimiento,
                "monto": p.monto_programado,
            }
            for p in sorted(cot.programados, key=lambda p: p.numero)
        ]

    if not cot.fecha_primer_pago:
        return []
    from app.cobranza.calculo import PlanInvalido, calcular_plan
    try:
        calculadas = calcular_plan(
            total=cot.total,
            anticipo=cot.anticipo,
            frecuencia=cot.frecuencia,
            fecha_primer_pago=cot.fecha_primer_pago,
            fecha_anticipo=cot.fecha,
            num_parcialidades=(
                cot.num_parcialidades
                if cot.monto_parcialidad is None else None
            ),
            monto_parcialidad=cot.monto_parcialidad,
        )
    except PlanInvalido:
        return []
    return [
        {
            "numero": fila["numero"],
            "etiqueta": (
                "Anticipo"
                if fila["numero"] == 0
                else f"Pago {fila['numero']}"
            ),
            "fecha": fila["fecha_vencimiento"],
            "monto": fila["monto"],
        }
        for fila in calculadas
    ]


def pdf_cotizacion(cot):
    return _render_pdf(
        "cobranza/_pdf_cotizacion.html",
        cot=cot,
        filas=_filas_cotizacion(cot),
        **_contexto_clinica(cot),
    )


def pdf_estado_cuenta(cot, datos):
    return _render_pdf(
        "cobranza/_pdf_estado_cuenta.html",
        cot=cot,
        datos=datos,
        **_contexto_clinica(cot),
    )
