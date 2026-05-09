"""
SAT Descarga Masiva de CFDI (XML)
==================================
Requiere:
  pip install cfdiclient openpyxl python-dotenv --target ./libs
 
Setup inicial:
  cp .env.example .env
  # Editar .env y definir SAT_CACHE_SALT
 
Modo interactivo (sin argumentos):
  python descarga_masiva.py

Modo CLI — descarga:
  python descarga_masiva.py \
    --rfc TURF010101ABC \
    --cer fiel.cer \
    --key fiel.key \
    --inicio 2024-01-01 \
    --fin 2024-12-31 \
    --tipo recibidos \
    --solicitud Metadata
 
Modo utilidad — revelar caché:
  python descarga_masiva.py --reveal-cache TURF010101ABC
  python descarga_masiva.py --reveal-cache all
 
Opcionales:
  --solicitud  CFDI|Metadata            (default: CFDI)
  --excel      resumen|detalle|completo (solo con CFDI)
  --intervalo  60                       segundos entre verificaciones
  --output     ruta                     carpeta base (default: ./results_RFC)
 
Estructura de salida:
  results_RFC/
  └── YYYY-MM-DD/
      ├── YYYY-MM-RFC.txt    (Metadata — ZIP borrado tras extraer)
      ├── YYYY-MM-RFC.zip    (CFDI — renombrado, conservado)
      └── YYYY-MM-RFC/       (CFDI — XMLs extraídos)
 
  .cache/
  └── VAVC930829LJ1.enc      (historial encriptado por RFC)
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
    pass  # Si no está instalado, se usarán variables de entorno del sistema
 
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
 
 
# ===========================================================================
# CACHÉ ENCRIPTADO — Fernet + PBKDF2 + SAT_CACHE_SALT desde .env
# ===========================================================================
 
def _validar_salt() -> bytes:
    """
    Lee SAT_CACHE_SALT del entorno. Falla con instrucciones claras si no existe.
    El salt nunca se guarda en código — viene de .env o variable de entorno.
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
    return CACHE_DIR / f"{rfc.upper()}.enc"
 
 
def _leer_cache(rfc: str) -> dict:
    """
    Lee y descifra el historial del RFC desde .cache/RFC.enc.
    Retorna dict vacío si no existe o está corrupto.
    """
    from cryptography.fernet import Fernet, InvalidToken
 
    ruta = _cache_path(rfc)
    if not ruta.exists():
        return {}
 
    try:
        clave   = _derivar_clave_fernet(rfc)
        f       = Fernet(clave)
        datos   = f.decrypt(ruta.read_bytes())
        return json.loads(datos.decode())
    except InvalidToken:
        log.warning(f"  ⚠ Caché de {rfc} corrupto o modificado manualmente — se reiniciará.")
        return {}
    except Exception as e:
        log.warning(f"  ⚠ No se pudo leer el caché de {rfc}. Causa: {e}")
        return {}
 
 
def _escribir_cache(rfc: str, datos: dict) -> None:
    """
    Cifra y guarda el historial del RFC en .cache/RFC.enc.
    """
    from cryptography.fernet import Fernet
 
    CACHE_DIR.mkdir(exist_ok=True)
    try:
        clave  = _derivar_clave_fernet(rfc)
        f      = Fernet(clave)
        cifrado = f.encrypt(json.dumps(datos, ensure_ascii=False).encode())
        _cache_path(rfc).write_bytes(cifrado)
    except Exception as e:
        log.warning(f"  ⚠ No se pudo guardar el caché de {rfc}. Causa: {e}")
 
 
def _clave_periodo(inicio: date, fin: date, tipo: str) -> str:
    """Genera la clave única de un período para el historial."""
    return f"{inicio}|{fin}|{tipo}"
 
 
def consultar_historial(rfc: str, inicio: date, fin: date, tipo: str) -> dict:
    """
    Retorna el registro del historial para un período específico.
    Si no existe, retorna un dict con valores iniciales.
    """
    cache  = _leer_cache(rfc)
    clave  = _clave_periodo(inicio, fin, tipo)
    return cache.get(clave, {"intentos": 0, "offset_segundos": 0, "ultimo": None})
 
 
