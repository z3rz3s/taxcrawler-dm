"""
SAT Descarga Masiva de CFDI (XML)
==================================
Requiere: 
    pip install cfdiclient --target ./libs
    pip install openpyxl --target ./libs --break-system-packages
 
Modo interactivo (sin argumentos):
  python sat_descarga_masiva.py
 
Modo CLI:
  python sat_descarga_masiva.py \
    --rfc TURF010101ABC \
    --cer fiel.cer \
    --key fiel.key \
    --password "mi password" \
    --inicio 2024-01-01 \
    --fin 2024-12-31 \
    --tipo recibidos \
    --solicitud Metadata \
    --output ./xml_sat
 
Opcionales:
  --solicitud  CFDI|Metadata  (default: CFDI)
  --intervalo  60             segundos entre verificaciones (default: 60)
 
Comportamiento según --solicitud:
  Metadata → divide por mes automáticamente, continúa si un mes no tiene CFDIs
  CFDI     → respeta el rango completo sin dividir (para no gastar los 2 intentos por período)
"""
 
import sys
from pathlib import Path
 
# Dependencias instaladas localmente con: pip install cfdiclient --target ./libs
_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))
 
import argparse
import base64
import logging
import time
import zipfile
from calendar import monthrange
from datetime import date, datetime
from getpass import getpass
 
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
 
