"""
api/routes/cache.py
-------------------
Endpoints de inspeccion del cache encriptado.
Llama a services/cache_service.py unicamente.
No requiere FIEL ni password — solo SAT_CACHE_SALT en .env.
"""

from fastapi import APIRouter, HTTPException

from services.cache_service import get_all_pending, get_history, get_pending, get_profile
from pathlib import Path
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

@router.get("/profiles")
def api_get_all_profiles():
    """
    Retorna todos los perfiles guardados en .cache/
    Lee todos los archivos RFC.profile.enc disponibles.
    """
    _check_salt()
    try:
        from core.config import CACHE_DIR
        profiles = []
        if CACHE_DIR.exists():
            for archivo in sorted(CACHE_DIR.glob("*.profile.enc")):
                rfc = archivo.stem.replace(".profile", "")
                from core.cache_manager import read_profile
                profile = read_profile(rfc)
                if profile:
                    cer_path = Path(profile.get("cer", ""))
                    key_path = Path(profile.get("key", ""))
                    profiles.append({
                        **profile,
                        "rfc":        rfc.upper(),
                        "cer_exists": cer_path.exists(),
                        "key_exists": key_path.exists(),
                    })
        return {"total": len(profiles), "profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

@router.get("/results")
def api_get_results_history():
    """
    Retorna el historial de resultados generados.
    Evalua en tiempo real si cada archivo existe en disco.
    Historial compartible entre PCs con el mismo SAT_CACHE_SALT.
    """
    _check_salt()
    try:
        from core.cache_manager import get_results_history
        history = get_results_history()
        return {"total": len(history), "results": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/results/{entry_id}")
def api_delete_result(entry_id: str):
    """
    Elimina una entrada del historial de resultados por ID.
    Solo elimina el registro del historial — no borra archivos del disco.
    """
    _check_salt()
    try:
        from core.cache_manager import remove_from_results_history
        found = remove_from_results_history(entry_id)
        if not found:
            raise HTTPException(status_code=404,
                                detail=f"Entrada no encontrada: {entry_id}")
        return {"status": "deleted", "id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))