def registrar_intento(rfc: str, inicio: date, fin: date, tipo: str) -> int:
    """
    Registra un nuevo intento en el historial y retorna el offset de segundos
    que debe usarse en esta solicitud para evitar duplicados exactos.
    Incrementa el offset en 1 segundo por cada intento.
    """
    cache  = _leer_cache(rfc)
    clave  = _clave_periodo(inicio, fin, tipo)
    actual = cache.get(clave, {"intentos": 0, "offset_segundos": 0, "ultimo": None})
 
    nuevo_offset  = actual["intentos"]  # intento 0→offset 0, intento 1→offset 1, etc.
    actual["intentos"]        += 1
    actual["offset_segundos"]  = nuevo_offset
    actual["ultimo"]           = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
 
    cache[clave] = actual
    _escribir_cache(rfc, cache)
    return nuevo_offset
 
 
def fechas_con_offset(inicio: date, fin: date, offset_seg: int) -> tuple[datetime, datetime]:
    """
    Convierte date a datetime aplicando el offset de segundos al inicio.
    Esto hace que cada solicitud al SAT sea técnicamente un período distinto,
    evitando el bloqueo permanente por solicitudes duplicadas (error 5002).
 
    Ejemplo:
      offset 0 → 2025-01-01 00:00:00 → 2025-01-31 23:59:59
      offset 1 → 2025-01-01 00:00:01 → 2025-01-31 23:59:59
      offset 2 → 2025-01-01 00:00:02 → 2025-01-31 23:59:59
    """
    dt_inicio = datetime(inicio.year, inicio.month, inicio.day, 0, 0, 0) + timedelta(seconds=offset_seg)
    dt_fin    = datetime(fin.year, fin.month, fin.day, 23, 59, 59)
    return dt_inicio, dt_fin
 
 
# ===========================================================================
# REVEAL CACHE — utilidad de consola para inspeccionar el historial
# ===========================================================================
 
def reveal_cache(rfc_target: str) -> None:
    """
    Descifra y muestra el historial de solicitudes de un RFC o de todos.
    Modo de utilidad — no requiere FIEL ni parámetros de descarga.
    """
    _validar_salt()  # Verificar que el entorno esté configurado
 
    if not CACHE_DIR.exists() or not any(CACHE_DIR.glob("*.enc")):
        log.info("No existe caché todavía. Aún no se ha ejecutado ninguna descarga CFDI.")
        return
 
    archivos = list(CACHE_DIR.glob("*.enc")) if rfc_target == "all" \
               else [_cache_path(rfc_target)]
 
    for archivo in archivos:
        rfc = archivo.stem
        log.info("")
        log.info("=" * 65)
        log.info(f"CACHÉ DESCIFRADO — {rfc}")
        log.info("=" * 65)
 
        cache = _leer_cache(rfc)
 
        if not cache:
            log.info("  Sin registros en el caché para este RFC.")
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
 
    password = getpass("  → Contraseña de la FIEL (oculta): ")
 
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
 
    output    = pedir(f"Carpeta base (Enter para usar ./results_{rfc})", requerido=False, default="")
    intervalo = pedir("Segundos entre verificaciones", default="60")
 
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
        "output":    Path(output) if output else Path(f"./results_{rfc}"),
        "intervalo": int(intervalo),
    }
 
 
