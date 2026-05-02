"""
sat_client.py
-------------
Comunicacion con el Web Service oficial del SAT v1.5.
Maneja autenticacion, solicitud de descarga, verificacion de estado y descarga de paquetes.
No tiene conocimiento del cache ni del sistema de archivos — solo habla con el SAT.
"""

import base64
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from cfdiclient import (
    Autenticacion,
    DescargaMasiva,
    Fiel,
    SolicitaDescargaEmitidos,
    SolicitaDescargaRecibidos,
    VerificaSolicitudDescarga,
)

from config import (
    MAX_DOWNLOAD_RETRIES,
    MAX_TOKEN_RETRIES,
    RETRY_PAUSE_SEC,
    SAT_ESTADOS,
    log,
)


# ===========================================================================
# FIEL
# ===========================================================================

def load_fiel(cer: Path, key: Path, password: str) -> Fiel:
    """
    Carga los archivos de la FIEL y construye el objeto Fiel.
    Un error aqui suele indicar contrasena incorrecta o archivos corruptos.
    """
    log.info("Cargando FIEL desde archivos:")
    log.info(f"  .cer -> {cer}")
    log.info(f"  .key -> {key}")
    try:
        fiel = Fiel(cer.read_bytes(), key.read_bytes(), password)
        log.info("  FIEL cargada y validada correctamente.")
        return fiel
    except Exception as e:
        log.error("  X No se pudo cargar la FIEL.")
        log.error(f"    Causa: {e}")
        log.error("    Verifica que la contrasena sea correcta y los archivos no esten corruptos.")
        raise


# ===========================================================================
# Token de autenticacion
# ===========================================================================

def get_token(fiel: Fiel, attempt: int = 1) -> str:
    """
    Autentica contra el SAT y obtiene un token temporal (~5 min).
    Reintenta automaticamente hasta MAX_TOKEN_RETRIES veces ante fallos de red.
    """
    log.info(f"Solicitando token de autenticacion al SAT (intento {attempt}/{MAX_TOKEN_RETRIES})...")
    try:
        token = Autenticacion(fiel).obtener_token()
        log.info("  Token obtenido. Sesion activa con el SAT.")
        return token
    except Exception as e:
        log.warning(f"  ! El SAT no respondio la autenticacion. Causa: {e}")
        if attempt < MAX_TOKEN_RETRIES:
            log.info(f"  Reintentando en {RETRY_PAUSE_SEC}s...")
            time.sleep(RETRY_PAUSE_SEC)
            return get_token(fiel, attempt + 1)
        log.error("  Se agotaron los reintentos de autenticacion.")
        log.error("  Posibles causas: FIEL vencida, sin conexion o el SAT esta caido.")
        raise


# ===========================================================================
# Offset de fechas — bypass para evitar bloqueo SAT (error 5002)
# ===========================================================================

def apply_date_offset(start: date, end: date,
                      offset_sec: int) -> tuple[datetime, datetime]:
    """
    Convierte date a datetime aplicando offset en segundos al inicio.
    Cada solicitud usa un timestamp ligeramente diferente para evitar
    que el SAT lo considere duplicado y bloquee el periodo permanentemente.

    offset 0 -> 2025-01-01 00:00:00
    offset 1 -> 2025-01-01 00:00:01
    offset 2 -> 2025-01-01 00:00:02
    """
    dt_start = datetime(start.year, start.month, start.day) + timedelta(seconds=offset_sec)
    dt_end   = datetime(end.year, end.month, end.day, 23, 59, 59)
    return dt_start, dt_end


# ===========================================================================
# Solicitud de descarga
# ===========================================================================

