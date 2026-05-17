"""
file_handler.py
---------------
Manejo de archivos locales: extraccion de ZIPs, organizacion de carpetas
y resolucion de rutas de salida.

Metadata: extrae TXT, renombra YYYY-MM-RFC.txt, elimina ZIP.
CFDI:     extrae XMLs en subcarpeta, renombra ZIP YYYY-MM-RFC.zip, conserva.
"""

import zipfile
from datetime import datetime
from pathlib import Path

from core.config import log


# ===========================================================================
# Resolucion de carpeta de salida
# ===========================================================================

def resolve_output_dir(params: dict) -> Path:
    """
    Crea la estructura de carpetas de salida:
      results_RFC / metadata|cfdi / YYYY-MM-DD /

    Si la carpeta del dia ya existe, advierte que se sobreescribira silenciosamente.
    Devuelve la ruta completa lista para usar.
    """
    mode      = "metadata" if params["solicitud"] == "Metadata" else "cfdi"
    today     = datetime.now().strftime("%Y-%m-%d")
    directory = params["output"] / mode / today

    if directory.exists():
        log.warning(f"La carpeta de hoy ya existe: {directory.resolve()}")
        log.warning("  Los archivos existentes seran sobreescritos silenciosamente.")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        log.info(f"Carpeta de salida creada: {directory.resolve()}")

    return directory


def resolve_retomar_output_dir(params: dict) -> Path:
    """
    Crea la carpeta de salida para una solicitud retomada.
    Siempre usa cfdi como modo ya que el retomar solo aplica a CFDI.
    """
    today     = datetime.now().strftime("%Y-%m-%d")
    directory = params["output"] / "cfdi" / today

    if directory.exists():
        log.warning(f"  Carpeta ya existe: {directory.resolve()} — archivos seran sobreescritos.")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        log.info(f"  Carpeta de salida: {directory.resolve()}")

    return directory


# ===========================================================================
# Extraccion de Metadata (TXT)
# ===========================================================================

def extract_metadata(zip_path: Path, dest_name: str) -> list[Path]:
    """
    Extrae el TXT de Metadata del ZIP, lo renombra como YYYY-MM-RFC.txt
    y elimina el ZIP original despues de extraer exitosamente.

    Si el paquete contiene mas de un archivo, se agrega sufijo numerico.
    """
    output_dir = zip_path.parent
    log.info(f"  Extrayendo Metadata de: {zip_path.name}")

    try:
        extracted: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            contents = zf.namelist()
            log.info(f"  Archivos en el paquete: {len(contents)}")

            for i, name in enumerate(contents):
                ext    = Path(name).suffix or ".txt"
                suffix = f"_{i + 1}" if i > 0 else ""
                dest   = output_dir / f"{dest_name}{suffix}{ext}"
                dest.write_bytes(zf.read(name))
                extracted.append(dest)
                log.info(f"    -> {dest.name}")

        log.info(f"  Eliminando ZIP de Metadata: {zip_path.name}...")
        zip_path.unlink()
        log.info(f"  ZIP eliminado correctamente: {zip_path.name}")
        return extracted

    except zipfile.BadZipFile:
        log.error(f"  X ZIP corrupto: {zip_path}. Eliminalo y re-ejecuta el script.")
        return []
    except Exception as e:
        log.error(f"  X Error al extraer Metadata. Causa: {e}")
        return []


# ===========================================================================
# Extraccion de CFDI (XML)
# ===========================================================================

def _unique_zip_path(directory: Path, dest_name: str) -> Path:
    """
    Genera una ruta unica para el ZIP de CFDI.
    Si YYYY-MM-RFC.zip ya existe, agrega sufijo: _2, _3, etc.
    """
    candidate = directory / f"{dest_name}.zip"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = directory / f"{dest_name}_{counter}.zip"
        if not candidate.exists():
            log.info(f"  ZIP con nombre existente — usando: {candidate.name}")
            return candidate
        counter += 1


def extract_cfdi(zip_path: Path, dest_name: str,
                 keep_zip: bool = True) -> tuple[list[Path], Path | None]:
    """
    Extrae los XMLs del ZIP en una subcarpeta YYYY-MM-RFC/.
    Si keep_zip es True: conserva el ZIP renombrado con nombre unico.
    Si keep_zip es False: elimina el ZIP tras extraer.
    Retorna (lista de XMLs extraidos, ruta al ZIP o None).
    """
    output_dir = zip_path.parent
    xml_dir    = output_dir / dest_name
    xml_dir.mkdir(exist_ok=True)

    log.info(f"  Extrayendo XMLs de: {zip_path.name} -> {xml_dir.name}/")

    try:
        extracted: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            log.info(f"  XMLs en el paquete: {len(xmls)}")
            for name in xmls:
                dest = xml_dir / name
                dest.write_bytes(zf.read(name))
                extracted.append(dest)

        if keep_zip:
            new_zip = _unique_zip_path(output_dir, dest_name)
            zip_path.rename(new_zip)
            log.info(f"  ZIP renombrado: {new_zip.name}")
            log.info(f"  {len(extracted)} XML(s) extraidos en: {xml_dir.name}/")
            return extracted, new_zip
        else:
            zip_path.unlink()
            log.info(f"  ZIP eliminado: {zip_path.name}")
            log.info(f"  {len(extracted)} XML(s) extraidos en: {xml_dir.name}/")
            return extracted, None

    except zipfile.BadZipFile:
        log.error(f"  X ZIP corrupto: {zip_path}")
        return [], None
    except Exception as e:
        log.error(f"  X Error al extraer XMLs. Causa: {e}")
        return [], None