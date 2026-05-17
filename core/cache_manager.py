"""
cache_manager.py
----------------
Manejo del cache encriptado: historial de intentos (bypass offset),
solicitudes pendientes y perfil de RFC.

Todos los archivos se guardan en .cache/ con encriptacion Fernet + PBKDF2-SHA256.
La clave se deriva de SAT_CACHE_SALT (variable de entorno) + RFC.
La contrasena nunca se almacena.
"""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path

from core.config import CACHE_DIR, log, validate_salt


# ===========================================================================
# Infraestructura de encriptado
# ===========================================================================

def _derive_fernet_key(rfc: str) -> bytes:
    """
    Deriva una clave Fernet unica por RFC usando PBKDF2-SHA256 + SAT_CACHE_SALT.
    La clave no se almacena — se recalcula en cada operacion.
    """
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    salt = validate_salt()
    kdf  = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(rfc.upper().encode()))


def _read_enc(rfc: str, path: Path) -> dict:
    """
    Lee y descifra cualquier archivo .enc del RFC.
    Retorna dict vacio si no existe, esta corrupto o fue modificado manualmente.
    """
    from cryptography.fernet import Fernet, InvalidToken

    if not path.exists():
        return {}
    try:
        key  = _derive_fernet_key(rfc)
        f    = Fernet(key)
        data = f.decrypt(path.read_bytes())
        return json.loads(data.decode())
    except InvalidToken:
        log.warning(f"  ! Archivo {path.name} corrupto o modificado — se reiniciara.")
        return {}
    except Exception as e:
        log.warning(f"  ! No se pudo leer {path.name}. Causa: {e}")
        return {}


def _write_enc(rfc: str, path: Path, data: dict) -> None:
    """Cifra y guarda cualquier archivo .enc del RFC."""
    from cryptography.fernet import Fernet

    CACHE_DIR.mkdir(exist_ok=True)
    try:
        key       = _derive_fernet_key(rfc)
        f         = Fernet(key)
        encrypted = f.encrypt(json.dumps(data, ensure_ascii=False).encode())
        path.write_bytes(encrypted)
    except Exception as e:
        log.warning(f"  ! No se pudo guardar {path.name}. Causa: {e}")


# ---------------------------------------------------------------------------
# Rutas de los archivos de cache
# ---------------------------------------------------------------------------

def _history_path(rfc: str) -> Path:
    """Ruta al historial de intentos por periodo."""
    return CACHE_DIR / f"{rfc.upper()}.enc"


def _pending_path(rfc: str) -> Path:
    """Ruta al archivo de solicitudes pendientes."""
    return CACHE_DIR / f"{rfc.upper()}.pending.enc"


def _profile_path(rfc: str) -> Path:
    """Ruta al perfil del RFC (rutas FIEL, output, intervalo)."""
    return CACHE_DIR / f"{rfc.upper()}.profile.enc"


# ===========================================================================
# Historial de intentos — bypass offset para evitar bloqueo SAT (error 5002)
# ===========================================================================

def _period_key(start_date, end_date, tipo: str) -> str:
    """Clave unica para identificar un periodo en el historial."""
    return f"{start_date}|{end_date}|{tipo}"


def get_attempt_history(rfc: str, start_date, end_date, tipo: str) -> dict:
    """
    Retorna el registro de intentos para un periodo especifico.
    Si no existe, retorna valores iniciales (sin intentos previos).
    """
    history = _read_enc(rfc, _history_path(rfc))
    key     = _period_key(start_date, end_date, tipo)
    return history.get(key, {"intentos": 0, "offset_segundos": 0, "ultimo": None})


def register_attempt(rfc: str, start_date, end_date, tipo: str) -> int:
    """
    Registra un nuevo intento y retorna el offset en segundos a usar.
    Cada intento incrementa el offset en 1s — evita el bloqueo permanente del SAT.

    Intento 0 -> offset 0s  (2025-01-01 00:00:00)
    Intento 1 -> offset 1s  (2025-01-01 00:00:01)
    Intento 2 -> offset 2s  (2025-01-01 00:00:02)
    """
    history    = _read_enc(rfc, _history_path(rfc))
    key        = _period_key(start_date, end_date, tipo)
    current    = history.get(key, {"intentos": 0, "offset_segundos": 0, "ultimo": None})
    new_offset = current["intentos"]

    current["intentos"]       += 1
    current["offset_segundos"] = new_offset
    current["ultimo"]          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    history[key] = current
    _write_enc(rfc, _history_path(rfc), history)
    return new_offset