def request_download(fiel: Fiel, token: str, params: dict,
                     dt_start: datetime | None = None,
                     dt_end: datetime | None = None) -> str | None:
    """
    Envia la solicitud de descarga al SAT para un periodo dado.
    Acepta datetime para el bypass de offset (modo CFDI).
    Retorna el ID de solicitud o None si hay error.

    ADVERTENCIA CFDI: El bypass de offset maneja el bloqueo automaticamente.
    Metadata: no tiene restriccion de intentos — no usa offset.
    """
    start = dt_start or params["inicio"]
    end   = dt_end   or params["fin"]

    log.info(f"  Enviando solicitud -> {params['tipo']} ({params['solicitud']})")
    log.info(f"  Periodo efectivo  : {start} -> {end}")

    try:
        if params["tipo"] == "emitidos":
            client = SolicitaDescargaEmitidos(fiel)
            result = client.solicitar_descarga(
                token, params["rfc"], start, end,
                rfc_emisor=params["rfc"],
                tipo_solicitud=params["solicitud"],
            )
        else:
            client = SolicitaDescargaRecibidos(fiel)
            result = client.solicitar_descarga(
                token, params["rfc"], start, end,
                rfc_receptor=params["rfc"],
                tipo_solicitud=params["solicitud"],
                # El SAT no permite CFDI recibidos cancelados en descarga masiva
                estado_comprobante="Vigente" if params["solicitud"] == "CFDI" else None,
            )

        cod        = result.get("cod_estatus", "")
        request_id = result.get("id_solicitud")
        mensaje    = result.get("mensaje", "")

        if not request_id:
            log.warning(f"  ! SAT rechazo la solicitud. Codigo: {cod} | {mensaje}")
            return None

        log.info(f"  Solicitud aceptada. ID: {request_id}")
        return request_id

    except Exception as e:
        log.error(f"  X Error al enviar solicitud. Causa: {e}")
        log.error("    RFC incorrecto o FIEL no asociada a ese RFC")
        log.error("    Token expirado — se renovara en el proximo intento")
        return None


# ===========================================================================
# Verificacion con timeout — para flujo CFDI
# ===========================================================================

def verify_with_timeout(fiel: Fiel, request_id: str, params: dict,
                        timeout_min: int | None = None) -> list[str] | str | None:
    """
    Polling hasta que la solicitud este lista o se agote el timeout.

    Retorna:
      list[str]    -> lista de paquetes cuando el SAT termina (estado 3)
      'rechazada'  -> estado terminal, eliminar de pendientes
      'vencida'    -> estado terminal, eliminar de pendientes
      None         -> timeout alcanzado, solicitud conservada en pendientes
    """
    log.info(f"Verificando solicitud: {request_id}")
    if timeout_min:
        log.info(f"  Timeout configurado: {timeout_min} minutos")
        deadline = datetime.now().timestamp() + timeout_min * 60
    else:
        log.info(f"  Sin timeout — consultando cada {params['intervalo']}s hasta que el SAT responda.")
        deadline = None

    attempt = 0
    while True:
        attempt += 1
        now     = datetime.now().strftime("%H:%M:%S")

        if deadline:
            remaining = (deadline - datetime.now().timestamp()) / 60
            if remaining <= 0:
                log.warning("")
                log.warning(f"  ! Timeout de {timeout_min} min alcanzado tras {attempt - 1} verificaciones.")
                log.warning(f"  La solicitud sigue en proceso en los servidores del SAT.")
                log.warning(f"  ID conservado en pendientes. Usa: --retomar {request_id}")
                return None
            log.info(f"  [{now}] Verificacion #{attempt} | Tiempo restante: {int(remaining)}m...")
        else:
            log.info(f"  [{now}] Verificacion #{attempt}...")

        try:
            token        = get_token(fiel)
            verification = VerificaSolicitudDescarga(fiel).verificar_descarga(
                token, params["rfc"], request_id
            )
        except Exception as e:
            log.warning(f"  ! Error de red en verificacion #{attempt}. Causa: {e}")
            log.info(f"  Reintentando en {params['intervalo']}s... (solicitud conservada en pendientes)")
            time.sleep(params["intervalo"])
            continue

        estado      = int(verification.get("estado_solicitud", -1))
        estado_desc = SAT_ESTADOS.get(estado, f"Desconocido ({estado})")
        num_cfdi    = verification.get("numero_cfdis", "0")
        paquetes    = verification.get("paquetes") or []

        log.info(f"  Estado: {estado} — {estado_desc} | CFDIs: {num_cfdi}")

        if estado in (1, 2):
            log.info(f"  SAT procesando. Proximo intento en {params['intervalo']}s...")
            time.sleep(params["intervalo"])

        elif estado == 3:
            log.info(f"  Solicitud terminada. Paquetes disponibles: {len(paquetes)}")
            for i, pk in enumerate(paquetes, 1):
                log.info(f"    [{i}] {pk}")
            return paquetes

        elif estado == 5:
            cod = verification.get("codigo_estado_solicitud", "")
            log.error(f"  X Solicitud rechazada por el SAT. Codigo: {cod}")
            log.error("    Esta solicitud no es recuperable.")
            return "rechazada"

        elif estado == 6:
            log.error("  X Solicitud vencida. El SAT la expiro por inactividad.")
            log.error("    Esta solicitud no es recuperable.")
            log.error("    Genera una nueva solicitud para el mismo periodo.")
            return "vencida"

        else:
            log.warning(f"  ! Estado desconocido ({estado_desc}) — solicitud conservada en pendientes.")
            log.warning("    Usa --pendientes para revisar o --retomar para reintentar.")
            return None


