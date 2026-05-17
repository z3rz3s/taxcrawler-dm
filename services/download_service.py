"""
download_service.py
-------------------
Orquesta los flujos de descarga de Metadata y CFDI.
Llama exclusivamente a funciones de core/ — no contiene logica de negocio.
Expone firmas limpias usables desde cli/, api/ y ui/ sin modificacion.
"""

import sys
from datetime import date
from pathlib import Path

_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from core.config import log, resolve_password
from core.cache_manager import (
    add_pending,
    get_attempt_history,
    read_pending,
    read_profile,
    register_attempt,
    remove_pending,
    write_profile,
)
from core.sat_client import (
    apply_date_offset,
    download_package,
    get_token,
    load_fiel,
    request_download,
    verify_raw,
    verify_with_timeout,
)
from core.file_handler import (
    extract_cfdi,
    extract_metadata,
    resolve_output_dir,
    resolve_retomar_output_dir,
)
from core.metadata_parser import (
    generate_metadata_summary,
    generate_monthly_periods,
)


def download_metadata(
    rfc: str,
    cer_path: Path,
    key_path: Path,
    password: str,
    start_date: date,
    end_date: date,
    tipo: str = "recibidos",
    output_dir: Path | None = None,
    intervalo: int = 60,
) -> list[Path]:
    """
    Descarga Metadata TXT para un RFC y rango de fechas.
    Divide automaticamente por mes y continua si un mes no tiene CFDIs (5004).
    Elimina los ZIPs despues de extraer cada TXT.
    Guarda el perfil del RFC si se descargo al menos un archivo.
    Retorna la lista de archivos TXT descargados.
    """
    if output_dir is None:
        output_dir = Path(f"./results_{rfc.upper()}")

    params = {
        "rfc":       rfc.upper(),
        "tipo":      tipo,
        "solicitud": "Metadata",
        "inicio":    start_date,
        "fin":       end_date,
        "output":    output_dir,
        "intervalo": intervalo,
    }

    fiel       = load_fiel(cer_path, key_path, password)
    output_day = resolve_output_dir(params)
    periods    = generate_monthly_periods(start_date, end_date)
    all_files: list[Path] = []
    months_with  = 0
    months_empty = 0

    from core.config import MESES_ES
    for i, (month_start, month_end) in enumerate(periods, 1):
        month_num = month_start.strftime("%m")
        month_lbl = f"{MESES_ES[month_num]} {month_start.year}"
        log.info(f"  +-- [{i}/{len(periods)}] {month_lbl}  ({month_start} -> {month_end})")

        p_month = {**params, "inicio": month_start, "fin": month_end, "output": output_day}
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
                log.info(f"  +-- {month_lbl}: Sin CFDIs — continuando.")
                months_empty += 1
                continue
            if estado == 5:
                log.warning(f"  +-- {month_lbl}: Rechazado (codigo {cod}) — continuando.")
                months_empty += 1
                continue
            if estado != 3:
                log.warning(f"  +-- {month_lbl}: Estado inesperado {estado} — continuando.")
                months_empty += 1
                continue

            log.info(f"  |   {num_cfdi} CFDI(s) | {len(packages)} paquete(s)")
            month_files: list[Path] = []
            for j, pkg_id in enumerate(packages, 1):
                zip_path = download_package(fiel, pkg_id, rfc.upper(), output_day, j, len(packages))
                if zip_path:
                    dest_name = f"{month_start.strftime('%Y-%m')}-{rfc.upper()}"
                    extracted = extract_metadata(zip_path, dest_name)
                    month_files.extend(extracted)

            log.info(f"  +-- {month_lbl}: {len(month_files)} archivo(s) guardados.")
            all_files.extend(month_files)
            months_with += 1

        except Exception as e:
            log.warning(f"  +-- {month_lbl}: Error inesperado ({e}) — continuando.")
            months_empty += 1

    log.info(f"  Meses con CFDIs    : {months_with}")
    log.info(f"  Meses sin actividad: {months_empty}")

    if all_files:
        write_profile(rfc.upper(), cer_path, key_path, output_dir, intervalo)
    else:
        log.warning("  ! No se descargo ningun archivo — perfil no actualizado.")

    return all_files


