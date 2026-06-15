#!/usr/bin/env python3
"""
clients.py — Gestion multi-cliente de FIELs
============================================
Almacena RFCs, nombres, rutas de FIEL y passwords en un JSON
encriptado con Fernet (misma logica que el cache del SAT).

Comandos:
  python clients.py add                         # Registrar nuevo cliente (interactivo)
  python clients.py list                        # Listar todos los clientes
  python clients.py run --rfc SARR9110035Q3 --mes 2026-06    # Ejecutar para un cliente
  python clients.py run-all --mes 2026-06                    # Ejecutar para TODOS

El archivo clients.json.enc se guarda en el mismo directorio que este script.
La encriptacion usa CLIENTS_SALT (o SAT_CACHE_SALT como fallback) desde .env.
"""

import json
import os
import sys
from datetime import date
from getpass import getpass
from pathlib import Path

# Asegurar que libs/ este en el path
_libs_abs = Path(__file__).resolve().parent / "libs"
if _libs_abs.exists() and str(_libs_abs) not in sys.path:
    sys.path.insert(0, str(_libs_abs))

from config import log
from sat_documentos import descargar_documentos_sat

CLIENTS_FILE = Path(__file__).resolve().parent / "clients.json.enc"

REGIMENES = {
    "626": "RESICO PF (Art. 113-E)",
    "612": "PFAE (Art. 111 LISR)",
    "601": "General (Art. 110 LISR)",
    "605": "Sueldos y Salarios",
    "606": "Arrendamiento",
}


# ===========================================================================
# Encriptacion — Fernet + PBKDF2
# ===========================================================================

def _derivar_clave_maestra() -> bytes:
    """
    Deriva una clave Fernet maestra para clients.json.enc.
    Usa CLIENTS_SALT del .env (prioridad) o SAT_CACHE_SALT como fallback.
    """
    import base64
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    salt = os.environ.get("CLIENTS_SALT", "").strip()
    if not salt:
        salt = os.environ.get("SAT_CACHE_SALT", "").strip()
    if not salt:
        raise RuntimeError(
            "Define CLIENTS_SALT en .env (o asegurate de tener SAT_CACHE_SALT).\n"
            "  echo 'CLIENTS_SALT=tu_valor_secreto' >> .env"
        )

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode(),
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(b"taxcrawler_clients_master"))


def _leer_clientes() -> dict:
    """Lee y descifra clients.json.enc. Retorna dict vacio si no existe o esta corrupto."""
    from cryptography.fernet import Fernet, InvalidToken

    if not CLIENTS_FILE.exists():
        return {"clients": {}}

    try:
        clave = _derivar_clave_maestra()
        f = Fernet(clave)
        datos = f.decrypt(CLIENTS_FILE.read_bytes())
        return json.loads(datos.decode())
    except InvalidToken:
        log.warning("⚠  clients.json.enc corrupto o clave incorrecta. Se iniciara vacio.")
        return {"clients": {}}
    except Exception as e:
        log.warning(f"⚠  No se pudo leer clients.json.enc: {e}")
        return {"clients": {}}


def _guardar_clientes(data: dict) -> None:
    """Cifra y guarda clients.json.enc."""
    from cryptography.fernet import Fernet

    clave = _derivar_clave_maestra()
    f = Fernet(clave)
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode()
    CLIENTS_FILE.write_bytes(f.encrypt(json_bytes))


# ===========================================================================
# Operaciones CRUD
# ===========================================================================

