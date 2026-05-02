"""
descarga_masiva.py
------------------
Entry point del CLI de taxcrawler-dm.
Orquesta los flujos de descarga usando los modulos especializados.

Uso rapido:
  python descarga_masiva.py --help

Flujos disponibles:
  Metadata       : --solicitud Metadata
  CFDI           : --solicitud CFDI
  Completo E2E   : --flujo-completo
  Utilitarios    : --pendientes | --retomar | --retomar-todas | --perfil | --reveal-cache
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependencias locales — libs/ tiene prioridad sobre el sistema
# ---------------------------------------------------------------------------
_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

# ---------------------------------------------------------------------------
# Modulos del proyecto
# ---------------------------------------------------------------------------
from config import (
    RETOMAR_TIMEOUT_MIN,
    get_despacho_name,
    log,
    resolve_isr_table,
    resolve_password,
    validate_salt,
)
from cache_manager import (
    add_pending,
    get_attempt_history,
    read_pending,
    read_profile,
    register_attempt,
    remove_pending,
    reveal_history,
    show_pending,
    show_profile,
    write_profile,
)
from sat_client import (
    apply_date_offset,
    download_package,
    get_token,
    load_fiel,
    request_download,
    verify_raw,
    verify_with_timeout,
)
from file_handler import (
    extract_cfdi,
    extract_metadata,
    resolve_output_dir,
    resolve_retomar_output_dir,
)
from metadata_parser import (
    generate_metadata_summary,
    generate_monthly_periods,
)


# ===========================================================================
# Validacion de parametros — fail-fast antes de tocar el SAT
# ===========================================================================

def validate_params(p: dict) -> None:
    """
    Valida todos los parametros antes de cualquier llamada al SAT.
    Lista todos los errores juntos y sale — no gasta solicitudes con datos invalidos.
    """
    log.info("Validando parametros antes de iniciar el proceso...")
    errors = []

    if not p["cer"].exists():
        errors.append(f"Archivo .cer no encontrado: {p['cer']}")

    if not p["key"].exists():
        errors.append(f"Archivo .key no encontrado: {p['key']}")

    if p["inicio"] > p["fin"]:
        errors.append(
            f"La fecha de inicio ({p['inicio']}) es posterior a la fecha fin ({p['fin']})"
        )

    today     = date.today()
    sat_limit = date(today.year - 6, today.month, today.day)
    if p["inicio"] < sat_limit:
        errors.append(
            f"El SAT solo permite descargar CFDI desde {sat_limit} (6 anios atras). "
            f"Tu fecha de inicio es {p['inicio']}"
        )

    if p["intervalo"] < 10:
        errors.append("El intervalo de verificacion debe ser al menos 10 segundos.")

    if p.get("timeout") is not None and p["timeout"] < 5:
        errors.append("El timeout debe ser al menos 5 minutos.")

    if p.get("excel") and p.get("solicitud") != "CFDI":
        errors.append("--excel solo esta disponible en modo --solicitud CFDI.")

    if errors:
        log.error(f"Se encontraron {len(errors)} error(es) de validacion:")
        for e in errors:
            log.error(f"  X {e}")
        sys.exit(1)

    log.info("  Todos los parametros son validos.")


# ===========================================================================
# Modo interactivo
# ===========================================================================

def ask_params() -> dict:
    """
    Solicita los parametros de forma interactiva cuando no se pasan argumentos CLI.
    Valida rutas de archivos en tiempo real.
    """
    log.info("=" * 65)
    log.info("MODO INTERACTIVO — Se solicitaran los parametros necesarios")
    log.info("=" * 65)
    print()

    def ask(prompt: str, required: bool = True, default: str = "") -> str:
        while True:
            suffix = f" [{default}]" if default else ""
            value  = input(f"  -> {prompt}{suffix}: ").strip()
            if not value and default:
                return default
            if value or not required:
                return value
            print("    ! Este campo es obligatorio.")

    rfc = ask("RFC del contribuyente").upper()

    cer = ask("Ruta al archivo .cer de la FIEL")
    while not Path(cer).exists():
        print(f"    X No se encontro: {cer}")
        cer = ask("Ruta al archivo .cer de la FIEL")

    key = ask("Ruta al archivo .key de la FIEL")
    while not Path(key).exists():
        print(f"    X No se encontro: {key}")
        key = ask("Ruta al archivo .key de la FIEL")

    password    = resolve_password(rfc)
    inicio      = ask("Fecha inicio (YYYY-MM-DD)", default="2024-01-01")
    fin         = ask("Fecha fin    (YYYY-MM-DD)", default=str(date.today()))

    tipo = ""
    while tipo not in ("emitidos", "recibidos"):
        tipo = ask("Tipo [emitidos / recibidos]", default="recibidos").lower()

    solicitud = ""
    while solicitud not in ("CFDI", "Metadata"):
        solicitud = ask("Tipo de solicitud [CFDI / Metadata]", default="CFDI")

    timeout_str = ask("Timeout en minutos (Enter para sin limite)", required=False, default="")
    output      = ask(f"Carpeta base (Enter para usar ./results_{rfc})", required=False, default="")
    intervalo   = ask("Segundos entre verificaciones", default="60")

    print()
    log.info("Parametros capturados correctamente.")

    return {
        "rfc":             rfc,
        "cer":             Path(cer),
        "key":             Path(key),
        "password":        password,
        "inicio":          date.fromisoformat(inicio),
        "fin":             date.fromisoformat(fin),
        "tipo":            tipo,
        "solicitud":       solicitud,
        "excel":           None,
        "timeout":         int(timeout_str) if timeout_str.isdigit() else None,
        "output":          Path(output) if output else Path(f"./results_{rfc}"),
        "intervalo":       int(intervalo),
        "flujo_completo":  False,
        "regimen":         "resico",
        "acumulado_anual": False,
        "despacho":        None,
        "tabla_isr":       None,
    }


# ===========================================================================
# Flujo: retomar solicitud pendiente
# ===========================================================================

def run_retomar(request_id: str, fiel, timeout_min: int | None) -> bool:
    """
    Retoma el polling de una solicitud pendiente especifica por ID.
    Busca el ID en todos los archivos .pending.enc disponibles.
    Retorna True si completo exitosamente, False si sigue pendiente o fallo.
    """
    from config import CACHE_DIR
    from cache_manager import elapsed_label

    validate_salt()

    info = None
    rfc  = None
    for archivo in CACHE_DIR.glob("*.pending.enc") if CACHE_DIR.exists() else []:
        rfc_candidate = archivo.stem.replace(".pending", "")
        pending       = read_pending(rfc_candidate)
        if request_id in pending:
            info = pending[request_id]
            rfc  = rfc_candidate
            break

    if not info or rfc is None:
        log.error(f"X ID no encontrado en ningun archivo de pendientes: {request_id}")
        log.error("  Usa --pendientes para ver las solicitudes disponibles.")
        return False

    rfc = str(rfc)

    log.info("")
    log.info("=" * 65)
    log.info(f"Retomando solicitud: {request_id}")
    log.info(f"  RFC      : {info.get('rfc', rfc)}")
    log.info(f"  Periodo  : {info.get('inicio')} -> {info.get('fin')} "
             f"({info.get('tipo')} / {info.get('solicitud')})")
    log.info(f"  Creado   : {info.get('creado', '—')} "
             f"({elapsed_label(info.get('creado', ''))})")
    log.info(f"  Salida   : {info.get('output')}")
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

    result = verify_with_timeout(fiel, request_id, p_retomar, timeout_min)

    if result in ("rechazada", "vencida"):
        remove_pending(rfc, request_id, result)
        log.info(f"  Solicitud eliminada de pendientes ({result}).")
        return False

    if result is None:
        log.warning(f"  Solicitud {request_id} sigue pendiente.")
        log.warning(f"  Retoma con: python descarga_masiva.py --retomar {request_id}")
        return False

    packages   = result
    output_dir = resolve_retomar_output_dir(p_retomar)
    base_name  = f"{p_retomar['inicio'].strftime('%Y-%m')}-{rfc}"
    all_xmls: list[Path] = []

    log.info(f"  Iniciando descarga de {len(packages)} paquete(s)...")
    for i, pkg_id in enumerate(packages, 1):
        zip_path = download_package(fiel, pkg_id, rfc, output_dir, i, len(packages))
        if zip_path:
            pkg_name = base_name if len(packages) == 1 else f"{base_name}_{i}"
            xmls, _  = extract_cfdi(zip_path, pkg_name)
            all_xmls.extend(xmls)

    remove_pending(rfc, request_id, "completada")
    log.info(f"  Solicitud completada. {len(all_xmls)} XML(s) descargados.")
    return True


def run_retomar_todas(rfc_target: str, timeout_min: int | None) -> None:
    """
    Retoma en secuencia todas las solicitudes pendientes de un RFC o de todos.
    Una contrasena por RFC por sesion — no se repite si hay multiples pendientes.
    Si un RFC falla, continua con el siguiente.
    """
    from config import CACHE_DIR

    validate_salt()

    pending_files = list(CACHE_DIR.glob("*.pending.enc")) if CACHE_DIR.exists() else []

    if not pending_files:
        log.info("No hay solicitudes pendientes para retomar.")
        return

    if rfc_target != "all":
        pending_files = [f for f in pending_files
                         if f.stem.replace(".pending", "").upper() == rfc_target.upper()]

    if not pending_files:
        log.info(f"No hay solicitudes pendientes para RFC: {rfc_target}")
        return

    ids_to_resume: list[tuple[str, str]] = []
    for archivo in sorted(pending_files):
        rfc_file = archivo.stem.replace(".pending", "")
        pending  = read_pending(rfc_file)
        for req_id in pending:
            ids_to_resume.append((rfc_file, req_id))

    total          = len(ids_to_resume)
    completed      = 0
    failed         = 0
    still_pending: list[str] = []
    session_pwds: dict[str, str] = {}

    log.info("")
    log.info("=" * 65)
    log.info(f"RETOMAR SOLICITUDES PENDIENTES — {total} en total")
    log.info("=" * 65)

    for i, (rfc, req_id) in enumerate(ids_to_resume, 1):
        log.info(f"\nProcesando {i}/{total}: {req_id} ({rfc})")

        if rfc not in session_pwds:
            log.info(f"  Autenticacion requerida para RFC {rfc}.")
            profile = read_profile(rfc)
            cer_r   = Path(profile["cer"]) if profile.get("cer") and Path(profile["cer"]).exists() else None
            key_r   = Path(profile["key"]) if profile.get("key") and Path(profile["key"]).exists() else None

            if not cer_r or not key_r:
                log.warning(f"  ! Sin perfil valido para {rfc} — saltando.")
                continue

            pwd = resolve_password(rfc, f"Contrasena de la FIEL para {rfc}")
            try:
                from cfdiclient import Fiel as FielClass
                FielClass(cer_r.read_bytes(), key_r.read_bytes(), pwd)
                session_pwds[rfc] = pwd
                log.info(f"  Contrasena validada para {rfc}. Reutilizando en esta sesion.")
            except Exception as e:
                log.error(f"  X Contrasena incorrecta para {rfc}: {e}")
                continue

        profile = read_profile(rfc)
        fiel_r  = load_fiel(Path(profile["cer"]), Path(profile["key"]), session_pwds[rfc])
        success = run_retomar(req_id, fiel_r, timeout_min)

        if success:
            completed += 1
        else:
            if req_id in read_pending(rfc):
                still_pending.append(req_id)
            else:
                failed += 1

    log.info("")
    log.info("=" * 65)
    log.info("RESUMEN — RETOMAR SOLICITUDES PENDIENTES")
    log.info("=" * 65)
    log.info(f"  Procesadas     : {total}")
    log.info(f"  Completadas    : {completed}")
    log.info(f"  Error terminal : {failed}")
    log.info(f"  Aun pendientes : {len(still_pending)}")
    log.info("=" * 65)

    if still_pending:
        log.info("")
        log.info("  Solicitudes que siguen pendientes:")
        for req_id in still_pending:
            log.info(f"    * --retomar {req_id}")
        log.info("")
        log.info("  Para retomar automaticamente con cron:")
        log.info("  0 * * * * cd /ruta/proyecto && python descarga_masiva.py \\")
        log.info(f"    --retomar-todas {rfc_target}")
    log.info("=" * 65)


# ===========================================================================
# Flujo: Metadata mensual
# ===========================================================================

def run_metadata(fiel, params: dict, output_dir: Path) -> list[Path]:
    """
    Ejecuta la descarga de Metadata para cada mes en el rango.
    Continua automaticamente si un mes no tiene CFDIs (codigo 5004).
    Retorna la lista de archivos TXT descargados.
    """
    from config import MESES_ES

    periods = generate_monthly_periods(params["inicio"], params["fin"])
    total   = len(periods)

    log.info("")
    log.info(f"Modo METADATA — {total} mes(es) a procesar")
    log.info(f"  RFC        : {params['rfc']}")
    log.info(f"  Tipo       : {params['tipo']}")
    log.info(f"  Rango      : {params['inicio']} -> {params['fin']}")
    log.info(f"  Salida     : {output_dir.resolve()}")
    log.info("  ZIPs se eliminaran automaticamente tras extraer cada TXT.")
    log.info("  El script avanzara si un mes no tiene CFDIs (codigo 5004).")

    all_files: list[Path] = []
    months_with  = 0
    months_empty = 0

    for i, (month_start, month_end) in enumerate(periods, 1):
        month_num = month_start.strftime("%m")
        month_lbl = f"{MESES_ES[month_num]} {month_start.year}"

        log.info("")
        log.info(f"  +-- [{i}/{total}] {month_lbl}  ({month_start} -> {month_end})")

        p_month = {**params, "inicio": month_start, "fin": month_end, "output": output_dir}

        try:
            token      = get_token(fiel)
            request_id = request_download(fiel, token, p_month)

            if not request_id:
                log.info(f"  +-- {month_lbl}: Sin actividad — continuando.")
                months_empty += 1
                continue

            verification = verify_raw(fiel, request_id, p_month)
            estado       = int(verification.get("estado_solicitud", -1))
            cod          = verification.get("codigo_estado_solicitud", "")
            num_cfdi     = int(verification.get("numero_cfdis", 0) or 0)
            packages     = verification.get("paquetes") or []

            if estado == 5 and cod == "5004":
                log.info(f"  +-- {month_lbl}: Sin CFDIs en este periodo — continuando.")
                months_empty += 1
                continue
            if estado == 5:
                log.warning(f"  +-- {month_lbl}: Rechazado por SAT (codigo {cod}) — continuando.")
                months_empty += 1
                continue
            if estado != 3:
                log.warning(f"  +-- {month_lbl}: Estado inesperado {estado} — continuando.")
                months_empty += 1
                continue

            log.info(f"  |   {num_cfdi} CFDI(s) | {len(packages)} paquete(s)")

            month_files: list[Path] = []
            for j, pkg_id in enumerate(packages, 1):
                zip_path = download_package(fiel, pkg_id, params["rfc"], output_dir, j, len(packages))
                if zip_path:
                    dest_name = f"{month_start.strftime('%Y-%m')}-{params['rfc']}"
                    extracted = extract_metadata(zip_path, dest_name)
                    month_files.extend(extracted)

            log.info(f"  +-- {month_lbl}: {len(month_files)} archivo(s) guardados.")
            all_files.extend(month_files)
            months_with += 1

        except Exception as e:
            log.warning(f"  +-- {month_lbl}: Error inesperado ({e}) — continuando.")
            months_empty += 1

    log.info("")
    log.info(f"  Meses con CFDIs    : {months_with}")
    log.info(f"  Meses sin actividad: {months_empty}")
    return all_files


# ===========================================================================
# Flujo: CFDI rango completo
# ===========================================================================

def run_cfdi(fiel, params: dict, output_dir: Path) -> list[Path]:
    """
    Ejecuta la descarga de CFDI para el rango completo.
    Aplica bypass de offset automaticamente usando el cache encriptado.
    Registra la solicitud como pendiente inmediatamente tras la aceptacion.
    """
    timeout_min = params.get("timeout")

    log.info("")
    log.info("Modo CFDI — procesando rango completo")
    log.info(f"  RFC        : {params['rfc']}")
    log.info(f"  Tipo       : {params['tipo']}")
    log.info(f"  Rango      : {params['inicio']} -> {params['fin']}")
    log.info(f"  Salida     : {output_dir.resolve()}")
    log.info(f"  Timeout    : {f'{timeout_min} min' if timeout_min else 'sin limite'}")

    history       = get_attempt_history(params["rfc"], params["inicio"],
                                        params["fin"], params["tipo"])
    prev_attempts = history["intentos"]

    if prev_attempts == 0:
        log.info("  Cache: primera solicitud para este periodo.")
    else:
        log.info(f"  Cache: {prev_attempts} intento(s) previo(s) detectado(s).")
        log.info(f"  Bypass activado: offset de +{history['offset_segundos']}s.")

    current_offset   = register_attempt(params["rfc"], params["inicio"],
                                        params["fin"], params["tipo"])
    dt_start, dt_end = apply_date_offset(params["inicio"], params["fin"], current_offset)

    log.info(f"  Periodo efectivo : {dt_start} -> {dt_end}")

    token      = get_token(fiel)
    request_id = request_download(fiel, token, params, dt_start, dt_end)

    if not request_id:
        log.error("X No se pudo obtener un ID de solicitud del SAT.")
        sys.exit(1)

    add_pending(params["rfc"], request_id, params, dt_start, dt_end)

    result = verify_with_timeout(fiel, request_id, params, timeout_min)

    if result in ("rechazada", "vencida"):
        remove_pending(params["rfc"], request_id, result)
        log.error(f"X Solicitud {result}. No es posible recuperarla.")
        sys.exit(1)

    if result is None:
        log.warning("")
        log.warning("Proceso detenido por timeout.")
        log.warning("La solicitud sigue registrada en pendientes.")
        log.warning(f"Para retomar: python descarga_masiva.py --retomar {request_id}")
        log.warning("O revisa todos: python descarga_masiva.py --pendientes")
        sys.exit(0)

    packages   = result
    base_name  = f"{params['inicio'].strftime('%Y-%m')}-{params['rfc']}"
    all_xmls: list[Path] = []

    log.info(f"Iniciando descarga de {len(packages)} paquete(s)...")
    for i, pkg_id in enumerate(packages, 1):
        zip_path = download_package(fiel, pkg_id, params["rfc"], output_dir, i, len(packages))
        if zip_path:
            pkg_name = base_name if len(packages) == 1 else f"{base_name}_{i}"
            xmls, _  = extract_cfdi(zip_path, pkg_name)
            all_xmls.extend(xmls)

    remove_pending(params["rfc"], request_id, "completada")
    log.info(f"  Intento #  : {prev_attempts + 1} (offset: +{current_offset}s)")
    log.info(f"  XMLs       : {len(all_xmls)} descargados")
    return all_xmls


# ===========================================================================
# Flujo completo E2E: Metadata + Excel
# ===========================================================================

def run_full_flow(fiel, params: dict) -> None:
    """
    Ejecuta el flujo completo para un cliente:
      Paso 1 — Descarga Metadata de emitidos (ingresos)
      Paso 2 — Descarga Metadata de recibidos (gastos)
      Paso 3 — Genera el Excel con Papel de Trabajo
    """
    log.info("")
    log.info("=" * 65)
    log.info("FLUJO COMPLETO — METADATA + EXCEL")
    log.info(f"  RFC    : {params['rfc']}")
    log.info(f"  Rango  : {params['inicio']} -> {params['fin']}")
    log.info("=" * 65)

    # Paso 1 — ingresos
    log.info("")
    log.info("PASO 1/3 — Descargando Metadata de INGRESOS (emitidos)...")
    params_emitidos = {**params, "tipo": "emitidos", "solicitud": "Metadata"}
    output_emitidos = resolve_output_dir(params_emitidos)
    files_ingresos  = run_metadata(fiel, params_emitidos, output_emitidos)

    # Paso 2 — gastos
    log.info("")
    log.info("PASO 2/3 — Descargando Metadata de GASTOS (recibidos)...")
    params_recibidos = {**params, "tipo": "recibidos", "solicitud": "Metadata"}
    output_recibidos = resolve_output_dir(params_recibidos)
    files_gastos     = run_metadata(fiel, params_recibidos, output_recibidos)

    # Paso 3 — Excel
    log.info("")
    log.info("PASO 3/3 — Generando Excel con Papel de Trabajo...")

    try:
        from excel_generator import generate_excel
        isr_table  = resolve_isr_table(params.get("tabla_isr"))
        despacho   = get_despacho_name(params.get("despacho"))

        excel_path = generate_excel(
            rfc             = params["rfc"],
            start_date      = params["inicio"],
            end_date        = params["fin"],
            income_files    = files_ingresos,
            expense_files   = files_gastos,
            output_dir      = params["output"],
            isr_table       = isr_table,
            despacho        = despacho,
            regimen         = params.get("regimen", "resico"),
            acumulado_anual = params.get("acumulado_anual", False),
            excel_mode      = params.get("excel", "completo") or "completo",
        )
        log.info(f"  Excel generado: {excel_path}")
    except ImportError:
        log.warning("  ! Modulo excel_generator no disponible aun.")
        log.warning("    El Excel se generara en la siguiente iteracion.")
    except Exception as e:
        log.error(f"  X Error al generar Excel. Causa: {e}")

    log.info("")
    log.info("=" * 65)
    log.info("FLUJO COMPLETO FINALIZADO")
    log.info(f"  Archivos de ingresos : {len(files_ingresos)}")
    log.info(f"  Archivos de gastos   : {len(files_gastos)}")
    log.info("=" * 65)


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> dict | None:
    """
    Parsea los argumentos del CLI.
    Retorna dict con parametros o None para modo interactivo.
    Los modos utilitarios se despachan aqui directamente.
    """
    if len(sys.argv) == 1:
        return None

    p = argparse.ArgumentParser(
        prog="descarga_masiva.py",
        description=(
            "taxcrawler-dm — Descarga masiva de CFDI (XML) del SAT\n"
            "Consume el Web Service oficial del SAT v1.5 sin APIs de terceros.\n"
            "\n"
            "Ejemplos:\n"
            "  %(prog)s --rfc XAXX010101000 --cer fiel.cer --key fiel.key "
            "--inicio 2025-01-01 --fin 2025-12-31 --solicitud Metadata\n"
            "  %(prog)s --rfc XAXX010101000 --inicio 2025-01-01 --fin 2025-12-31 "
            "--flujo-completo\n"
            "  %(prog)s --pendientes\n"
            "  %(prog)s --retomar 3a4341a7-81d6-4830-9210-bf02f46085e0\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Documentacion:\n"
            "  FLOWS.md   — descripcion de cada flujo\n"
            "  ROADMAP.md — estado y funcionalidades planeadas\n"
            "\n"
            "Variables de entorno (.env):\n"
            "  SAT_CACHE_SALT    — salt para encriptar el cache (obligatorio)\n"
            "  SAT_PASSWORD_RFC  — contrasena FIEL del RFC (opcional)\n"
            "  DESPACHO_NOMBRE   — nombre del despacho contable (opcional)\n"
            "  TABLA_ISR_PATH    — ruta a CSV con tabla ISR personalizada (opcional)\n"
        ),
    )

    g_util = p.add_argument_group("modos utilitarios")
    g_util.add_argument("--pendientes",    action="store_true", default=False,
                        help="Muestra todas las solicitudes CFDI pendientes.")
    g_util.add_argument("--retomar",       metavar="ID",        default=None,
                        help="Retoma el polling de una solicitud pendiente por ID.")
    g_util.add_argument("--retomar-todas", metavar="RFC|all",   default=None,
                        help="Retoma en secuencia todas las solicitudes pendientes.")
    g_util.add_argument("--perfil",        metavar="RFC",       default=None,
                        help="Muestra el perfil guardado de un RFC.")
    g_util.add_argument("--reveal-cache",  metavar="RFC|all",   default=None,
                        help="Descifra y muestra el historial de intentos.")

    g_desc = p.add_argument_group("descarga")
    g_desc.add_argument("--rfc",       metavar="RFC",        default=None,
                        help="RFC del contribuyente. Ejemplo: XAXX010101000.")
    g_desc.add_argument("--cer",       type=Path,            default=None, metavar="RUTA",
                        help="Ruta al .cer de la FIEL. Opcional si hay perfil guardado.")
    g_desc.add_argument("--key",       type=Path,            default=None, metavar="RUTA",
                        help="Ruta al .key de la FIEL. Opcional si hay perfil guardado.")
    g_desc.add_argument("--password",  default=None,         metavar="PASS",
                        help="Contrasena FIEL. Si se omite, se solicita de forma segura.")
    g_desc.add_argument("--inicio",    type=date.fromisoformat, default=None, metavar="YYYY-MM-DD",
                        help="Fecha de inicio del periodo.")
    g_desc.add_argument("--fin",       type=date.fromisoformat, default=None, metavar="YYYY-MM-DD",
                        help="Fecha de fin del periodo.")
    g_desc.add_argument("--tipo",      choices=["emitidos", "recibidos"], default="recibidos",
                        help="Tipo de CFDI. Default: %(default)s.")
    g_desc.add_argument("--solicitud", choices=["CFDI", "Metadata"],      default="CFDI",
                        help="Tipo de solicitud. Default: %(default)s.")
    g_desc.add_argument("--timeout",   type=int, default=None, metavar="MINUTOS",
                        help="Minutos maximos de espera al SAT. Default: sin limite.")
    g_desc.add_argument("--output",    type=Path, default=None, metavar="RUTA",
                        help="Carpeta base de salida. Default: ./results_RFC.")
    g_desc.add_argument("--intervalo", type=int, default=60,   metavar="SEG",
                        help="Segundos entre verificaciones. Minimo 10. Default: %(default)s.")

    g_excel = p.add_argument_group("excel y papel de trabajo")
    g_excel.add_argument("--excel",          choices=["resumen", "detalle", "completo"], default=None,
                         help="Modo de generacion del Excel.")
    g_excel.add_argument("--flujo-completo", action="store_true", default=False,
                         help="Descarga Metadata (ingresos + gastos) y genera el Excel.")
    g_excel.add_argument("--regimen",        choices=["resico", "pfae"], default="resico",
                         help="Regimen fiscal para calculos ISR. Default: %(default)s.")
    g_excel.add_argument("--acumulado-anual", action="store_true", default=False,
                         help="Mantiene un Excel anual acumulado (Opcion B).")
    g_excel.add_argument("--despacho",       default=None, metavar="NOMBRE",
                         help='Nombre del despacho entre comillas. Sobreescribe DESPACHO_NOMBRE del .env.')
    g_excel.add_argument("--tabla-isr",      default=None, metavar="RUTA",
                         help="CSV con tabla ISR personalizada. Sobreescribe TABLA_ISR_PATH del .env.")

    args = p.parse_args()

    # --- Modos utilitarios ---
    if args.reveal_cache:
        validate_salt()
        reveal_history(args.reveal_cache)
        sys.exit(0)

    if args.perfil:
        show_profile(args.perfil)
        sys.exit(0)

    if args.pendientes:
        validate_salt()
        show_pending()
        sys.exit(0)

    if args.retomar or args.retomar_todas:
        validate_salt()
        from config import CACHE_DIR

        rfc_retomar = None
        if args.retomar:
            for archivo in CACHE_DIR.glob("*.pending.enc") if CACHE_DIR.exists() else []:
                rfc_candidate = archivo.stem.replace(".pending", "")
                pending       = read_pending(rfc_candidate)
                if args.retomar in pending:
                    rfc_retomar = rfc_candidate
                    break
        elif args.retomar_todas and args.retomar_todas != "all":
            rfc_retomar = args.retomar_todas.upper()

        if rfc_retomar and not args.cer:
            profile = read_profile(rfc_retomar)
            if profile.get("cer") and Path(profile["cer"]).exists():
                args.cer = Path(profile["cer"])
                log.info(f"  .cer tomado del perfil de {rfc_retomar}: {args.cer}")
            if profile.get("key") and Path(profile["key"]).exists():
                args.key = Path(profile["key"])
                log.info(f"  .key tomado del perfil de {rfc_retomar}: {args.key}")

        fiel_errors = []
        if not args.cer:
            fiel_errors.append("--cer es requerido (o ejecuta una descarga primero para crear el perfil)")
        if not args.key:
            fiel_errors.append("--key es requerido (o ejecuta una descarga primero para crear el perfil)")
        if args.cer and not args.cer.exists():
            fiel_errors.append(f"Archivo .cer no encontrado: {args.cer}")
        if args.key and not args.key.exists():
            fiel_errors.append(f"Archivo .key no encontrado: {args.key}")
        if fiel_errors:
            for e in fiel_errors:
                log.error(f"  X {e}")
            sys.exit(1)

        password = args.password or resolve_password(
            rfc_retomar or "FIEL",
            f"Contrasena de la FIEL{f' para {rfc_retomar}' if rfc_retomar else ''}"
        )
        fiel = load_fiel(args.cer, args.key, password)

        if args.retomar:
            run_retomar(args.retomar, fiel, args.timeout or RETOMAR_TIMEOUT_MIN)
        else:
            run_retomar_todas(args.retomar_todas, args.timeout or RETOMAR_TIMEOUT_MIN)
        sys.exit(0)

    # --- Modo descarga normal ---
    if not args.rfc:
        p.error("--rfc es requerido")

    rfc = args.rfc.upper()

    profile = read_profile(rfc)
    if profile:
        if not args.cer and profile.get("cer"):
            cer_path = Path(profile["cer"])
            if cer_path.exists():
                args.cer = cer_path
                log.info(f"  .cer tomado del perfil: {cer_path}")
            else:
                log.warning(f"  .cer del perfil no existe en disco: {cer_path}")

        if not args.key and profile.get("key"):
            key_path = Path(profile["key"])
            if key_path.exists():
                args.key = key_path
                log.info(f"  .key tomado del perfil: {key_path}")
            else:
                log.warning(f"  .key del perfil no existe en disco: {key_path}")

        if not args.output and profile.get("output"):
            args.output = Path(profile["output"])
            log.info(f"  output tomado del perfil: {args.output}")

        if args.intervalo == 60 and profile.get("intervalo"):
            args.intervalo = profile["intervalo"]
            log.info(f"  intervalo tomado del perfil: {args.intervalo}s")

    # Para --flujo-completo, inicio y fin son obligatorios pero no cer/key si hay perfil
    missing = [f"--{f}" for f, v in [
        ("cer", args.cer), ("key", args.key),
        ("inicio", args.inicio), ("fin", args.fin)
    ] if v is None]

    if missing:
        hint = "no encontrados en perfil" if profile else f"sin perfil guardado para {rfc}"
        p.error(f"Argumentos requeridos ({hint}): {', '.join(missing)}")

    password = args.password or resolve_password(rfc)
    output   = args.output if args.output else Path(f"./results_{rfc}")

    return {
        "rfc":             rfc,
        "cer":             args.cer,
        "key":             args.key,
        "password":        password,
        "inicio":          args.inicio,
        "fin":             args.fin,
        "tipo":            args.tipo,
        "solicitud":       args.solicitud,
        "excel":           args.excel,
        "timeout":         args.timeout,
        "output":          output,
        "intervalo":       args.intervalo,
        "flujo_completo":  args.flujo_completo,
        "regimen":         args.regimen,
        "acumulado_anual": args.acumulado_anual,
        "despacho":        args.despacho,
        "tabla_isr":       args.tabla_isr,
    }


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    start_time = datetime.now()

    log.info("=" * 65)
    log.info("SAT — DESCARGA MASIVA DE CFDI (XML) | taxcrawler-dm")
    log.info(f"Inicio: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    params = parse_args() or ask_params()

    validate_salt()

    fiel = load_fiel(params["cer"], params["key"], params["password"])

    # --- Flujo completo E2E ---
    if params.get("flujo_completo"):
        log.info("Modo: FLUJO COMPLETO (Metadata ingresos + gastos + Excel)")
        run_full_flow(fiel, params)
        write_profile(params["rfc"], params["cer"], params["key"],
                      params["output"], params["intervalo"])
        duration = int((datetime.now() - start_time).total_seconds())
        log.info(f"Duracion total: {duration // 60}m {duration % 60}s")
        return

    validate_params(params)
    output_dir = resolve_output_dir(params)

    # --- Metadata ---
    if params["solicitud"] == "Metadata":
        all_files = run_metadata(fiel, params, output_dir)

        if all_files:
            write_profile(params["rfc"], params["cer"], params["key"],
                          params["output"], params["intervalo"])
        else:
            log.warning("  ! No se descargo ningun archivo — perfil no actualizado.")

        summary  = generate_metadata_summary(all_files, params)
        duration = int((datetime.now() - start_time).total_seconds())

        log.info("")
        log.info("=" * 65)
        log.info("RESUMEN FINAL — DESCARGA MASIVA METADATA")
        log.info("=" * 65)
        log.info(f"  RFC                  : {params['rfc']}")
        log.info(f"  Tipo                 : {params['tipo']}")
        log.info(f"  Rango procesado      : {params['inicio']} -> {params['fin']}")
        log.info(f"  Archivos descargados : {len(all_files)}")
        log.info(f"  Carpeta de salida    : {output_dir.resolve()}")
        log.info(f"  Duracion total       : {duration // 60}m {duration % 60}s")
        log.info(f"  Log guardado en      : sat_descarga.log")
        log.info("=" * 65)
        if summary:
            log.info("")
            log.info("CONTENIDO DE LOS METADATA DESCARGADOS")
            log.info("=" * 65)
            for line in summary:
                log.info(line)
            log.info("=" * 65)

    # --- CFDI ---
    else:
        all_xmls = run_cfdi(fiel, params, output_dir)

        if all_xmls:
            write_profile(params["rfc"], params["cer"], params["key"],
                          params["output"], params["intervalo"])
        else:
            log.warning("  ! No se descargo ningun XML — perfil no actualizado.")

        duration = int((datetime.now() - start_time).total_seconds())
        log.info("")
        log.info("=" * 65)
        log.info("RESUMEN FINAL — DESCARGA MASIVA CFDI")
        log.info("=" * 65)
        log.info(f"  RFC                  : {params['rfc']}")
        log.info(f"  Tipo                 : {params['tipo']}")
        log.info(f"  Rango solicitado     : {params['inicio']} -> {params['fin']}")
        log.info(f"  XMLs descargados     : {len(all_xmls)}")
        log.info(f"  Carpeta de salida    : {output_dir.resolve()}")
        log.info(f"  Duracion total       : {duration // 60}m {duration % 60}s")
        log.info(f"  Log guardado en      : sat_descarga.log")
        if params.get("excel"):
            log.info(f"  Excel solicitado     : {params['excel']} — usa --flujo-completo para generarlo")
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