def validar_parametros(p: dict) -> None:
    """
    Valida todos los parámetros antes de tocar el SAT.
    Lista todos los errores y sale — fail-fast.
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
 
    hoy = date.today()
    try:
        limite_sat = hoy.replace(year=hoy.year - 6)
    except ValueError:  # 29 feb en año no bisiesto
        limite_sat = date(hoy.year - 6, 2, 28)
    if p["inicio"] < limite_sat:
        errores.append(
            f"El SAT solo permite descargar CFDI desde {limite_sat} (6 años atrás). "
            f"Tu fecha de inicio es {p['inicio']}"
        )
 
    if p["intervalo"] < 10:
        errores.append("El intervalo de verificación debe ser al menos 10 segundos.")
 
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
    Crea la estructura results_RFC/YYYY-MM-DD/.
    Advierte si la carpeta del día ya existe (sobreescritura silenciosa).
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
    Carga los archivos de la FIEL y construye el objeto Fiel.
    Un error aquí suele indicar contraseña incorrecta o archivos corruptos.
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
    Acepta datetime opcionalmente para el bypass de offset de segundos (modo CFDI).
    Retorna el ID de solicitud o None si no hay CFDIs / hubo error.
 
    ⚠ CFDI: el bypass de offset maneja el bloqueo permanente automáticamente.
       Metadata: no tiene restricción de intentos — no usa offset.
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
            # El SAT no permite solicitar CFDI recibidos con cancelados incluidos.
            # "1" = vigente, "0" = cancelado (valores numéricos del API SOAP del SAT).
            # Para cancelados solo está disponible Metadata, no CFDI completo.
            resultado = cliente.solicitar_descarga(
                token, p["rfc"], fecha_inicio, fecha_fin,
                rfc_receptor=p["rfc"], tipo_solicitud=p["solicitud"],
                estado_comprobante="Vigente",
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
# VERIFICACIÓN
# ===========================================================================
 
def verificar_solicitud(fiel: Fiel, id_solicitud: str, p: dict) -> list[str]:
    """
    Polling hasta que la solicitud esté lista. Hace sys.exit() en error.
    Usada en modo CFDI donde un error es terminal.
    """
    log.info(f"Verificando solicitud: {id_solicitud}")
    log.info(f"  Consultando cada {p['intervalo']}s...")
 
    intento = 0
    while True:
        intento += 1
        ahora = datetime.now().strftime("%H:%M:%S")
        log.info(f"  [{ahora}] Verificación #{intento}...")
 
        try:
            token        = obtener_token(fiel)
            verificacion = VerificaSolicitudDescarga(fiel).verificar_descarga(
                token, p["rfc"], id_solicitud
            )
        except Exception as e:
            log.warning(f"  ✗ Error en verificación #{intento}. Causa: {e}")
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
            log.info(f"✔ Terminada. Paquetes disponibles: {len(paquetes)}")
            for i, pk in enumerate(paquetes, 1):
                log.info(f"    [{i}] {pk}")
            return paquetes
        elif estado == 5:
            cod = verificacion.get("codigo_estado_solicitud", "")
            log.error(f"✗ Rechazada por el SAT. Código: {cod}")
            sys.exit(1)
        elif estado == 6:
            log.error("✗ Solicitud vencida. Genera una nueva.")
            sys.exit(1)
        else:
            log.error(f"✗ Estado inesperado: {estado_desc}")
            sys.exit(1)
 
 
def verificar_solicitud_raw(fiel: Fiel, id_solicitud: str, p: dict) -> dict:
    """
    Igual que verificar_solicitud pero retorna el dict raw sin hacer sys.exit.
    Usada en el loop mensual de Metadata para continuar ante errores.
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
    Extrae XMLs del ZIP en subcarpeta YYYY-MM-RFC/ y renombra el ZIP.
    Conserva el ZIP renombrado como YYYY-MM-RFC.zip.
    """
    output_dir = zip_path.parent
    xml_dir    = output_dir / nombre_destino
    xml_dir.mkdir(exist_ok=True)
 
    log.info(f"  Extrayendo XMLs de: {zip_path.name}")
    log.info(f"  Destino           : {xml_dir.name}/")
 
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
# HELPERS — PERÍODOS Y RESUMEN
# ===========================================================================
 
def generar_periodos_mensuales(inicio: date, fin: date) -> list[tuple[date, date]]:
    """Divide un rango en períodos de un mes. Usado exclusivamente en modo Metadata."""
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
    Nunca hace sys.exit() — permite que el loop continúe.
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
                nombre   = f"{mes_inicio.strftime('%Y-%m')}-{p['rfc']}"
                extraidos = extraer_metadata(zip_path, nombre)
                archivos.extend(extraidos)
 
        log.info(f"  └─ {mes_label}: {len(archivos)} archivo(s) guardados. ✔")
        return archivos
 
    except Exception as e:
        log.warning(f"  └─ {mes_label}: Error inesperado ({e}) — continuando.")
        return []
 
 
def generar_resumen_metadata(archivos: list[Path], params: dict) -> list[str]:
    """
    Lee los TXT de Metadata y genera un resumen legible para humanos.
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
    Retorna dict con parámetros si se pasaron argumentos, o None para modo interactivo.
    --reveal-cache se maneja aquí antes que cualquier otra lógica.
    """
    if len(sys.argv) == 1:
        return None
 
    p = argparse.ArgumentParser(description="Descarga masiva de CFDI (XML) del SAT")
 
    # Modo utilidad
    p.add_argument("--reveal-cache", metavar="RFC|all", default=None,
                   help="Descifra y muestra el historial de caché de un RFC o de todos.")
 
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
    p.add_argument("--output",    type=Path, default=None)
    p.add_argument("--intervalo", type=int,  default=60)
 
    args = p.parse_args()
 
    # --reveal-cache es un modo independiente — no necesita los demás args
    if args.reveal_cache:
        reveal_cache(args.reveal_cache)
        sys.exit(0)
 
    # Validar que los args obligatorios estén presentes en modo descarga
    faltantes = [f"--{f}" for f, v in [
        ("rfc", args.rfc), ("cer", args.cer),
        ("key", args.key), ("inicio", args.inicio), ("fin", args.fin)
    ] if v is None]
 
    if faltantes:
        p.error(f"Los siguientes argumentos son requeridos: {', '.join(faltantes)}")
 
    rfc      = args.rfc.upper()
    password = args.password
    if not password:
        log.info("--password no proporcionado. Solicitando de forma segura...")
        password = getpass("  → Contraseña de la FIEL (oculta): ")
 
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
 
    # Verificar SAT_CACHE_SALT antes de cualquier otra cosa
    _validar_salt()
 
    validar_parametros(params)
 
    output_dir = resolver_output(params)
    fiel       = cargar_fiel(params["cer"], params["key"], params["password"])
 
    # -----------------------------------------------------------------------
    # Modo Metadata — procesa mes a mes, sin caché (no hay riesgo de bloqueo)
    # -----------------------------------------------------------------------
    if params["solicitud"] == "Metadata":
        periodos = generar_periodos_mensuales(params["inicio"], params["fin"])
        total    = len(periodos)
 
        log.info("")
        log.info(f"Modo METADATA — {total} mes(es) a procesar")
        log.info(f"  RFC    : {params['rfc']}")
        log.info(f"  Tipo   : {params['tipo']}")
        log.info(f"  Rango  : {params['inicio']} → {params['fin']}")
        log.info(f"  Salida : {output_dir.resolve()}")
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
    # Modo CFDI — bypass de offset automático via caché encriptado
    # -----------------------------------------------------------------------
    else:
        log.info("")
        log.info("Modo CFDI — procesando rango completo")
        log.info(f"  RFC    : {params['rfc']}")
        log.info(f"  Tipo   : {params['tipo']}")
        log.info(f"  Rango  : {params['inicio']} → {params['fin']}")
        log.info(f"  Salida : {output_dir.resolve()}")
 
        # Consultar historial antes de tocar el SAT
        historial = consultar_historial(
            params["rfc"], params["inicio"], params["fin"], params["tipo"]
        )
        intentos_previos = historial["intentos"]
        offset_seg       = historial["offset_segundos"]
 
        if intentos_previos == 0:
            log.info("  Caché: primera solicitud para este período.")
        else:
            log.info(f"  Caché: {intentos_previos} intento(s) previo(s) detectado(s).")
            log.info(f"  Bypass activado: se aplicará offset de +{offset_seg}s al inicio del período.")
            log.info(f"  Esto evita el bloqueo permanente del SAT (error 5002).")
 
        # Registrar este intento y obtener el offset a usar
        offset_actual = registrar_intento(
            params["rfc"], params["inicio"], params["fin"], params["tipo"]
        )
        dt_inicio, dt_fin = fechas_con_offset(params["inicio"], params["fin"], offset_actual)
 
        log.info(f"  Período efectivo : {dt_inicio} → {dt_fin}")
 
        token        = obtener_token(fiel)
        id_solicitud = solicitar_descarga(fiel, token, params, dt_inicio, dt_fin)
 
        if not id_solicitud:
            log.error("✗ No se pudo obtener un ID de solicitud del SAT.")
            sys.exit(1)
 
        paquetes = verificar_solicitud(fiel, id_solicitud, params)
 
        if not paquetes:
            log.warning("El SAT no devolvió paquetes. No hay CFDI en ese período.")
            sys.exit(0)
 
        nombre_base   = f"{params['inicio'].strftime('%Y-%m')}-{params['rfc']}"
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
        sys.exit(0)
    except Exception as e:
        log.critical(f"Error inesperado no controlado: {e}", exc_info=True)
        log.critical("Revisa sat_descarga.log para el stack trace completo.")
        sys.exit(1)
