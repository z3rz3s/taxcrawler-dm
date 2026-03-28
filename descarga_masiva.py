"""
SAT Descarga Masiva de CFDI (XML)
==================================
Requiere: pip install cfdiclient

Modo interactivo (sin argumentos):
  python sat_descarga_masiva.py

Modo CLI:
  python sat_descarga_masiva.py \
    --rfc TURF010101ABC \
    --cer fiel.cer \
    --key fiel.key \
    --password mipass \
    --inicio 2024-01-01 \
    --fin 2024-12-31 \
    --tipo recibidos \
    --output ./xml_sat

Opcionales:
  --solicitud  CFDI|Metadata  (default: CFDI)
  --intervalo  60             segundos entre verificaciones (default: 60)
"""

import argparse
import base64
import logging
import sys
import time
import zipfile
from datetime import date, datetime
from getpass import getpass
from pathlib import Path

from cfdiclient import (
    Autenticacion,
    DescargaMasiva,
    Fiel,
    SolicitaDescarga,
    VerificaSolicitudDescarga,
)

# ---------------------------------------------------------------------------
# Logging — formato claro y trazable
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

MAX_REINTENTOS_TOKEN    = 3
MAX_REINTENTOS_DESCARGA = 3
PAUSA_ENTRE_REINTENTOS  = 5  # segundos


# ---------------------------------------------------------------------------
# Preguntas interactivas
# ---------------------------------------------------------------------------
def preguntar_parametros() -> dict:
    """
    Solicita al usuario los parámetros necesarios de forma interactiva.
    Se usa cuando el script se ejecuta sin argumentos CLI.
    """
    log.info("=" * 65)
    log.info("MODO INTERACTIVO — Se solicitarán los parámetros necesarios")
    log.info("=" * 65)

    print()

    def pedir(prompt: str, requerido: bool = True, default: str = "") -> str:
        while True:
            sufijo = f" [{default}]" if default else ""
            valor = input(f"  → {prompt}{sufijo}: ").strip()
            if not valor and default:
                return default
            if valor or not requerido:
                return valor
            print("    ⚠ Este campo es obligatorio.")

    rfc = pedir("RFC del contribuyente").upper()

    cer = pedir("Ruta al archivo .cer de la FIEL")
    while not Path(cer).exists():
        print(f"    ✗ No se encontró el archivo: {cer}")
        cer = pedir("Ruta al archivo .cer de la FIEL")

    key = pedir("Ruta al archivo .key de la FIEL")
    while not Path(key).exists():
        print(f"    ✗ No se encontró el archivo: {key}")
        key = pedir("Ruta al archivo .key de la FIEL")

    password = getpass("  → Contraseña de la FIEL (oculta): ")

    inicio = pedir("Fecha inicio (YYYY-MM-DD)", default="2024-01-01")
    fin    = pedir("Fecha fin    (YYYY-MM-DD)", default=str(date.today()))

    tipo = ""
    while tipo not in ("emitidos", "recibidos"):
        tipo = pedir("Tipo de descarga [emitidos / recibidos]", default="recibidos").lower()

    solicitud = ""
    while solicitud not in ("CFDI", "Metadata"):
        solicitud = pedir("Tipo de solicitud [CFDI / Metadata]", default="CFDI")

    output    = pedir("Carpeta de salida", default="./xml_sat")
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
        "output":    Path(output),
        "intervalo": int(intervalo),
    }