def registrar_cliente(
    rfc: str,
    nombre: str,
    cer: Path,
    key: Path,
    password: str,
    regimen: str = "626",
) -> dict:
    """
    Registra un nuevo cliente en el almacen encriptado.

    Parametros:
      rfc      : RFC del contribuyente (12-13 caracteres)
      nombre   : Nombre o razon social
      cer      : ruta al archivo .cer de la FIEL
      key      : ruta al archivo .key de la FIEL
      password : contrasena de la FIEL
      regimen  : codigo de regimen fiscal (626=RESICO, 612=PFAE, etc.)

    Retorna el dict del cliente registrado.
    """
    rfc = rfc.upper().strip()

    # Validar archivos
    cer_path = Path(cer).resolve()
    key_path = Path(key).resolve()
    if not cer_path.exists():
        raise FileNotFoundError(f"Archivo .cer no encontrado: {cer_path}")
    if not key_path.exists():
        raise FileNotFoundError(f"Archivo .key no encontrado: {key_path}")

    clientes = _leer_clientes()

    clientes["clients"][rfc] = {
        "nombre":     nombre.strip(),
        "cer":        str(cer_path),
        "key":        str(key_path),
        "password":   password,          # Encriptado junto con todo el JSON
        "regimen":    regimen,
        "regimen_nombre": REGIMENES.get(regimen, f"Regimen {regimen}"),
        "fecha_alta": date.today().isoformat(),
    }

    _guardar_clientes(clientes)
    log.info(f"✅ Cliente {rfc} — {nombre} registrado ({REGIMENES.get(regimen, regimen)})")
    return clientes["clients"][rfc]


def listar_clientes() -> list[dict]:
    """Lista todos los clientes registrados. Retorna lista de dicts."""
    clientes = _leer_clientes()
    clist = clientes.get("clients", {})

    if not clist:
        print("No hay clientes registrados.")
        return []

    print(f"{'RFC':<15} {'Nombre':<32} {'Régimen':<22} {'Alta':<12}")
    print("-" * 81)
    for rfc, c in sorted(clist.items()):
        reg = c.get("regimen_nombre", c.get("regimen", "?"))
        alta = c.get("fecha_alta", "?")
        print(f"{rfc:<15} {c['nombre']:<32} {reg:<22} {alta:<12}")

    return [{"rfc": rfc, **c} for rfc, c in sorted(clist.items())]


def obtener_cliente(rfc: str) -> dict | None:
    """Obtiene los datos de un cliente por RFC. Retorna None si no existe."""
    clientes = _leer_clientes()
    return clientes.get("clients", {}).get(rfc.upper())


def eliminar_cliente(rfc: str) -> bool:
    """Elimina un cliente del registro. Retorna True si existia."""
    clientes = _leer_clientes()
    rfc = rfc.upper()
    if rfc not in clientes.get("clients", {}):
        return False
    nombre = clientes["clients"][rfc]["nombre"]
    del clientes["clients"][rfc]
    _guardar_clientes(clientes)
    log.info(f"🗑  Cliente eliminado: {rfc} — {nombre}")
    return True


# ===========================================================================
# Ejecucion — un cliente o todos
# ===========================================================================

def descargar_docs_cliente(rfc: str) -> dict | None:
    """
    Descarga documentos SAT (CSF + Opinión 32-D) para un cliente.
    """
    cliente = obtener_cliente(rfc)
    if not cliente:
        log.error(f"❌ Cliente {rfc} no registrado.")
        return None

    log.info(f"📄 Descargando documentos SAT para {rfc} — {cliente['nombre']}")
    base_dir = Path(f"results_{rfc}/documentos_sat")
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        resultado = descargar_documentos_sat(
            rfc=rfc.upper(),
            cer_path=cliente["cer"],
            key_path=cliente["key"],
            password=cliente["password"],
            output_dir=base_dir,
        )
        resultado["nombre"] = cliente["nombre"]
        return resultado
    except Exception as e:
        log.error(f"❌ Error descargando docs para {rfc}: {e}")
        return None


def descargar_docs_todos() -> dict[str, dict]:
    """Descarga documentos SAT para todos los clientes registrados."""
    clientes = _leer_clientes()
    clist = clientes.get("clients", {})
    if not clist:
        log.warning("No hay clientes registrados.")
        return {}

    resultados = {}
    total = len(clist)
    for i, (rfc, c) in enumerate(sorted(clist.items()), 1):
        log.info(f"[{i}/{total}] Documentos: {rfc} — {c['nombre']}")
        resultados[rfc] = descargar_docs_cliente(rfc) or {"error": "falló"}

    return resultados


