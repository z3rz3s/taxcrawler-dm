"""
excel_generator.py
------------------
Generacion del Excel de Papel de Trabajo contable.
Replica el formato del archivo de referencia para multiples clientes.

Siempre genera exactamente 6 hojas en el mismo orden:
  1. ingresos        — CFDIs emitidos agrupados por mes
  2. gastos          — CFDIs recibidos agrupados por mes
  3. Impuestos       — calculo IVA/ISR por mes + saldo acumulado IVA
  4. Papel de Trabajo — resumen ejecutivo ISR e IVA por mes
  5. INGRESOS historico — tabla anual con ingresos por mes
  6. Calculos        — tabla ISR RESICO

Uso normal: un mes → 6 hojas limpias identicas al archivo de referencia.
Uso multi-mes: mismo formato, bloques apilados por mes dentro de cada hoja.

Regimenes soportados:
  resico : tasa progresiva simplificada (implementado)
  pfae   : TODO — pendiente de definir el calculo con el equipo contable

Fuente de tabla ISR (prioridad):
  1. TABLA_ISR_RESICO_DEFAULT en config.py
  2. Variable de entorno TABLA_ISR_PATH con ruta a CSV
  3. Parametro CLI --tabla-isr con ruta a CSV
"""

import sys
from datetime import date, datetime
from pathlib import Path

_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from config import MESES_ES, log
from metadata_parser import (
    generate_monthly_periods,
    group_records_by_month,
)
from xml_parser import agrupar_por_mes, parsear_directorio


# ===========================================================================
# Estilos comunes
# ===========================================================================

FONT_TITLE    = Font(name="Arial", bold=True, size=11)
FONT_HEADER   = Font(name="Arial", bold=True, size=9, color="FFFFFF")
FONT_NORMAL   = Font(name="Arial", size=9)
FONT_BOLD     = Font(name="Arial", bold=True, size=9)
FONT_DESPACHO = Font(name="Arial", bold=True, size=10)
FONT_MES      = Font(name="Arial", bold=True, size=9, color="FFFFFF")
FONT_NOTE     = Font(name="Arial", italic=True, size=8, color="7F7F7F")

FILL_HEADER  = PatternFill("solid", start_color="2F5496")
FILL_MES     = PatternFill("solid", start_color="4472C4")
FILL_TOTAL   = PatternFill("solid", start_color="D9E1F2")
FILL_INGRESO = PatternFill("solid", start_color="E2EFDA")
FILL_GASTO   = PatternFill("solid", start_color="FCE4D6")
FILL_PAGO    = PatternFill("solid", start_color="FFF2CC")

THIN        = Side(style="thin", color="BFBFBF")
BORDER_THIN = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_RIGHT  = Alignment(horizontal="right",  vertical="center")
ALIGN_LEFT   = Alignment(horizontal="left",   vertical="center")

FMT_CURRENCY = '#,##0.00'
FMT_PERCENT  = '0.00%'


# ===========================================================================
# Helpers de formato
# ===========================================================================

def _set_col_widths(ws, widths: dict) -> None:
    """Asigna anchos de columna. widths = {'A': 20, 'B': 15, ...}"""
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def _header_row(ws, row: int, cols: list[str], fill=None) -> None:
    """Escribe una fila de encabezado con estilo."""
    fill = fill or FILL_HEADER
    for i, label in enumerate(cols, 1):
        cell           = ws.cell(row=row, column=i, value=label)
        cell.font      = FONT_HEADER
        cell.fill      = fill
        cell.alignment = ALIGN_CENTER
        cell.border    = BORDER_THIN


def _month_separator_row(ws, row: int, label: str, n_cols: int) -> None:
    """
    Escribe una fila separadora de mes que abarca todas las columnas.
    Usada para separar visualmente bloques de meses en hojas consolidadas.
    """
    cell           = ws.cell(row=row, column=1, value=label)
    cell.font      = FONT_MES
    cell.fill      = FILL_MES
    cell.alignment = ALIGN_LEFT
    cell.border    = BORDER_THIN
    for col in range(2, n_cols + 1):
        c           = ws.cell(row=row, column=col, value=None)
        c.fill      = FILL_MES
        c.border    = BORDER_THIN


def _data_row(ws, row: int, values: list, bold: bool = False,
              fill=None, fmt_map: dict | None = None) -> None:
    """Escribe una fila de datos con estilo opcional."""
    for i, val in enumerate(values, 1):
        cell        = ws.cell(row=row, column=i, value=val)
        cell.font   = FONT_BOLD if bold else FONT_NORMAL
        cell.border = BORDER_THIN
        if fill:
            cell.fill = fill
        if fmt_map and i in fmt_map:
            cell.number_format = fmt_map[i]
        if isinstance(val, (int, float)):
            cell.alignment = ALIGN_RIGHT
        else:
            cell.alignment = ALIGN_LEFT


