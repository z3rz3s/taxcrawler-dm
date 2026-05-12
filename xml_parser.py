"""
xml_parser.py
-------------
Parseo de archivos CFDI XML (version 4.0 del SAT).

Extrae los campos fiscales exactos de cada comprobante:
  UUID, Fecha, RFC/Nombre Emisor y Receptor, Subtotal, Total, Moneda,
  Tipo de Comprobante, IVA Trasladado 16%, IVA Retenido, ISR Retenido.

Manejo especial por tipo:
  I / E : impuestos en cfdi:Impuestos del Comprobante
  P     : montos reales en pago20:Totales del complemento
  N     : nomina — se registra como tal, impuestos generalmente 0
"""

import sys
from datetime import datetime
from pathlib import Path

_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from lxml import etree

from config import log

# ---------------------------------------------------------------------------
# Namespaces CFDI
# ---------------------------------------------------------------------------
_NS_CFDI  = "http://www.sat.gob.mx/cfd/4"
_NS_TFD   = "http://www.sat.gob.mx/TimbreFiscalDigital"
_NS_P20   = "http://www.sat.gob.mx/Pagos20"

TIPO_LABEL = {
    "I": "Ingreso",
    "E": "Egreso",
    "P": "Pago",
    "N": "Nomina",
    "T": "Traslado",
}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _attr(element, name: str, default: str = "") -> str:
    return element.get(name, default) if element is not None else default


def _float(value) -> float:
    try:
        return float(str(value).replace(",", "").strip() or "0")
    except (ValueError, TypeError):
        return 0.0


def _impuestos_comprobante(root) -> tuple[float, float, float]:
    """
    Lee IVA trasladado 16%, IVA retenido e ISR retenido del nodo
    cfdi:Impuestos del Comprobante.
    Retorna (iva_16, iva_ret, isr_ret).
    """
    iva_16  = 0.0
    iva_ret = 0.0
    isr_ret = 0.0

    imp = root.find(f"{{{_NS_CFDI}}}Impuestos")
    if imp is None:
        return iva_16, iva_ret, isr_ret

    # Traslados
    tras = imp.find(f"{{{_NS_CFDI}}}Traslados")
    if tras is not None:
        for t in tras.findall(f"{{{_NS_CFDI}}}Traslado"):
            if _attr(t, "Impuesto") != "002":
                continue
            try:
                tasa = float(_attr(t, "TasaOCuota", "0"))
            except ValueError:
                tasa = 0.0
            if abs(tasa - 0.16) < 1e-6:
                iva_16 += _float(_attr(t, "Importe"))

    # Retenciones
    reten = imp.find(f"{{{_NS_CFDI}}}Retenciones")
    if reten is not None:
        for r in reten.findall(f"{{{_NS_CFDI}}}Retencion"):
            code    = _attr(r, "Impuesto")
            importe = _float(_attr(r, "Importe"))
            if code == "002":
                iva_ret += importe
            elif code == "001":
                isr_ret += importe

    return iva_16, iva_ret, isr_ret


def _impuestos_pago(comp) -> tuple[float, float, float, float]:
    """
    Lee los totales del complemento pago20:Pagos.
    Retorna (monto_total, iva_16, iva_ret, isr_ret).
    """
    if comp is None:
        return 0.0, 0.0, 0.0, 0.0

    pagos = comp.find(f"{{{_NS_P20}}}Pagos")
    if pagos is None:
        return 0.0, 0.0, 0.0, 0.0

    tots = pagos.find(f"{{{_NS_P20}}}Totales")
    if tots is None:
        return 0.0, 0.0, 0.0, 0.0

    monto   = _float(_attr(tots, "MontoTotalPagos"))
    iva_16  = _float(_attr(tots, "TotalTrasladosImpuestoIVA16"))
    iva_ret = _float(_attr(tots, "TotalRetencionesImpuestoIVA"))
    isr_ret = _float(_attr(tots, "TotalRetencionesImpuestoISR"))
    return monto, iva_16, iva_ret, isr_ret


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------