MAX_REINTENTOS_TOKEN    = 3
MAX_REINTENTOS_DESCARGA = 3
PAUSA_ENTRE_REINTENTOS  = 5  # segundos
 
 
# ---------------------------------------------------------------------------
# Modo interactivo
# ---------------------------------------------------------------------------
def preguntar_parametros() -> dict:
    """
    Solicita al usuario los parámetros de forma interactiva.
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
 
    output    = pedir("Carpeta de salida (Enter para usar ./results_{RFC})", requerido=False, default="")
    intervalo = pedir("Segundos entre verificaciones", default="60")
 
    print()
    log.info("Parámetros capturados correctamente.")
 
    output_path = Path(output) if output else Path(f"./results_{rfc}")
 
    return {
        "rfc":       rfc,
        "cer":       Path(cer),
        "key":       Path(key),
        "password":  password,
        "inicio":    date.fromisoformat(inicio),
        "fin":       date.fromisoformat(fin),
        "tipo":      tipo,
        "solicitud": solicitud,
        "output":    output_path,
        "intervalo": int(intervalo),
    }
 
 
# ---------------------------------------------------------------------------
# Validaciones — fail-fast antes de tocar el SAT
# ---------------------------------------------------------------------------
def validar_parametros(p: dict) -> None:
    """
    Valida todos los parámetros antes de hacer cualquier llamada al SAT.
    Si hay errores los lista todos y sale — no gasta solicitudes con datos inválidos.
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
    El token dura ~5 minutos — se renueva antes de cada operación.
    Reintenta automáticamente hasta MAX_REINTENTOS_TOKEN veces.
    """
    log.info(f"Solicitando token de autenticación al SAT (intento {intento}/{MAX_REINTENTOS_TOKEN})...")
 
    try:
        token = Autenticacion(fiel).obtener_token()
        log.info("✔ Token obtenido. La sesión con el SAT está activa.")
        return token
    except Exception as e:
        log.warning(f"  ✗ El SAT no respondió la autenticación. Causa: {e}")
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
def solicitar_descarga(fiel: Fiel, token: str, p: dict) -> str | None:
    """
    Envía la solicitud de descarga al SAT para un período dado.
    Retorna el ID de solicitud, o None si el SAT indica que no hay CFDIs (5004).
    El ID no significa que los datos estén listos — solo que la solicitud fue recibida.
 
    ⚠ ADVERTENCIA CFDI: No repitas el mismo rango más de 2 veces.
    El SAT bloqueará ese período permanentemente con error 5002.
    Para Metadata no aplica esta restricción.
    """
    log.info(f"  Enviando solicitud al SAT → {p['tipo']} ({p['solicitud']}) | {p['inicio']} → {p['fin']}")
 
    try:
        if p["tipo"] == "emitidos":
            cliente   = SolicitaDescargaEmitidos(fiel)
            resultado = cliente.solicitar_descarga(
                token, p["rfc"], p["inicio"], p["fin"],
                rfc_emisor=p["rfc"], tipo_solicitud=p["solicitud"],
            )
        else:
            cliente   = SolicitaDescargaRecibidos(fiel)
            resultado = cliente.solicitar_descarga(
                token, p["rfc"], p["inicio"], p["fin"],
                rfc_receptor=p["rfc"], tipo_solicitud=p["solicitud"],
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
        log.error(f"  ✗ Error al enviar solicitud al SAT. Causa: {e}")
        log.error("  Posibles causas:")
        log.error("    • Período ya solicitado 2+ veces con CFDI (error 5002)")
        log.error("    • Token expirado — se renovará en el próximo intento")
        log.error("    • RFC incorrecto o FIEL no asociada a ese RFC")
        return None
 
 
# ---------------------------------------------------------------------------
# Paso 4a — Verificar con polling (para CFDI — hace sys.exit en error)
# ---------------------------------------------------------------------------
def verificar_solicitud(fiel: Fiel, id_solicitud: str, p: dict) -> list[str]:
    """
    Consulta periódicamente al SAT hasta que la solicitud esté lista.
    Retorna la lista de IDs de paquetes disponibles para descarga.
    Hace sys.exit() en estados de error — usado para el flujo CFDI.
    El SAT puede tardar de minutos a 72 horas en alta demanda.
    """
    log.info(f"Verificando solicitud: {id_solicitud}")
    log.info(f"  Consultando cada {p['intervalo']}s hasta que el SAT confirme...")
 
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
            log.warning(f"  ✗ Error en verificación #{intento}. Causa: {e}")
            log.info(f"  Reintentando en {p['intervalo']}s...")
            time.sleep(p["intervalo"])
            continue
 
        estado      = int(verificacion.get("estado_solicitud", -1))
        estado_desc = ESTADOS_SOLICITUD.get(estado, f"Desconocido ({estado})")
        num_cfdi    = verificacion.get("numero_cfdis", "0")
        paquetes    = verificacion.get("paquetes") or []
 
        log.info(f"  Estado: {estado} — {estado_desc} | CFDIs reportados: {num_cfdi}")
 
        if estado in (1, 2):
            log.info(f"  SAT aún procesando. Próximo intento en {p['intervalo']}s...")
            time.sleep(p["intervalo"])
 
        elif estado == 3:
            log.info(f"✔ Solicitud terminada. Paquetes disponibles: {len(paquetes)}")
            for i, pk in enumerate(paquetes, 1):
                log.info(f"    [{i}] {pk}")
            return paquetes
 
        elif estado == 5:
            cod = verificacion.get("codigo_estado_solicitud", "")
            log.error(f"✗ Solicitud rechazada por el SAT. Código: {cod}")
            log.error("  No hay CFDIs en ese período para este RFC, o la solicitud es inválida.")
            sys.exit(1)
 
        elif estado == 6:
            log.error("✗ Solicitud vencida. El SAT eliminó esta solicitud por inactividad.")
            log.error("  Genera una nueva solicitud.")
            sys.exit(1)
 
        else:
            log.error(f"✗ Estado inesperado: {estado_desc}")
            log.error("  Contacta la Mesa de Ayuda del SAT si persiste.")
            sys.exit(1)
 
 
# ---------------------------------------------------------------------------
# Paso 4b — Verificar sin sys.exit (para Metadata en loop mensual)
# ---------------------------------------------------------------------------
def verificar_solicitud_raw(fiel: Fiel, id_solicitud: str, p: dict) -> dict:
    """
    Igual que verificar_solicitud pero retorna el dict raw en lugar de hacer sys.exit.
    Usada en el loop mensual de Metadata para poder continuar ante 5004 u otros errores.
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
            log.info(f"    SAT procesando... próximo intento en {p['intervalo']}s (verificación #{intento})")
            time.sleep(p["intervalo"])
        else:
            return verificacion
 
 