def _labeled_value(ws, row: int, col_label: int, label: str,
                   col_value: int, value,
                   bold_label: bool = True,
                   fmt: str | None = None,
                   fill=None) -> None:
    """Escribe un par etiqueta / valor en celdas separadas."""
    lbl           = ws.cell(row=row, column=col_label, value=label)
    lbl.font      = FONT_BOLD if bold_label else FONT_NORMAL
    lbl.alignment = ALIGN_LEFT

    val           = ws.cell(row=row, column=col_value, value=value)
    val.font      = FONT_NORMAL
    val.alignment = ALIGN_RIGHT
    if fmt:
        val.number_format = fmt
    if fill:
        val.fill = fill


# ===========================================================================
# Calculos de impuestos
# ===========================================================================

def _lookup_isr(income: float, tabla: list[tuple]) -> dict:
    """
    Calcula el ISR mensual usando la tabla de tarifas RESICO.
    Retorna un dict con los componentes del calculo.

    TODO: cuando se defina el regimen PFAE, agregar funcion
    _lookup_isr_pfae(income, tabla) con la logica correspondiente.
    """
    for (lim_inf, lim_sup, cuota, tasa) in tabla:
        if lim_inf <= income <= lim_sup:
            base = income - lim_inf
            return {
                "ingreso":         income,
                "limite_inferior": lim_inf,
                "base":            base,
                "tasa":            tasa,
                "resultado":       base * tasa,
                "cuota_fija":      cuota,
                "isr_calculado":   base * tasa + cuota,
            }
    lim_inf, _, cuota, tasa = tabla[-1]
    base = income - lim_inf
    return {
        "ingreso":         income,
        "limite_inferior": lim_inf,
        "base":            base,
        "tasa":            tasa,
        "resultado":       base * tasa,
        "cuota_fija":      cuota,
        "isr_calculado":   base * tasa + cuota,
    }


def _build_month_calcs(income_recs: list[dict], expense_recs: list[dict],
                       isr_table: list[tuple],
                       xml_income: list[dict] | None = None,
                       xml_expense: list[dict] | None = None) -> dict:
    """
    Calcula IVA e ISR para un mes dado.

    Si se proporcionan xml_income / xml_expense (registros de xml_parser),
    los valores de IVA e ISR se toman directamente del CFDI.
    Si no, se estiman a 16% del total (fallback para modo solo Metadata).
    """
    total_ingresos = sum(r["monto"] for r in income_recs)
    total_gastos   = sum(r["monto"] for r in expense_recs)

    if xml_income is not None:
        iva_trasladado = sum(r["iva_16"]  for r in xml_income)
        isr_retenido   = sum(r["isr_ret"] for r in xml_income)
    else:
        iva_trasladado = total_ingresos * 0.16
        isr_retenido   = 0.0

    if xml_expense is not None:
        iva_acreditable = sum(r["iva_16"] for r in xml_expense)
    else:
        iva_acreditable = total_gastos * 0.16

    iva_saldo     = iva_trasladado - iva_acreditable
    isr_data      = _lookup_isr(total_ingresos, isr_table)
    isr_por_pagar = max(0.0, total_ingresos * 0.025 - isr_retenido)

    return {
        "total_ingresos":  total_ingresos,
        "total_gastos":    total_gastos,
        "iva_trasladado":  iva_trasladado,
        "iva_acreditable": iva_acreditable,
        "iva_saldo":       iva_saldo,
        "isr_retenido":    isr_retenido,
        "isr_calculado":   isr_data["isr_calculado"],
        "isr_por_pagar":   isr_por_pagar,
        "isr_data":        isr_data,
    }


# ===========================================================================
# Hoja 1 — ingresos
# ===========================================================================

COLS_INGRESOS = [
    "Periodo", "UUID", "RFC Emisor", "Nombre Emisor",
    "RFC Receptor", "Nombre Receptor", "Fecha Emision", "Monto", "Tipo",
]