def download_cfdi(
    rfc: str,
    cer_path: Path,
    key_path: Path,
    password: str,
    start_date: date,
    end_date: date,
    tipo: str = "recibidos",
    output_dir: Path | None = None,
    intervalo: int = 60,
    timeout_min: int | None = None,
    keep_zip: bool = True,
) -> list[Path]:
    """
    Descarga CFDIs XML para un RFC y rango de fechas.
    Aplica offset automatico de segundos para evitar bloqueo del SAT (error 5002).
    Registra la solicitud como pendiente inmediatamente tras la aceptacion.
    Retorna la lista de XMLs descargados, o lista vacia si quedo pendiente.
    """
    if output_dir is None:
        output_dir = Path(f"./results_{rfc.upper()}")

    params = {
        "rfc":       rfc.upper(),
        "tipo":      tipo,
        "solicitud": "CFDI",
        "inicio":    start_date,
        "fin":       end_date,
        "output":    output_dir,
        "intervalo": intervalo,
    }

    fiel      = load_fiel(cer_path, key_path, password)
    output_day = resolve_output_dir(params)

    history       = get_attempt_history(rfc.upper(), start_date, end_date, tipo)
    prev_attempts = history["intentos"]

    if prev_attempts == 0:
        log.info("  Cache: primera solicitud para este periodo.")
    else:
        log.info(f"  Cache: {prev_attempts} intento(s) previo(s) detectado(s).")
        log.info(f"  Bypass activado: offset de +{history['offset_segundos']}s.")

    current_offset   = register_attempt(rfc.upper(), start_date, end_date, tipo)
    dt_start, dt_end = apply_date_offset(start_date, end_date, current_offset)
    log.info(f"  Periodo efectivo : {dt_start} -> {dt_end}")

    token      = get_token(fiel)
    request_id = request_download(fiel, token, params, dt_start, dt_end)

    if not request_id:
        log.error("X No se pudo obtener un ID de solicitud del SAT.")
        return []

    add_pending(rfc.upper(), request_id, params, dt_start, dt_end)

    result = verify_with_timeout(fiel, request_id, params, timeout_min)

    if result in ("rechazada", "vencida"):
        remove_pending(rfc.upper(), request_id, result)
        log.error(f"X Solicitud {result}. No es posible recuperarla.")
        return []

    if result is None:
        log.warning(f"  Solicitud conservada en pendientes. Retoma con --retomar {request_id}")
        return []

    packages   = result
    base_name  = f"{start_date.strftime('%Y-%m')}-{rfc.upper()}"
    all_xmls: list[Path] = []

    for i, pkg_id in enumerate(packages, 1):
        zip_path = download_package(fiel, pkg_id, rfc.upper(), output_day, i, len(packages))
        if zip_path:
            pkg_name = base_name if len(packages) == 1 else f"{base_name}_{i}"
            xmls, _  = extract_cfdi(zip_path, pkg_name, keep_zip=keep_zip)
            all_xmls.extend(xmls)

    remove_pending(rfc.upper(), request_id, "completada")

    if all_xmls:
        write_profile(rfc.upper(), cer_path, key_path, output_dir, intervalo)

    return all_xmls


def full_flow(
    rfc: str,
    cer_path: Path,
    key_path: Path,
    password: str,
    start_date: date,
    end_date: date,
    output_dir: Path | None = None,
    intervalo: int = 60,
    despacho: str | None = None,
    tabla_isr: list | None = None,
    regimen: str = "resico",
) -> Path | None:
    """
    Ejecuta el flujo completo para un cliente:
      Paso 1: Descarga Metadata emitidos (ingresos)
      Paso 2: Descarga Metadata recibidos (gastos)
      Paso 3: Genera el Excel con Papel de Trabajo
    Retorna la ruta al Excel generado, o None si fallo.
    """
    if output_dir is None:
        output_dir = Path(f"./results_{rfc.upper()}")

    log.info(f"PASO 1/3 — Descargando Metadata INGRESOS (emitidos)...")
    files_income = download_metadata(
        rfc=rfc, cer_path=cer_path, key_path=key_path, password=password,
        start_date=start_date, end_date=end_date,
        tipo="emitidos", output_dir=output_dir, intervalo=intervalo,
    )

    log.info(f"PASO 2/3 — Descargando Metadata GASTOS (recibidos)...")
    files_expense = download_metadata(
        rfc=rfc, cer_path=cer_path, key_path=key_path, password=password,
        start_date=start_date, end_date=end_date,
        tipo="recibidos", output_dir=output_dir, intervalo=intervalo,
    )

    log.info("PASO 3/3 — Generando Excel con Papel de Trabajo...")
    from services.excel_service import generate_from_metadata
    from core.config import get_despacho_name, resolve_isr_table

    excel_path = generate_from_metadata(
        rfc=rfc,
        start_date=start_date,
        end_date=end_date,
        income_files=files_income,
        expense_files=files_expense,
        output_dir=output_dir,
        isr_table=tabla_isr or resolve_isr_table(),
        despacho=get_despacho_name(despacho),
        regimen=regimen,
    )

    return excel_path