def correr_cliente(
    rfc: str,
    mes: str,
    despacho: str = "Despacho Contable",
    intervalo: int = 60,
    descargar_docs: bool = True,
) -> Path | None:
    """
    Ejecuta el flujo completo (descarga + Excel) para un cliente.

    Parametros:
      rfc       : RFC del cliente (debe estar registrado)
      mes       : mes YYYY-MM
      despacho  : nombre del despacho contable
      intervalo : segundos entre verificaciones SAT

    Retorna la ruta al Excel generado, o None si fallo.
    """
    from run import ejecutar_flujo

    cliente = obtener_cliente(rfc)
    if not cliente:
        log.error(f"❌ Cliente {rfc} no registrado. Usa 'python clients.py add' primero.")
        return None

    log.info(f"🚀 Iniciando flujo para {rfc} — {cliente['nombre']} ({mes})")

    # ── Paso 0: Descargar documentos SAT ──
    if descargar_docs:
        log.info("")
        log.info("PASO 0: Descargando documentos SAT (CSF + Opinión 32-D)...")
        descargar_docs_cliente(rfc)

    try:
        excel = ejecutar_flujo(
            rfc=rfc.upper(),
            cer=Path(cliente["cer"]),
            key=Path(cliente["key"]),
            password=cliente["password"],
            mes=mes,
            despacho=despacho,
            intervalo=intervalo,
        )
        return excel
    except Exception as e:
        log.error(f"❌ Error procesando {rfc}: {e}")
        return None


def correr_todos(
    mes: str,
    despacho: str = "Despacho Contable",
    intervalo: int = 60,
    descargar_docs: bool = True,
) -> dict[str, dict]:
    """
    Ejecuta el flujo completo para TODOS los clientes registrados.

    Retorna dict con resultados por RFC:
      { "RFC": {"status": "ok", "excel": "/path/to/file.xlsx"} }
    """
    clientes = _leer_clientes()
    clist = clientes.get("clients", {})

    if not clist:
        log.warning("No hay clientes registrados.")
        return {}

    resultados = {}
    total = len(clist)
    exitos = 0
    fallos = 0

    for i, (rfc, c) in enumerate(sorted(clist.items()), 1):
        log.info("")
        log.info("=" * 65)
        log.info(f"[{i}/{total}] Procesando: {rfc} — {c['nombre']}")
        log.info("=" * 65)

        try:
            excel = correr_cliente(rfc, mes, despacho, intervalo, descargar_docs)
            if excel:
                resultados[rfc] = {"status": "ok", "excel": str(excel.resolve())}
                exitos += 1
            else:
                resultados[rfc] = {"status": "sin_actividad", "excel": None}
                exitos += 1  # sin actividad no es error
        except Exception as e:
            resultados[rfc] = {"status": "error", "error": str(e)}
            fallos += 1
            log.error(f"  ❌ {rfc}: {e}")

    log.info("")
    log.info("=" * 65)
    log.info(f"LOTE COMPLETO — {exitos} ok, {fallos} errores de {total}")
    log.info("=" * 65)
    for rfc, r in resultados.items():
        icon = "✅" if r["status"] in ("ok", "sin_actividad") else "❌"
        excel_info = f" → {r.get('excel', '')}" if r.get("excel") else ""
        log.info(f"  {icon} {rfc}: {r['status']}{excel_info}")

    return resultados


# ===========================================================================
# CLI interactivo
# ===========================================================================

def _cmd_add() -> None:
    """Comando interactivo para registrar un nuevo cliente."""
    print()
    print("=" * 50)
    print("REGISTRAR NUEVO CLIENTE")
    print("=" * 50)
    print()

    rfc = input("  RFC: ").strip().upper()
    if not rfc:
        print("❌ RFC es obligatorio.")
        return

    nombre = input("  Nombre / Razon social: ").strip()
    if not nombre:
        print("❌ Nombre es obligatorio.")
        return

    cer = input("  Ruta al archivo .cer: ").strip()
    key = input("  Ruta al archivo .key: ").strip()
    password = getpass("  Contrasena de la FIEL (oculta): ")

    print()
    print("  Regimenes disponibles:")
    for cod, desc in REGIMENES.items():
        print(f"    {cod} — {desc}")
    regimen = input("  Codigo de regimen [626]: ").strip() or "626"

    try:
        registrar_cliente(rfc, nombre, cer, key, password, regimen)
    except Exception as e:
        print(f"❌ Error: {e}")