def _write_ingresos(ws, grouped: dict[str, list[dict]]) -> None:
    """
    Escribe la hoja de ingresos con un bloque por mes.
    Cada bloque tiene: fila separadora de mes, encabezados, datos, subtotal.
    Si no hay ingresos en ningun mes, escribe una hoja vacia con encabezados.
    """
    ws.cell(row=1, column=1, value="INGRESOS").font = FONT_TITLE
    current_row = 2

    if not grouped:
        _header_row(ws, current_row, COLS_INGRESOS)
        ws.cell(row=current_row + 1, column=1,
                value="Sin ingresos registrados en el periodo.").font = FONT_NOTE
        _set_col_widths(ws, {"A": 12, "B": 38, "C": 18, "D": 35,
                              "E": 18, "F": 35, "G": 20, "H": 16, "I": 10})
        log.info("    Hoja 'ingresos': sin registros.")
        return

    total_general = 0.0
    for month_key in sorted(grouped.keys()):
        records   = grouped[month_key]
        parts     = month_key.split("-")
        month_num = parts[1] if len(parts) >= 2 else "??"
        month_lbl = f"{MESES_ES.get(month_num, month_num)} {parts[0]}"

        # Separador de mes
        _month_separator_row(ws, current_row, month_lbl, len(COLS_INGRESOS))
        current_row += 1

        # Encabezados
        _header_row(ws, current_row, COLS_INGRESOS)
        current_row += 1

        # Datos
        subtotal = 0.0
        fmt_map  = {8: FMT_CURRENCY}
        for r in records:
            _data_row(ws, current_row, [
                month_lbl,
                r["uuid"], r["rfc_emisor"], r["nombre_emisor"],
                r["rfc_receptor"], r["nombre_receptor"],
                r["fecha_emision"], r["monto"], r["tipo"],
            ], fill=FILL_INGRESO, fmt_map=fmt_map)
            subtotal    += r["monto"]
            current_row += 1

        # Subtotal del mes
        ws.cell(row=current_row, column=7, value="SUBTOTAL").font = FONT_BOLD
        sub_cell = ws.cell(row=current_row, column=8, value=subtotal)
        sub_cell.font           = FONT_BOLD
        sub_cell.number_format  = FMT_CURRENCY
        sub_cell.fill           = FILL_TOTAL
        sub_cell.alignment      = ALIGN_RIGHT
        sub_cell.border         = BORDER_THIN
        total_general += subtotal
        current_row   += 2  # espacio entre meses

    # Total general
    ws.cell(row=current_row, column=7, value="TOTAL").font = FONT_BOLD
    tot_cell = ws.cell(row=current_row, column=8, value=total_general)
    tot_cell.font           = FONT_BOLD
    tot_cell.number_format  = FMT_CURRENCY
    tot_cell.fill           = FILL_TOTAL
    tot_cell.alignment      = ALIGN_RIGHT
    tot_cell.border         = BORDER_THIN

    _set_col_widths(ws, {"A": 14, "B": 38, "C": 18, "D": 35,
                          "E": 18, "F": 35, "G": 20, "H": 16, "I": 10})
    log.info(f"    Hoja 'ingresos': {sum(len(v) for v in grouped.values())} "
             f"registros | Total: ${total_general:,.2f}")


# ===========================================================================
# Hoja 2 — gastos
# ===========================================================================

COLS_GASTOS = [
    "Periodo", "UUID", "RFC Emisor", "Nombre Emisor",
    "RFC Receptor", "Nombre Receptor", "Fecha Emision", "Monto", "Tipo",
]

