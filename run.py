#!/usr/bin/env python3
"""
run.py — Entry point unico para el flujo completo
=================================================
  descarga CFDIs → separa ingresos/gastos → parsea XMLs → genera Excel

Uso:
  python run.py --rfc SARR9110035Q3 --cer cert.cer --key key.key --mes 2026-06

  python run.py --rfc SARR9110035Q3 --cer cert.cer --key key.key \\
                --mes 2026-06 --despacho "Despacho Contable"

Opciones:
  --rfc        RFC del contribuyente (requerido)
  --cer        Ruta al archivo .cer de la FIEL (requerido)
  --key        Ruta al archivo .key de la FIEL (requerido)
  --password   Contrasena de la FIEL (si se omite, se pide interactivamente)
  --mes        Mes a procesar en formato YYYY-MM (requerido)
  --despacho   Nombre del despacho contable (default: 'Despacho Contable')
  --output     Carpeta base de salida (default: ./results_{RFC})
  --intervalo  Segundos entre verificaciones al SAT (default: 60)
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


def parse_args() -> dict:
    """Parsea argumentos de linea de comandos o los pide interactivamente."""
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

    # Calcular inicio y fin del mes
    # El SAT no acepta fechas futuras: si el mes es el actual, usar hoy como fin
    inicio = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    fin = min(date(year, month, last_day), date.today())

    return {
        "rfc":       rfc,
        "cer":       args.cer,
        "key":       args.key,
        "password":  password,
        "mes":       args.mes,
        "inicio":    inicio,
        "fin":       fin,
        "despacho":  args.despacho,
        "output":    output,
        "intervalo": args.intervalo,
    }


def main() -> None:
    inicio_proceso = datetime.now()

    log.info("=" * 65)
    log.info("FLUJO COMPLETO — DESCARGA CFDI + EXCEL")
    log.info(f"Inicio: {inicio_proceso.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    params = parse_args()

    # Validar FIEL
    if not params["cer"].exists():
        log.error(f"✗ Archivo .cer no encontrado: {params['cer']}")
        sys.exit(1)
    if not params["key"].exists():
        log.error(f"✗ Archivo .key no encontrado: {params['key']}")
        sys.exit(1)

    _validar_salt()

    rfc        = params["rfc"]
    mes_key    = params["mes"]
    base_dir   = params["output"]
    descarga_dir = base_dir / "cfdi_download"

    log.info(f"  RFC     : {rfc}")
    log.info(f"  Mes     : {mes_key} ({params['inicio']} → {params['fin']})")
    log.info(f"  Salida  : {base_dir.resolve()}")
    log.info("")

    # -------------------------------------------------------------------
    # PASO 1: Cargar FIEL y autenticar
    # -------------------------------------------------------------------
    log.info("PASO 1: Cargando FIEL...")
    fiel = cargar_fiel(params["cer"], params["key"], params["password"])

    # -------------------------------------------------------------------
    # PASO 2: Descargar CFDIs (emitidos y recibidos)
    # -------------------------------------------------------------------
    log.info("")
    log.info("PASO 2: Descargando CFDIs del SAT...")
    log.info("-" * 50)

    xmls_emitidos  = descargar_cfdi(
        fiel, rfc, params["inicio"], params["fin"],
        "emitidos", descarga_dir, params["intervalo"],
    )

    xmls_recibidos = descargar_cfdi(
        fiel, rfc, params["inicio"], params["fin"],
        "recibidos", descarga_dir, params["intervalo"],
    )

    todos_xmls = xmls_emitidos + xmls_recibidos
    log.info(f"  Total XMLs descargados: {len(todos_xmls)} "
             f"({len(xmls_emitidos)} emitidos, {len(xmls_recibidos)} recibidos)")

    if not todos_xmls:
        log.warning("✗ No se descargaron XMLs. Verifica que el periodo tenga actividad.")
        sys.exit(0)

    # -------------------------------------------------------------------
    # PASO 3: Organizar XMLs en ingresos/ y gastos/
    # -------------------------------------------------------------------
    log.info("")
    log.info("PASO 3: Organizando XMLs por tipo...")
    log.info("-" * 50)

    ingresos_dir, gastos_dir = _organizar_xmls_para_excel(
        todos_xmls, rfc, base_dir, mes_key
    )

    # -------------------------------------------------------------------
    # PASO 4: Generar Excel
    # -------------------------------------------------------------------
    log.info("")
    log.info("PASO 4: Generando Excel de Papel de Trabajo...")
    log.info("-" * 50)

    excel_path = generate_excel_from_xml(
        rfc=rfc,
        start_date=params["inicio"],
        end_date=params["fin"],
        xml_income_dir=ingresos_dir,
        xml_expense_dir=gastos_dir,
        output_dir=base_dir,
        isr_table=TABLA_ISR_RESICO_DEFAULT,
        despacho=params["despacho"],
    )

    # Limpiar carpeta temporal de descarga (opcional — se conservan los XMLs organizados)
    if descarga_dir.exists():
        shutil.rmtree(descarga_dir)
        log.info(f"  Carpeta temporal eliminada: {descarga_dir}")

    # -------------------------------------------------------------------
    # Resumen final
    # -------------------------------------------------------------------
    duracion = int((datetime.now() - inicio_proceso).total_seconds())

    log.info("")
    log.info("=" * 65)
    log.info("FLUJO COMPLETO — FINALIZADO")
    log.info("=" * 65)
    log.info(f"  RFC               : {rfc}")
    log.info(f"  Mes               : {mes_key}")
    log.info(f"  XMLs procesados   : {len(todos_xmls)}")
    log.info(f"  Ingresos          : {ingresos_dir.resolve()}")
    log.info(f"  Gastos            : {gastos_dir.resolve()}")
    log.info(f"  Duración total    : {duracion // 60}m {duracion % 60}s")
    log.info("")
    log.info(f"  📊 Excel generado : {excel_path.resolve()}")
    log.info("=" * 65)

    # Imprimir ruta del Excel como ultima linea para consumo programatico
    print(f"\n✅ Excel: {excel_path.resolve()}")


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
