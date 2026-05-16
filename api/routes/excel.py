"""
api/routes/excel.py
-------------------
Endpoints de generacion de Excel desde Metadata TXT o XMLs de CFDI.
Llama a services/excel_service.py unicamente.
"""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.excel_service import generate_from_metadata, generate_from_cfdi
from core.config import get_despacho_name, resolve_isr_table

router = APIRouter()


# ===========================================================================
# Modelos de request
# ===========================================================================

class MetadataExcelRequest(BaseModel):
    rfc:           str        = Field(..., example="XAXX010101000")
    start_date:    date       = Field(..., example="2025-01-01")
    end_date:      date       = Field(..., example="2025-03-31")
    income_files:  list[str]  = Field(..., example=["/path/to/2025-01-RFC.txt"])
    expense_files: list[str]  = Field(..., example=["/path/to/2025-01-RFC.txt"])
    output_dir:    str        = Field(..., example="/path/to/output")
    despacho:      str | None = Field(None, example="Mi Despacho Contable SC")
    regimen:       str        = Field("resico", example="resico")


class CfdiExcelRequest(BaseModel):
    rfc:        str      = Field(..., example="XAXX010101000")
    start_date: date     = Field(..., example="2025-01-01")
    end_date:   date     = Field(..., example="2025-03-31")
    xml_dir:    str      = Field(..., example="/path/to/cfdi/folder")
    output_dir: str      = Field(..., example="/path/to/output")
    despacho:   str | None = Field(None, example="Mi Despacho Contable SC")
    regimen:    str      = Field("resico", example="resico")


# ===========================================================================
# Endpoints
# ===========================================================================

@router.post("/from-metadata")
def api_excel_from_metadata(req: MetadataExcelRequest):
    """
    Genera el Excel de Papel de Trabajo desde archivos TXT de Metadata ya descargados.
    Los archivos deben existir en disco antes de llamar este endpoint.
    """
    income_paths  = [Path(f) for f in req.income_files]
    expense_paths = [Path(f) for f in req.expense_files]

    # Validar que los archivos existen
    missing = [str(f) for f in income_paths + expense_paths if not f.exists()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Archivos no encontrados: {', '.join(missing)}"
        )

    output    = Path(req.output_dir)
    isr_table = resolve_isr_table()
    despacho  = get_despacho_name(req.despacho)

    try:
        excel_path = generate_from_metadata(
            rfc           = req.rfc,
            start_date    = req.start_date,
            end_date      = req.end_date,
            income_files  = income_paths,
            expense_files = expense_paths,
            output_dir    = output,
            isr_table     = isr_table,
            despacho      = despacho,
            regimen       = req.regimen,
        )

        if not excel_path:
            raise HTTPException(status_code=500, detail="Error al generar el Excel.")

        return {
            "status":     "completed",
            "excel_path": str(excel_path),
            "rfc":        req.rfc.upper(),
            "start_date": str(req.start_date),
            "end_date":   str(req.end_date),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-cfdi")
def api_excel_from_cfdi(req: CfdiExcelRequest):
    """
    Genera el Excel con datos exactos desde archivos XML de CFDI.
    TODO: requiere xml_parser.py — pendiente de implementar en Phase 7.
    Ver US-010 en docs/specification/user-stories.md
    """
    # TODO: implementar cuando xml_parser.py este disponible (Phase 7)
    raise HTTPException(
        status_code=501,
        detail=(
            "Endpoint no implementado aun. "
            "Requiere xml_parser.py (Phase 7). "
            "Usa /excel/from-metadata mientras tanto."
        )
    )