def _write_gastos(ws, grouped_gastos: dict[str, list[dict]],
                  grouped_pagos: dict[str, list[dict]]) -> None:
    """
    Escribe la hoja de gastos con dos secciones por mes:
      1. Facturas de gasto (tipo I, receptor = RFC)
      2. Complementos de pago (tipo P, referencia — no suman)
    """
    ws.cell(row=1, column=1, value="GASTOS").font = FONT_TITLE
    current_row = 2

    all_months = sorted(set(list(grouped_gastos.keys()) + list(grouped_pagos.keys())))

    if not all_months:
        _header_row(ws, current_row, COLS_GASTOS)
        ws.cell(row=current_row + 1, column=1,
                value="Sin gastos registrados en el periodo.").font = FONT_NOTE
        _set_col_widths(ws, {"A": 12, "B": 38, "C": 18, "D": 35,
                              "E": 18, "F": 35, "G": 20, "H": 16, "I": 10})
        log.info("    Hoja 'gastos': sin registros.")
        return

    total_general = 0.0
    for month_key in all_months:
        records_g = grouped_gastos.get(month_key, [])
        records_p = grouped_pagos.get(month_key, [])
        parts     = month_key.split("-")
        month_num = parts[1] if len(parts) >= 2 else "??"
        month_lbl = f"{MESES_ES.get(month_num, month_num)} {parts[0]}"

        # Separador de mes
        _month_separator_row(ws, current_row, month_lbl, len(COLS_GASTOS))
        current_row += 1

        # Encabezados
        _header_row(ws, current_row, COLS_GASTOS)
        current_row += 1

        # Datos de gasto
        subtotal = 0.0
        fmt_map  = {8: FMT_CURRENCY}
        for r in records_g:
            _data_row(ws, current_row, [
                month_lbl,
                r["uuid"], r["rfc_emisor"], r["nombre_emisor"],
                r["rfc_receptor"], r["nombre_receptor"],
                r["fecha_emision"], r["monto"], r["tipo"],
            ], fill=FILL_GASTO, fmt_map=fmt_map)
            subtotal    += r["monto"]
            current_row += 1

        # Subtotal gastos del mes
        ws.cell(row=current_row, column=7, value="SUBTOTAL").font = FONT_BOLD
        sub_cell = ws.cell(row=current_row, column=8, value=subtotal)
        sub_cell.font           = FONT_BOLD
        sub_cell.number_format  = FMT_CURRENCY
        sub_cell.fill           = FILL_TOTAL
        sub_cell.alignment      = ALIGN_RIGHT
        sub_cell.border         = BORDER_THIN
        total_general += subtotal
        current_row   += 1

        # Complementos de pago — seccion de referencia
        if records_p:
            ws.cell(row=current_row, column=1,
                    value="Complementos de pago (referencia — no suman al total)").font = FONT_NOTE
            current_row += 1
            for r in records_p:
                _data_row(ws, current_row, [
                    month_lbl,
                    r["uuid"], r["rfc_emisor"], r["nombre_emisor"],
                    r["rfc_receptor"], r["nombre_receptor"],
                    r["fecha_emision"], r["monto"], r["tipo"],
                ], fill=FILL_PAGO, fmt_map=fmt_map)
                current_row += 1

        current_row += 1  # espacio entre meses

    # Total general
    ws.cell(row=current_row, column=7, value="TOTAL").font = FONT_BOLD
    tot_cell = ws.cell(row=current_row, column=8, value=total_general)
    tot_cell.font           = FONT_BOLD
    tot_cell.number_format  = FMT_CURRENCY
    tot_cell.fill           = FILL_TOTAL
    tot_cell.alignment      = ALIGN_RIGHT
    tot_cell.border         = BORDER_THIN

    _set_col_widths(ws, {"A": 14, "B": 38, "C": 18, "D": 35,
                          "E": 18, "F": 35, "G": 20, "H": 16, "I": 10})
    log.info(f"    Hoja 'gastos': {sum(len(v) for v in grouped_gastos.values())} "
             f"registros | Total: ${total_general:,.2f}")


# ===========================================================================
# Hoja 3 — Impuestos
# ===========================================================================

def _write_impuestos(ws, month_calcs: list[dict]) -> None:
    """
    Escribe la hoja de Impuestos con dos secciones:
      Izquierda (cols A-D): calculo IVA/ISR por mes apilado
      Derecha (cols F-J):   saldo acumulado de IVA mes a mes (como en referencia)
    """
    # --- Encabezado izquierdo ---
    ws.cell(row=1, column=1, value="CALCULO DE IMPUESTOS").font = FONT_TITLE

    current_row = 2
    for mc in month_calcs:
        month_lbl = mc["label"]

        ws.cell(row=current_row, column=1, value=month_lbl).font = FONT_BOLD
        current_row += 1

        # IVA
        ws.cell(row=current_row, column=1, value="Ingresos").font = FONT_BOLD
        current_row += 1
        _labeled_value(ws, current_row, 1, month_lbl, 4,
                        mc["total_ingresos"], bold_label=False, fmt=FMT_CURRENCY)
        current_row += 1
        _labeled_value(ws, current_row, 1, "IVA retenido", 4,
                        mc["isr_retenido"], bold_label=False, fmt=FMT_CURRENCY)
        current_row += 1
        _labeled_value(ws, current_row, 1, "IVA a pagar / favor", 4,
                        mc["iva_saldo"], fmt=FMT_CURRENCY)
        current_row += 1

        # Egresos
        ws.cell(row=current_row, column=1, value="Egresos").font = FONT_BOLD
        current_row += 1
        _labeled_value(ws, current_row, 1, f"{month_lbl} 16%", 2,
                        mc["total_gastos"], bold_label=False, fmt=FMT_CURRENCY)
        _labeled_value(ws, current_row, 3, "IVA acreditable", 4,
                        mc["iva_acreditable"], bold_label=False, fmt=FMT_CURRENCY)
        current_row += 1
        _labeled_value(ws, current_row, 1, "IVA neto", 4,
                        mc["iva_saldo"], fmt=FMT_CURRENCY)
        current_row += 2  # espacio entre meses

    # --- Seccion derecha: saldo acumulado IVA ---
    ws.cell(row=2, column=6, value="Saldo acumulado IVA").font = FONT_BOLD
    ws.cell(row=3, column=7, value="a favor").font  = FONT_BOLD
    ws.cell(row=3, column=8, value="por pagar").font = FONT_BOLD
    ws.cell(row=3, column=9, value="acumulado").font = FONT_BOLD

    saldo_acum = 0.0
    for i, mc in enumerate(month_calcs, 4):
        ws.cell(row=i, column=6, value=mc["label"]).font = FONT_NORMAL
        saldo = mc["iva_saldo"]
        if saldo >= 0:
            ws.cell(row=i, column=7, value=saldo).number_format = FMT_CURRENCY
        else:
            ws.cell(row=i, column=8, value=abs(saldo)).number_format = FMT_CURRENCY
        saldo_acum += saldo
        acum_cell = ws.cell(row=i, column=9, value=saldo_acum)
        acum_cell.number_format = FMT_CURRENCY

    _set_col_widths(ws, {"A": 22, "B": 16, "C": 16, "D": 16,
                          "E": 4,  "F": 16, "G": 14, "H": 14, "I": 14})
    log.info(f"    Hoja 'Impuestos': {len(month_calcs)} mes(es) | "
             f"Saldo IVA acumulado: ${saldo_acum:,.2f}")


