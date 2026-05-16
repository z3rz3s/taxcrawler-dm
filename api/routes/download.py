"""
api/routes/download.py
----------------------
Endpoints de descarga de Metadata y CFDI.
Llama a services/download_service.py unicamente.
"""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.download_service import download_metadata, download_cfdi, full_flow
from core.config import get_despacho_name, resolve_isr_table

router = APIRouter()


# ===========================================================================
# Modelos de request
# ===========================================================================

class MetadataRequest(BaseModel):
    rfc:        str  = Field(..., example="XAXX010101000")
    cer_path:   str  = Field(..., example="/path/to/fiel.cer")
    key_path:   str  = Field(..., example="/path/to/fiel.key")
    password:   str  = Field(..., example="M1C0ntr4s3n4")
    start_date: date = Field(..., example="2025-01-01")
    end_date:   date = Field(..., example="2025-03-31")
    tipo:       str  = Field("recibidos", example="recibidos")
    output_dir: str  = Field(None, example="/path/to/output")
    intervalo:  int  = Field(60, ge=10, example=60)


class CfdiRequest(BaseModel):
    rfc:         str      = Field(..., example="XAXX010101000")
    cer_path:    str      = Field(..., example="/path/to/fiel.cer")
    key_path:    str      = Field(..., example="/path/to/fiel.key")
    password:    str      = Field(..., example="M1C0ntr4s3n4")
    start_date:  date     = Field(..., example="2025-01-01")
    end_date:    date     = Field(..., example="2025-01-31")
    tipo:        str      = Field("recibidos", example="recibidos")
    output_dir:  str      = Field(None, example="/path/to/output")
    intervalo:   int      = Field(60, ge=10, example=60)
    timeout_min: int | None = Field(30, example=30)


class FullFlowRequest(BaseModel):
    rfc:        str      = Field(..., example="XAXX010101000")
    cer_path:   str      = Field(..., example="/path/to/fiel.cer")
    key_path:   str      = Field(..., example="/path/to/fiel.key")
    password:   str      = Field(..., example="M1C0ntr4s3n4")
    start_date: date     = Field(..., example="2025-01-01")
    end_date:   date     = Field(..., example="2025-03-31")
    output_dir: str      = Field(None, example="/path/to/output")
    intervalo:  int      = Field(60, ge=10, example=60)
    despacho:   str | None = Field(None, example="Mi Despacho Contable SC")
    regimen:    str      = Field("resico", example="resico")


# ===========================================================================
# Validaciones comunes
# ===========================================================================

def _validate_fiel(cer_path: str, key_path: str) -> tuple[Path, Path]:
    """
    Valida que los archivos .cer y .key existan en disco.
    Lanza HTTPException 400 si alguno no se encuentra.
    """
    cer = Path(cer_path)
    key = Path(key_path)
    errors = []
    if not cer.exists():
        errors.append(f"Archivo .cer no encontrado: {cer_path}")
    if not key.exists():
        errors.append(f"Archivo .key no encontrado: {key_path}")
    if errors:
        raise HTTPException(status_code=400, detail=" | ".join(errors))
    return cer, key


def _validate_dates(start_date: date, end_date: date) -> None:
    """
    Valida rango de fechas: inicio <= fin y dentro de los ultimos 6 anios.
    """
    from datetime import date as date_type
    today     = date_type.today()
    sat_limit = date_type(today.year - 6, today.month, today.day)
    errors    = []
    if start_date > end_date:
        errors.append(f"start_date ({start_date}) es posterior a end_date ({end_date})")
    if start_date < sat_limit:
        errors.append(f"El SAT solo permite descargar desde {sat_limit}. start_date: {start_date}")
    if errors:
        raise HTTPException(status_code=400, detail=" | ".join(errors))


# ===========================================================================
# Endpoints
# ===========================================================================

@router.post("/metadata")
def api_download_metadata(req: MetadataRequest):
    """
    Descarga archivos Metadata TXT del SAT para un RFC y rango de fechas.
    Procesa mes por mes — continua si un mes no tiene CFDIs (codigo 5004).
    """
    cer, key = _validate_fiel(req.cer_path, req.key_path)
    _validate_dates(req.start_date, req.end_date)

    output = Path(req.output_dir) if req.output_dir else Path(f"./results_{req.rfc.upper()}")

    try:
        files = download_metadata(
            rfc        = req.rfc,
            cer_path   = cer,
            key_path   = key,
            password   = req.password,
            start_date = req.start_date,
            end_date   = req.end_date,
            tipo       = req.tipo,
            output_dir = output,
            intervalo  = req.intervalo,
        )
        return {
            "status":        "completed",
            "files":         [str(f) for f in files],
            "files_count":   len(files),
            "rfc":           req.rfc.upper(),
            "start_date":    str(req.start_date),
            "end_date":      str(req.end_date),
            "tipo":          req.tipo,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cfdi")
def api_download_cfdi(req: CfdiRequest):
    """
    Descarga archivos CFDI XML del SAT para un RFC y rango de fechas.
    Aplica offset automatico para evitar bloqueo permanente (error 5002).
    Si el SAT no responde antes del timeout, la solicitud queda en pendientes.
    """
    cer, key = _validate_fiel(req.cer_path, req.key_path)
    _validate_dates(req.start_date, req.end_date)

    output = Path(req.output_dir) if req.output_dir else Path(f"./results_{req.rfc.upper()}")

    try:
        files = download_cfdi(
            rfc         = req.rfc,
            cer_path    = cer,
            key_path    = key,
            password    = req.password,
            start_date  = req.start_date,
            end_date    = req.end_date,
            tipo        = req.tipo,
            output_dir  = output,
            intervalo   = req.intervalo,
            timeout_min = req.timeout_min,
        )

        if files:
            return {
                "status":      "completed",
                "xml_files":   len(files),
                "files":       [str(f) for f in files],
                "output_dir":  str(output),
            }
        else:
            return {
                "status":  "pending_or_empty",
                "message": "Solicitud en pendientes o sin CFDIs. Usa --pendientes para verificar.",
                "output_dir": str(output),
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full-flow")
def api_full_flow(req: FullFlowRequest):
    """
    Ejecuta el flujo completo: Metadata emitidos + Metadata recibidos + Excel.
    Equivalente a --flujo-completo en el CLI.
    """
    cer, key = _validate_fiel(req.cer_path, req.key_path)
    _validate_dates(req.start_date, req.end_date)

    output    = Path(req.output_dir) if req.output_dir else Path(f"./results_{req.rfc.upper()}")
    isr_table = resolve_isr_table()
    despacho  = get_despacho_name(req.despacho)

    try:
        excel_path = full_flow(
            rfc        = req.rfc,
            cer_path   = cer,
            key_path   = key,
            password   = req.password,
            start_date = req.start_date,
            end_date   = req.end_date,
            output_dir = output,
            intervalo  = req.intervalo,
            despacho   = despacho,
            tabla_isr  = isr_table,
            regimen    = req.regimen,
        )

        return {
            "status":     "completed",
            "excel_path": str(excel_path) if excel_path else None,
            "rfc":        req.rfc.upper(),
            "start_date": str(req.start_date),
            "end_date":   str(req.end_date),
            "despacho":   despacho,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))