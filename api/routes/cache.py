"""
api/routes/cache.py
-------------------
Endpoints de inspeccion del cache encriptado.
Llama a services/cache_service.py unicamente.
No requiere FIEL ni password — solo SAT_CACHE_SALT en .env.
"""

from fastapi import APIRouter, HTTPException

from services.cache_service import get_all_pending, get_history, get_pending, get_profile
from core.config import validate_salt

router = APIRouter()


def _check_salt() -> None:
    """
    Verifica que SAT_CACHE_SALT este configurado antes de cualquier operacion de cache.
    Lanza HTTPException 500 si no esta definido.
    """
    try:
        validate_salt()
    except SystemExit:
        raise HTTPException(
            status_code=500,
            detail="SAT_CACHE_SALT no esta definido en .env. El cache no puede desencriptarse."
        )


# ===========================================================================
# Endpoints
# ===========================================================================

@router.get("/pending")
def api_get_all_pending():
    """
    Retorna todas las solicitudes CFDI pendientes de todos los RFCs.
    Equivalente a --pendientes en el CLI.
    """
    _check_salt()
    try:
        pending = get_all_pending()
        return {
            "total":    len(pending),
            "requests": pending,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending/{rfc}")
def api_get_pending_by_rfc(rfc: str):
    """
    Retorna las solicitudes CFDI pendientes de un RFC especifico.
    """
    _check_salt()
    try:
        pending = get_pending(rfc.upper())
        return {
            "rfc":      rfc.upper(),
            "total":    len(pending),
            "requests": pending,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/{rfc}")
def api_get_profile(rfc: str):
    """
    Retorna el perfil guardado de un RFC.
    Equivalente a --perfil RFC en el CLI.
    Incluye si los archivos .cer y .key aun existen en disco.
    """
    _check_salt()
    try:
        profile = get_profile(rfc.upper())
        if not profile:
            return {
                "rfc":     rfc.upper(),
                "profile": None,
                "message": "Sin perfil guardado para este RFC.",
            }
        return {
            "rfc":     rfc.upper(),
            "profile": profile,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{rfc}")
def api_get_history(rfc: str):
    """
    Retorna el historial de intentos de descarga CFDI para un RFC.
    Equivalente a --reveal-cache RFC en el CLI.
    Muestra cuantos intentos hay por periodo y el proximo offset.
    """
    _check_salt()
    try:
        history = get_history(rfc.upper())
        return {
            "rfc":     rfc.upper(),
            "total":   len(history),
            "periods": history,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))