# ===========================================================================
# Hoja 4 — Papel de Trabajo
# ===========================================================================

def _write_papel(ws, rfc: str, client_name: str, despacho: str,
                 month_calcs: list[dict]) -> None:
    """
    Escribe el Papel de Trabajo replicando el formato del archivo de referencia.
    Izquierda: ISR. Derecha: IVA.
    Un bloque por mes si el rango es multi-mes.
    """
    # Encabezado del despacho
    ws.cell(row=1, column=2, value=despacho).font      = FONT_DESPACHO
    ws.cell(row=1, column=9, value=despacho).font      = FONT_DESPACHO
    ws.cell(row=3, column=2, value="CLIENTE:").font    = FONT_BOLD
    ws.cell(row=3, column=3, value=client_name).font   = FONT_NORMAL
    ws.cell(row=3, column=9, value="CLIENTE:").font    = FONT_BOLD
    ws.cell(row=3, column=10, value=client_name).font  = FONT_NORMAL
    ws.cell(row=4, column=2, value="RFC:").font        = FONT_BOLD
    ws.cell(row=4, column=3, value=rfc).font           = FONT_NORMAL

    current_row = 6
    for mc in month_calcs:
        month_lbl = mc["label"]

        ws.cell(row=current_row, column=2, value="PERIODO:").font  = FONT_BOLD
        ws.cell(row=current_row, column=3, value=month_lbl).font   = FONT_NORMAL
        ws.cell(row=current_row, column=9, value="PERIODO:").font  = FONT_BOLD
        ws.cell(row=current_row, column=10, value=month_lbl).font  = FONT_NORMAL
        current_row += 2

        # --- ISR (izquierda, cols B-F) ---
        _labeled_value(ws, current_row, 2, "INGRESOS DEL MES", 5,
                        mc["total_ingresos"], fmt=FMT_CURRENCY)
        current_row += 1

        _labeled_value(ws, current_row, 2, "TOTAL INGRESOS", 5,
                        mc["total_ingresos"], fmt=FMT_CURRENCY)
        current_row += 1

        _labeled_value(ws, current_row, 2, "TASA APLICABLE (2.5%)", 5,
                        mc["total_ingresos"] * 0.025, fmt=FMT_CURRENCY)
        current_row += 1

        _labeled_value(ws, current_row, 2, "ISR RETENIDO", 5,
                        mc["isr_retenido"], fmt=FMT_CURRENCY)
        current_row += 1

        _labeled_value(ws, current_row, 2, "IMPUESTO POR PAGAR", 5,
                        mc["isr_por_pagar"], fmt=FMT_CURRENCY,
                        fill=FILL_TOTAL)
        current_row += 2

        # --- IVA (derecha, cols I-M) ---
        r_base = current_row - 6
        _labeled_value(ws, r_base,     9, "IVA (A FAVOR) PERIODO ANTERIOR", 13,
                        0.0, bold_label=False, fmt=FMT_CURRENCY)
        _labeled_value(ws, r_base + 1, 9, "IVA TRASLADADO",  13,
                        mc["iva_trasladado"],  bold_label=False, fmt=FMT_CURRENCY)
        _labeled_value(ws, r_base + 2, 9, "IVA RETENIDO",    13,
                        mc["isr_retenido"],    bold_label=False, fmt=FMT_CURRENCY)
        _labeled_value(ws, r_base + 3, 9, "IVA ACREDITABLE", 13,
                        mc["iva_acreditable"], bold_label=False, fmt=FMT_CURRENCY)
        _labeled_value(ws, r_base + 4, 9, "IVA (A FAVOR) / A PAGAR", 13,
                        mc["iva_saldo"], fmt=FMT_CURRENCY, fill=FILL_TOTAL)

        current_row += 2  # espacio entre meses

    # Tabla utilidad/perdida por mes (parte inferior izquierda)
    current_row += 1
    ws.cell(row=current_row, column=2, value="Mes").font         = FONT_BOLD
    ws.cell(row=current_row, column=3, value="Utilidad").font    = FONT_BOLD
    ws.cell(row=current_row, column=4, value="Perdida").font     = FONT_BOLD
    current_row += 1

    for mc in month_calcs:
        ws.cell(row=current_row, column=2, value=mc["label"]).font = FONT_NORMAL
        resultado = mc["total_ingresos"] - mc["total_gastos"]
        if resultado >= 0:
            cell = ws.cell(row=current_row, column=3, value=resultado)
        else:
            cell = ws.cell(row=current_row, column=4, value=abs(resultado))
        cell.number_format = FMT_CURRENCY
        cell.alignment     = ALIGN_RIGHT
        current_row += 1

    _set_col_widths(ws, {
        "A": 3,  "B": 30, "C": 25, "D": 14, "E": 16,
        "F": 3,  "G": 3,  "H": 3,
        "I": 30, "J": 14, "K": 5,  "L": 5,  "M": 16,
    })
    log.info(f"    Hoja 'Papel de Trabajo': {len(month_calcs)} mes(es).")