def parsear_cfdi(xml_path: Path) -> dict | None:
    """
    Parsea un archivo XML CFDI y retorna un dict con los campos fiscales.

    Campos retornados:
      uuid, fecha (date), rfc_emisor, nombre_emisor, rfc_receptor,
      subtotal, iva_16, iva_ret, isr_ret, total, moneda, tipo, tipo_label

    Retorna None si el archivo no es un CFDI valido o no se puede parsear.
    """
    try:
        tree = etree.parse(str(xml_path))
        root = tree.getroot()
    except Exception as e:
        log.warning(f"  ! No se pudo parsear {xml_path.name}: {e}")
        return None

    # Verificar que sea un Comprobante CFDI
    if _NS_CFDI not in (root.tag or ""):
        log.warning(f"  ! Namespace CFDI no reconocido en {xml_path.name}")
        return None

    tipo     = _attr(root, "TipoDeComprobante")
    moneda   = _attr(root, "Moneda")
    subtotal = _float(_attr(root, "SubTotal"))
    total    = _float(_attr(root, "Total"))

    # Emisor y receptor
    emisor   = root.find(f"{{{_NS_CFDI}}}Emisor")
    receptor = root.find(f"{{{_NS_CFDI}}}Receptor")

    rfc_emisor    = _attr(emisor,   "Rfc")
    nombre_emisor = _attr(emisor,   "Nombre")
    rfc_receptor  = _attr(receptor, "Rfc")

    # UUID desde el Timbre Fiscal Digital
    uuid = ""
    comp = root.find(f"{{{_NS_CFDI}}}Complemento")
    if comp is not None:
        tfd = comp.find(f"{{{_NS_TFD}}}TimbreFiscalDigital")
        if tfd is not None:
            uuid = _attr(tfd, "UUID").upper()

    # Impuestos — logica diferenciada por tipo
    if tipo == "P":
        monto_p, iva_16, iva_ret, isr_ret = _impuestos_pago(comp)
        if monto_p > 0:
            total    = monto_p
            subtotal = round(total - iva_16, 2)
            if subtotal < 0:
                subtotal = 0.0
    else:
        iva_16, iva_ret, isr_ret = _impuestos_comprobante(root)

    # Fecha de emision
    fecha_str = _attr(root, "Fecha")
    try:
        fecha = datetime.fromisoformat(fecha_str).date() if fecha_str else None
    except ValueError:
        fecha = None

    return {
        "uuid":          uuid,
        "fecha":         fecha,
        "rfc_emisor":    rfc_emisor,
        "nombre_emisor": nombre_emisor,
        "rfc_receptor":  rfc_receptor,
        "subtotal":      round(subtotal, 2),
        "iva_16":        round(iva_16,   2),
        "iva_ret":       round(iva_ret,  2),
        "isr_ret":       round(isr_ret,  2),
        "total":         round(total,    2),
        "moneda":        moneda,
        "tipo":          tipo,
        "tipo_label":    TIPO_LABEL.get(tipo, tipo),
    }


def parsear_directorio(cfdi_dir: Path) -> list[dict]:
    """
    Escanea cfdi_dir recursivamente y parsea todos los XMLs CFDI encontrados.
    Retorna lista de dicts ordenada por fecha de emision.
    Omite XMLs que no puedan parsearse (se loguean como warnings).
    """
    xml_files = sorted(cfdi_dir.rglob("*.xml"))
    if not xml_files:
        log.warning(f"No se encontraron XMLs en: {cfdi_dir}")
        return []

    log.info(f"Parseando {len(xml_files)} XML(s) en: {cfdi_dir}")
    registros = []
    errores   = 0

    for path in xml_files:
        rec = parsear_cfdi(path)
        if rec is None:
            errores += 1
        else:
            registros.append(rec)

    registros.sort(key=lambda r: r["fecha"] or __import__("datetime").date.min)

    log.info(f"  Parseados: {len(registros)} validos, {errores} con error")
    return registros


def agrupar_por_mes(registros: list[dict]) -> dict[str, list[dict]]:
    """
    Agrupa una lista de registros CFDI por mes (clave YYYY-MM).
    Usa la fecha del atributo Fecha del comprobante.
    """
    grupos: dict[str, list[dict]] = {}
    for r in registros:
        clave = r["fecha"].strftime("%Y-%m") if r["fecha"] else "0000-00"
        grupos.setdefault(clave, []).append(r)
    return grupos
