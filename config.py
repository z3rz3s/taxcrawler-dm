"""
config.py
---------
Constantes globales, logging, validacion de entorno y resolucion de credenciales.
Importado por todos los demas modulos del proyecto.
"""

import logging
import os
import sys
from getpass import getpass
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependencias locales — libs/ tiene prioridad sobre el sistema
# ---------------------------------------------------------------------------
_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

# Cargar .env antes que cualquier otra cosa
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
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

# Estados de solicitud SAT (Web Service v1.5)
SAT_ESTADOS = {
    1: "Aceptada",
    2: "En proceso",
    3: "Terminada",
    4: "Error",
    5: "Rechazada",
    6: "Vencida",
}

# Meses en español para nombres de archivo y reportes
MESES_ES = {
    "01": "Enero",      "02": "Febrero",   "03": "Marzo",
    "04": "Abril",      "05": "Mayo",      "06": "Junio",
    "07": "Julio",      "08": "Agosto",    "09": "Septiembre",
    "10": "Octubre",    "11": "Noviembre", "12": "Diciembre",
}

# Reintentos para autenticacion y descarga
MAX_TOKEN_RETRIES    = 3
MAX_DOWNLOAD_RETRIES  = 3
RETRY_PAUSE_SEC       = 5

# Carpeta de cache encriptado
CACHE_DIR = Path(__file__).resolve().parent / ".cache"

# Timeout minimo en minutos antes de reintentar una descarga en espera
RETOMAR_TIMEOUT_MIN = 30

# Nombre por defecto del despacho contable (sobrescribible con DESPACHO_NOMBRE)
DEFAULT_DESPACHO = "TEST_DESPACHO_TEST"

# ---------------------------------------------------------------------------
# Tabla ISR RESICO Personas Fisicas — Art. 113-E LISR
# Regimen 625: Regimen Simplificado de Confianza
# Montos fijos en ley (NO se actualizan por inflacion como el Art. 96)
# Formato: (limite_inferior, limite_superior, cuota_fija, tasa)
# ---------------------------------------------------------------------------
TABLA_ISR_RESICO_DEFAULT = [
    (0.01,        1000.00,    0.00,       0.01),
    (1000.01,     5000.00,    10.00,      0.011),
    (5000.01,     10000.00,   54.00,      0.012),
    (10000.01,    25000.00,   114.00,     0.015),
    (25000.01,    50000.00,   339.00,     0.02),
    (50000.01,    100000.00,  839.00,     0.025),
    (100000.01,   250000.00,  2089.00,    0.03),
    (250000.01,   float("inf"), 6589.00,   0.035),
]

# ---------------------------------------------------------------------------
# Funciones de validacion y resolucion
# ---------------------------------------------------------------------------

def validate_salt() -> bytes:
    """
    Lee SAT_CACHE_SALT del entorno. Falla con instrucciones claras si no existe.
    El salt nunca se guarda en codigo — viene exclusivamente de .env.
    """
    salt = os.environ.get("SAT_CACHE_SALT", "").strip()
    if not salt:
        log.error("=" * 65)
        log.error("Variable de entorno SAT_CACHE_SALT no definida.")
        log.error("Pasos para configurarla:")
        log.error("  1. Copia .env.example -> .env")
        log.error("  2. Define SAT_CACHE_SALT=tu_valor_secreto en .env")
        log.error("  3. Asegurate de que .env este en .gitignore")
        log.error("=" * 65)
        sys.exit(1)
    return salt.encode()


def get_despacho_name(cli_value: str | None = None) -> str:
    """
    Resuelve el nombre del despacho en este orden de prioridad:
    1. DEFAULT_DESPACHO (hardcoded en config)
    2. Variable de entorno DESPACHO_NOMBRE
    3. Parametro CLI --despacho (pendiente de implementar en CLI)

    Retorna el nombre resuelto.
    """
    name = DEFAULT_DESPACHO

    env_value = os.environ.get("DESPACHO_NOMBRE", "").strip()
    if env_value:
        name = env_value
        log.info(f"  Nombre de despacho tomado de variable de entorno: {name}")
        return name

    if cli_value and cli_value.strip():
        name = cli_value.strip()
        log.info(f"  Nombre de despacho tomado de parametro CLI: {name}")
        return name

    return name


def _load_isr_csv(path: Path) -> list[tuple]:
    """
    Carga una tabla ISR desde un archivo CSV.
    Columnas esperadas: limite_inferior, limite_superior, cuota_fija, tasa
    Ignora filas con valores no numericos y encabezados.
    """
    tabla = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.replace(",", ".").split(",")
            p = [p.strip() for p in parts]
            if len(p) < 4:
                continue
            # Verificar que los primeros 3 campos sean numericos
            if not p[0].replace(".", "").isdigit():
                continue
            try:
                limite_inf = float(p[0])
                if p[1].lower() in ("inf", "en adelante", "infinito"):
                    limite_sup = float("inf")
                else:
                    limite_sup = float(p[1])
                cuota_fija = float(p[2])
                tasa = float(p[3])
                tabla.append((limite_inf, limite_sup, cuota_fija, tasa))
            except ValueError:
                continue

    if not tabla:
        raise ValueError("El CSV no contiene filas validas de tabla ISR.")
    return tabla


def resolve_isr_table(cli_path: str | None = None) -> list[tuple]:
    """
    Resuelve la tabla ISR en este orden de prioridad:
    1. TABLA_ISR_RESICO_DEFAULT (hardcoded en config)
    2. Variable de entorno TABLA_ISR_PATH con ruta a CSV
    3. Parametro CLI --tabla-isr con ruta a CSV

    Retorna la tabla como lista de tuplas (lim_inf, lim_sup, cuota, tasa).
    """
    tabla = TABLA_ISR_RESICO_DEFAULT

    # Variable de entorno
    path_str = os.environ.get("TABLA_ISR_PATH", "").strip()
    if path_str:
        path = Path(path_str)
        if path.exists():
            try:
                tabla = _load_isr_csv(path)
                log.info(f"  Tabla ISR cargada desde: {path} ({len(tabla)} rangos)")
                return tabla
            except Exception as e:
                log.error(f"  X Error al leer tabla ISR desde {path}: {e}")
                log.error("    Usando tabla por defecto.")
        else:
            log.error(f"  X Archivo de tabla ISR no encontrado: {path}")
            log.error("    Usando tabla por defecto.")

    # Parametro CLI
    if cli_path:
        path = Path(cli_path)
        if path.exists():
            try:
                tabla = _load_isr_csv(path)
                log.info(f"  Tabla ISR cargada desde: {path} ({len(tabla)} rangos)")
                return tabla
            except Exception as e:
                log.error(f"  X Error al leer tabla ISR desde {path}: {e}")

    log.info(f"  Tabla ISR: usando tabla RESICO por defecto ({len(tabla)} rangos)")
    return tabla


def resolve_password(rfc: str) -> str:
    """
    Intenta obtener la contrasena en este orden de prioridad:
    1. Variable de entorno SAT_PASSWORD_{RFC} (para automatizacion/cron)
    2. getpass interactivo con prompt descriptivo

    Retorna la contrasena.
    """
    prompt_label = f"Contrasena de la FIEL para {rfc}"
    env_key = f"SAT_PASSWORD_{rfc.upper()}"

    password = os.environ.get(env_key, "").strip()
    if password:
        log.info(f"  Contrasena obtenida desde variable de entorno {env_key}")
        return password

    return getpass(f"  -> {prompt_label} (oculta): ")
