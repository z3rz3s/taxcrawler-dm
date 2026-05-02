"""
metadata_parser.py
------------------
Parseo de archivos TXT de Metadata del SAT, filtros de CFDIs
y generacion de resumen legible para humanos.

Columnas del Metadata SAT (separadas por ~):
  UUID ~ RfcEmisor ~ NombreEmisor ~ RfcReceptor ~ NombreReceptor ~ PacCertificado
  ~ FechaEmision ~ FechaCertificacionSat ~ Monto ~ EfectoComprobante
  ~ Estatus ~ FechaCancelacion
"""

from calendar import monthrange
from datetime import date
from pathlib import Path

from config import MESES_ES, log


# ===========================================================================
# Columnas del Metadata SAT — indices de referencia
# ===========================================================================
COL_UUID             = 0
COL_RFC_EMISOR       = 1
COL_NOMBRE_EMISOR    = 2
COL_RFC_RECEPTOR     = 3
COL_NOMBRE_RECEPTOR  = 4
COL_FECHA_EMISION    = 6
COL_MONTO            = 8
COL_TIPO             = 9   # I=Ingreso, E=Egreso, P=Pago, N=Nomina
COL_ESTATUS          = 10  # '' = vigente, 'Cancelado' = cancelado


# ===========================================================================
# Generacion de periodos mensuales
# ===========================================================================

def generate_monthly_periods(start: date, end: date) -> list[tuple[date, date]]:
    """
    Divide un rango en periodos de un mes cada uno.
    Usado en modo Metadata para logs granulares y manejo de meses vacios (5004).
    """
    periods = []
    current = start.replace(day=1)

    while current <= end:
        last_day    = monthrange(current.year, current.month)[1]
        month_start = max(current, start)
        month_end   = min(date(current.year, current.month, last_day), end)
        periods.append((month_start, month_end))

        current = date(current.year + 1, 1, 1) if current.month == 12 \
                  else date(current.year, current.month + 1, 1)

    return periods


# ===========================================================================
# Parseo de lineas de Metadata
# ===========================================================================

def parse_metadata_line(line: str) -> dict | None:
    """
    Parsea una linea del TXT de Metadata separada por ~.
    Retorna un dict con los campos relevantes, o None si la linea es invalida.
    """
    cols = line.split("~")
    if len(cols) < 11:
        return None

    try:
        monto = float(cols[COL_MONTO].replace(",", "").strip()) \
                if cols[COL_MONTO].strip() else 0.0
    except ValueError:
        monto = 0.0

    return {
        "uuid":           cols[COL_UUID].strip(),
        "rfc_emisor":     cols[COL_RFC_EMISOR].strip(),
        "nombre_emisor":  cols[COL_NOMBRE_EMISOR].strip(),
        "rfc_receptor":   cols[COL_RFC_RECEPTOR].strip(),
        "nombre_receptor":cols[COL_NOMBRE_RECEPTOR].strip(),
        "fecha_emision":  cols[COL_FECHA_EMISION].strip(),
        "monto":          monto,
        "tipo":           cols[COL_TIPO].strip(),      # I, E, P, N
        "estatus":        cols[COL_ESTATUS].strip(),   # '' o 'Cancelado'
    }


def read_metadata_file(path: Path) -> list[dict]:
    """
    Lee un archivo TXT de Metadata y retorna una lista de dicts por CFDI.
    Ignora la primera linea (encabezado) y las lineas invalidas.
    Excluye automaticamente los CFDIs cancelados.
    """
    records = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        # La primera linea es encabezado — ignorar
        for line in lines[1:]:
            if not line.strip():
                continue
            record = parse_metadata_line(line)
            if record is None:
                continue
            # Excluir cancelados
            if record["estatus"].lower() == "cancelado":
                continue
            records.append(record)
    except Exception as e:
        log.warning(f"  ! No se pudo leer: {path.name}. Causa: {e}")
    return records