def reveal_history(rfc_target: str) -> None:
    """
    Descifra y muestra el historial de intentos de un RFC o de todos.
    Modo utilitario — no requiere FIEL.
    """
    validate_salt()

    enc_files = [f for f in CACHE_DIR.glob("*.enc")
                 if not f.name.endswith(".pending.enc")
                 and not f.name.endswith(".profile.enc")] \
                if CACHE_DIR.exists() else []

    if not enc_files:
        log.info("No existe historial todavia. Aun no se ha ejecutado ninguna descarga CFDI.")
        return

    targets = enc_files if rfc_target == "all" else [_history_path(rfc_target)]

    for archivo in targets:
        rfc     = archivo.stem
        history = _read_enc(rfc, archivo)

        log.info("")
        log.info("=" * 65)
        log.info(f"CACHE DESCIFRADO — {rfc}")
        log.info("=" * 65)

        if not history:
            log.info("  Sin registros de intentos para este RFC.")
            continue

        for key, info in sorted(history.items()):
            try:
                start_str, end_str, tipo = key.split("|")
            except ValueError:
                continue
            intentos = info.get("intentos", 0)
            offset   = info.get("offset_segundos", 0)
            ultimo   = info.get("ultimo", "—")
            log.info(f"  Periodo  : {start_str} -> {end_str} ({tipo})")
            log.info(f"  Intentos : {intentos}")
            log.info(f"  Ultimo   : {ultimo}")
            log.info(f"  Proximo offset : +{offset}s -> inicio efectivo {start_str} 00:00:{offset:02d}")
            log.info("")

    log.info("=" * 65)


# ===========================================================================
# Solicitudes pendientes
# ===========================================================================

