"""
api_client.py
-------------
Cliente HTTP para comunicacion con la API de taxcrawler-dm.
Todas las llamadas a la API pasan por este modulo.

TODO: agregar headers de autorizacion (Basic o JWT) cuando se implemente auth.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_libs = _root / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

import requests

API_BASE    = "http://localhost:8000"
API_TIMEOUT = 300


def api_post(endpoint: str, body: dict) -> dict:
    """
    POST a la API.
    TODO: agregar headers=AUTH_HEADER cuando se implemente auth.
    """
    try:
        r = requests.post(f"{API_BASE}{endpoint}", json=body, timeout=API_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        raise Exception(
            "No se pudo conectar con el servidor.\n"
            "Asegurate de que este corriendo:\n"
            "python3 -m uvicorn api.main:app --reload"
        )
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
            if " | " in detail:
                detail = detail.split(" | ")[0]
        except Exception:
            detail = str(e)
        raise Exception(f"Error del servidor: {detail}")
    except requests.exceptions.Timeout:
        raise Exception("El servidor tardo demasiado. Intenta de nuevo.")


def api_get(endpoint: str) -> dict:
    """
    GET a la API.
    TODO: agregar headers=AUTH_HEADER cuando se implemente auth.
    """
    try:
        r = requests.get(f"{API_BASE}{endpoint}", timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        raise Exception("Servidor no disponible.")
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        raise Exception(f"Error del servidor: {detail}")


def check_server() -> bool:
    """Verifica que el servidor este activo sin lanzar excepciones."""
    try:
        return requests.get(f"{API_BASE}/health", timeout=3).status_code == 200
    except Exception:
        return False