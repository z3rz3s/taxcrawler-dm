"""
excel_service.py
----------------
Orquesta la generacion de Excel desde Metadata TXT o XMLs de CFDI.
Llama exclusivamente a funciones de core/ — no contiene logica de negocio.
"""

import sys
from datetime import date
from pathlib import Path

_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from core.config import log
from core.excel_generator import generate_excel


def generate_from_metadata(
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
) -> Path | None:
    """
    Genera el Excel de Papel de Trabajo desde archivos TXT de Metadata.
    Retorna la ruta al archivo Excel generado, o None si fallo.
    """
    try:
        excel_path = generate_excel(
            rfc             = rfc.upper(),
            start_date      = start_date,
            end_date        = end_date,
            income_files    = income_files,
            expense_files   = expense_files,
            output_dir      = output_dir,
            isr_table       = isr_table,
            despacho        = despacho,
            regimen         = regimen,
            acumulado_anual = acumulado_anual,
            excel_mode      = excel_mode,
        )
        log.info(f"  Excel generado: {excel_path}")
        return excel_path
    except Exception as e:
        log.error(f"  X Error al generar Excel. Causa: {e}")
        return None


def generate_from_cfdi(
    rfc: str,
    start_date: date,
    end_date: date,
    xml_dir: Path,
    output_dir: Path,
    isr_table: list[tuple],
    despacho: str,
    regimen: str = "resico",
) -> Path | None:
    """
    Genera el Excel con datos exactos desde archivos XML de CFDI.
    TODO: implementar cuando core/xml_parser.py este disponible (Phase 7).
    Por ahora retorna None con mensaje informativo.
    """
    # TODO: implementar cuando xml_parser.py este disponible
    # from core.xml_parser import parse_cfdi_folder
    # records = parse_cfdi_folder(xml_dir, rfc)
    # return generate_excel(...)
    log.warning("  ! generate_from_cfdi no esta implementado aun.")
    log.warning("    Usa generate_from_metadata mientras tanto.")
    log.warning("    Ver US-010 en docs/specification/user-stories.md")
    return None