def resume_cfdi(
    request_id: str,
    timeout_min: int = 30,
) -> dict:
    """
    Retoma el polling de una solicitud CFDI pendiente por ID.
    Busca el request_id en todos los archivos .pending.enc disponibles.
    Retorna dict con status, xml_files y files.

    status posibles:
      completed      -> descarga exitosa
      pending        -> timeout alcanzado, sigue en pending
      not_found      -> request_id no existe en ningun pending
      terminal_error -> rechazada o vencida por el SAT
    """
    from core.config import CACHE_DIR
    from core.cache_manager import elapsed_label

    # Buscar el ID en todos los pendientes
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
        return {"status": "not_found", "request_id": request_id, "xml_files": 0, "files": []}

    profile = read_profile(rfc)
    if not profile:
        return {
            "status":  "error",
            "message": f"Sin perfil guardado para RFC {rfc}. Ejecuta una descarga primero.",
            "xml_files": 0, "files": [],
        }

    cer_path = Path(profile.get("cer", ""))
    key_path = Path(profile.get("key", ""))

    if not cer_path.exists() or not key_path.exists():
        return {
            "status":  "error",
            "message": f"Archivos FIEL no encontrados en disco para RFC {rfc}.",
            "xml_files": 0, "files": [],
        }

    # La contrasena no esta en el cache — leerla del entorno si existe
    from core.config import resolve_password
    import os
    env_key  = f"SAT_PASSWORD_{rfc.upper()}"
    password = os.environ.get(env_key, "").strip()

    if not password:
        return {
            "status":  "needs_password",
            "message": f"Se requiere contrasena para RFC {rfc}. Proveerla en el request.",
            "rfc":     rfc,
            "xml_files": 0, "files": [],
        }

    fiel = load_fiel(cer_path, key_path, password)

    p_retomar = {
        "rfc":       info["rfc"],
        "tipo":      info["tipo"],
        "solicitud": info["solicitud"],
        "inicio":    __import__("datetime").date.fromisoformat(info["inicio"]),
        "fin":       __import__("datetime").date.fromisoformat(info["fin"]),
        "intervalo": info.get("intervalo", 60),
        "output":    Path(info["output"]),
    }

    result = verify_with_timeout(fiel, request_id, p_retomar, timeout_min)

    if result in ("rechazada", "vencida"):
        remove_pending(rfc, request_id, result)
        return {"status": "terminal_error", "reason": result, "xml_files": 0, "files": []}

    if result is None:
        return {"status": "pending", "request_id": request_id, "xml_files": 0, "files": []}

    # Completada — descargar y extraer
    from core.file_handler import resolve_retomar_output_dir
    output_dir = resolve_retomar_output_dir(p_retomar)
    base_name  = f"{p_retomar['inicio'].strftime('%Y-%m')}-{rfc}"
    all_xmls: list[Path] = []

    for i, pkg_id in enumerate(result, 1):
        zip_path = download_package(fiel, pkg_id, rfc, output_dir, i, len(result))
        if zip_path:
            pkg_name = base_name if len(result) == 1 else f"{base_name}_{i}"
            xmls, _  = extract_cfdi(zip_path, pkg_name)
            all_xmls.extend(xmls)

    remove_pending(rfc, request_id, "completada")
    write_profile(rfc, cer_path, key_path, p_retomar["output"], p_retomar["intervalo"])

    return {
        "status":    "completed",
        "rfc":       rfc,
        "xml_files": len(all_xmls),
        "files":     [str(f) for f in all_xmls],
        "output_dir": str(output_dir),
    }