# ===========================================================================
# Hoja 5 — INGRESOS historico
# ===========================================================================

_MESES_ORDEN = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

def _write_ingresos_historico(ws, rfc: str, year: int,
                               month_calcs: list[dict]) -> None:
    """
    Escribe la hoja de historico anual de ingresos.
    Todos los meses del anio aparecen — los meses con datos tienen valores reales,
    el resto queda en blanco.
    """
    ws.cell(row=1, column=1,
            value=f"INGRESOS {year} — {rfc}").font = FONT_TITLE
    ws.cell(row=2, column=2, value="Ingresos").font    = FONT_BOLD
    ws.cell(row=3, column=2, value="facturados").font  = FONT_BOLD

    # Construir lookup por nombre de mes en minusculas
    calcs_by_mes: dict[str, float] = {}
    for mc in month_calcs:
        # mc["label"] = "Enero 2025", extraer solo el nombre del mes
        nombre_mes = mc["label"].split()[0].lower()
        calcs_by_mes[nombre_mes] = mc["total_ingresos"]

    total = 0.0
    for i, mes in enumerate(_MESES_ORDEN, 4):
        ws.cell(row=i, column=1, value=mes.capitalize()).font = FONT_NORMAL
        if mes in calcs_by_mes:
            val = calcs_by_mes[mes]
            cell = ws.cell(row=i, column=2, value=val)
            cell.number_format = FMT_CURRENCY
            cell.alignment     = ALIGN_RIGHT
            total += val
        # Si no hay datos del mes, la celda queda en blanco

    total_row = 4 + len(_MESES_ORDEN)
    tot_cell = ws.cell(row=total_row, column=2, value=total)
    tot_cell.font           = FONT_BOLD
    tot_cell.number_format  = FMT_CURRENCY
    tot_cell.alignment      = ALIGN_RIGHT
    tot_cell.fill           = FILL_TOTAL
    tot_cell.border         = BORDER_THIN

    _set_col_widths(ws, {"A": 16, "B": 18})
    log.info(f"    Hoja 'INGRESOS historico': {year} | "
             f"Total: ${total:,.2f}")


# ===========================================================================
# Hoja 6 — Calculos (tabla ISR)
# ===========================================================================

def _write_calculos(ws, isr_table: list[tuple]) -> None:
    """
    Escribe la hoja de Calculos con la tabla ISR RESICO.
    Incluye nota para actualizar cuando cambie la legislacion fiscal.
    """
    ws.cell(row=1, column=1, value="TABLA ISR — RESICO").font = FONT_TITLE
    ws.cell(row=2, column=1,
            value="Actualizar cuando cambie la legislacion fiscal.").font = FONT_NOTE

    headers = ["Limite Inferior", "Limite Superior", "Cuota Fija", "Tasa (%)"]
    _header_row(ws, 4, headers)

    for i, (lim_inf, lim_sup, cuota, tasa) in enumerate(isr_table, 5):
        sup_val = "En adelante" if lim_sup >= 999999999 else lim_sup
        for j, val in enumerate([lim_inf, sup_val, cuota, tasa], 1):
            cell           = ws.cell(row=i, column=j, value=val)
            cell.font      = FONT_NORMAL
            cell.border    = BORDER_THIN
            cell.alignment = ALIGN_RIGHT if isinstance(val, (int, float)) else ALIGN_LEFT
            if j in (1, 3):
                cell.number_format = FMT_CURRENCY
            elif j == 4:
                cell.number_format = FMT_PERCENT

    _set_col_widths(ws, {"A": 20, "B": 20, "C": 18, "D": 12})
    log.info(f"    Hoja 'Calculos': {len(isr_table)} rangos ISR.")