# ===========================================================================
# Filtros de CFDIs por tipo y rol del RFC
# ===========================================================================

def filter_ingresos(records: list[dict], rfc: str) -> list[dict]:
    """
    Filtra CFDIs de ingresos: el RFC es emisor y el tipo es I (Ingreso).
    Excluye complementos de pago (P), nomina (N) y egresos (E).
    """
    rfc = rfc.upper()
    return [
        r for r in records
        if r["rfc_emisor"].upper() == rfc
        and r["tipo"].upper() == "I"
    ]


def filter_gastos(records: list[dict], rfc: str) -> list[dict]:
    """
    Filtra CFDIs de gastos: el RFC es receptor y el tipo es I (Ingreso).
    Son las facturas que proveedores emitieron al cliente.
    """
    rfc = rfc.upper()
    return [
        r for r in records
        if r["rfc_receptor"].upper() == rfc
        and r["tipo"].upper() == "I"
    ]


def filter_pagos(records: list[dict], rfc: str) -> list[dict]:
    """
    Filtra complementos de pago (Tipo P): el RFC es receptor.
    Se muestran como referencia — no suman al total de gastos porque
    el gasto ya fue registrado con la factura original.
    """
    rfc = rfc.upper()
    return [
        r for r in records
        if r["rfc_receptor"].upper() == rfc
        and r["tipo"].upper() == "P"
    ]


# ===========================================================================
# Resumen legible para humanos (logs al final del proceso Metadata)
# ===========================================================================

def generate_metadata_summary(files: list[Path], params: dict) -> list[str]:
    """
    Lee los TXTs de Metadata descargados y genera un resumen legible.
    Incluye total de CFDIs, monto acumulado, desglose por mes y top emisores.
    """
    if not files:
        return ["  Sin archivos de Metadata para resumir."]

    total_cfdis = 0
    total_monto = 0.0
    by_month: dict[str, dict] = {}
    issuers:  dict[str, int]  = {}

    for path in files:
        if path.suffix.lower() != ".txt":
            continue

        records = read_metadata_file(path)

        # Extraer YYYY-MM del nombre del archivo (formato YYYY-MM-RFC.txt)
        parts     = path.stem.split("-")
        year      = parts[0] if len(parts) >= 1 else "????"
        month_num = parts[1] if len(parts) >= 2 else "??"
        month_key = f"{year}-{month_num}"
        month_lbl = f"{MESES_ES.get(month_num, month_num)} {year}"

        month_count = 0
        month_total = 0.0

        for r in records:
            month_count += 1
            total_cfdis += 1
            month_total += r["monto"]
            total_monto += r["monto"]

            issuer_key = f"{r['rfc_emisor']} — {r['nombre_emisor']}"
            issuers[issuer_key] = issuers.get(issuer_key, 0) + 1

        by_month[month_key] = {"label": month_lbl, "count": month_count, "total": month_total}

    if total_cfdis == 0:
        return ["  No se encontraron registros legibles en los archivos de Metadata."]

    tipo_lbl = "emitidas" if params["tipo"] == "emitidos" else "recibidas"
    lines: list[str] = []

    lines.append(f"  El RFC {params['rfc']} tiene {total_cfdis} factura(s) {tipo_lbl}")
    lines.append(f"  en el periodo {params['inicio']} -> {params['fin']}.")
    lines.append(f"  Monto total acumulado: ${total_monto:,.2f} MXN")
    lines.append("")
    lines.append("  Desglose por mes:")

    for key in sorted(by_month.keys()):
        info = by_month[key]
        lines.append(
            f"    * {info['label']:<20} {info['count']:>5} CFDI(s)   "
            f"${info['total']:>14,.2f} MXN"
        )

    if issuers:
        top = sorted(issuers.items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append("")
        lines.append("  Top 5 emisores/receptores mas frecuentes:")
        for name, count in top:
            lines.append(f"    * {count:>4}x  {name}")

    return lines