def _cmd_run(args: list[str]) -> None:
    """Comando run: ejecuta flujo para un cliente."""
    import argparse
    p = argparse.ArgumentParser(prog="clients.py run")
    p.add_argument("--rfc", required=True)
    p.add_argument("--mes", required=True)
    p.add_argument("--despacho", default="Despacho Contable")
    p.add_argument("--intervalo", type=int, default=60)
    p.add_argument("--no-docs", action="store_true", help="Saltar descarga de documentos SAT")
    parsed = p.parse_args(args)

    correr_cliente(parsed.rfc.upper(), parsed.mes, parsed.despacho, parsed.intervalo, descargar_docs=not parsed.no_docs)


def _cmd_run_all(args: list[str]) -> None:
    """Comando run-all: ejecuta flujo para todos los clientes."""
    import argparse
    p = argparse.ArgumentParser(prog="clients.py run-all")
    p.add_argument("--mes", required=True)
    p.add_argument("--despacho", default="Despacho Contable")
    p.add_argument("--intervalo", type=int, default=60)
    p.add_argument("--no-docs", action="store_true", help="Saltar descarga de documentos SAT")
    parsed = p.parse_args(args)

    correr_todos(parsed.mes, parsed.despacho, parsed.intervalo, descargar_docs=not parsed.no_docs)


def _cmd_list() -> None:
    """Comando list: muestra todos los clientes."""
    listar_clientes()


def _cmd_docs(args: list[str]) -> None:
    """Comando docs: descarga documentos SAT para un cliente o todos."""
    import argparse
    p = argparse.ArgumentParser(prog="clients.py docs")
    p.add_argument("--rfc", default=None, help="RFC del cliente (si se omite, todos)")
    parsed = p.parse_args(args)

    if parsed.rfc:
        resultado = descargar_docs_cliente(parsed.rfc.upper())
        if resultado:
            csf = resultado.get("constancia_fiscal")
            op = resultado.get("opinion_cumplimiento")
            errs = resultado.get("errores", [])
            print(f"\n📄 {parsed.rfc.upper()}")
            print(f"  CSF     : {csf or '❌'}")
            print(f"  Opinión : {op or '❌'}")
            if errs:
                for e in errs:
                    print(f"  ⚠ {e}")
    else:
        resultados = descargar_docs_todos()
        ok = sum(1 for r in resultados.values() if r and r.get("constancia_fiscal"))
        print(f"\n✅ {ok}/{len(resultados)} clientes con CSF descargado")


def _cmd_delete(args: list[str]) -> None:
    """Comando delete: elimina un cliente."""
    import argparse
    p = argparse.ArgumentParser(prog="clients.py delete")
    p.add_argument("--rfc", required=True)
    parsed = p.parse_args(args)

    if eliminar_cliente(parsed.rfc.upper()):
        print(f"✅ {parsed.rfc.upper()} eliminado.")
    else:
        print(f"❌ {parsed.rfc.upper()} no encontrado.")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nComandos disponibles: add, list, run, run-all, delete, docs")
        sys.exit(0)

    comando = sys.argv[1].lower()
    resto = sys.argv[2:]

    comandos = {
        "add":     lambda: _cmd_add(),
        "list":    lambda: _cmd_list(),
        "run":     lambda: _cmd_run(resto),
        "run-all": lambda: _cmd_run_all(resto),
        "delete":  lambda: _cmd_delete(resto),
        "docs":    lambda: _cmd_docs(resto),
    }

    if comando not in comandos:
        print(f"❌ Comando desconocido: {comando}")
        print(f"   Disponibles: {', '.join(comandos.keys())}")
        sys.exit(1)

    try:
        comandos[comando]()
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