def verify_raw(fiel: Fiel, request_id: str, params: dict) -> dict:
    """
    Polling simple sin timeout ni sys.exit. Retorna el dict raw del SAT.
    Usado en el loop mensual de Metadata para continuar ante errores.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            token        = get_token(fiel)
            verification = VerificaSolicitudDescarga(fiel).verificar_descarga(
                token, params["rfc"], request_id
            )
        except Exception as e:
            log.warning(f"    Error en verificacion #{attempt}: {e}. Reintentando en {params['intervalo']}s...")
            time.sleep(params["intervalo"])
            continue

        estado = int(verification.get("estado_solicitud", -1))
        if estado in (1, 2):
            log.info(f"    SAT procesando... proximo intento en {params['intervalo']}s (#{attempt})")
            time.sleep(params["intervalo"])
        else:
            return verification


# ===========================================================================
# Descarga de paquetes ZIP
# ===========================================================================

def download_package(fiel: Fiel, package_id: str, rfc: str,
                     output_dir: Path, number: int, total: int) -> Path | None:
    """
    Descarga un paquete ZIP del SAT (en base64) y lo guarda en disco.
    Reintenta hasta MAX_DOWNLOAD_RETRIES veces ante fallos de red o token expirado.
    Retorna la ruta al ZIP guardado, o None si fallo tras todos los reintentos.
    """
    log.info(f"  Descargando paquete {number}/{total}: {package_id}")

    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        log.info(f"    Intento {attempt}/{MAX_DOWNLOAD_RETRIES}...")
        try:
            token  = get_token(fiel)
            result = DescargaMasiva(fiel).descargar_paquete(token, rfc, package_id)

            zip_bytes = base64.b64decode(result["paquete_b64"])
            zip_path  = output_dir / f"{package_id}.zip"
            zip_path.write_bytes(zip_bytes)

            kb = len(zip_bytes) / 1024
            log.info(f"    Guardado: {zip_path.name} ({kb:.1f} KB)")
            return zip_path

        except Exception as e:
            log.warning(f"    ! Fallo en intento {attempt}. Causa: {e}")
            if attempt < MAX_DOWNLOAD_RETRIES:
                log.info(f"    Reintentando en {RETRY_PAUSE_SEC}s...")
                time.sleep(RETRY_PAUSE_SEC)
            else:
                log.error(f"  X Se agotaron los reintentos para: {package_id}")
                log.error("    Este paquete se omitira. Re-ejecuta el script para reintentarlo.")
                return None