# ---------------------------------------------------------------------------
# Validaciones — Fail-fast antes de tocar el SAT
# ---------------------------------------------------------------------------
def validar_parametros(p: dict) -> None:
    """
    Valida coherencia de los parámetros antes de hacer cualquier llamada al SAT.
    Falla rápido (fail-fast) para no gastar solicitudes con datos inválidos.
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

    hoy         = date.today()
    limite_sat  = date(hoy.year - 6, hoy.month, hoy.day)
    if p["inicio"] < limite_sat:
        errores.append(
            f"El SAT solo permite descargar CFDI desde {limite_sat} (6 años atrás). "
            f"Tu fecha de inicio es {p['inicio']}"
        )

    if p["intervalo"] < 10:
        errores.append("El intervalo de verificación debe ser al menos 10 segundos.")

    if errores:
        log.error(f"Se encontraron {len(errores)} error(es) de validación:")
        for e in errores:
            log.error(f"  ✗ {e}")
        sys.exit(1)

    log.info("✔ Todos los parámetros son válidos.")


# ---------------------------------------------------------------------------
# Paso 1 — Cargar FIEL
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Paso 2 — Obtener token SAT
# ---------------------------------------------------------------------------
def obtener_token(fiel: Fiel, intento: int = 1) -> str:
    """
    Autentica contra el Web Service del SAT y obtiene un token temporal.
    El token es de vida corta (~5 min), se renueva antes de cada operación.
    Reintenta automáticamente ante fallos transitorios de red o servicio.
    """
    log.info(f"Solicitando token de autenticación al SAT (intento {intento}/{MAX_REINTENTOS_TOKEN})...")

    try:
        token = Autenticacion(fiel).obtener_token()
        log.info("✔ Token obtenido. La sesión con el SAT está activa.")
        return token
    except Exception as e:
        log.warning(f"  ✗ El SAT rechazó o no respondió la autenticación. Causa: {e}")
        if intento < MAX_REINTENTOS_TOKEN:
            log.info(f"  Reintentando en {PAUSA_ENTRE_REINTENTOS}s...")
            time.sleep(PAUSA_ENTRE_REINTENTOS)
            return obtener_token(fiel, intento + 1)
        log.error("  Se agotaron los reintentos de autenticación.")
        log.error("  Posibles causas: FIEL vencida, sin conexión o el SAT está caído.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Paso 3 — Solicitar descarga
# ---------------------------------------------------------------------------
def solicitar_descarga(fiel: Fiel, token: str, p: dict) -> str:
    """
    Envía la solicitud de descarga al SAT.
    El SAT la recibe y devuelve un ID; esto NO significa que los datos estén listos.

    ⚠ ADVERTENCIA: No repitas el mismo rango de fechas más de 2 veces.
    El SAT bloqueará ese período permanentemente con error 5002.
    """
    log.info("Preparando solicitud de descarga masiva...")
    log.info(f"  RFC        : {p['rfc']}")
    log.info(f"  Tipo       : {p['tipo']} ({p['solicitud']})")
    log.info(f"  Período    : {p['inicio']} → {p['fin']}")
    log.info("  Enviando solicitud al Web Service del SAT...")

    kwargs = dict(
        token          = token,
        rfc            = p["rfc"],
        fecha_inicial  = p["inicio"],
        fecha_final    = p["fin"],
        tipo_solicitud = p["solicitud"],
    )
    if p["tipo"] == "emitidos":
        kwargs["rfc_emisor"]   = p["rfc"]
    else:
        kwargs["rfc_receptor"] = p["rfc"]

    try:
        resultado    = SolicitaDescarga(fiel).solicitar_descarga(**kwargs)
        id_solicitud = resultado["id_solicitud"]
        log.info("✔ Solicitud aceptada por el SAT.")
        log.info(f"  ID de solicitud : {id_solicitud}")
        log.info("  Guarda este ID por si necesitas reanudar el proceso manualmente.")
        log.info("  El SAT procesará en segundo plano (minutos a horas según demanda).")
        return id_solicitud
    except Exception as e:
        log.error(f"✗ El SAT rechazó la solicitud. Causa: {e}")
        log.error("  Posibles causas:")
        log.error("    • Período ya solicitado 2+ veces (error 5002) — cambia fechas en al menos 1 segundo")
        log.error("    • Token expirado — vuelve a ejecutar el script")
        log.error("    • RFC incorrecto o FIEL no asociada a ese RFC")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Paso 4 — Verificar estado con polling
# ---------------------------------------------------------------------------
def verificar_solicitud(fiel: Fiel, id_solicitud: str, p: dict) -> list[str]:
    """
    Consulta periódicamente al SAT si la solicitud ya está procesada.
    Retorna la lista de IDs de paquetes listos para descargar.
    El SAT puede tardar minutos o hasta 72 horas en momentos de alta demanda.
    """
    log.info(f"Iniciando verificación de solicitud: {id_solicitud}")
    log.info(f"  Verificando cada {p['intervalo']}s hasta que el SAT confirme.")

    intento = 0

    while True:
        intento += 1
        ahora = datetime.now().strftime("%H:%M:%S")
        log.info(f"  [{ahora}] Verificación #{intento} — consultando estado...")

        try:
            token        = obtener_token(fiel)
            verificacion = VerificaSolicitudDescarga(fiel).verificar_descarga(
                token, p["rfc"], id_solicitud
            )
        except Exception as e:
            log.warning(f"  ✗ Error al consultar verificación #{intento}. Causa: {e}")
            log.info(f"  Reintentando en {p['intervalo']}s...")
            time.sleep(p["intervalo"])
            continue

        estado      = verificacion.get("estado_solicitud", -1)
        estado_desc = ESTADOS_SOLICITUD.get(estado, f"Desconocido ({estado})")
        paquetes    = verificacion.get("paquetes", [])

        log.info(f"  Estado actual : {estado} — {estado_desc}")

        if estado in (1, 2):
            log.info(f"  SAT aún preparando tu solicitud. Próximo intento en {p['intervalo']}s...")
            time.sleep(p["intervalo"])

        elif estado == 3:
            log.info("✔ Solicitud terminada. Paquetes disponibles para descarga:")
            for i, pk in enumerate(paquetes, 1):
                log.info(f"    [{i}] {pk}")
            return paquetes

        elif estado == 5:
            log.error("✗ Solicitud rechazada por el SAT.")
            log.error("  El RFC o las fechas pueden no tener CFDI en ese período.")
            sys.exit(1)

        elif estado == 6:
            log.error("✗ Solicitud vencida. El SAT eliminó esta solicitud por inactividad.")
            log.error("  Debes generar una nueva solicitud con el mismo o distinto período.")
            sys.exit(1)

        else:
            log.error(f"✗ Estado de error inesperado: {estado_desc}")
            log.error("  Contacta la Mesa de Ayuda del SAT si el problema persiste.")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Paso 5 — Descargar un paquete ZIP
# ---------------------------------------------------------------------------
def descargar_paquete(fiel: Fiel, id_paquete: str, rfc: str, output_dir: Path, numero: int, total: int) -> Path | None:
    """
    Descarga un paquete individual del SAT (viene como ZIP codificado en base64).
    Reintenta ante errores de red o token expirado.
    Retorna la ruta al ZIP guardado, o None si falló tras todos los reintentos.
    """
    log.info(f"  Descargando paquete {numero}/{total}: {id_paquete}")

    for intento in range(1, MAX_REINTENTOS_DESCARGA + 1):
        log.info(f"    Intento {intento}/{MAX_REINTENTOS_DESCARGA} — solicitando paquete al SAT...")
        try:
            token     = obtener_token(fiel)
            resultado = DescargaMasiva(fiel).descargar_paquete(token, rfc, id_paquete)

            zip_bytes = base64.b64decode(resultado["paquete_b64"])
            zip_path  = output_dir / f"{id_paquete}.zip"
            zip_path.write_bytes(zip_bytes)

            kb = len(zip_bytes) / 1024
            log.info(f"    ✔ Paquete guardado: {zip_path.name} ({kb:.1f} KB)")
            return zip_path

        except Exception as e:
            log.warning(f"    ✗ Fallo en intento {intento}. Causa: {e}")
            if intento < MAX_REINTENTOS_DESCARGA:
                log.info(f"    Reintentando en {PAUSA_ENTRE_REINTENTOS}s...")
                time.sleep(PAUSA_ENTRE_REINTENTOS)
            else:
                log.error(f"  ✗ Se agotaron los reintentos para el paquete: {id_paquete}")
                log.error("    Este paquete se omitirá. Puedes re-ejecutar el script para reintentarlo.")
                return None


# ---------------------------------------------------------------------------
# Paso 6 — Extraer XMLs del ZIP
# ---------------------------------------------------------------------------
def extraer_xmls(zip_path: Path) -> list[Path]:
    """
    Extrae los archivos XML del ZIP descargado.
    Cada ZIP puede contener miles de XML individuales.
    Los guarda en una subcarpeta con el nombre del paquete para trazabilidad.
    """
    xml_dir = zip_path.parent / zip_path.stem
    xml_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"  Extrayendo contenido de: {zip_path.name}")
    log.info(f"  Destino: {xml_dir}")

    try:
        extraidos: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            archivos_xml = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            log.info(f"  Archivos XML en este paquete: {len(archivos_xml)}")

            for nombre in archivos_xml:
                dest = xml_dir / nombre
                dest.write_bytes(zf.read(nombre))
                extraidos.append(dest)

        log.info(f"  ✔ {len(extraidos)} XML extraídos en: {xml_dir}")
        return extraidos

    except zipfile.BadZipFile:
        log.error(f"  ✗ El archivo ZIP está corrupto o incompleto: {zip_path}")
        log.error("  Elimina el ZIP y vuelve a ejecutar el script para re-descargarlo.")
        return []
    except Exception as e:
        log.error(f"  ✗ Error inesperado extrayendo ZIP. Causa: {e}")
        return []


# ---------------------------------------------------------------------------
# Paso 7 — Resumen final
# ---------------------------------------------------------------------------
def imprimir_resumen(xmls_totales: list[Path], output_dir: Path, inicio: datetime) -> None:
    """Imprime un resumen ejecutivo del proceso completo."""
    duracion = int((datetime.now() - inicio).total_seconds())
    minutos  = duracion // 60
    segundos = duracion % 60

    log.info("")
    log.info("=" * 65)
    log.info("RESUMEN FINAL DE LA DESCARGA MASIVA")
    log.info("=" * 65)
    log.info(f"  Total XML descargados : {len(xmls_totales)}")
    log.info(f"  Carpeta de salida     : {output_dir.resolve()}")
    log.info(f"  Duración total        : {minutos}m {segundos}s")
    log.info(f"  Log guardado en       : sat_descarga.log")
    log.info("=" * 65)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> dict | None:
    """Retorna dict con parámetros si se pasaron argumentos, o None para modo interactivo."""
    if len(sys.argv) == 1:
        return None

    p = argparse.ArgumentParser(description="Descarga masiva de CFDI (XML) del SAT")
    p.add_argument("--rfc",       required=True)
    p.add_argument("--cer",       required=True, type=Path)
    p.add_argument("--key",       required=True, type=Path)
    p.add_argument("--password",  required=True)
    p.add_argument("--inicio",    required=True, type=date.fromisoformat)
    p.add_argument("--fin",       required=True, type=date.fromisoformat)
    p.add_argument("--tipo",      choices=["emitidos", "recibidos"], default="recibidos")
    p.add_argument("--solicitud", choices=["CFDI", "Metadata"],      default="CFDI")
    p.add_argument("--output",    type=Path, default=Path("./xml_sat"))
    p.add_argument("--intervalo", type=int,  default=60)
    args = p.parse_args()

    return {
        "rfc":       args.rfc.upper(),
        "cer":       args.cer,
        "key":       args.key,
        "password":  args.password,
        "inicio":    args.inicio,
        "fin":       args.fin,
        "tipo":      args.tipo,
        "solicitud": args.solicitud,
        "output":    args.output,
        "intervalo": args.intervalo,
    }


# ---------------------------------------------------------------------------
# Main — orquesta el flujo completo paso a paso
# ---------------------------------------------------------------------------
def main() -> None:
    inicio_proceso = datetime.now()

    log.info("=" * 65)
    log.info("SAT — DESCARGA MASIVA DE CFDI (XML)")
    log.info(f"Inicio: {inicio_proceso.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    params = parse_args() or preguntar_parametros()

    validar_parametros(params)

    params["output"].mkdir(parents=True, exist_ok=True)
    log.info(f"Carpeta de salida lista: {params['output'].resolve()}")

    fiel         = cargar_fiel(params["cer"], params["key"], params["password"])
    token        = obtener_token(fiel)
    id_solicitud = solicitar_descarga(fiel, token, params)
    paquetes     = verificar_solicitud(fiel, id_solicitud, params)

    if not paquetes:
        log.warning("El SAT no devolvió paquetes. No hay CFDI en ese período para este RFC.")
        sys.exit(0)

    xmls_totales: list[Path] = []
    log.info(f"Iniciando descarga de {len(paquetes)} paquete(s)...")

    for i, id_paquete in enumerate(paquetes, 1):
        zip_path = descargar_paquete(fiel, id_paquete, params["rfc"], params["output"], i, len(paquetes))
        if zip_path:
            xmls = extraer_xmls(zip_path)
            xmls_totales.extend(xmls)

    imprimir_resumen(xmls_totales, params["output"], inicio_proceso)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("")
        log.warning("Proceso interrumpido por el usuario (Ctrl+C).")
        log.warning("Los paquetes descargados hasta ahora siguen en la carpeta de salida.")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Error inesperado no controlado: {e}", exc_info=True)
        log.critical("Revisa sat_descarga.log para el stack trace completo.")
        sys.exit(1)