# ---------------------------------------------------------------------------
# Paso 5 — Descargar un paquete ZIP
# ---------------------------------------------------------------------------
def descargar_paquete(fiel: Fiel, id_paquete: str, rfc: str, output_dir: Path,
                      numero: int, total: int) -> Path | None:
    """
    Descarga un paquete del SAT (ZIP en base64) y lo guarda en disco.
    Reintenta hasta MAX_REINTENTOS_DESCARGA veces ante fallos de red o token expirado.
    Retorna la ruta al ZIP guardado, o None si falló tras todos los reintentos.
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
            log.info(f"    ✔ Paquete guardado: {zip_path.name} ({kb:.1f} KB)")
            return zip_path
 
        except Exception as e:
            log.warning(f"    ✗ Fallo en intento {intento}. Causa: {e}")
            if intento < MAX_REINTENTOS_DESCARGA:
                log.info(f"    Reintentando en {PAUSA_ENTRE_REINTENTOS}s...")
                time.sleep(PAUSA_ENTRE_REINTENTOS)
            else:
                log.error(f"  ✗ Se agotaron los reintentos para: {id_paquete}")
                log.error("    Este paquete se omitirá. Puedes re-ejecutar para reintentarlo.")
                return None
 
 
# ---------------------------------------------------------------------------
# Paso 6 — Extraer archivos del ZIP
# ---------------------------------------------------------------------------
def extraer_archivos(zip_path: Path, nombre_destino: str | None = None) -> list[Path]:
    """
    Extrae todos los archivos del ZIP descargado.
    - nombre_destino: si se pasa, renombra el primer archivo con ese nombre.
      Usado en modo Metadata para nombrar el .txt como YYYY-MM-RFC.txt
    - Sin nombre_destino: extrae con nombres originales en subcarpeta del paquete.
    """
    archivo_dir = zip_path.parent
    archivo_dir.mkdir(parents=True, exist_ok=True)
 
    log.info(f"  Extrayendo: {zip_path.name}")
 
    try:
        extraidos: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            contenido = zf.namelist()
            log.info(f"  Archivos en el paquete: {len(contenido)}")
 
            for i, nombre in enumerate(contenido):
                if nombre_destino and i == 0:
                    # Preservar la extensión original del archivo
                    ext  = Path(nombre).suffix or ".txt"
                    dest = archivo_dir / f"{nombre_destino}{ext}"
                else:
                    # Sin nombre personalizado: subcarpeta por paquete
                    sub = archivo_dir / zip_path.stem
                    sub.mkdir(exist_ok=True)
                    dest = sub / nombre
 
                dest.write_bytes(zf.read(nombre))
                extraidos.append(dest)
                log.info(f"    → {dest.name}")
 
        log.info(f"  ✔ {len(extraidos)} archivo(s) extraído(s).")
        return extraidos
 
    except zipfile.BadZipFile:
        log.error(f"  ✗ ZIP corrupto o incompleto: {zip_path}")
        log.error("  Elimina el ZIP y re-ejecuta el script para volver a descargarlo.")
        return []
    except Exception as e:
        log.error(f"  ✗ Error inesperado al extraer ZIP. Causa: {e}")
        return []
 
 
# ---------------------------------------------------------------------------
# Helper — Generar períodos mensuales
# ---------------------------------------------------------------------------
def generar_periodos_mensuales(inicio: date, fin: date) -> list[tuple[date, date]]:
    """
    Divide un rango de fechas en sub-períodos de un mes cada uno.
    Usado exclusivamente en modo Metadata para logs granulares por mes/año
    y para continuar automáticamente cuando un mes no tiene CFDIs (5004).
    """
    periodos = []
    actual   = inicio.replace(day=1)
 
    while actual <= fin:
        ultimo_dia = monthrange(actual.year, actual.month)[1]
        mes_inicio = max(actual, inicio)
        mes_fin    = min(date(actual.year, actual.month, ultimo_dia), fin)
        periodos.append((mes_inicio, mes_fin))
 
        if actual.month == 12:
            actual = date(actual.year + 1, 1, 1)
        else:
            actual = date(actual.year, actual.month + 1, 1)
 
    return periodos
 
 
# ---------------------------------------------------------------------------
# Helper — Procesar un período mensual completo
# ---------------------------------------------------------------------------
def procesar_periodo_metadata(fiel: Fiel, p: dict, mes_inicio: date, mes_fin: date,
                              numero: int, total: int) -> list[Path]:
    """
    Ejecuta el flujo completo (solicitar → verificar → descargar → extraer)
    para un mes específico en modo Metadata.
    Retorna lista de archivos descargados, o lista vacía si el mes no tiene CFDIs.
    Nunca hace sys.exit() — deja que el loop principal decida continuar.
    """
    MESES_ES = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }
    mes_label = f"{MESES_ES[mes_inicio.month]} {mes_inicio.year}"
 
    log.info("")
    log.info(f"  ┌─ [{numero}/{total}] {mes_label}  ({mes_inicio} → {mes_fin})")
 
    p_mes = {**p, "inicio": mes_inicio, "fin": mes_fin}
 
    try:
        token        = obtener_token(fiel)
        id_solicitud = solicitar_descarga(fiel, token, p_mes)
 
        if not id_solicitud:
            log.info(f"  └─ {mes_label}: Sin actividad reportada por el SAT — continuando.")
            return []
 
        verificacion = verificar_solicitud_raw(fiel, id_solicitud, p_mes)
 
        estado   = int(verificacion.get("estado_solicitud", -1))
        cod      = verificacion.get("codigo_estado_solicitud", "")
        num_cfdi = int(verificacion.get("numero_cfdis", 0) or 0)
        paquetes = verificacion.get("paquetes") or []
 
        if estado == 5 and cod == "5004":
            log.info(f"  └─ {mes_label}: Sin CFDIs en este período — continuando.")
            return []
 
        if estado == 5:
            log.warning(f"  └─ {mes_label}: Rechazado por el SAT (código {cod}) — continuando.")
            return []
 
        if estado != 3:
            log.warning(f"  └─ {mes_label}: Estado inesperado {estado} — continuando.")
            return []
 
        log.info(f"  │  ✔ {num_cfdi} CFDI(s) encontrados")
        log.info(f"  │  Paquetes a descargar: {len(paquetes)}")
 
        archivos: list[Path] = []
        for i, id_paquete in enumerate(paquetes, 1):
            zip_path = descargar_paquete(fiel, id_paquete, p["rfc"], p["output"], i, len(paquetes))
            if zip_path:
                # Nombre: YYYY-MM-RFC (ej. 2025-01-VAVC930829LJ1)
                nombre_destino = f"{mes_inicio.strftime('%Y-%m')}-{p['rfc']}"
                extraidos = extraer_archivos(zip_path, nombre_destino=nombre_destino)
                archivos.extend(extraidos)
 
        log.info(f"  └─ {mes_label}: {len(archivos)} archivo(s) guardados. ✔")
        return archivos
 
    except Exception as e:
        log.warning(f"  └─ {mes_label}: Error inesperado ({e}) — continuando con el siguiente mes.")
        return []
 
 
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> dict | None:
    """Retorna dict con parámetros si se pasaron argumentos, o None para modo interactivo."""
    if len(sys.argv) == 1:
        return None
 
    p = argparse.ArgumentParser(description="Descarga masiva de CFDI (XML) del SAT")
    p.add_argument("--rfc",       required=True)
    p.add_argument("--cer",       required=True,  type=Path)
    p.add_argument("--key",       required=True,  type=Path)
    p.add_argument("--password",  required=False, default=None,
                   help="Contraseña FIEL. Si se omite, se pedirá de forma segura (recomendado para contraseñas con espacios).")
    p.add_argument("--inicio",    required=True,  type=date.fromisoformat)
    p.add_argument("--fin",       required=True,  type=date.fromisoformat)
    p.add_argument("--tipo",      choices=["emitidos", "recibidos"], default="recibidos")
    p.add_argument("--solicitud", choices=["CFDI", "Metadata"],      default="CFDI")
    p.add_argument("--output",    type=Path, default=None,
                   help="Carpeta de salida. Si se omite, se crea automáticamente como ./results_RFC")
    p.add_argument("--intervalo", type=int,  default=60)
    args = p.parse_args()
 
    password = args.password
    if not password:
        log.info("--password no proporcionado. Solicitando de forma segura...")
        password = getpass("  → Contraseña de la FIEL (oculta): ")
 
    rfc    = args.rfc.upper()
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
        "output":    output,
        "intervalo": args.intervalo,
    }
 
 
 
# ---------------------------------------------------------------------------
# Helper — Generar resumen legible del contenido de Metadata
# ---------------------------------------------------------------------------
def generar_resumen_metadata(archivos: list[Path], params: dict) -> list[str]:
    """
    Lee los archivos .txt de Metadata descargados y genera un resumen
    legible para humanos con totales por mes, emisores frecuentes y montos.
    Formato del Metadata SAT (separado por ~):
    UUID~RfcEmisor~NombreEmisor~RfcReceptor~NombreReceptor~PacCertificado
    ~FechaEmision~FechaCertificacionSat~Monto~EfectoComprobante~Estatus~FechaCancelacion
    """
    if not archivos:
        return ["  Sin archivos de Metadata para resumir."]
 
    MESES_ES = {
        "01": "Enero",   "02": "Febrero",  "03": "Marzo",    "04": "Abril",
        "05": "Mayo",    "06": "Junio",    "07": "Julio",    "08": "Agosto",
        "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
    }
 
    total_cfdis  = 0
    total_monto  = 0.0
    por_mes: dict[str, dict] = {}
    emisores: dict[str, int] = {}
 
    for archivo in archivos:
        if not archivo.suffix.lower() == ".txt":
            continue
        try:
            lineas = archivo.read_text(encoding="utf-8", errors="ignore").splitlines()
            # Primera línea es encabezado
            datos = [l for l in lineas[1:] if l.strip()]
            # Extraer YYYY-MM del nombre del archivo (formato YYYY-MM-RFC.txt)
            partes    = archivo.stem.split("-")
            clave_mes = f"{partes[0]}-{partes[1]}" if len(partes) >= 2 else "??-??"
            mes_num   = partes[1] if len(partes) >= 2 else "??"
            anio      = partes[0] if len(partes) >= 1 else "????"
            mes_label = f"{MESES_ES.get(mes_num, mes_num)} {anio}"
 
            mes_cfdis = 0
            mes_monto = 0.0
 
            for linea in datos:
                cols = linea.split("~")
                if len(cols) < 9:
                    continue
                mes_cfdis += 1
                total_cfdis += 1
                try:
                    monto = float(cols[8].replace(",", "").strip())
                    mes_monto   += monto
                    total_monto += monto
                except ValueError:
                    pass
                rfc_emisor    = cols[1].strip() if len(cols) > 1 else "?"
                nombre_emisor = cols[2].strip() if len(cols) > 2 else "?"
                clave_emisor  = f"{rfc_emisor} — {nombre_emisor}"
                emisores[clave_emisor] = emisores.get(clave_emisor, 0) + 1
 
            por_mes[clave_mes] = {
                "label":  mes_label,
                "cfdis":  mes_cfdis,
                "monto":  mes_monto,
            }
        except Exception as e:
            log.warning(f"  No se pudo leer el archivo de Metadata: {archivo.name}. Causa: {e}")
 
    if total_cfdis == 0:
        return ["  No se encontraron registros legibles en los archivos de Metadata."]
 
    lineas_resumen = []
    tipo_label = "emitidas" if params["tipo"] == "emitidos" else "recibidas"
 
    lineas_resumen.append(f"  El RFC {params['rfc']} tiene {total_cfdis} factura(s) {tipo_label}")
    lineas_resumen.append(f"  en el período {params['inicio']} → {params['fin']}.")
    lineas_resumen.append(f"  Monto total acumulado: ${total_monto:,.2f} MXN")
    lineas_resumen.append("")
    lineas_resumen.append("  Desglose por mes:")
 
    for clave in sorted(por_mes.keys()):
        info = por_mes[clave]
        lineas_resumen.append(
            f"    • {info['label']:<20} {info['cfdis']:>5} CFDI(s)   "
            f"${info['monto']:>14,.2f} MXN"
        )
 
    if emisores:
        top_emisores = sorted(emisores.items(), key=lambda x: x[1], reverse=True)[:5]
        lineas_resumen.append("")
        lineas_resumen.append("  Top 5 emisores/receptores frecuentes:")
        for nombre, cantidad in top_emisores:
            lineas_resumen.append(f"    • {cantidad:>4}x  {nombre}")
 
    return lineas_resumen
 
 
# ---------------------------------------------------------------------------
# Main
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
    log.info(f"Carpeta de salida: {params['output'].resolve()}")
 
    fiel = cargar_fiel(params["cer"], params["key"], params["password"])
 
    # -----------------------------------------------------------------------
    # Modo Metadata — procesa mes a mes, continúa si no hay CFDIs en un mes
    # -----------------------------------------------------------------------
    if params["solicitud"] == "Metadata":
        periodos = generar_periodos_mensuales(params["inicio"], params["fin"])
        total    = len(periodos)
 
        log.info("")
        log.info(f"Modo METADATA — {total} mes(es) a procesar")
        log.info(f"  RFC    : {params['rfc']}")
        log.info(f"  Tipo   : {params['tipo']}")
        log.info(f"  Rango  : {params['inicio']} → {params['fin']}")
        log.info("  El script avanzará automáticamente si un mes no tiene CFDIs.")
 
        archivos_totales: list[Path] = []
        meses_con_datos  = 0
        meses_sin_datos  = 0
 
        for i, (mes_inicio, mes_fin) in enumerate(periodos, 1):
            archivos = procesar_periodo_metadata(fiel, params, mes_inicio, mes_fin, i, total)
            if archivos:
                meses_con_datos += 1
                archivos_totales.extend(archivos)
            else:
                meses_sin_datos += 1
 
        duracion = int((datetime.now() - inicio_proceso).total_seconds())
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
        log.info(f"  Carpeta de salida    : {params['output'].resolve()}")
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
    # Modo CFDI — respeta el rango completo sin dividir por mes
    # -----------------------------------------------------------------------
    else:
        log.info("")
        log.info("Modo CFDI — procesando rango completo (sin dividir por mes)")
        log.info("⚠  Recuerda: máximo 2 solicitudes por el mismo período+RFC.")
 
        token        = obtener_token(fiel)
        id_solicitud = solicitar_descarga(fiel, token, params)
 
        if not id_solicitud:
            log.error("✗ No se pudo obtener un ID de solicitud del SAT.")
            sys.exit(1)
 
        paquetes = verificar_solicitud(fiel, id_solicitud, params)
 
        if not paquetes:
            log.warning("El SAT no devolvió paquetes. No hay CFDI en ese período para este RFC.")
            sys.exit(0)
 
        archivos_totales: list[Path] = []
        log.info(f"Iniciando descarga de {len(paquetes)} paquete(s)...")
 
        for i, id_paquete in enumerate(paquetes, 1):
            zip_path = descargar_paquete(fiel, id_paquete, params["rfc"], params["output"], i, len(paquetes))
            if zip_path:
                extraidos = extraer_archivos(zip_path)
                archivos_totales.extend(extraidos)
 
        duracion = int((datetime.now() - inicio_proceso).total_seconds())
        log.info("")
        log.info("=" * 65)
        log.info("RESUMEN FINAL — DESCARGA MASIVA CFDI")
        log.info("=" * 65)
        log.info(f"  RFC                  : {params['rfc']}")
        log.info(f"  Rango procesado      : {params['inicio']} → {params['fin']}")
        log.info(f"  Archivos descargados : {len(archivos_totales)}")
        log.info(f"  Carpeta de salida    : {params['output'].resolve()}")
        log.info(f"  Duración total       : {duracion // 60}m {duracion % 60}s")
        log.info(f"  Log guardado en      : sat_descarga.log")
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