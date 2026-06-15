#!/usr/bin/env python3
"""
run.py — Entry point unico para el flujo completo
=================================================
  descarga CFDIs → separa ingresos/gastos → parsea XMLs → genera Excel

Uso CLI:
  python run.py --rfc SARR9110035Q3 --cer cert.cer --key key.key --mes 2026-06

Uso programatico (desde clients.py):
  from run import ejecutar_flujo
  excel = ejecutar_flujo(rfc="SARR9110035Q3", cer=Path("cert.cer"), ...)
"""

import sys
import shutil
from calendar import monthrange
from datetime import date, datetime
from getpass import getpass
from pathlib import Path

# Asegurar que libs/ este en el path para dependencias locales
_libs = Path(__file__).resolve().parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

from config import TABLA_ISR_RESICO_DEFAULT, log
from descarga_masiva import (
    cargar_fiel,
    descargar_cfdi,
    _organizar_xmls_para_excel,
    _validar_salt,
)
from excel_generator import generate_excel_from_xml


# ===========================================================================
# Funcion reusable — ejecutar_flujo
# ===========================================================================

def ejecutar_flujo(
    rfc: str,
    cer: Path,
    key: Path,
    password: str,
    mes: str,
    despacho: str = "Despacho Contable",
    output: Path | None = None,
    intervalo: int = 60,
) -> Path:
    """
    Flujo completo para un RFC y mes:
      1. Descarga CFDIs emitidos y recibidos del SAT
      2. Organiza XMLs en ingresos/ y gastos/
      3. Genera Excel de Papel de Trabajo

    Parametros:
      rfc       : RFC del contribuyente
      cer       : ruta al archivo .cer de la FIEL
      key       : ruta al archivo .key de la FIEL
      password  : contrasena de la FIEL
      mes       : mes a procesar en formato YYYY-MM
      despacho  : nombre del despacho contable
      output    : carpeta base de salida (default: ./results_{RFC})
      intervalo : segundos entre verificaciones al SAT

    Retorna:
      Ruta (Path) al archivo Excel generado.
    """
    inicio_proceso = datetime.now()

    # Validar FIEL
    if not cer.exists():
        raise FileNotFoundError(f"Archivo .cer no encontrado: {cer}")
    if not key.exists():
        raise FileNotFoundError(f"Archivo .key no encontrado: {key}")

    _validar_salt()

    # Parsear mes
    try:
        year, month = map(int, mes.split("-"))
    except ValueError:
        raise ValueError(f"--mes debe tener formato YYYY-MM (ej. 2026-06), recibido: {mes}")

    inicio = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    fin = min(date(year, month, last_day), date.today())

    base_dir = output if output else Path(f"./results_{rfc}")
    descarga_dir = base_dir / "cfdi_download"

    log.info("=" * 65)
    log.info(f"FLUJO COMPLETO — {rfc} | {mes}")
    log.info(f"Inicio: {inicio_proceso.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)
    log.info(f"  RFC     : {rfc}")
    log.info(f"  Mes     : {mes} ({inicio} → {fin})")
    log.info(f"  Salida  : {base_dir.resolve()}")
    log.info("")

    # -------------------------------------------------------------------
    # PASO 1: Cargar FIEL y autenticar
    # -------------------------------------------------------------------
    log.info("PASO 1: Cargando FIEL...")
    fiel = cargar_fiel(cer, key, password)

    # -------------------------------------------------------------------
    # PASO 2: Descargar CFDIs (emitidos y recibidos)
    # -------------------------------------------------------------------
    log.info("")
    log.info("PASO 2: Descargando CFDIs del SAT...")
    log.info("-" * 50)

    xmls_emitidos = descargar_cfdi(
        fiel, rfc, inicio, fin, "emitidos", descarga_dir, intervalo,
    )

    xmls_recibidos = descargar_cfdi(
        fiel, rfc, inicio, fin, "recibidos", descarga_dir, intervalo,
    )

    todos_xmls = xmls_emitidos + xmls_recibidos
    log.info(f"  Total XMLs descargados: {len(todos_xmls)} "
             f"({len(xmls_emitidos)} emitidos, {len(xmls_recibidos)} recibidos)")

    if not todos_xmls:
        log.warning("✗ No se descargaron XMLs. Verifica que el periodo tenga actividad.")
        return None

    # -------------------------------------------------------------------
    # PASO 3: Organizar XMLs en ingresos/ y gastos/
    # -------------------------------------------------------------------
    log.info("")
    log.info("PASO 3: Organizando XMLs por tipo...")
    log.info("-" * 50)

    ingresos_dir, gastos_dir = _organizar_xmls_para_excel(
        todos_xmls, rfc, base_dir, mes
    )

    # -------------------------------------------------------------------
    # PASO 4: Generar Excel
    # -------------------------------------------------------------------
    log.info("")
    log.info("PASO 4: Generando Excel de Papel de Trabajo...")
    log.info("-" * 50)

    excel_path = generate_excel_from_xml(
        rfc=rfc,
        start_date=inicio,
        end_date=fin,
        xml_income_dir=ingresos_dir,
        xml_expense_dir=gastos_dir,
        output_dir=base_dir,
        isr_table=TABLA_ISR_RESICO_DEFAULT,
        despacho=despacho,
    )

    # Limpiar carpeta temporal
    if descarga_dir.exists():
        shutil.rmtree(descarga_dir)
        log.info(f"  Carpeta temporal eliminada: {descarga_dir}")

    # -------------------------------------------------------------------
    # Resumen final
    # -------------------------------------------------------------------
    duracion = int((datetime.now() - inicio_proceso).total_seconds())

    log.info("")
    log.info("=" * 65)
    log.info(f"FLUJO COMPLETO — FINALIZADO — {rfc}")
    log.info("=" * 65)
    log.info(f"  RFC               : {rfc}")
    log.info(f"  Mes               : {mes}")
    log.info(f"  XMLs procesados   : {len(todos_xmls)}")
    log.info(f"  Ingresos          : {ingresos_dir.resolve()}")
    log.info(f"  Gastos            : {gastos_dir.resolve()}")
    log.info(f"  Duración total    : {duracion // 60}m {duracion % 60}s")
    log.info("")
    log.info(f"  📊 Excel generado : {excel_path.resolve()}")
    log.info("=" * 65)

    print(f"\n✅ Excel: {excel_path.resolve()}")
    return excel_path


# ===========================================================================
# CLI entry point
# ===========================================================================

def parse_args() -> dict:
    """Parsea argumentos de linea de comandos."""
    import argparse

    p = argparse.ArgumentParser(
        description="Flujo completo: descarga CFDI → Excel de Papel de Trabajo"
    )

    p.add_argument("--rfc",      required=True,  help="RFC del contribuyente")
    p.add_argument("--cer",      required=True,  type=Path, help="Archivo .cer de la FIEL")
    p.add_argument("--key",      required=True,  type=Path, help="Archivo .key de la FIEL")
    p.add_argument("--password", default=None,   help="Contrasena de la FIEL")
    p.add_argument("--mes",      required=True,  help="Mes a procesar (YYYY-MM)")
    p.add_argument("--despacho", default="Despacho Contable", help="Nombre del despacho")
    p.add_argument("--output",   type=Path, default=None, help="Carpeta base de salida")
    p.add_argument("--intervalo", type=int, default=60, help="Segundos entre verificaciones")

    args = p.parse_args()

    # Validar --mes
    try:
        year, month = map(int, args.mes.split("-"))
    except ValueError:
        p.error("--mes debe tener formato YYYY-MM (ej. 2026-06)")

    rfc      = args.rfc.upper()
    password = args.password
    if not password:
        password = getpass("  → Contrasena de la FIEL (oculta): ")

    output = args.output if args.output else Path(f"./results_{rfc}")

    return {
        "rfc":       rfc,
        "cer":       args.cer,
        "key":       args.key,
        "password":  password,
        "mes":       args.mes,
        "despacho":  args.despacho,
        "output":    output,
        "intervalo": args.intervalo,
    }


def main() -> None:
    params = parse_args()
    ejecutar_flujo(
        rfc=params["rfc"],
        cer=params["cer"],
        key=params["key"],
        password=params["password"],
        mes=params["mes"],
        despacho=params["despacho"],
        output=params["output"],
        intervalo=params["intervalo"],
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("")
        log.warning("Proceso interrumpido por el usuario (Ctrl+C).")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Error inesperado: {e}", exc_info=True)
        sys.exit(1)
