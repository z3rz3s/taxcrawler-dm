"""
excel_generator.py
------------------
Generacion del Excel de Papel de Trabajo contable.
Replica el formato del archivo de referencia para multiples clientes.

Hojas generadas segun modo:
  resumen  : Papel de Trabajo + Summary + Calculos
  detalle  : ingresos_MM + gastos_MM + pagos_MM + Calculos
  completo : todo lo anterior junto

Modos de acumulado anual:
  False (default) : reconstruye todo desde los TXTs en disco cada vez (Opcion A)
  True            : mantiene un Excel anual que se actualiza mes a mes (Opcion B)
  -- activar con --acumulado-anual

Regimenes soportados:
  resico : tasa progresiva simplificada (implementado)
  pfae   : TODO — pendiente de definir el calculo con el equipo contable

Fuente de tabla ISR (prioridad):
  1. Hardcoded en config.py (TABLA_ISR_RESICO_DEFAULT)
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
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from config import MESES_ES, log
from metadata_parser import (
    filter_gastos,
    filter_ingresos,
    filter_pagos,
    generate_monthly_periods,
    read_metadata_file,
)


# ===========================================================================
# Estilos comunes
# ===========================================================================

FONT_TITLE   = Font(name="Arial", bold=True, size=11)
FONT_HEADER  = Font(name="Arial", bold=True, size=9, color="FFFFFF")
FONT_NORMAL  = Font(name="Arial", size=9)
FONT_BOLD    = Font(name="Arial", bold=True, size=9)
FONT_DESPACHO = Font(name="Arial", bold=True, size=10)

FILL_HEADER  = PatternFill("solid", start_color="2F5496")   # azul oscuro
FILL_SUBHEAD = PatternFill("solid", start_color="BDD7EE")   # azul claro
FILL_TOTAL   = PatternFill("solid", start_color="D9E1F2")   # azul muy claro
FILL_INGRESO = PatternFill("solid", start_color="E2EFDA")   # verde claro
FILL_GASTO   = PatternFill("solid", start_color="FCE4D6")   # naranja claro
FILL_PAGO    = PatternFill("solid", start_color="FFF2CC")   # amarillo claro

THIN = Side(style="thin", color="BFBFBF")
BORDER_THIN = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_RIGHT  = Alignment(horizontal="right",  vertical="center")
ALIGN_LEFT   = Alignment(horizontal="left",   vertical="center")

FMT_CURRENCY = '#,##0.00'
FMT_PERCENT  = '0.00%'
FMT_DATE     = 'YYYY-MM-DD'


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
        cell = ws.cell(row=row, column=i, value=label)
        cell.font      = FONT_HEADER
        cell.fill      = fill
        cell.alignment = ALIGN_CENTER
        cell.border    = BORDER_THIN


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
        # Alinear numeros a la derecha automaticamente
        if isinstance(val, (int, float)):
            cell.alignment = ALIGN_RIGHT
        else:
            cell.alignment = ALIGN_LEFT


def _labeled_value(ws, row: int, col: int, label: str, value_col: int,
                   value, bold_label: bool = True, fmt: str | None = None) -> None:
    """Escribe un par etiqueta / valor en celdas contiguas."""
    lbl_cell            = ws.cell(row=row, column=col, value=label)
    lbl_cell.font       = FONT_BOLD if bold_label else FONT_NORMAL
    lbl_cell.alignment  = ALIGN_LEFT

    val_cell            = ws.cell(row=row, column=value_col, value=value)
    val_cell.font       = FONT_NORMAL
    val_cell.alignment  = ALIGN_RIGHT
    if fmt:
        val_cell.number_format = fmt


# ===========================================================================
# Calculos de impuestos
# ===========================================================================

def _lookup_isr(income: float, tabla: list[tuple]) -> dict:
    """
    Calcula el ISR mensual usando la tabla de tarifas RESICO.
    Retorna un dict con los componentes del calculo.

    TODO: cuando se defina el regimen PFAE, agregar una funcion similar
    _lookup_isr_pfae(income, tabla) con la logica correspondiente.
    """
    for (lim_inf, lim_sup, cuota, tasa) in tabla:
        if lim_inf <= income <= lim_sup:
            base       = income - lim_inf
            isr_calc   = base * tasa + cuota
            return {
                "ingreso":         income,
                "limite_inferior": lim_inf,
                "base":            base,
                "tasa":            tasa,
                "resultado":       base * tasa,
                "cuota_fija":      cuota,
                "isr_calculado":   isr_calc,
            }
    # Si supera todos los rangos, usar el ultimo
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


def _calc_iva(ingresos: list[dict], gastos: list[dict]) -> dict:
    """
    Calcula el IVA del mes.
    IVA trasladado (ingresos) - IVA acreditable (gastos) = saldo del mes.
    """
    iva_trasladado  = sum(r["monto"] * 0.16 for r in ingresos)
    iva_acreditable = sum(r["monto"] * 0.16 for r in gastos)
    saldo           = iva_trasladado - iva_acreditable
    return {
        "trasladado":  iva_trasladado,
        "acreditable": iva_acreditable,
        "saldo":       saldo,
    }


# ===========================================================================
# Hoja de ingresos, gastos o pagos
# ===========================================================================

COLS_METADATA = [
    "UUID", "RFC Emisor", "Nombre Emisor", "RFC Receptor", "Nombre Receptor",
    "Fecha Emision", "Monto", "Tipo", "Estatus",
]

def _write_cfdi_sheet(ws, records: list[dict], title: str,
                      fill_header=None, fill_data=None) -> None:
    """
    Escribe una hoja con registros de CFDIs.
    Usada para ingresos, gastos y pagos.
    """
    fill_header = fill_header or FILL_HEADER
    fill_data   = fill_data   or None

    ws.cell(row=1, column=1, value=title).font = FONT_TITLE
    _header_row(ws, 2, COLS_METADATA, fill=fill_header)

    fmt_map = {7: FMT_CURRENCY}
    total   = 0.0

    for i, r in enumerate(records, 3):
        row_vals = [
            r["uuid"], r["rfc_emisor"], r["nombre_emisor"],
            r["rfc_receptor"], r["nombre_receptor"],
            r["fecha_emision"], r["monto"], r["tipo"], r["estatus"],
        ]
        _data_row(ws, i, row_vals, fill=fill_data, fmt_map=fmt_map)
        total += r["monto"]

    # Fila de total
    total_row = len(records) + 3
    ws.cell(row=total_row, column=6, value="TOTAL").font = FONT_BOLD
    total_cell = ws.cell(row=total_row, column=7,
                         value=f"=SUM(G3:G{total_row - 1})")
    total_cell.font           = FONT_BOLD
    total_cell.number_format  = FMT_CURRENCY
    total_cell.fill           = FILL_TOTAL
    total_cell.alignment      = ALIGN_RIGHT
    total_cell.border         = BORDER_THIN

    _set_col_widths(ws, {
        "A": 38, "B": 18, "C": 35, "D": 18, "E": 35,
        "F": 20, "G": 16, "H": 10, "I": 12,
    })

    log.info(f"    Hoja '{ws.title}': {len(records)} registro(s) | Total: ${total:,.2f}")


# ===========================================================================
# Hoja de impuestos del mes
# ===========================================================================

def _write_impuestos_sheet(ws, month_label: str, ingresos: list[dict],
                           gastos: list[dict], isr_table: list[tuple],
                           isr_retenido: float = 0.0) -> dict:
    """
    Escribe la hoja de impuestos de un mes con formulas Excel.
    Replica la estructura del archivo de referencia.
    Retorna el dict de calculos para uso en el Papel de Trabajo.
    """
    total_ingresos = sum(r["monto"] for r in ingresos)
    total_gastos   = sum(r["monto"] for r in gastos)
    iva            = _calc_iva(ingresos, gastos)
    isr_data       = _lookup_isr(total_ingresos, isr_table)
    isr_por_pagar  = max(0.0, isr_data["isr_calculado"] - isr_retenido)

    # --- Encabezado ---
    ws.cell(row=1, column=1, value="CALCULO DE IMPUESTOS").font = FONT_TITLE
    ws.cell(row=2, column=1, value=f"Periodo: {month_label}").font = FONT_BOLD

    # --- Seccion IVA ---
    ws.cell(row=4, column=1, value="IVA").font = FONT_BOLD
    _labeled_value(ws, 5,  1, "Ingresos del mes",    3, total_ingresos,   fmt=FMT_CURRENCY)
    _labeled_value(ws, 6,  1, "IVA trasladado 16%",  3, iva["trasladado"], fmt=FMT_CURRENCY)
    _labeled_value(ws, 7,  1, "IVA acreditable",      3, iva["acreditable"], fmt=FMT_CURRENCY)
    _labeled_value(ws, 8,  1, "IVA a pagar / favor",  3, iva["saldo"],     fmt=FMT_CURRENCY)

    # --- Seccion ISR ---
    ws.cell(row=10, column=1, value="ISR").font = FONT_BOLD
    _labeled_value(ws, 11, 1, "Total ingresos",        3, total_ingresos,           fmt=FMT_CURRENCY)
    _labeled_value(ws, 12, 1, "(-) Limite inferior",   3, isr_data["limite_inferior"], fmt=FMT_CURRENCY)
    _labeled_value(ws, 13, 1, "Base",                  3, isr_data["base"],         fmt=FMT_CURRENCY)
    _labeled_value(ws, 14, 1, "(x) Tasa",              3, isr_data["tasa"],          fmt=FMT_PERCENT)
    _labeled_value(ws, 15, 1, "Resultado",              3, isr_data["resultado"],    fmt=FMT_CURRENCY)
    _labeled_value(ws, 16, 1, "(+) Cuota fija",        3, isr_data["cuota_fija"],   fmt=FMT_CURRENCY)
    _labeled_value(ws, 17, 1, "ISR calculado",         3, isr_data["isr_calculado"], fmt=FMT_CURRENCY)
    _labeled_value(ws, 18, 1, "(-) ISR retenido",      3, isr_retenido,             fmt=FMT_CURRENCY)
    _labeled_value(ws, 19, 1, "ISR por pagar",         3, isr_por_pagar,            fmt=FMT_CURRENCY,
                   bold_label=True)

    _set_col_widths(ws, {"A": 25, "B": 5, "C": 18})

    return {
        "total_ingresos": total_ingresos,
        "total_gastos":   total_gastos,
        "iva":            iva,
        "isr":            isr_data,
        "isr_retenido":   isr_retenido,
        "isr_por_pagar":  isr_por_pagar,
    }


# ===========================================================================
# Papel de Trabajo del mes
# ===========================================================================

def _write_papel_sheet(ws, rfc: str, client_name: str, month_label: str,
                       despacho: str, calcs: dict) -> None:
    """
    Escribe el Papel de Trabajo del mes.
    Replica el formato del archivo de referencia con dos secciones:
      Izquierda: ISR
      Derecha:   IVA
    """
    # --- Encabezado del despacho ---
    cell = ws.cell(row=1, column=2, value=despacho)
    cell.font      = FONT_DESPACHO
    cell.alignment = ALIGN_CENTER
    # Duplicar en columna derecha (como en el archivo de referencia)
    ws.cell(row=1, column=9, value=despacho).font = FONT_DESPACHO

    ws.cell(row=3, column=2, value="CLIENTE:").font = FONT_BOLD
    ws.cell(row=3, column=3, value=client_name).font = FONT_NORMAL
    ws.cell(row=3, column=9, value="CLIENTE:").font = FONT_BOLD
    ws.cell(row=3, column=10, value=client_name).font = FONT_NORMAL

    ws.cell(row=4, column=2, value="RFC:").font = FONT_BOLD
    ws.cell(row=4, column=3, value=rfc).font = FONT_NORMAL

    ws.cell(row=5, column=2, value="PERIODO:").font = FONT_BOLD
    ws.cell(row=5, column=3, value=month_label).font = FONT_NORMAL
    ws.cell(row=5, column=9, value="PERIODO:").font = FONT_BOLD
    ws.cell(row=5, column=10, value=month_label).font = FONT_NORMAL

    # --- Separador ---
    ws.cell(row=7, column=2, value="=" * 40).font = Font(name="Arial", size=8, color="BFBFBF")

    # --- Seccion ISR (columnas B-F) ---
    isr   = calcs["isr"]
    tasa  = 0.025  # tasa RESICO aplicable sobre ingresos para el mes

    ws.cell(row=8,  column=2, value="INGRESOS DEL MES").font = FONT_BOLD
    ws.cell(row=8,  column=5, value=calcs["total_ingresos"]).number_format = FMT_CURRENCY

    ws.cell(row=9,  column=2, value="TASA APLICABLE (2.5%)").font = FONT_NORMAL
    ws.cell(row=9,  column=5, value=calcs["total_ingresos"] * tasa).number_format = FMT_CURRENCY

    ws.cell(row=10, column=2, value="ISR RETENIDO").font = FONT_NORMAL
    ws.cell(row=10, column=5, value=calcs["isr_retenido"]).number_format = FMT_CURRENCY

    ws.cell(row=11, column=2, value="IMPUESTO POR PAGAR").font = FONT_BOLD
    pay_cell = ws.cell(row=11, column=5,
                       value=max(0.0, calcs["total_ingresos"] * tasa - calcs["isr_retenido"]))
    pay_cell.number_format = FMT_CURRENCY
    pay_cell.font          = FONT_BOLD
    pay_cell.fill          = FILL_TOTAL

    # --- Seccion IVA (columnas I-M) ---
    iva = calcs["iva"]
    ws.cell(row=8,  column=9,  value="IVA TRASLADADO").font = FONT_NORMAL
    ws.cell(row=8,  column=13, value=iva["trasladado"]).number_format = FMT_CURRENCY

    ws.cell(row=9,  column=9,  value="IVA ACREDITABLE").font = FONT_NORMAL
    ws.cell(row=9,  column=13, value=iva["acreditable"]).number_format = FMT_CURRENCY

    ws.cell(row=10, column=9,  value="IVA A PAGAR / A FAVOR").font = FONT_BOLD
    saldo_cell = ws.cell(row=10, column=13, value=iva["saldo"])
    saldo_cell.number_format = FMT_CURRENCY
    saldo_cell.font          = FONT_BOLD
    saldo_cell.fill          = FILL_TOTAL

    _set_col_widths(ws, {
        "A": 3, "B": 30, "C": 25, "D": 5, "E": 18,
        "F": 3, "G": 3,  "H": 3,  "I": 30, "J": 25,
        "K": 5, "L": 5,  "M": 18,
    })

    log.info(f"    Papel de Trabajo '{month_label}': ISR ${calcs['isr_por_pagar']:,.2f} | "
             f"IVA ${iva['saldo']:,.2f}")


# ===========================================================================
# Hoja Calculos (tabla ISR)
# ===========================================================================

def _write_calculos_sheet(ws, isr_table: list[tuple]) -> None:
    """
    Escribe la hoja de Calculos con la tabla ISR.
    Incluye nota sobre como actualizar la tabla cuando cambia la legislacion.
    """
    ws.cell(row=1, column=1, value="TABLA ISR — RESICO").font = FONT_TITLE
    ws.cell(row=2, column=1,
            value="Fuente: SAT. Actualizar cuando cambie la legislacion fiscal.").font = \
        Font(name="Arial", size=8, italic=True, color="7F7F7F")

    headers = ["Limite Inferior", "Limite Superior", "Cuota Fija", "Tasa (%)"]
    _header_row(ws, 4, headers)

    for i, (lim_inf, lim_sup, cuota, tasa) in enumerate(isr_table, 5):
        sup_val = "En adelante" if lim_sup >= 999999999 else lim_sup
        _data_row(ws, i, [lim_inf, sup_val, cuota, tasa],
                  fmt_map={1: FMT_CURRENCY, 3: FMT_CURRENCY, 4: FMT_PERCENT})

    _set_col_widths(ws, {"A": 20, "B": 20, "C": 18, "D": 12})
    log.info(f"    Hoja 'Calculos': {len(isr_table)} rangos de tabla ISR escritos.")


# ===========================================================================
# Hoja Summary — resumen de todos los meses
# ===========================================================================

def _write_summary_sheet(ws, rfc: str, start_date: date, end_date: date,
                         month_summaries: list[dict], despacho: str) -> None:
    """
    Escribe la hoja de resumen con todos los meses procesados.
    Incluye totales de ingresos, gastos, IVA e ISR por mes.
    """
    ws.cell(row=1, column=1, value="RESUMEN ANUAL / DE PERIODO").font = FONT_TITLE
    ws.cell(row=2, column=1, value=f"RFC: {rfc}").font = FONT_BOLD
    ws.cell(row=3, column=1, value=f"Periodo: {start_date} -> {end_date}").font = FONT_NORMAL
    ws.cell(row=4, column=1, value=f"Despacho: {despacho}").font = FONT_NORMAL
    ws.cell(row=5, column=1,
            value=f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").font = \
        Font(name="Arial", size=8, italic=True, color="7F7F7F")

    headers = [
        "Periodo", "Ingresos", "Gastos", "IVA Trasladado",
        "IVA Acreditable", "IVA Saldo", "ISR Calculado",
        "ISR Retenido", "ISR Por Pagar",
    ]
    _header_row(ws, 7, headers)

    fmt_map = {i: FMT_CURRENCY for i in range(2, 10)}
    total_row_data = [0.0] * 8

    for i, ms in enumerate(month_summaries, 8):
        row_vals = [
            ms["label"],
            ms["total_ingresos"],
            ms["total_gastos"],
            ms["iva"]["trasladado"],
            ms["iva"]["acreditable"],
            ms["iva"]["saldo"],
            ms["isr"]["isr_calculado"],
            ms["isr_retenido"],
            ms["isr_por_pagar"],
        ]
        _data_row(ws, i, row_vals, fmt_map=fmt_map)
        for j, v in enumerate(row_vals[1:], 0):
            total_row_data[j] += v if isinstance(v, (int, float)) else 0

    # Fila de totales
    total_row = 8 + len(month_summaries)
    ws.cell(total_row, 1, value="TOTAL").font = FONT_BOLD
    for j, val in enumerate(total_row_data, 2):
        cell = ws.cell(total_row, j, value=val)
        cell.font           = FONT_BOLD
        cell.number_format  = FMT_CURRENCY
        cell.fill           = FILL_TOTAL
        cell.alignment      = ALIGN_RIGHT
        cell.border         = BORDER_THIN

    _set_col_widths(ws, {
        "A": 18, "B": 16, "C": 16, "D": 16,
        "E": 16, "F": 16, "G": 16, "H": 16, "I": 16,
    })

    log.info(f"    Hoja 'Summary': {len(month_summaries)} mes(es) resumidos.")


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
    Genera el Excel de Papel de Trabajo contable.

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
      acumulado_anual: True = Opcion B (Excel anual acumulado)
      excel_mode     : 'resumen' | 'detalle' | 'completo'

    Retorna la ruta al archivo Excel generado.
    """
    if regimen != "resico":
        # TODO: implementar calculo PFAE cuando el equipo contable defina la logica
        log.warning(f"  ! Regimen '{regimen}' no implementado aun. Usando RESICO por defecto.")

    log.info(f"Generando Excel | RFC: {rfc} | Modo: {excel_mode} | "
             f"Periodo: {start_date} -> {end_date}")

    # Determinar nombre del archivo
    if start_date.replace(day=1) == end_date.replace(day=1):
        filename = f"{rfc}_{start_date.strftime('%Y-%m')}.xlsx"
    else:
        filename = f"{rfc}_{start_date.strftime('%Y-%m')}__{end_date.strftime('%Y-%m')}.xlsx"

    # Si es acumulado anual, apuntar a la raiz de results_RFC
    if acumulado_anual:
        excel_dir = output_dir
        log.info(f"  Modo acumulado anual — actualizando Excel existente si lo hay.")
    else:
        excel_dir = output_dir
    excel_dir.mkdir(parents=True, exist_ok=True)
    excel_path = excel_dir / filename

    # Construir indice de archivos por mes
    income_by_month  = _index_files_by_month(income_files)
    expense_by_month = _index_files_by_month(expense_files)

    # Generar periodos mensuales del rango
    periods = generate_monthly_periods(start_date, end_date)

    wb = Workbook()
    wb.remove(wb.active)  # Eliminar hoja por defecto

    month_summaries: list[dict] = []

    for month_start, month_end in periods:
        month_key = month_start.strftime("%Y-%m")
        month_num = month_start.strftime("%m")
        month_lbl = f"{MESES_ES[month_num]} {month_start.year}"

        log.info(f"  Procesando mes: {month_lbl}")

        # Leer y filtrar registros del mes
        income_recs  = _load_month_records(income_by_month.get(month_key, []), rfc, "ingresos")
        expense_recs = _load_month_records(expense_by_month.get(month_key, []), rfc, "gastos")
        payment_recs = _load_month_records(expense_by_month.get(month_key, []), rfc, "pagos")

        # Calculos del mes
        isr_retenido = sum(r.get("isr_retenido", 0.0) for r in income_recs)
        calcs = _build_month_calcs(income_recs, expense_recs, isr_table, isr_retenido)
        calcs["label"] = month_lbl
        month_summaries.append(calcs)

        # Nombre del cliente (tomado del primer registro de ingresos)
        client_name = income_recs[0]["nombre_emisor"] if income_recs else rfc

        # --- Hojas de detalle ---
        if excel_mode in ("detalle", "completo"):
            ws_ing = wb.create_sheet(f"ingresos_{month_key}")
            _write_cfdi_sheet(ws_ing, income_recs,
                              f"Ingresos — {month_lbl}", fill_header=FILL_HEADER,
                              fill_data=FILL_INGRESO)

            ws_gst = wb.create_sheet(f"gastos_{month_key}")
            _write_cfdi_sheet(ws_gst, expense_recs,
                              f"Gastos — {month_lbl}", fill_header=FILL_HEADER,
                              fill_data=FILL_GASTO)

            ws_pag = wb.create_sheet(f"pagos_{month_key}")
            _write_cfdi_sheet(ws_pag, payment_recs,
                              f"Complementos de Pago — {month_lbl} (referencia, no suman al total)",
                              fill_header=FILL_HEADER, fill_data=FILL_PAGO)

        # --- Hoja de impuestos ---
        if excel_mode in ("detalle", "completo"):
            ws_imp = wb.create_sheet(f"impuestos_{month_key}")
            _write_impuestos_sheet(ws_imp, month_lbl, income_recs,
                                   expense_recs, isr_table, isr_retenido)

        # --- Papel de Trabajo del mes ---
        if excel_mode in ("resumen", "completo"):
            ws_pt = wb.create_sheet(f"papel_{month_key}")
            _write_papel_sheet(ws_pt, rfc, client_name, month_lbl, despacho, calcs)

    # --- Hoja Summary (siempre) ---
    ws_sum = wb.create_sheet("Summary")
    _write_summary_sheet(ws_sum, rfc, start_date, end_date, month_summaries, despacho)

    # --- Hoja Calculos (siempre) ---
    ws_calc = wb.create_sheet("Calculos")
    _write_calculos_sheet(ws_calc, isr_table)

    wb.save(excel_path)
    log.info(f"  Excel guardado: {excel_path}")
    log.info(f"  Hojas generadas: {wb.sheetnames}")

    return excel_path