# ===========================================================================
# Funcion principal — generate_excel
# ===========================================================================

def generate_excel(
    rfc: str,
    start_date: date,
    end_date: date,
    income_files: list[Path],
    expense_files: list[Path],
    output_dir: Path,
    isr_table: list[tuple],
    despacho: str,
    regimen: str = "resico",
    acumulado_anual: bool = False,
    excel_mode: str = "completo",
) -> Path:
    """
    Genera el Excel de Papel de Trabajo con exactamente 6 hojas fijas.

    Parametros:
      rfc            : RFC del contribuyente
      start_date     : inicio del periodo
      end_date       : fin del periodo
      income_files   : lista de TXTs de Metadata de ingresos (emitidos)
      expense_files  : lista de TXTs de Metadata de gastos (recibidos)
      output_dir     : carpeta base de salida (results_RFC/)
      isr_table      : tabla ISR como lista de tuplas
      despacho       : nombre del despacho contable
      regimen        : 'resico' (implementado) | 'pfae' (TODO)
      acumulado_anual: reservado para Opcion B — actualmente no usado
      excel_mode     : reservado para modos futuros — actualmente genera completo

    Retorna la ruta al archivo Excel generado.
    """
    if regimen != "resico":
        # TODO: implementar calculo PFAE cuando el equipo contable lo defina
        log.warning(f"  ! Regimen '{regimen}' no implementado. Usando RESICO.")

    log.info(f"Generando Excel | RFC: {rfc} | Periodo: {start_date} -> {end_date}")

    # Nombre del archivo
    if start_date.replace(day=1) == end_date.replace(day=1):
        filename = f"{rfc}_{start_date.strftime('%Y-%m')}.xlsx"
    else:
        filename = f"{rfc}_{start_date.strftime('%Y-%m')}__{end_date.strftime('%Y-%m')}.xlsx"

    output_dir.mkdir(parents=True, exist_ok=True)
    excel_path = output_dir / filename

    # Agrupar registros por mes
    log.info("  Agrupando registros por mes...")
    grouped_ingresos = group_records_by_month(income_files,  rfc, "ingresos")
    grouped_gastos   = group_records_by_month(expense_files, rfc, "gastos")
    grouped_pagos    = group_records_by_month(expense_files, rfc, "pagos")

    # Calculos por mes en orden cronologico
    periods    = generate_monthly_periods(start_date, end_date)
    month_calcs: list[dict] = []

    for month_start, _ in periods:
        month_key = month_start.strftime("%Y-%m")
        month_num = month_start.strftime("%m")
        month_lbl = f"{MESES_ES[month_num]} {month_start.year}"

        income_recs  = grouped_ingresos.get(month_key, [])
        expense_recs = grouped_gastos.get(month_key, [])
        calcs        = _build_month_calcs(income_recs, expense_recs, isr_table)
        calcs["label"]     = month_lbl
        calcs["month_key"] = month_key
        month_calcs.append(calcs)

    # Nombre del cliente — primer registro de ingresos o gastos
    client_name = rfc
    for recs in grouped_ingresos.values():
        if recs:
            client_name = recs[0]["nombre_emisor"]
            break
    if client_name == rfc:
        for recs in grouped_gastos.values():
            if recs:
                client_name = recs[0]["nombre_receptor"]
                break

    # Anio predominante del rango para la hoja historico
    year = start_date.year

    # Crear workbook con exactamente 6 hojas
    wb = Workbook()
    wb.remove(wb.active)

    log.info("  Escribiendo hojas...")

    ws1 = wb.create_sheet("ingresos")
    _write_ingresos(ws1, grouped_ingresos)

    ws2 = wb.create_sheet("gastos")
    _write_gastos(ws2, grouped_gastos, grouped_pagos)

    ws3 = wb.create_sheet("Impuestos")
    _write_impuestos(ws3, month_calcs)

    ws4 = wb.create_sheet("Papel de Trabajo")
    _write_papel(ws4, rfc, client_name, despacho, month_calcs)

    ws5 = wb.create_sheet(f"INGRESOS {year}")
    _write_ingresos_historico(ws5, rfc, year, month_calcs)

    ws6 = wb.create_sheet("Calculos")
    _write_calculos(ws6, isr_table)

    wb.save(excel_path)
    log.info(f"  Excel guardado: {excel_path}")
    log.info(f"  Hojas: {wb.sheetnames}")

    return excel_path


# ===========================================================================
# Papel de trabajo desde XMLs CFDI — una hoja por mes, datos exactos
# ===========================================================================

