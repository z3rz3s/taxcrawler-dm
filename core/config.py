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
_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging — formato consistente para CLI y futura UI
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
# Constantes — estados SAT, meses, limites de reintentos
# ---------------------------------------------------------------------------

# Mapeo de codigos de estado del SAT a descripciones legibles
SAT_ESTADOS = {
    1: "Aceptada",
    2: "En proceso",
    3: "Terminada",
    4: "Error",
    5: "Rechazada",
    6: "Vencida",
}

# Nombres de meses en espanol para logs y reportes
MESES_ES = {
    "01": "Enero",      "02": "Febrero",   "03": "Marzo",
    "04": "Abril",      "05": "Mayo",      "06": "Junio",
    "07": "Julio",      "08": "Agosto",    "09": "Septiembre",
    "10": "Octubre",    "11": "Noviembre", "12": "Diciembre",
}

# Limites de reintentos ante fallos de red o servicio
MAX_TOKEN_RETRIES    = 3
MAX_DOWNLOAD_RETRIES = 3
RETRY_PAUSE_SEC      = 5

# Directorio del cache encriptado — relativo al script principal
CACHE_DIR = Path(__file__).resolve().parent / ".cache"

# Timeout por defecto para --retomar y --retomar-todas (en minutos)
# None = sin limite para el flujo normal de descarga
RETOMAR_TIMEOUT_MIN = 30

# Nombre del despacho por defecto — sobreescrito por DESPACHO_NOMBRE en .env
# o por --despacho en el CLI
DEFAULT_DESPACHO = "TEST_DESPACHO_TEST"

# Tabla ISR RESICO por defecto — extraida del Excel de referencia
# Cada entrada: (limite_inferior, limite_superior, cuota_fija, tasa_excedente)
# TODO: agregar soporte para regimen PFAE cuando se defina el calculo
TABLA_ISR_RESICO_DEFAULT = [
    (0.01,      1157.04,    0.00,      0.0192),
    (1157.05,   9820.36,    22.22,     0.0640),
    (9820.37,   17258.40,   576.66,    0.1088),
    (17258.41,  20062.14,   1385.92,   0.1600),
    (20062.15,  24019.88,   1834.52,   0.1792),
    (24019.89,  48444.62,   2543.74,   0.2136),
    (48444.63,  76355.38,   7760.88,   0.2352),
    (76355.39,  145775.00,  14325.48,  0.3000),
    (145775.01, 194366.66,  35151.38,  0.3200),
    (194366.67, 583100.00,  50700.70,  0.3400),
    (583100.01, float("inf"), 182870.04, 0.3500),
]


# ===========================================================================
# Validacion de entorno
# ===========================================================================

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
    3. Parametro CLI --despacho "valor entre comillas"

    El ultimo que exista sobreescribe al anterior.
    """
    name = DEFAULT_DESPACHO
    env_value = os.environ.get("DESPACHO_NOMBRE", "").strip()
    if env_value:
        name = env_value
        log.info(f"  Nombre de despacho tomado de variable de entorno: {name}")
    if cli_value and cli_value.strip():
        name = cli_value.strip()
        log.info(f"  Nombre de despacho tomado de parametro CLI: {name}")
    return name


def resolve_isr_table(cli_path: str | None = None) -> list[tuple]:
    """
    Resuelve la tabla ISR en este orden de prioridad:
    1. TABLA_ISR_RESICO_DEFAULT (hardcoded en config)
    2. Variable de entorno TABLA_ISR_PATH con ruta a un CSV
    3. Parametro CLI --tabla-isr con ruta a un CSV

    El CSV debe tener columnas: limite_inferior, limite_superior, cuota_fija, tasa
    Sin encabezado o con encabezado — se detecta automaticamente.
    """
    # Intentar cargar desde CLI primero (maxima prioridad)
    path_str = cli_path or os.environ.get("TABLA_ISR_PATH", "").strip()

    if path_str:
        path = Path(path_str)
        if not path.exists():
            log.error(f"  X Archivo de tabla ISR no encontrado: {path}")
            log.error("    Usando tabla por defecto.")
            return TABLA_ISR_RESICO_DEFAULT

        try:
            tabla = _load_isr_csv(path)
            log.info(f"  Tabla ISR cargada desde: {path} ({len(tabla)} rangos)")
            return tabla
        except Exception as e:
            log.error(f"  X Error al leer tabla ISR desde {path}: {e}")
            log.error("    Usando tabla por defecto.")

    log.info(f"  Tabla ISR: usando tabla RESICO por defecto ({len(TABLA_ISR_RESICO_DEFAULT)} rangos)")
    return TABLA_ISR_RESICO_DEFAULT


def _load_isr_csv(path: Path) -> list[tuple]:
    """
    Carga una tabla ISR desde un archivo CSV.
    Columnas esperadas: limite_inferior, limite_superior, cuota_fija, tasa
    Ignora filas con valores no numericos (encabezados o notas).
    """
    tabla = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip().replace(",", "") for p in line.split(",")]
            if len(parts) < 4:
                continue
            try:
                limite_inf = float(parts[0])
                # El limite superior puede ser "En adelante" -> infinity
                limite_sup = float("inf") if not parts[1].replace(".", "").isdigit() \
                             else float(parts[1])
                cuota_fija = float(parts[2])
                tasa       = float(parts[3])
                tabla.append((limite_inf, limite_sup, cuota_fija, tasa))
            except ValueError:
                # Fila de encabezado u otra no numerica — ignorar
                continue
    if not tabla:
        raise ValueError("El CSV no contiene filas validas de tabla ISR.")
    return tabla


# ===========================================================================
# Resolucion de password
# ===========================================================================

def resolve_password(rfc: str, prompt_label: str = "") -> str:
    """
    Intenta obtener la contrasena en este orden de prioridad:
    1. Variable de entorno SAT_PASSWORD_RFC (para automatizacion/cron)
    2. getpass interactivo — nunca se almacena en disco

    La contrasena NUNCA se guarda en ningun archivo.
    Para automatizacion completa, define en .env:
      SAT_PASSWORD_XAXX010101000=tu_password
    """
    env_key  = f"SAT_PASSWORD_{rfc.upper()}"
    password = os.environ.get(env_key, "").strip()

    if password:
        log.info(f"  Contrasena obtenida desde variable de entorno {env_key}.")
        return password

    label = prompt_label or f"Contrasena de la FIEL para {rfc.upper()}"
    return getpass(f"  -> {label} (oculta): ")