def add_pending(rfc: str, request_id: str, params: dict,
                dt_start, dt_end) -> None:
    """
    Registra una solicitud CFDI como pendiente de descarga.
    Se llama justo despues de que el SAT acepta la solicitud.
    Garantiza que ninguna solicitud se pierda ante interrupciones o timeouts.
    """
    pending = _read_enc(rfc, _pending_path(rfc))
    pending[request_id] = {
        "rfc":       rfc,
        "tipo":      params["tipo"],
        "solicitud": params["solicitud"],
        "inicio":    str(params["inicio"]),
        "fin":       str(params["fin"]),
        "dt_inicio": str(dt_start),
        "dt_fin":    str(dt_end),
        "output":    str(params["output"].resolve()),
        "intervalo": params["intervalo"],
        "creado":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_enc(rfc, _pending_path(rfc), pending)
    log.info(f"  Solicitud registrada en pendientes: {request_id}")


def remove_pending(rfc: str, request_id: str, reason: str) -> None:
    """
    Elimina una solicitud del archivo de pendientes.
    reason: 'completada' | 'rechazada' | 'vencida'
    """
    pending = _read_enc(rfc, _pending_path(rfc))
    if request_id in pending:
        del pending[request_id]
        _write_enc(rfc, _pending_path(rfc), pending)
        log.info(f"  Solicitud eliminada de pendientes ({reason}): {request_id}")
    else:
        log.warning(f"  ! ID no encontrado en pendientes al intentar eliminar: {request_id}")


def read_pending(rfc: str) -> dict:
    """Retorna todas las solicitudes pendientes de un RFC."""
    return _read_enc(rfc, _pending_path(rfc))


def elapsed_label(created_str: str) -> str:
    """Retorna tiempo transcurrido desde created_str en formato legible."""
    try:
        created = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
        total   = int((datetime.now() - created).total_seconds())
        hours   = total // 3600
        minutes = (total % 3600) // 60
        return f"hace {hours}h {minutes}m" if hours > 0 else f"hace {minutes}m"
    except Exception:
        return "tiempo desconocido"


def show_pending() -> None:
    """
    Muestra todas las solicitudes pendientes de todos los RFCs.
    Modo utilitario — no requiere FIEL.
    """
    validate_salt()

    pending_files = list(CACHE_DIR.glob("*.pending.enc")) \
                   if CACHE_DIR.exists() else []

    if not pending_files:
        log.info("No hay solicitudes pendientes.")
        return

    total = 0
    log.info("")
    log.info("=" * 65)
    log.info("SOLICITUDES PENDIENTES")
    log.info("=" * 65)

    for archivo in sorted(pending_files):
        rfc     = archivo.stem.replace(".pending", "")
        pending = read_pending(rfc)

        for req_id, info in sorted(pending.items(), key=lambda x: x[1].get("creado", "")):
            total += 1
            log.info(f"  RFC      : {info.get('rfc', rfc)}")
            log.info(f"  ID       : {req_id}")
            log.info(f"  Periodo  : {info.get('inicio')} -> {info.get('fin')} "
                     f"({info.get('tipo')} / {info.get('solicitud')})")
            log.info(f"  Creado   : {info.get('creado', '—')} "
                     f"({elapsed_label(info.get('creado', ''))})")
            log.info(f"  Salida   : {info.get('output')}")
            log.info(f"  Retomar  : --retomar {req_id}")
            log.info("")

    if total == 0:
        log.info("  No hay solicitudes pendientes.")
    else:
        log.info(f"  Total pendientes: {total}")

    log.info("=" * 65)


# ===========================================================================
# Perfil de RFC — rutas FIEL y configuracion preferida
# ===========================================================================

def read_profile(rfc: str) -> dict:
    """
    Lee el perfil del RFC desde .cache/RFC.profile.enc.
    Retorna dict vacio si no existe o esta corrupto.
    La contrasena NUNCA se almacena en el perfil.
    """
    profile = _read_enc(rfc, _profile_path(rfc))
    if profile:
        log.info(f"  Perfil encontrado para RFC {rfc.upper()}.")
    return profile


def write_profile(rfc: str, cer: Path, key: Path,
                  output: Path, intervalo: int) -> None:
    """
    Guarda el perfil del RFC con rutas y configuracion.
    Se llama automaticamente al completar cualquier descarga exitosa.
    La contrasena NUNCA se incluye.
    """
    data = {
        "cer":       str(cer.resolve()),
        "key":       str(key.resolve()),
        "output":    str(output.resolve()),
        "intervalo": intervalo,
        "guardado":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_enc(rfc, _profile_path(rfc), data)
    log.info(f"  Perfil actualizado para RFC {rfc.upper()}.")


def show_profile(rfc: str) -> None:
    """
    Descifra y muestra el perfil guardado de un RFC.
    Modo utilitario — no requiere FIEL.
    """
    validate_salt()

    profile = read_profile(rfc.upper())

    log.info("")
    log.info("=" * 65)
    log.info(f"PERFIL — {rfc.upper()}")
    log.info("=" * 65)

    if not profile:
        log.info("  Sin perfil guardado para este RFC.")
        log.info("  El perfil se crea automaticamente al completar una descarga.")
        log.info("=" * 65)
        return

    cer_path = Path(profile.get("cer", ""))
    key_path = Path(profile.get("key", ""))
    cer_ok   = "existe" if cer_path.exists() else "NO encontrado en disco"
    key_ok   = "existe" if key_path.exists() else "NO encontrado en disco"

    log.info(f"  .cer      : {cer_path}  [{cer_ok}]")
    log.info(f"  .key      : {key_path}  [{key_ok}]")
    log.info(f"  Output    : {profile.get('output', '—')}")
    log.info(f"  Intervalo : {profile.get('intervalo', '—')}s")
    log.info(f"  Guardado  : {profile.get('guardado', '—')}")

    if not cer_path.exists() or not key_path.exists():
        log.warning("  ! Algunos archivos del perfil ya no existen en disco.")
        log.warning("  Ejecuta una descarga con --cer y --key para actualizar el perfil.")

    log.info("=" * 65)

# ===========================================================================
# Historial de resultados — archivos generados por operacion
# ===========================================================================

def _results_history_path() -> Path:
    """Ruta al archivo de historial de resultados (compartible entre PCs)."""
    return CACHE_DIR / "results_history.enc"


def _shared_fernet_key() -> bytes:
    """
    Clave Fernet compartida (no ligada a un RFC especifico).
    Usa SAT_CACHE_SALT como base — misma clave en cualquier PC con el mismo salt.
    """
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64

    salt = validate_salt()
    kdf  = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(b"results_history"))


def _read_results_enc() -> list:
    """Lee y descifra el historial de resultados. Retorna lista vacia si no existe."""
    from cryptography.fernet import Fernet, InvalidToken

    path = _results_history_path()
    if not path.exists():
        return []
    try:
        f    = Fernet(_shared_fernet_key())
        data = f.decrypt(path.read_bytes())
        return json.loads(data.decode())
    except (InvalidToken, Exception) as e:
        log.warning(f"  ! No se pudo leer historial de resultados: {e}")
        return []


def _write_results_enc(history: list) -> None:
    """Cifra y guarda el historial de resultados."""
    from cryptography.fernet import Fernet

    CACHE_DIR.mkdir(exist_ok=True)
    try:
        f         = Fernet(_shared_fernet_key())
        encrypted = f.encrypt(json.dumps(history, ensure_ascii=False).encode())
        _results_history_path().write_bytes(encrypted)
    except Exception as e:
        log.warning(f"  ! No se pudo guardar historial de resultados: {e}")


def add_to_results_history(entry: dict) -> str:
    """
    Agrega una entrada al historial de resultados.
    Genera un ID unico para la entrada.
    Retorna el ID generado.
    """
    import uuid
    history    = _read_results_enc()
    entry_id   = str(uuid.uuid4())
    entry["id"] = entry_id
    history.insert(0, entry)  # mas reciente primero
    # Mantener maximo 200 entradas
    history = history[:200]
    _write_results_enc(history)
    log.info(f"  Resultado guardado en historial: {entry_id}")
    return entry_id


def get_results_history() -> list:
    """
    Retorna el historial de resultados.
    Evalua en tiempo real si cada archivo excel_path existe en disco.
    """
    history = _read_results_enc()
    for entry in history:
        excel_path = entry.get("excel_path")
        if excel_path:
            entry["excel_exists"] = Path(excel_path).exists()
        else:
            entry["excel_exists"] = False
        # Verificar archivos individuales
        files = entry.get("files", [])
        entry["files_exist"] = [Path(f).exists() for f in files]
    return history


def remove_from_results_history(entry_id: str) -> bool:
    """
    Elimina una entrada del historial por ID.
    Retorna True si se encontro y elimino, False si no existe.
    """
    history  = _read_results_enc()
    original = len(history)
    history  = [e for e in history if e.get("id") != entry_id]
    if len(history) < original:
        _write_results_enc(history)
        log.info(f"  Entrada eliminada del historial: {entry_id}")
        return True
    return False