_COLS_PT = [
    ("UUID (Folio Fiscal)",    38),
    ("Fecha",                  12),
    ("RFC Emisor",             16),
    ("Nombre Emisor",          35),
    ("RFC Receptor",           16),
    ("Subtotal",               16),
    ("IVA Trasladado 16%",     18),
    ("IVA Retenido",           14),
    ("ISR Retenido",           14),
    ("Total",                  16),
    ("Moneda",                  8),
    ("Tipo",                   12),
]

# Indices de columnas numericas (1-based) en _COLS_PT
_COLS_NUM_PT = {6, 7, 8, 9, 10}


def _write_hoja_mes(ws, filas: list[dict], mes_label: str) -> None:
    """Escribe encabezados, datos y fila de totales en una hoja mensual."""
    from openpyxl.utils import get_column_letter

    # --- Encabezados ---
    for col_i, (titulo, ancho) in enumerate(_COLS_PT, start=1):
        cell           = ws.cell(row=1, column=col_i, value=titulo)
        cell.font      = FONT_HEADER
        cell.fill      = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border    = BORDER_THIN
        ws.column_dimensions[get_column_letter(col_i)].width = ancho

    ws.row_dimensions[1].height = 18
    ws.freeze_panes = "A2"

    # --- Filas de datos ---
    for row_i, d in enumerate(filas, start=2):
        valores = [
            d["uuid"],
            str(d["fecha"]) if d["fecha"] else "",
            d["rfc_emisor"],
            d["nombre_emisor"],
            d["rfc_receptor"],
            d["subtotal"],
            d["iva_16"],
            d["iva_ret"],
            d["isr_ret"],
            d["total"],
            d["moneda"],
            d["tipo_label"],
        ]
        for col_i, val in enumerate(valores, start=1):
            cell        = ws.cell(row=row_i, column=col_i, value=val)
            cell.font   = FONT_NORMAL
            cell.border = BORDER_THIN
            if col_i in _COLS_NUM_PT:
                cell.number_format = FMT_CURRENCY
                cell.alignment     = ALIGN_RIGHT
            else:
                cell.alignment = ALIGN_LEFT

    # --- Fila de totales con fórmulas SUM ---
    from openpyxl.utils import get_column_letter
    tot_row = len(filas) + 2
    for col_i in range(1, len(_COLS_PT) + 1):
        cell        = ws.cell(row=tot_row, column=col_i)
        cell.font   = FONT_BOLD
        cell.fill   = FILL_TOTAL
        cell.border = BORDER_THIN
        if col_i == 1:
            cell.value     = "TOTALES"
            cell.alignment = ALIGN_LEFT
        elif col_i in _COLS_NUM_PT:
            col_letter         = get_column_letter(col_i)
            cell.value         = f"=SUM({col_letter}2:{col_letter}{tot_row - 1})"
            cell.number_format = FMT_CURRENCY
            cell.alignment     = ALIGN_RIGHT


def generate_papel_trabajo_xml(
    cfdi_dir: Path,
    output_path: Path,
) -> Path | None:
    """
    Genera un papel de trabajo contable en Excel a partir de XMLs CFDI.

    Una hoja por mes, con los campos exactos del comprobante:
      UUID, Fecha, RFC/Nombre Emisor, RFC Receptor, Subtotal,
      IVA Trasladado 16%, IVA Retenido, ISR Retenido, Total, Moneda, Tipo.

    Los valores de IVA e ISR se leen directamente del XML — no son estimaciones.
    Para complementos de pago (Tipo P), los montos vienen del nodo pago20:Totales.

    Parametros:
      cfdi_dir    : carpeta que contiene los XMLs (se escanea recursivamente)
      output_path : ruta completa del archivo .xlsx a generar

    Retorna la ruta del archivo generado, o None si no habia XMLs validos.
    """
    registros = parsear_directorio(cfdi_dir)
    if not registros:
        log.error("No se encontraron CFDIs validos para generar el Excel.")
        return None

    por_mes = agrupar_por_mes(registros)

    wb = Workbook()
    wb.remove(wb.active)

    for clave in sorted(por_mes.keys()):
        filas      = por_mes[clave]
        partes     = clave.split("-")
        mes_num    = partes[1] if len(partes) >= 2 else "??"
        mes_label  = f"{MESES_ES.get(mes_num, mes_num)} {partes[0]}"
        ws         = wb.create_sheet(title=mes_label[:31])
        _write_hoja_mes(ws, filas, mes_label)
        log.info(f"  Hoja '{mes_label}': {len(filas)} CFDI(s)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))

    log.info(f"Excel papel de trabajo guardado: {output_path.resolve()}")
    log.info(f"  Meses: {len(por_mes)} | CFDIs: {len(registros)}")
    return output_path