# ===========================================================================
# Helpers internos
# ===========================================================================

def _index_files_by_month(files: list[Path]) -> dict[str, list[Path]]:
    """
    Agrupa los archivos TXT por mes (YYYY-MM) segun su nombre.
    Nombre esperado: YYYY-MM-RFC.txt
    """
    index: dict[str, list[Path]] = {}
    for f in files:
        parts = f.stem.split("-")
        if len(parts) >= 2:
            key = f"{parts[0]}-{parts[1]}"
            index.setdefault(key, []).append(f)
    return index


def _load_month_records(files: list[Path], rfc: str,
                        record_type: str) -> list[dict]:
    """
    Lee los archivos TXT de un mes y filtra segun el tipo de registro.
    record_type: 'ingresos' | 'gastos' | 'pagos'
    """
    all_records: list[dict] = []
    for f in files:
        all_records.extend(read_metadata_file(f))

    if record_type == "ingresos":
        return filter_ingresos(all_records, rfc)
    elif record_type == "gastos":
        return filter_gastos(all_records, rfc)
    elif record_type == "pagos":
        return filter_pagos(all_records, rfc)
    return []


def _build_month_calcs(income_recs: list[dict], expense_recs: list[dict],
                       isr_table: list[tuple], isr_retenido: float) -> dict:
    """
    Construye el dict de calculos de un mes para uso en Papel de Trabajo y Summary.
    """
    total_ingresos = sum(r["monto"] for r in income_recs)
    total_gastos   = sum(r["monto"] for r in expense_recs)
    iva            = _calc_iva(income_recs, expense_recs)
    isr_data       = _lookup_isr(total_ingresos, isr_table)
    isr_por_pagar  = max(0.0, isr_data["isr_calculado"] - isr_retenido)

    return {
        "total_ingresos": total_ingresos,
        "total_gastos":   total_gastos,
        "iva":            iva,
        "isr":            isr_data,
        "isr_retenido":   isr_retenido,
        "isr_por_pagar":  isr_por_pagar,
    }