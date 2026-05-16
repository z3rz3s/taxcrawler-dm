"""
cache_service.py
----------------
Expone operaciones de cache para cli/, api/ y ui/.
Proporciona retornos tipados en lugar de dicts raw.
Llama exclusivamente a funciones de core/cache_manager.py.
"""

import sys
from pathlib import Path

_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from core.config import CACHE_DIR, log
from core.cache_manager import (
    elapsed_label,
    read_pending,
    read_profile,
    _read_enc,
    _history_path,
)


def get_profile(rfc: str) -> dict:
    """
    Retorna el perfil guardado de un RFC.
    Agrega campo 'cer_exists' y 'key_exists' para facilitar validacion en UI y API.
    Retorna dict vacio si no hay perfil.
    """
    profile = read_profile(rfc.upper())
    if not profile:
        return {}

    cer_path = Path(profile.get("cer", ""))
    key_path = Path(profile.get("key", ""))

    return {
        **profile,
        "rfc":        rfc.upper(),
        "cer_exists": cer_path.exists(),
        "key_exists": key_path.exists(),
    }


def get_pending(rfc: str) -> list[dict]:
    """
    Retorna las solicitudes pendientes de un RFC especifico.
    Cada entrada incluye el tiempo transcurrido desde la creacion.
    """
    pending = read_pending(rfc.upper())
    result  = []
    for req_id, info in sorted(pending.items(), key=lambda x: x[1].get("creado", "")):
        result.append({
            **info,
            "request_id":     req_id,
            "elapsed":        elapsed_label(info.get("creado", "")),
            "resume_command": f"--retomar {req_id}",
        })
    return result


def get_all_pending() -> list[dict]:
    """
    Retorna todas las solicitudes pendientes de todos los RFCs.
    Ordena por fecha de creacion ascendente.
    """
    if not CACHE_DIR.exists():
        return []

    all_pending = []
    for archivo in sorted(CACHE_DIR.glob("*.pending.enc")):
        rfc = archivo.stem.replace(".pending", "")
        all_pending.extend(get_pending(rfc))

    return sorted(all_pending, key=lambda x: x.get("creado", ""))


def get_history(rfc: str) -> list[dict]:
    """
    Retorna el historial de intentos de descarga CFDI para un RFC.
    Cada entrada incluye el proximo offset a usar.
    """
    history = _read_enc(rfc.upper(), _history_path(rfc.upper()))
    result  = []

    for key, info in sorted(history.items()):
        try:
            start_str, end_str, tipo = key.split("|")
        except ValueError:
            continue
        result.append({
            "start_date":      start_str,
            "end_date":        end_str,
            "tipo":            tipo,
            "intentos":        info.get("intentos", 0),
            "last_attempt":    info.get("ultimo", "—"),
            "next_offset_sec": info.get("offset_segundos", 0),
        })

    return result