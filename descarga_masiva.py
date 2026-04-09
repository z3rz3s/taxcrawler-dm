"""
SAT Descarga Masiva de CFDI (XML)
==================================
Requiere:
  pip install cfdiclient openpyxl python-dotenv --target ./libs

Setup inicial:
  cp .env.example .env
  # Editar .env y definir SAT_CACHE_SALT

Modo interactivo (sin argumentos):
  python sat_descarga_masiva.py

Modo CLI — descarga:
  python sat_descarga_masiva.py \
    --rfc TURF010101ABC \
    --cer fiel.cer \
    --key fiel.key \
    --inicio 2024-01-01 \
    --fin 2024-12-31 \
    --tipo recibidos \
    --solicitud CFDI \
    --timeout 60

Modos utilitarios:
  python sat_descarga_masiva.py --reveal-cache RFC|all
  python sat_descarga_masiva.py --pendientes
  python sat_descarga_masiva.py --perfil RFC
  python sat_descarga_masiva.py --retomar ID
  python sat_descarga_masiva.py --retomar-todas RFC|all

  Nota: --retomar y --retomar-todas usan el perfil guardado para --cer/--key.
  Si no hay perfil, pasar --cer y --key explícitamente.
  Para automatización sin intervención, definir en .env:
    SAT_PASSWORD_RFC=tu_password

Opcionales:
  --solicitud  CFDI|Metadata            (default: CFDI)
  --excel      resumen|detalle|completo (solo con CFDI, pendiente)
  --timeout    minutos                  (default: sin límite)
  --intervalo  60                       segundos entre verificaciones
  --output     ruta                     carpeta base (default: ./results_RFC)

Estructura de salida:
  results_RFC/
  ├── metadata/YYYY-MM-DD/
  │   └── YYYY-MM-RFC.txt
  └── cfdi/YYYY-MM-DD/
      ├── YYYY-MM-RFC.zip
      └── YYYY-MM-RFC/uuid.xml ...

  .cache/
  ├── RFC.enc           → historial de intentos (bypass offset)
  ├── RFC.pending.enc   → solicitudes pendientes de descarga
  └── RFC.profile.enc   → perfil de RFC (rutas FIEL, output, intervalo)
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependencias locales — libs/ tiene prioridad sobre el sistema
# ---------------------------------------------------------------------------
_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

import argparse
import base64
import json
import logging
import os
import time
import zipfile
from calendar import monthrange
from datetime import date, datetime, timedelta
from getpass import getpass

# ---------------------------------------------------------------------------
# Cargar .env antes que cualquier otra cosa
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cfdiclient import (
    Autenticacion,
    DescargaMasiva,
    Fiel,
    SolicitaDescargaEmitidos,
    SolicitaDescargaRecibidos,
    VerificaSolicitudDescarga,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sat_descarga.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ESTADOS_SOLICITUD = {
    1: "Aceptada",
    2: "En proceso",
    3: "Terminada",
    4: "Error",
    5: "Rechazada",
    6: "Vencida",
}

MESES_ES = {
    "01": "Enero",      "02": "Febrero",   "03": "Marzo",
    "04": "Abril",      "05": "Mayo",      "06": "Junio",
    "07": "Julio",      "08": "Agosto",    "09": "Septiembre",
    "10": "Octubre",    "11": "Noviembre", "12": "Diciembre",
}

MAX_REINTENTOS_TOKEN    = 3
MAX_REINTENTOS_DESCARGA = 3
PAUSA_ENTRE_REINTENTOS  = 5
CACHE_DIR               = Path(__file__).resolve().parent / ".cache"
TIMEOUT_DEFAULT_MIN     = None   # None = sin límite


# ===========================================================================
# CACHÉ ENCRIPTADO — Fernet + PBKDF2 + SAT_CACHE_SALT
# ===========================================================================

def _validar_salt() -> bytes:
    """
    Lee SAT_CACHE_SALT del entorno. Falla con instrucciones claras si no existe.
    El salt nunca se guarda en código — viene exclusivamente de .env.
    """
    salt = os.environ.get("SAT_CACHE_SALT", "").strip()
    if not salt:
        log.error("=" * 65)
        log.error("Variable de entorno SAT_CACHE_SALT no definida.")
        log.error("Pasos para configurarla:")
        log.error("  1. Copia .env.example → .env")
        log.error("  2. Define SAT_CACHE_SALT=tu_valor_secreto en .env")
        log.error("  3. Asegúrate de que .env esté en .gitignore")
        log.error("=" * 65)
        sys.exit(1)
    return salt.encode()


def _derivar_clave_fernet(rfc: str) -> bytes:
    """
    Deriva una clave Fernet única por RFC usando PBKDF2-SHA256 + SAT_CACHE_SALT.
    La clave no se almacena — se recalcula en cada operación.
    """
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    salt = _validar_salt()
    kdf  = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(rfc.upper().encode()))


def _cache_path(rfc: str) -> Path:
    """Ruta al archivo de historial de intentos."""
    return CACHE_DIR / f"{rfc.upper()}.enc"


def _pending_path(rfc: str) -> Path:
    """Ruta al archivo de solicitudes pendientes."""
    return CACHE_DIR / f"{rfc.upper()}.pending.enc"


def _leer_enc(rfc: str, path: Path) -> dict:
    """
    Lee y descifra cualquier archivo .enc del RFC.
    Retorna dict vacío si no existe o está corrupto/modificado.
    """
    from cryptography.fernet import Fernet, InvalidToken

    if not path.exists():
        return {}
    try:
        clave = _derivar_clave_fernet(rfc)
        f     = Fernet(clave)
        datos = f.decrypt(path.read_bytes())
        return json.loads(datos.decode())
    except InvalidToken:
        log.warning(f"  ⚠ Archivo {path.name} corrupto o modificado manualmente — se reiniciará.")
        return {}
    except Exception as e:
        log.warning(f"  ⚠ No se pudo leer {path.name}. Causa: {e}")
        return {}


def _escribir_enc(rfc: str, path: Path, datos: dict) -> None:
    """Cifra y guarda cualquier archivo .enc del RFC."""
    from cryptography.fernet import Fernet

    CACHE_DIR.mkdir(exist_ok=True)
    try:
        clave   = _derivar_clave_fernet(rfc)
        f       = Fernet(clave)
        cifrado = f.encrypt(json.dumps(datos, ensure_ascii=False).encode())
        path.write_bytes(cifrado)
    except Exception as e:
        log.warning(f"  ⚠ No se pudo guardar {path.name}. Causa: {e}")


def _leer_cache(rfc: str) -> dict:
    return _leer_enc(rfc, _cache_path(rfc))


def _escribir_cache(rfc: str, datos: dict) -> None:
    _escribir_enc(rfc, _cache_path(rfc), datos)


def _leer_pendientes(rfc: str) -> dict:
    return _leer_enc(rfc, _pending_path(rfc))


def _escribir_pendientes(rfc: str, datos: dict) -> None:
    _escribir_enc(rfc, _pending_path(rfc), datos)



# ---------------------------------------------------------------------------
# Perfil de RFC — rutas FIEL y configuración preferida (encriptado)
# ---------------------------------------------------------------------------

def _profile_path(rfc: str) -> Path:
    """Ruta al archivo de perfil del RFC."""
    return CACHE_DIR / f"{rfc.upper()}.profile.enc"


def _leer_perfil(rfc: str) -> dict:
    """
    Lee el perfil del RFC desde .cache/RFC.profile.enc.
    Retorna dict vacío si no existe o está corrupto.
    La contraseña NUNCA se almacena en el perfil.
    """
    perfil = _leer_enc(rfc, _profile_path(rfc))
    if perfil:
        log.info(f"  Perfil encontrado para RFC {rfc.upper()}.")
    return perfil


def _escribir_perfil(rfc: str, cer: Path, key: Path, output: Path, intervalo: int) -> None:
    """
    Guarda el perfil del RFC con rutas y configuración.
    Se llama automáticamente al completar cualquier descarga exitosa.
    La contraseña NUNCA se incluye.
    """
    datos = {
        "cer":       str(cer.resolve()),
        "key":       str(key.resolve()),
        "output":    str(output.resolve()),
        "intervalo": intervalo,
        "guardado":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _escribir_enc(rfc, _profile_path(rfc), datos)
    log.info(f"  ✔ Perfil actualizado para RFC {rfc.upper()}.")

def _clave_periodo(inicio: date, fin: date, tipo: str) -> str:
    return f"{inicio}|{fin}|{tipo}"


# ---------------------------------------------------------------------------
# Historial de intentos (bypass offset)
# ---------------------------------------------------------------------------

def consultar_historial(rfc: str, inicio: date, fin: date, tipo: str) -> dict:
    """Retorna el registro de intentos para un período. Valores iniciales si no existe."""
    cache = _leer_cache(rfc)
    clave = _clave_periodo(inicio, fin, tipo)
    return cache.get(clave, {"intentos": 0, "offset_segundos": 0, "ultimo": None})


def registrar_intento(rfc: str, inicio: date, fin: date, tipo: str) -> int:
    """
    Registra un nuevo intento y retorna el offset en segundos a usar.
    Cada intento incrementa el offset en 1s — evita el bloqueo permanente del SAT.
    """
    cache        = _leer_cache(rfc)
    clave        = _clave_periodo(inicio, fin, tipo)
    actual       = cache.get(clave, {"intentos": 0, "offset_segundos": 0, "ultimo": None})
    nuevo_offset = actual["intentos"]
    actual["intentos"]       += 1
    actual["offset_segundos"] = nuevo_offset
    actual["ultimo"]          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache[clave] = actual
    _escribir_cache(rfc, cache)
    return nuevo_offset


def fechas_con_offset(inicio: date, fin: date, offset_seg: int) -> tuple[datetime, datetime]:
    """
    Convierte date a datetime aplicando offset al inicio para bypass SAT.
    offset 0 → 00:00:00, offset 1 → 00:00:01, etc.
    """
    dt_inicio = datetime(inicio.year, inicio.month, inicio.day) + timedelta(seconds=offset_seg)
    dt_fin    = datetime(fin.year, fin.month, fin.day, 23, 59, 59)
    return dt_inicio, dt_fin


# ---------------------------------------------------------------------------
# Solicitudes pendientes
# ---------------------------------------------------------------------------

def agregar_pendiente(rfc: str, id_solicitud: str, params: dict,
                      dt_inicio: datetime, dt_fin: datetime) -> None:
    """
    Registra una solicitud CFDI como pendiente de descarga.
    Se llama justo después de que el SAT acepta la solicitud.
    """
    pendientes = _leer_pendientes(rfc)
    pendientes[id_solicitud] = {
        "rfc":       rfc,
        "tipo":      params["tipo"],
        "solicitud": params["solicitud"],
        "inicio":    str(params["inicio"]),
        "fin":       str(params["fin"]),
        "dt_inicio": str(dt_inicio),
        "dt_fin":    str(dt_fin),
        "output":    str(params["output"].resolve()),
        "intervalo": params["intervalo"],
        "creado":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _escribir_pendientes(rfc, pendientes)
    log.info(f"  ✔ Solicitud registrada en pendientes: {id_solicitud}")


def eliminar_pendiente(rfc: str, id_solicitud: str, motivo: str) -> None:
    """
    Elimina una solicitud del archivo de pendientes.
    motivo: 'completada' | 'rechazada' | 'vencida'
    """
    pendientes = _leer_pendientes(rfc)
    if id_solicitud in pendientes:
        del pendientes[id_solicitud]
        _escribir_pendientes(rfc, pendientes)
        log.info(f"  ✔ Solicitud eliminada de pendientes ({motivo}): {id_solicitud}")
    else:
        log.warning(f"  ⚠ ID no encontrado en pendientes al intentar eliminar: {id_solicitud}")


def _tiempo_transcurrido(creado_str: str) -> str:
    """Retorna tiempo transcurrido desde creado en formato legible."""
    try:
        creado   = datetime.strptime(creado_str, "%Y-%m-%d %H:%M:%S")
        delta    = datetime.now() - creado
        total    = int(delta.total_seconds())
        horas    = total // 3600
        minutos  = (total % 3600) // 60
        if horas > 0:
            return f"hace {horas}h {minutos}m"
        return f"hace {minutos}m"
    except Exception:
        return "tiempo desconocido"


# ===========================================================================
# UTILIDADES DE CONSOLA
# ===========================================================================

def reveal_cache(rfc_target: str) -> None:
    """
    Descifra y muestra el historial de intentos de un RFC o de todos.
    No requiere FIEL — solo SAT_CACHE_SALT.
    """
    _validar_salt()

    archivos_enc = [f for f in CACHE_DIR.glob("*.enc")
                    if not f.name.endswith(".pending.enc")] \
                   if CACHE_DIR.exists() else []

    if not archivos_enc:
        log.info("No existe historial todavía. Aún no se ha ejecutado ninguna descarga CFDI.")
        return

    targets = archivos_enc if rfc_target == "all" else [_cache_path(rfc_target)]

    for archivo in targets:
        rfc   = archivo.stem
        cache = _leer_cache(rfc)

        log.info("")
        log.info("=" * 65)
        log.info(f"CACHÉ DESCIFRADO — {rfc}")
        log.info("=" * 65)

        if not cache:
            log.info("  Sin registros de intentos para este RFC.")
            continue

        for clave, info in sorted(cache.items()):
            try:
                inicio_str, fin_str, tipo = clave.split("|")
            except ValueError:
                continue
            intentos = info.get("intentos", 0)
            offset   = info.get("offset_segundos", 0)
            ultimo   = info.get("ultimo", "—")
            log.info(f"  Período  : {inicio_str} → {fin_str} ({tipo})")
            log.info(f"  Intentos : {intentos}")
            log.info(f"  Último   : {ultimo}")
            log.info(f"  Próximo offset : +{offset}s → inicio efectivo {inicio_str} 00:00:{offset:02d}")
            log.info("")

    log.info("=" * 65)



def mostrar_perfil(rfc: str) -> None:
    """
    Descifra y muestra el perfil guardado de un RFC.
    Útil para verificar qué rutas y configuración están guardadas.
    """
    _validar_salt()

    perfil = _leer_perfil(rfc.upper())

    log.info("")
    log.info("=" * 65)
    log.info(f"PERFIL — {rfc.upper()}")
    log.info("=" * 65)

    if not perfil:
        log.info("  Sin perfil guardado para este RFC.")
        log.info("  El perfil se crea automáticamente al completar una descarga.")
        log.info("=" * 65)
        return

    cer_path = Path(perfil.get("cer", ""))
    key_path = Path(perfil.get("key", ""))
    cer_ok   = "✔ existe" if cer_path.exists() else "✗ NO encontrado en disco"
    key_ok   = "✔ existe" if key_path.exists() else "✗ NO encontrado en disco"

    log.info(f"  .cer      : {cer_path}  [{cer_ok}]")
    log.info(f"  .key      : {key_path}  [{key_ok}]")
    log.info(f"  Output    : {perfil.get('output', '—')}")
    log.info(f"  Intervalo : {perfil.get('intervalo', '—')}s")
    log.info(f"  Guardado  : {perfil.get('guardado', '—')}")
    log.info("")

    if not cer_path.exists() or not key_path.exists():
        log.warning("  ⚠ Algunos archivos del perfil ya no existen en disco.")
        log.warning("  Ejecuta una descarga con --cer y --key para actualizar el perfil.")

    log.info("=" * 65)

def mostrar_pendientes() -> None:
    """
    Muestra todas las solicitudes pendientes de todos los RFCs.
    No requiere FIEL — solo SAT_CACHE_SALT.
    """
    _validar_salt()

    archivos_pending = list(CACHE_DIR.glob("*.pending.enc")) \
                       if CACHE_DIR.exists() else []

    if not archivos_pending:
        log.info("No hay solicitudes pendientes.")
        return

    total_pendientes = 0

    log.info("")
    log.info("=" * 65)
    log.info("SOLICITUDES PENDIENTES")
    log.info("=" * 65)

    for archivo in sorted(archivos_pending):
        rfc        = archivo.stem.replace(".pending", "")
        pendientes = _leer_pendientes(rfc)

        if not pendientes:
            continue

        for id_sol, info in sorted(pendientes.items(), key=lambda x: x[1].get("creado", "")):
            total_pendientes += 1
            creado   = info.get("creado", "—")
            transcurrido = _tiempo_transcurrido(creado)
            log.info(f"  RFC      : {info.get('rfc', rfc)}")
            log.info(f"  ID       : {id_sol}")
            log.info(f"  Período  : {info.get('inicio')} → {info.get('fin')} ({info.get('tipo')} / {info.get('solicitud')})")
            log.info(f"  Creado   : {creado} ({transcurrido})")
            log.info(f"  Salida   : {info.get('output')}")
            log.info(f"  Retomar  : --retomar {id_sol}")
            log.info("")

    if total_pendientes == 0:
        log.info("  No hay solicitudes pendientes.")
    else:
        log.info(f"  Total pendientes: {total_pendientes}")

    log.info("=" * 65)


# ===========================================================================
# VERIFICACIÓN CON TIMEOUT
# ===========================================================================

def verificar_con_timeout(fiel: Fiel, id_solicitud: str, p: dict,
                           timeout_min: int | None = None) -> list[str] | None:
    """
    Polling hasta que la solicitud esté lista o se agote el timeout.

    Retorna:
      list[str]  → lista de paquetes cuando el SAT termina (estado 3)
      None       → timeout alcanzado (solicitud sigue pendiente)

    Hace sys.exit() solo en estados terminales (5=rechazada, 6=vencida).
    Estados no terminales (timeout, red) conservan la solicitud en pendientes.
    """
    log.info(f"Verificando solicitud: {id_solicitud}")
    if timeout_min:
        log.info(f"  Timeout configurado: {timeout_min} minutos")
        log.info(f"  Consultando cada {p['intervalo']}s — máximo hasta las "
                 f"{(datetime.now() + timedelta(minutes=timeout_min)).strftime('%H:%M:%S')}")
    else:
        log.info(f"  Sin timeout — consultando cada {p['intervalo']}s hasta que el SAT responda.")

    inicio_verificacion = datetime.now()
    intento             = 0

    while True:
        intento += 1
        ahora   = datetime.now().strftime("%H:%M:%S")

        # Verificar timeout antes de consultar
        if timeout_min:
            elapsed_min = (datetime.now() - inicio_verificacion).total_seconds() / 60
            restante    = timeout_min - elapsed_min
            if restante <= 0:
                log.warning("")
                log.warning(f"  ⚠ Timeout de {timeout_min} min alcanzado tras {intento - 1} verificaciones.")
                log.warning(f"  La solicitud sigue en proceso en los servidores del SAT.")
                log.warning(f"  ID conservado en pendientes para retomar después.")
                log.warning(f"  Usa: --retomar {id_solicitud}")
                return None  # No terminal — conservar en pendientes
            log.info(f"  [{ahora}] Verificación #{intento} | Tiempo restante: {int(restante)}m...")
        else:
            log.info(f"  [{ahora}] Verificación #{intento}...")

        try:
            token        = obtener_token(fiel)
            verificacion = VerificaSolicitudDescarga(fiel).verificar_descarga(
                token, p["rfc"], id_solicitud
            )
        except Exception as e:
            log.warning(f"  ✗ Error de red en verificación #{intento}. Causa: {e}")
            log.info(f"  Reintentando en {p['intervalo']}s... (solicitud conservada en pendientes)")
            time.sleep(p["intervalo"])
            continue

        estado      = int(verificacion.get("estado_solicitud", -1))
        estado_desc = ESTADOS_SOLICITUD.get(estado, f"Desconocido ({estado})")
        num_cfdi    = verificacion.get("numero_cfdis", "0")
        paquetes    = verificacion.get("paquetes") or []

        log.info(f"  Estado: {estado} — {estado_desc} | CFDIs: {num_cfdi}")

        if estado in (1, 2):
            log.info(f"  SAT procesando. Próximo intento en {p['intervalo']}s...")
            time.sleep(p["intervalo"])

        elif estado == 3:
            log.info(f"✔ Solicitud terminada. Paquetes disponibles: {len(paquetes)}")
            for i, pk in enumerate(paquetes, 1):
                log.info(f"    [{i}] {pk}")
            return paquetes

        elif estado == 5:
            # TERMINAL — rechazada por el SAT, no tiene caso retomar
            cod = verificacion.get("codigo_estado_solicitud", "")
            log.error(f"✗ Solicitud rechazada por el SAT. Código: {cod}")
            log.error("  Esta solicitud no es recuperable.")
            log.error("  Será eliminada de pendientes automáticamente.")
            return "rechazada"  # Señal para eliminar de pendientes

        elif estado == 6:
            # TERMINAL — vencida por inactividad del SAT
            log.error("✗ Solicitud vencida. El SAT la expiró por inactividad.")
            log.error("  Esta solicitud no es recuperable.")
            log.error("  Será eliminada de pendientes automáticamente.")
            log.error("  Genera una nueva solicitud para el mismo período.")
            return "vencida"  # Señal para eliminar de pendientes

        else:
            # AMBIGUO — estado desconocido, conservar en pendientes
            log.warning(f"  ⚠ Estado desconocido ({estado_desc}) — solicitud conservada en pendientes.")
            log.warning("  Usa --pendientes para revisar o --retomar para reintentar.")
            return None


def verificar_solicitud_raw(fiel: Fiel, id_solicitud: str, p: dict) -> dict:
    """
    Polling simple sin timeout ni sys.exit. Retorna el dict raw.
    Usado en el loop mensual de Metadata para continuar ante errores.
    """
    intento = 0
    while True:
        intento += 1
        try:
            token        = obtener_token(fiel)
            verificacion = VerificaSolicitudDescarga(fiel).verificar_descarga(
                token, p["rfc"], id_solicitud
            )
        except Exception as e:
            log.warning(f"    Error en verificación #{intento}: {e}. Reintentando en {p['intervalo']}s...")
            time.sleep(p["intervalo"])
            continue

        estado = int(verificacion.get("estado_solicitud", -1))
        if estado in (1, 2):
            log.info(f"    SAT procesando... próximo intento en {p['intervalo']}s (#{intento})")
            time.sleep(p["intervalo"])
        else:
            return verificacion


# ===========================================================================
# RETOMAR SOLICITUDES PENDIENTES
# ===========================================================================

def retomar_solicitud(id_solicitud: str, fiel: Fiel, timeout_min: int | None) -> bool:
    """
    Retoma el polling de una solicitud pendiente específica por ID.
    Busca el ID en todos los archivos .pending.enc disponibles.
    Retorna True si completó exitosamente, False si sigue pendiente o falló.
    """
    _validar_salt()

    # Buscar el ID en todos los pendientes
    info = None
    rfc  = None
    for archivo in CACHE_DIR.glob("*.pending.enc"):
        rfc_candidato = archivo.stem.replace(".pending", "")
        pendientes    = _leer_pendientes(rfc_candidato)
        if id_solicitud in pendientes:
            info = pendientes[id_solicitud]
            rfc  = rfc_candidato
            break

    if not info:
        log.error(f"✗ ID no encontrado en ningún archivo de pendientes: {id_solicitud}")
        log.error("  Usa --pendientes para ver las solicitudes disponibles.")
        return False

    creado       = info.get("creado", "—")
    transcurrido = _tiempo_transcurrido(creado)

    log.info("")
    log.info("=" * 65)
    log.info(f"┌─ Retomando solicitud: {id_solicitud}")
    log.info(f"│  RFC      : {info.get('rfc', rfc)}")
    log.info(f"│  Período  : {info.get('inicio')} → {info.get('fin')} ({info.get('tipo')} / {info.get('solicitud')})")
    log.info(f"│  Creado   : {creado} ({transcurrido})")
    log.info(f"│  Salida   : {info.get('output')}")
    log.info("=" * 65)

    p_retomar = {
        "rfc":       info["rfc"],
        "tipo":      info["tipo"],
        "solicitud": info["solicitud"],
        "inicio":    date.fromisoformat(info["inicio"]),
        "fin":       date.fromisoformat(info["fin"]),
        "intervalo": info.get("intervalo", 60),
        "output":    Path(info["output"]),
    }

    resultado = verificar_con_timeout(fiel, id_solicitud, p_retomar, timeout_min)

    # --- Estado terminal: rechazada o vencida ---
    if resultado in ("rechazada", "vencida"):
        eliminar_pendiente(rfc, id_solicitud, resultado)
        log.info(f"└─ Solicitud eliminada de pendientes ({resultado}).")
        return False

    # --- Timeout o error de red: conservar pendiente ---
    if resultado is None:
        log.warning(f"└─ Solicitud {id_solicitud} sigue pendiente. Retoma con --retomar {id_solicitud}")
        return False

    # --- Terminada exitosamente: descargar y extraer ---
    paquetes    = resultado
    output_dir  = _resolver_output_retomar(p_retomar)
    nombre_base = f"{p_retomar['inicio'].strftime('%Y-%m')}-{rfc}"

    xmls_totales: list[Path] = []
    log.info(f"│  Iniciando descarga de {len(paquetes)} paquete(s)...")

    for i, id_paquete in enumerate(paquetes, 1):
        zip_path = descargar_paquete(fiel, id_paquete, rfc, output_dir, i, len(paquetes))
        if zip_path:
            nombre_paquete = nombre_base if len(paquetes) == 1 else f"{nombre_base}_{i}"
            xmls, _        = extraer_cfdi(zip_path, nombre_paquete)
            xmls_totales.extend(xmls)

    eliminar_pendiente(rfc, id_solicitud, "completada")
    log.info(f"└─ ✔ Solicitud completada. {len(xmls_totales)} XML(s) descargados.")
    return True


def _resolver_output_retomar(p: dict) -> Path:
    """Crea la carpeta de salida para una solicitud retomada."""
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    carpeta   = p["output"] / "cfdi" / fecha_hoy
    if carpeta.exists():
        log.warning(f"  Carpeta ya existe: {carpeta.resolve()} — archivos serán sobreescritos.")
    else:
        carpeta.mkdir(parents=True, exist_ok=True)
        log.info(f"  Carpeta de salida: {carpeta.resolve()}")
    return carpeta


def retomar_todas(rfc_target: str, timeout_min: int | None) -> None:
    """
    Retoma en secuencia todas las solicitudes pendientes de un RFC o de todos.
    Cada RFC construye su propia FIEL desde el perfil guardado.
    Una contraseña por RFC por sesión — no se repite si hay múltiples pendientes del mismo RFC.
    Si un RFC falla, continúa con el siguiente — no aborta todo.
    """
    _validar_salt()

    archivos_pending = list(CACHE_DIR.glob("*.pending.enc")) \
                       if CACHE_DIR.exists() else []

    if not archivos_pending:
        log.info("No hay solicitudes pendientes para retomar.")
        return

    # Filtrar por RFC si no es "all"
    if rfc_target != "all":
        archivos_pending = [f for f in archivos_pending
                            if f.stem.replace(".pending", "").upper() == rfc_target.upper()]

    if not archivos_pending:
        log.info(f"No hay solicitudes pendientes para RFC: {rfc_target}")
        return

    # Recopilar todos los IDs a procesar
    ids_a_retomar: list[tuple[str, str]] = []  # (rfc, id_solicitud)
    for archivo in sorted(archivos_pending):
        rfc_archivo = archivo.stem.replace(".pending", "")
        pendientes  = _leer_pendientes(rfc_archivo)
        for id_sol in pendientes:
            ids_a_retomar.append((rfc_archivo, id_sol))

    total       = len(ids_a_retomar)
    completadas = 0
    fallidas    = 0
    aun_pendientes: list[str] = []

    log.info("")
    log.info("=" * 65)
    log.info(f"RETOMAR SOLICITUDES PENDIENTES — {total} en total")
    log.info("=" * 65)

    # Caché de passwords por sesión — una contraseña por RFC por ejecución
    _passwords_sesion: dict[str, str] = {}

    for i, (rfc, id_sol) in enumerate(ids_a_retomar, 1):
        log.info(f"\nProcesando {i}/{total}: {id_sol} ({rfc})")

        # Reutilizar password de sesión o resolver una nueva para este RFC
        if rfc not in _passwords_sesion:
            log.info(f"  Necesaria autenticación para RFC {rfc}.")
            # Intentar perfil para --cer y --key
            perfil = _leer_perfil(rfc)
            cer_r  = Path(perfil["cer"]) if perfil.get("cer") and Path(perfil["cer"]).exists() else None
            key_r  = Path(perfil["key"]) if perfil.get("key") and Path(perfil["key"]).exists() else None

            if not cer_r or not key_r:
                log.warning(f"  ⚠ Sin perfil válido para {rfc} — saltando. Pasa --cer/--key o ejecuta una descarga primero.")
                continue

            pwd = _resolver_password(rfc, f"Contraseña de la FIEL para {rfc}")
            # Validar la contraseña cargando la FIEL
            try:
                Fiel(cer_r.read_bytes(), key_r.read_bytes(), pwd)
                _passwords_sesion[rfc] = pwd
                log.info(f"  ✔ Contraseña validada para {rfc}. Se reutilizará en esta sesión.")
            except Exception as e:
                log.error(f"  ✗ Contraseña incorrecta para {rfc}. Causa: {e}")
                log.error(f"  Saltando todas las solicitudes de {rfc} en esta sesión.")
                continue

        # Construir FIEL desde perfil + password de sesión
        perfil  = _leer_perfil(rfc)
        cer_r   = Path(perfil["cer"])
        key_r   = Path(perfil["key"])
        fiel_r  = cargar_fiel(cer_r, key_r, _passwords_sesion[rfc])

        exito = retomar_solicitud(id_sol, fiel_r, timeout_min)
        if exito:
            completadas += 1
        else:
            # Verificar si sigue en pendientes (timeout) o fue eliminada (error terminal)
            pendientes_actuales = _leer_pendientes(rfc)
            if id_sol in pendientes_actuales:
                aun_pendientes.append(id_sol)
            else:
                fallidas += 1

    duracion = 0  # calculado arriba implícitamente
    log.info("")
    log.info("=" * 65)
    log.info("RESUMEN — RETOMAR SOLICITUDES PENDIENTES")
    log.info("=" * 65)
    log.info(f"  Procesadas        : {total}")
    log.info(f"  Completadas ✔     : {completadas}")
    log.info(f"  Error terminal ✗  : {fallidas}")
    log.info(f"  Aún en proceso ⚠  : {len(aun_pendientes)}")
    log.info("=" * 65)

    if aun_pendientes:
        log.info("")
        log.info("  Solicitudes que siguen pendientes (timeout o SAT ocupado):")
        for id_sol in aun_pendientes:
            log.info(f"    • --retomar {id_sol}")
        log.info("")
        log.info("  Para retomar automáticamente puedes usar cron:")
        log.info("  0 * * * * cd /ruta/proyecto && python3.13 sat_descarga_masiva.py \\")
        log.info(f"    --retomar-todas {rfc_target} --cer ... --key ...")
    log.info("=" * 65)



# ---------------------------------------------------------------------------
# Resolución de contraseña — variable de entorno opcional por RFC
# ---------------------------------------------------------------------------

def _resolver_password(rfc: str, prompt_label: str = "") -> str:
    """
    Intenta obtener la contraseña en este orden de prioridad:
    1. Variable de entorno SAT_PASSWORD_RFC (para automatización/cron)
    2. getpass interactivo — nunca se almacena en disco

    La contraseña NUNCA se guarda en ningún archivo.
    Para automatización completa, define en .env:
      SAT_PASSWORD_VAVC930829LJ1=tu_password
    """
    env_key  = f"SAT_PASSWORD_{rfc.upper()}"
    password = os.environ.get(env_key, "").strip()

    if password:
        log.info(f"  Contraseña obtenida desde variable de entorno {env_key}.")
        return password

    label = prompt_label or f"Contraseña de la FIEL para {rfc.upper()}"
    return getpass(f"  → {label} (oculta): ")

# ===========================================================================
# PARÁMETROS
# ===========================================================================

def preguntar_parametros() -> dict:
    """
    Solicita los parámetros de forma interactiva.
    Valida rutas en tiempo real y oculta la contraseña.
    """
    log.info("=" * 65)
    log.info("MODO INTERACTIVO — Se solicitarán los parámetros necesarios")
    log.info("=" * 65)
    print()

    def pedir(prompt: str, requerido: bool = True, default: str = "") -> str:
        while True:
            sufijo = f" [{default}]" if default else ""
            valor  = input(f"  → {prompt}{sufijo}: ").strip()
            if not valor and default:
                return default
            if valor or not requerido:
                return valor
            print("    ⚠ Este campo es obligatorio.")

    rfc = pedir("RFC del contribuyente").upper()

    cer = pedir("Ruta al archivo .cer de la FIEL")
    while not Path(cer).exists():
        print(f"    ✗ No se encontró: {cer}")
        cer = pedir("Ruta al archivo .cer de la FIEL")

    key = pedir("Ruta al archivo .key de la FIEL")
    while not Path(key).exists():
        print(f"    ✗ No se encontró: {key}")
        key = pedir("Ruta al archivo .key de la FIEL")

    password = _resolver_password(rfc)

    inicio = pedir("Fecha inicio (YYYY-MM-DD)", default="2024-01-01")
    fin    = pedir("Fecha fin    (YYYY-MM-DD)", default=str(date.today()))

    tipo = ""
    while tipo not in ("emitidos", "recibidos"):
        tipo = pedir("Tipo [emitidos / recibidos]", default="recibidos").lower()

    solicitud = ""
    while solicitud not in ("CFDI", "Metadata"):
        solicitud = pedir("Tipo de solicitud [CFDI / Metadata]", default="CFDI")

    excel = ""
    if solicitud == "CFDI":
        while excel not in ("resumen", "detalle", "completo", ""):
            excel = pedir("Excel [resumen / detalle / completo] (Enter para omitir)",
                          requerido=False, default="").lower()

    timeout_str = pedir("Timeout en minutos (Enter para sin límite)", requerido=False, default="")
    output      = pedir(f"Carpeta base (Enter para usar ./results_{rfc})", requerido=False, default="")
    intervalo   = pedir("Segundos entre verificaciones", default="60")

    print()
    log.info("Parámetros capturados correctamente.")

    return {
        "rfc":       rfc,
        "cer":       Path(cer),
        "key":       Path(key),
        "password":  password,
        "inicio":    date.fromisoformat(inicio),
        "fin":       date.fromisoformat(fin),
        "tipo":      tipo,
        "solicitud": solicitud,
        "excel":     excel or None,
        "timeout":   int(timeout_str) if timeout_str.isdigit() else None,
        "output":    Path(output) if output else Path(f"./results_{rfc}"),
        "intervalo": int(intervalo),
    }


def validar_parametros(p: dict) -> None:
    """
    Valida todos los parámetros antes de tocar el SAT. Fail-fast.
    Lista todos los errores juntos y sale.
    """
    log.info("Validando parámetros antes de iniciar el proceso...")
    errores = []

    if not p["cer"].exists():
        errores.append(f"Archivo .cer no encontrado: {p['cer']}")

    if not p["key"].exists():
        errores.append(f"Archivo .key no encontrado: {p['key']}")

    if p["inicio"] > p["fin"]:
        errores.append(
            f"La fecha de inicio ({p['inicio']}) es posterior a la fecha fin ({p['fin']})"
        )

    hoy        = date.today()
    limite_sat = date(hoy.year - 6, hoy.month, hoy.day)
    if p["inicio"] < limite_sat:
        errores.append(
            f"El SAT solo permite descargar CFDI desde {limite_sat} (6 años atrás). "
            f"Tu fecha de inicio es {p['inicio']}"
        )

    if p["intervalo"] < 10:
        errores.append("El intervalo de verificación debe ser al menos 10 segundos.")

    if p.get("timeout") is not None and p["timeout"] < 5:
        errores.append("El timeout debe ser al menos 5 minutos.")

    if p.get("excel") and p["solicitud"] != "CFDI":
        errores.append("--excel solo está disponible en modo --solicitud CFDI.")

    if errores:
        log.error(f"Se encontraron {len(errores)} error(es) de validación:")
        for e in errores:
            log.error(f"  ✗ {e}")
        sys.exit(1)

    log.info("✔ Todos los parámetros son válidos.")


def resolver_output(params: dict) -> Path:
    """
    Crea results_RFC/metadata|cfdi/YYYY-MM-DD/.
    Advierte si ya existe — sobreescritura silenciosa.
    """
    modo      = "metadata" if params["solicitud"] == "Metadata" else "cfdi"
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    carpeta   = params["output"] / modo / fecha_hoy

    if carpeta.exists():
        log.warning(f"La carpeta de hoy ya existe: {carpeta.resolve()}")
        log.warning("  Los archivos existentes serán sobreescritos silenciosamente.")
    else:
        carpeta.mkdir(parents=True, exist_ok=True)
        log.info(f"Carpeta de salida creada: {carpeta.resolve()}")

    return carpeta


# ===========================================================================
# FIEL Y TOKEN
# ===========================================================================

def cargar_fiel(cer: Path, key: Path, password: str) -> Fiel:
    """
    Carga los archivos de la FIEL. Error aquí = contraseña incorrecta o archivos corruptos.
    """
    log.info("Cargando FIEL desde archivos:")
    log.info(f"  .cer → {cer}")
    log.info(f"  .key → {key}")
    try:
        fiel = Fiel(cer.read_bytes(), key.read_bytes(), password)
        log.info("✔ FIEL cargada y validada correctamente.")
        return fiel
    except Exception as e:
        log.error("✗ No se pudo cargar la FIEL.")
        log.error(f"  Causa: {e}")
        log.error("  Verifica que la contraseña sea correcta y que los archivos no estén corruptos.")
        sys.exit(1)


def obtener_token(fiel: Fiel, intento: int = 1) -> str:
    """
    Autentica contra el SAT y obtiene un token temporal (~5 min).
    Reintenta automáticamente hasta MAX_REINTENTOS_TOKEN veces.
    """
    log.info(f"Solicitando token de autenticación al SAT (intento {intento}/{MAX_REINTENTOS_TOKEN})...")
    try:
        token = Autenticacion(fiel).obtener_token()
        log.info("✔ Token obtenido. Sesión activa con el SAT.")
        return token
    except Exception as e:
        log.warning(f"  ✗ El SAT no respondió. Causa: {e}")
        if intento < MAX_REINTENTOS_TOKEN:
            log.info(f"  Reintentando en {PAUSA_ENTRE_REINTENTOS}s...")
            time.sleep(PAUSA_ENTRE_REINTENTOS)
            return obtener_token(fiel, intento + 1)
        log.error("  Se agotaron los reintentos de autenticación.")
        log.error("  Posibles causas: FIEL vencida, sin conexión o el SAT está caído.")
        sys.exit(1)


# ===========================================================================
# SOLICITUD AL SAT
# ===========================================================================

def solicitar_descarga(fiel: Fiel, token: str, p: dict,
                       dt_inicio: datetime | None = None,
                       dt_fin: datetime | None = None) -> str | None:
    """
    Envía la solicitud de descarga al SAT.
    Acepta datetime para el bypass de offset (modo CFDI).
    Retorna el ID de solicitud o None si hay error.
    """
    fecha_inicio = dt_inicio or p["inicio"]
    fecha_fin    = dt_fin    or p["fin"]

    log.info(f"  Enviando solicitud → {p['tipo']} ({p['solicitud']})")
    log.info(f"  Período efectivo  : {fecha_inicio} → {fecha_fin}")

    try:
        if p["tipo"] == "emitidos":
            cliente   = SolicitaDescargaEmitidos(fiel)
            resultado = cliente.solicitar_descarga(
                token, p["rfc"], fecha_inicio, fecha_fin,
                rfc_emisor=p["rfc"], tipo_solicitud=p["solicitud"],
            )
        else:
            cliente   = SolicitaDescargaRecibidos(fiel)
            resultado = cliente.solicitar_descarga(
                token, p["rfc"], fecha_inicio, fecha_fin,
                rfc_receptor=p["rfc"], tipo_solicitud=p["solicitud"],
                # El SAT no permite CFDI recibidos cancelados en descarga masiva
                estado_comprobante="Vigente" if p["solicitud"] == "CFDI" else None,
            )

        cod          = resultado.get("cod_estatus", "")
        id_solicitud = resultado.get("id_solicitud")
        mensaje      = resultado.get("mensaje", "")

        if not id_solicitud:
            log.warning(f"  ✗ SAT rechazó la solicitud. Código: {cod} | {mensaje}")
            return None

        log.info(f"  ✔ Solicitud aceptada. ID: {id_solicitud}")
        return id_solicitud

    except Exception as e:
        log.error(f"  ✗ Error al enviar solicitud. Causa: {e}")
        log.error("    • RFC incorrecto o FIEL no asociada a ese RFC")
        log.error("    • Token expirado — se renovará en el próximo intento")
        return None


# ===========================================================================
# DESCARGA Y EXTRACCIÓN
# ===========================================================================

def descargar_paquete(fiel: Fiel, id_paquete: str, rfc: str, output_dir: Path,
                      numero: int, total: int) -> Path | None:
    """
    Descarga un paquete ZIP del SAT (base64) y lo guarda en disco.
    Reintenta hasta MAX_REINTENTOS_DESCARGA veces.
    """
    log.info(f"  Descargando paquete {numero}/{total}: {id_paquete}")
    for intento in range(1, MAX_REINTENTOS_DESCARGA + 1):
        log.info(f"    Intento {intento}/{MAX_REINTENTOS_DESCARGA}...")
        try:
            token     = obtener_token(fiel)
            resultado = DescargaMasiva(fiel).descargar_paquete(token, rfc, id_paquete)
            zip_bytes = base64.b64decode(resultado["paquete_b64"])
            zip_path  = output_dir / f"{id_paquete}.zip"
            zip_path.write_bytes(zip_bytes)
            kb = len(zip_bytes) / 1024
            log.info(f"    ✔ Guardado: {zip_path.name} ({kb:.1f} KB)")
            return zip_path
        except Exception as e:
            log.warning(f"    ✗ Fallo en intento {intento}. Causa: {e}")
            if intento < MAX_REINTENTOS_DESCARGA:
                log.info(f"    Reintentando en {PAUSA_ENTRE_REINTENTOS}s...")
                time.sleep(PAUSA_ENTRE_REINTENTOS)
            else:
                log.error(f"  ✗ Se agotaron los reintentos para: {id_paquete}")
                return None


def extraer_metadata(zip_path: Path, nombre_destino: str) -> list[Path]:
    """
    Extrae TXT de Metadata, renombra como YYYY-MM-RFC.txt y borra el ZIP.
    """
    output_dir = zip_path.parent
    log.info(f"  Extrayendo Metadata de: {zip_path.name}")
    try:
        extraidos: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            contenido = zf.namelist()
            log.info(f"  Archivos en el paquete: {len(contenido)}")
            for i, nombre in enumerate(contenido):
                ext    = Path(nombre).suffix or ".txt"
                sufijo = f"_{i + 1}" if i > 0 else ""
                dest   = output_dir / f"{nombre_destino}{sufijo}{ext}"
                dest.write_bytes(zf.read(nombre))
                extraidos.append(dest)
                log.info(f"    → {dest.name}")
        log.info(f"  Eliminando ZIP de Metadata: {zip_path.name}...")
        zip_path.unlink()
        log.info(f"  ✔ ZIP eliminado correctamente: {zip_path.name}")
        return extraidos
    except zipfile.BadZipFile:
        log.error(f"  ✗ ZIP corrupto: {zip_path}. Elimínalo y re-ejecuta.")
        return []
    except Exception as e:
        log.error(f"  ✗ Error al extraer Metadata. Causa: {e}")
        return []


def extraer_cfdi(zip_path: Path, nombre_destino: str) -> tuple[list[Path], Path | None]:
    """
    Extrae XMLs en subcarpeta YYYY-MM-RFC/ y renombra el ZIP.
    Conserva el ZIP renombrado.
    """
    output_dir = zip_path.parent
    xml_dir    = output_dir / nombre_destino
    xml_dir.mkdir(exist_ok=True)
    log.info(f"  Extrayendo XMLs de: {zip_path.name} → {xml_dir.name}/")
    try:
        extraidos: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            log.info(f"  XMLs en el paquete: {len(xmls)}")
            for nombre in xmls:
                dest = xml_dir / nombre
                dest.write_bytes(zf.read(nombre))
                extraidos.append(dest)
        nuevo_zip = output_dir / f"{nombre_destino}.zip"
        zip_path.rename(nuevo_zip)
        log.info(f"  ✔ ZIP renombrado: {nuevo_zip.name}")
        log.info(f"  ✔ {len(extraidos)} XML(s) extraídos en: {xml_dir.name}/")
        return extraidos, nuevo_zip
    except zipfile.BadZipFile:
        log.error(f"  ✗ ZIP corrupto: {zip_path}")
        return [], None
    except Exception as e:
        log.error(f"  ✗ Error al extraer XMLs. Causa: {e}")
        return [], None


# ===========================================================================
# HELPERS — PERÍODOS Y RESUMEN METADATA
# ===========================================================================

def generar_periodos_mensuales(inicio: date, fin: date) -> list[tuple[date, date]]:
    """Divide un rango en períodos mensuales. Solo para modo Metadata."""
    periodos = []
    actual   = inicio.replace(day=1)
    while actual <= fin:
        ultimo_dia = monthrange(actual.year, actual.month)[1]
        mes_inicio = max(actual, inicio)
        mes_fin    = min(date(actual.year, actual.month, ultimo_dia), fin)
        periodos.append((mes_inicio, mes_fin))
        actual = date(actual.year + 1, 1, 1) if actual.month == 12 \
                 else date(actual.year, actual.month + 1, 1)
    return periodos


def procesar_mes_metadata(fiel: Fiel, p: dict, output_dir: Path,
                          mes_inicio: date, mes_fin: date,
                          numero: int, total: int) -> list[Path]:
    """
    Flujo completo para un mes en modo Metadata.
    Nunca hace sys.exit() — permite que el loop continúe ante 5004.
    """
    mes_num   = mes_inicio.strftime("%m")
    mes_label = f"{MESES_ES[mes_num]} {mes_inicio.year}"

    log.info("")
    log.info(f"  ┌─ [{numero}/{total}] {mes_label}  ({mes_inicio} → {mes_fin})")

    p_mes = {**p, "inicio": mes_inicio, "fin": mes_fin, "output": output_dir}

    try:
        token        = obtener_token(fiel)
        id_solicitud = solicitar_descarga(fiel, token, p_mes)

        if not id_solicitud:
            log.info(f"  └─ {mes_label}: Sin actividad — continuando.")
            return []

        verificacion = verificar_solicitud_raw(fiel, id_solicitud, p_mes)
        estado       = int(verificacion.get("estado_solicitud", -1))
        cod          = verificacion.get("codigo_estado_solicitud", "")
        num_cfdi     = int(verificacion.get("numero_cfdis", 0) or 0)
        paquetes     = verificacion.get("paquetes") or []

        if estado == 5 and cod == "5004":
            log.info(f"  └─ {mes_label}: Sin CFDIs — continuando.")
            return []
        if estado == 5:
            log.warning(f"  └─ {mes_label}: Rechazado (código {cod}) — continuando.")
            return []
        if estado != 3:
            log.warning(f"  └─ {mes_label}: Estado inesperado {estado} — continuando.")
            return []

        log.info(f"  │  ✔ {num_cfdi} CFDI(s) | {len(paquetes)} paquete(s)")

        archivos: list[Path] = []
        for i, id_paquete in enumerate(paquetes, 1):
            zip_path = descargar_paquete(fiel, id_paquete, p["rfc"], output_dir, i, len(paquetes))
            if zip_path:
                nombre    = f"{mes_inicio.strftime('%Y-%m')}-{p['rfc']}"
                extraidos = extraer_metadata(zip_path, nombre)
                archivos.extend(extraidos)

        log.info(f"  └─ {mes_label}: {len(archivos)} archivo(s) guardados. ✔")
        return archivos

    except Exception as e:
        log.warning(f"  └─ {mes_label}: Error inesperado ({e}) — continuando.")
        return []


def generar_resumen_metadata(archivos: list[Path], params: dict) -> list[str]:
    """
    Lee los TXT de Metadata y genera resumen legible para humanos.
    Columnas SAT (separadas por ~):
    UUID~RfcEmisor~NombreEmisor~RfcReceptor~NombreReceptor~Pac
    ~FechaEmision~FechaCertSat~Monto~EfectoComprobante~Estatus~FechaCancelacion
    """
    if not archivos:
        return ["  Sin archivos de Metadata para resumir."]

    total_cfdis = 0
    total_monto = 0.0
    por_mes: dict[str, dict] = {}
    emisores: dict[str, int] = {}

    for archivo in archivos:
        if archivo.suffix.lower() != ".txt":
            continue
        try:
            lineas = archivo.read_text(encoding="utf-8", errors="ignore").splitlines()
            datos  = [l for l in lineas[1:] if l.strip()]
            partes    = archivo.stem.split("-")
            anio      = partes[0] if len(partes) >= 1 else "????"
            mes_num   = partes[1] if len(partes) >= 2 else "??"
            clave_mes = f"{anio}-{mes_num}"
            mes_label = f"{MESES_ES.get(mes_num, mes_num)} {anio}"
            mes_cfdis = 0
            mes_monto = 0.0

            for linea in datos:
                cols = linea.split("~")
                if len(cols) < 9:
                    continue
                mes_cfdis   += 1
                total_cfdis += 1
                try:
                    monto        = float(cols[8].replace(",", "").strip())
                    mes_monto   += monto
                    total_monto += monto
                except ValueError:
                    pass
                rfc_emisor    = cols[1].strip() if len(cols) > 1 else "?"
                nombre_emisor = cols[2].strip() if len(cols) > 2 else "?"
                clave_emisor  = f"{rfc_emisor} — {nombre_emisor}"
                emisores[clave_emisor] = emisores.get(clave_emisor, 0) + 1

            por_mes[clave_mes] = {"label": mes_label, "cfdis": mes_cfdis, "monto": mes_monto}
        except Exception as e:
            log.warning(f"  No se pudo leer: {archivo.name}. Causa: {e}")

    if total_cfdis == 0:
        return ["  No se encontraron registros legibles en los archivos de Metadata."]

    tipo_label = "emitidas" if params["tipo"] == "emitidos" else "recibidas"
    lineas: list[str] = []
    lineas.append(f"  El RFC {params['rfc']} tiene {total_cfdis} factura(s) {tipo_label}")
    lineas.append(f"  en el período {params['inicio']} → {params['fin']}.")
    lineas.append(f"  Monto total acumulado: ${total_monto:,.2f} MXN")
    lineas.append("")
    lineas.append("  Desglose por mes:")
    for clave in sorted(por_mes.keys()):
        info = por_mes[clave]
        lineas.append(
            f"    • {info['label']:<20} {info['cfdis']:>5} CFDI(s)   "
            f"${info['monto']:>14,.2f} MXN"
        )
    if emisores:
        top = sorted(emisores.items(), key=lambda x: x[1], reverse=True)[:5]
        lineas.append("")
        lineas.append("  Top 5 emisores/receptores más frecuentes:")
        for nombre, cantidad in top:
            lineas.append(f"    • {cantidad:>4}x  {nombre}")
    return lineas


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> dict | None:
    """
    Retorna dict con parámetros o None para modo interactivo.
    Los modos utilitarios (--reveal-cache, --pendientes, --retomar, --retomar-todas)
    se despachan aquí antes de cualquier otra lógica.
    """
    if len(sys.argv) == 1:
        return None

    p = argparse.ArgumentParser(description="Descarga masiva de CFDI (XML) del SAT")

    # Modos utilitarios
    p.add_argument("--reveal-cache",   metavar="RFC|all",  default=None,
                   help="Descifra y muestra el historial de intentos.")
    p.add_argument("--perfil",         metavar="RFC",       default=None,
                   help="Muestra el perfil guardado de un RFC (rutas FIEL, output, intervalo).")
    p.add_argument("--pendientes",     action="store_true", default=False,
                   help="Muestra todas las solicitudes pendientes.")
    p.add_argument("--retomar",        metavar="ID",        default=None,
                   help="Retoma el polling de una solicitud específica por ID.")
    p.add_argument("--retomar-todas",  metavar="RFC|all",   default=None,
                   help="Retoma en secuencia todas las solicitudes pendientes.")

    # Parámetros de descarga
    p.add_argument("--rfc",       default=None)
    p.add_argument("--cer",       type=Path, default=None)
    p.add_argument("--key",       type=Path, default=None)
    p.add_argument("--password",  default=None,
                   help="Contraseña FIEL. Si se omite, se pedirá de forma segura.")
    p.add_argument("--inicio",    type=date.fromisoformat, default=None)
    p.add_argument("--fin",       type=date.fromisoformat, default=None)
    p.add_argument("--tipo",      choices=["emitidos", "recibidos"], default="recibidos")
    p.add_argument("--solicitud", choices=["CFDI", "Metadata"],      default="CFDI")
    p.add_argument("--excel",     choices=["resumen", "detalle", "completo"], default=None)
    p.add_argument("--timeout",   type=int, default=None,
                   help="Minutos máximos de espera al SAT (default: sin límite).")
    p.add_argument("--output",    type=Path, default=None)
    p.add_argument("--intervalo", type=int,  default=60)

    args = p.parse_args()

    # --- Modo: revelar caché ---
    if args.reveal_cache:
        _validar_salt()
        reveal_cache(args.reveal_cache)
        sys.exit(0)

    # --- Modo: ver perfil de RFC ---
    if args.perfil:
        mostrar_perfil(args.perfil)
        sys.exit(0)

    # --- Modo: ver pendientes ---
    if args.pendientes:
        _validar_salt()
        mostrar_pendientes()
        sys.exit(0)

    # --- Modo: retomar o retomar-todas (requieren FIEL) ---
    if args.retomar or args.retomar_todas:
        _validar_salt()

        # Intentar obtener RFC del pending para leer perfil
        rfc_retomar = None
        if args.retomar:
            # Buscar el RFC asociado al ID en los pendientes
            for archivo in CACHE_DIR.glob("*.pending.enc") if CACHE_DIR.exists() else []:
                rfc_candidato = archivo.stem.replace(".pending", "")
                pendientes    = _leer_pendientes(rfc_candidato)
                if args.retomar in pendientes:
                    rfc_retomar = rfc_candidato
                    break
        elif args.retomar_todas and args.retomar_todas != "all":
            rfc_retomar = args.retomar_todas.upper()

        # Completar --cer y --key desde perfil si están disponibles
        if rfc_retomar and not args.cer:
            perfil = _leer_perfil(rfc_retomar)
            if perfil.get("cer") and Path(perfil["cer"]).exists():
                args.cer = Path(perfil["cer"])
                log.info(f"  .cer tomado del perfil de {rfc_retomar}: {args.cer}")
            if perfil.get("key") and Path(perfil["key"]).exists():
                args.key = Path(perfil["key"])
                log.info(f"  .key tomado del perfil de {rfc_retomar}: {args.key}")

        errores_fiel = []
        if not args.cer:
            errores_fiel.append("--cer es requerido (o configura el perfil corriendo una descarga primero)")
        if not args.key:
            errores_fiel.append("--key es requerido (o configura el perfil corriendo una descarga primero)")
        if args.cer and not args.cer.exists():
            errores_fiel.append(f"Archivo .cer no encontrado: {args.cer}")
        if args.key and not args.key.exists():
            errores_fiel.append(f"Archivo .key no encontrado: {args.key}")
        if errores_fiel:
            for e in errores_fiel:
                log.error(f"  ✗ {e}")
            sys.exit(1)

        password = args.password or _resolver_password(
            rfc_retomar or "FIEL",
            f"Contraseña de la FIEL{f' para {rfc_retomar}' if rfc_retomar else ''}"
        )

        fiel = cargar_fiel(args.cer, args.key, password)

        if args.retomar:
            retomar_solicitud(args.retomar, fiel, args.timeout)
        else:
            retomar_todas(args.retomar_todas, args.timeout)
        sys.exit(0)

    # --- Modo: descarga normal ---
    # Validar RFC primero — es necesario para leer el perfil
    if not args.rfc:
        p.error("--rfc es requerido")

    rfc = args.rfc.upper()

    # Intentar completar args faltantes desde el perfil guardado
    perfil = _leer_perfil(rfc)
    if perfil:
        if not args.cer and perfil.get("cer"):
            cer_path = Path(perfil["cer"])
            if cer_path.exists():
                args.cer = cer_path
                log.info(f"  .cer tomado del perfil: {cer_path}")
            else:
                log.warning(f"  .cer guardado en perfil no existe en disco: {cer_path}")
                log.warning("  Pasa --cer explícitamente para actualizar el perfil.")

        if not args.key and perfil.get("key"):
            key_path = Path(perfil["key"])
            if key_path.exists():
                args.key = key_path
                log.info(f"  .key tomado del perfil: {key_path}")
            else:
                log.warning(f"  .key guardado en perfil no existe en disco: {key_path}")
                log.warning("  Pasa --key explícitamente para actualizar el perfil.")

        if not args.output and perfil.get("output"):
            args.output = Path(perfil["output"])
            log.info(f"  output tomado del perfil: {args.output}")

        if args.intervalo == 60 and perfil.get("intervalo"):
            args.intervalo = perfil["intervalo"]
            log.info(f"  intervalo tomado del perfil: {args.intervalo}s")

    # Validar faltantes después de completar desde perfil
    faltantes = [f"--{f}" for f, v in [
        ("cer", args.cer), ("key", args.key),
        ("inicio", args.inicio), ("fin", args.fin)
    ] if v is None]

    if faltantes:
        if perfil:
            p.error(f"Argumentos requeridos (no encontrados en perfil): {', '.join(faltantes)}")
        else:
            p.error(f"Argumentos requeridos (sin perfil guardado para {rfc}): {', '.join(faltantes)}")

    password = args.password or _resolver_password(rfc)

    output = args.output if args.output else Path(f"./results_{rfc}")

    return {
        "rfc":       rfc,
        "cer":       args.cer,
        "key":       args.key,
        "password":  password,
        "inicio":    args.inicio,
        "fin":       args.fin,
        "tipo":      args.tipo,
        "solicitud": args.solicitud,
        "excel":     args.excel,
        "timeout":   args.timeout,
        "output":    output,
        "intervalo": args.intervalo,
    }


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    inicio_proceso = datetime.now()

    log.info("=" * 65)
    log.info("SAT — DESCARGA MASIVA DE CFDI (XML)")
    log.info(f"Inicio: {inicio_proceso.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    params = parse_args() or preguntar_parametros()

    _validar_salt()
    validar_parametros(params)

    output_dir = resolver_output(params)
    fiel       = cargar_fiel(params["cer"], params["key"], params["password"])

    # -----------------------------------------------------------------------
    # Modo Metadata — procesa mes a mes, sin caché, sin riesgo de bloqueo
    # -----------------------------------------------------------------------
    if params["solicitud"] == "Metadata":
        periodos = generar_periodos_mensuales(params["inicio"], params["fin"])
        total    = len(periodos)

        log.info("")
        log.info(f"Modo METADATA — {total} mes(es) a procesar")
        log.info(f"  RFC        : {params['rfc']}")
        log.info(f"  Tipo       : {params['tipo']}")
        log.info(f"  Rango      : {params['inicio']} → {params['fin']}")
        log.info(f"  Salida     : {output_dir.resolve()}")
        log.info("  ZIPs se eliminarán automáticamente tras extraer cada TXT.")
        log.info("  El script avanzará si un mes no tiene CFDIs (código 5004).")

        archivos_totales: list[Path] = []
        meses_con_datos = 0
        meses_sin_datos = 0

        for i, (mes_inicio, mes_fin) in enumerate(periodos, 1):
            archivos = procesar_mes_metadata(
                fiel, params, output_dir, mes_inicio, mes_fin, i, total
            )
            if archivos:
                meses_con_datos += 1
                archivos_totales.extend(archivos)
            else:
                meses_sin_datos += 1

        # Guardar perfil solo si se descargó al menos un archivo de Metadata
        if archivos_totales:
            _escribir_perfil(params["rfc"], params["cer"], params["key"],
                             params["output"], params["intervalo"])
        else:
            log.warning("  ⚠ No se descargó ningún archivo — perfil no actualizado.")

        duracion        = int((datetime.now() - inicio_proceso).total_seconds())
        resumen_legible = generar_resumen_metadata(archivos_totales, params)

        log.info("")
        log.info("=" * 65)
        log.info("RESUMEN FINAL — DESCARGA MASIVA METADATA")
        log.info("=" * 65)
        log.info(f"  RFC                  : {params['rfc']}")
        log.info(f"  Tipo                 : {params['tipo']}")
        log.info(f"  Rango procesado      : {params['inicio']} → {params['fin']}")
        log.info(f"  Meses procesados     : {total}")
        log.info(f"  Meses con CFDIs      : {meses_con_datos}")
        log.info(f"  Meses sin actividad  : {meses_sin_datos}")
        log.info(f"  Archivos descargados : {len(archivos_totales)}")
        log.info(f"  Carpeta de salida    : {output_dir.resolve()}")
        log.info(f"  Duración total       : {duracion // 60}m {duracion % 60}s")
        log.info(f"  Log guardado en      : sat_descarga.log")
        log.info("=" * 65)
        if resumen_legible:
            log.info("")
            log.info("CONTENIDO DE LOS METADATA DESCARGADOS")
            log.info("=" * 65)
            for linea in resumen_legible:
                log.info(linea)
            log.info("=" * 65)

    # -----------------------------------------------------------------------
    # Modo CFDI — bypass offset + pendientes + timeout
    # -----------------------------------------------------------------------
    else:
        timeout_min = params.get("timeout")

        log.info("")
        log.info("Modo CFDI — procesando rango completo")
        log.info(f"  RFC        : {params['rfc']}")
        log.info(f"  Tipo       : {params['tipo']}")
        log.info(f"  Rango      : {params['inicio']} → {params['fin']}")
        log.info(f"  Salida     : {output_dir.resolve()}")
        log.info(f"  Timeout    : {f'{timeout_min} min' if timeout_min else 'sin límite'}")

        # Consultar historial y calcular offset
        historial        = consultar_historial(params["rfc"], params["inicio"], params["fin"], params["tipo"])
        intentos_previos = historial["intentos"]
        offset_seg       = historial["offset_segundos"]

        if intentos_previos == 0:
            log.info("  Caché: primera solicitud para este período.")
        else:
            log.info(f"  Caché: {intentos_previos} intento(s) previo(s) detectado(s).")
            log.info(f"  Bypass activado: offset de +{offset_seg}s para evitar bloqueo SAT.")

        offset_actual     = registrar_intento(params["rfc"], params["inicio"], params["fin"], params["tipo"])
        dt_inicio, dt_fin = fechas_con_offset(params["inicio"], params["fin"], offset_actual)

        log.info(f"  Período efectivo : {dt_inicio} → {dt_fin}")

        token        = obtener_token(fiel)
        id_solicitud = solicitar_descarga(fiel, token, params, dt_inicio, dt_fin)

        if not id_solicitud:
            log.error("✗ No se pudo obtener un ID de solicitud del SAT.")
            sys.exit(1)

        # Registrar como pendiente inmediatamente después de la aceptación
        agregar_pendiente(params["rfc"], id_solicitud, params, dt_inicio, dt_fin)

        # Verificar con timeout
        resultado = verificar_con_timeout(fiel, id_solicitud, params, timeout_min)

        # Estado terminal — rechazada o vencida
        if resultado in ("rechazada", "vencida"):
            eliminar_pendiente(params["rfc"], id_solicitud, resultado)
            log.error(f"✗ Solicitud {resultado}. No es posible recuperarla.")
            sys.exit(1)

        # Timeout — solicitud conservada en pendientes
        if resultado is None:
            log.warning("")
            log.warning("Proceso detenido por timeout.")
            log.warning(f"La solicitud sigue registrada en pendientes.")
            log.warning(f"Para retomar cuando el SAT responda:")
            log.warning(f"  python3.13 sat_descarga_masiva.py --retomar {id_solicitud} \\")
            log.warning(f"    --cer {params['cer']} --key {params['key']}")
            log.warning("")
            log.warning("O para revisar todos los pendientes:")
            log.warning("  python3.13 sat_descarga_masiva.py --pendientes")
            sys.exit(0)

        # Terminada — descargar y extraer
        paquetes    = resultado
        nombre_base = f"{params['inicio'].strftime('%Y-%m')}-{params['rfc']}"
        xmls_totales: list[Path] = []

        log.info(f"Iniciando descarga de {len(paquetes)} paquete(s)...")

        for i, id_paquete in enumerate(paquetes, 1):
            zip_path = descargar_paquete(
                fiel, id_paquete, params["rfc"], output_dir, i, len(paquetes)
            )
            if zip_path:
                nombre_paquete = nombre_base if len(paquetes) == 1 else f"{nombre_base}_{i}"
                xmls, _        = extraer_cfdi(zip_path, nombre_paquete)
                xmls_totales.extend(xmls)

        # Eliminar de pendientes
        eliminar_pendiente(params["rfc"], id_solicitud, "completada")

        # Guardar perfil solo si se descargó al menos un XML exitosamente
        if xmls_totales:
            _escribir_perfil(params["rfc"], params["cer"], params["key"],
                             params["output"], params["intervalo"])
        else:
            log.warning("  ⚠ No se descargó ningún XML — perfil no actualizado.")

        duracion = int((datetime.now() - inicio_proceso).total_seconds())
        log.info("")
        log.info("=" * 65)
        log.info("RESUMEN FINAL — DESCARGA MASIVA CFDI")
        log.info("=" * 65)
        log.info(f"  RFC                  : {params['rfc']}")
        log.info(f"  Tipo                 : {params['tipo']}")
        log.info(f"  Rango solicitado     : {params['inicio']} → {params['fin']}")
        log.info(f"  Período efectivo     : {dt_inicio} → {dt_fin}")
        log.info(f"  Intento #            : {intentos_previos + 1} (offset: +{offset_actual}s)")
        log.info(f"  XMLs descargados     : {len(xmls_totales)}")
        log.info(f"  Carpeta de salida    : {output_dir.resolve()}")
        log.info(f"  Duración total       : {duracion // 60}m {duracion % 60}s")
        log.info(f"  Log guardado en      : sat_descarga.log")
        if params.get("excel"):
            log.info(f"  Excel solicitado     : {params['excel']} (pendiente de implementar)")
        log.info("=" * 65)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("")
        log.warning("Proceso interrumpido por el usuario (Ctrl+C).")
        log.warning("Los archivos descargados hasta ahora siguen en la carpeta de salida.")
        log.warning("Las solicitudes CFDI activas siguen registradas en pendientes.")
        log.warning("Usa --pendientes para verlas o --retomar ID para continuar.")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Error inesperado no controlado: {e}", exc_info=True)
        log.critical("Revisa sat_descarga.log para el stack trace completo.")
        sys.exit(1)