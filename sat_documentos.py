"""
sat_documentos.py
-----------------
Descarga automática de documentos oficiales del SAT con FIEL (e.firma):
  1. Constancia de Situación Fiscal (CSF)
  2. Opinión de Cumplimiento de Obligaciones Fiscales (32-D)

Usa Playwright + Chromium headless. Flujo 100% automático (sin captcha).

Flujo descubierto:
  1. Lanzador wwwmat.sat.gob.mx → login.siat.sat.gob.mx (fiel_Aviso)
  2. FIEL auth → accesoF → servicio (dentro de iframe rfcampc.siat.sat.gob.mx)
  3. Click "Generar Constancia" / "Generar" → descarga PDF
"""

import sys
import os
import time
import base64
import logging
from pathlib import Path
from datetime import date
from typing import Optional

LIBS = Path(__file__).resolve().parent / "libs"
if str(LIBS) not in sys.path:
    sys.path.insert(0, str(LIBS))

log = logging.getLogger("sat_documentos")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(h)
    log.propagate = False

# ═══════════════════════════════════════════════════════════
# Constantes
# ═══════════════════════════════════════════════════════════

SAT_HOST = "https://wwwmat.sat.gob.mx"
SAT_LANZADOR = f"{SAT_HOST}/app/seg/faces/pages/lanzador.jsf"

SERVICIOS = {
    "constancia": {
        "nombre": "Constancia de Situación Fiscal",
        "operacion": 53027,
        "slug": "genera-tu-constancia-de-situacion-fiscal",
        "boton_generar": [
            "#formReimpAcuse\\:j_idt50",
            "text='Generar Constancia'",
        ],
    },
    "opinion": {
        "nombre": "Opinión de Cumplimiento 32-D",
        "operacion": 53048,
        "slug": "consulta-tu-opinion-del-cumplimiento-de-obligaciones-fiscales",
        "boton_generar": [
            "text='Generar'",
            "text='Obtener Opinión'",
            "button:has-text('Generar')",
        ],
    },
}


def _build_lanzador_url(servicio_key: str) -> str:
    """Lanzador con tipoLogeo=f (FIEL)."""
    svc = SERVICIOS[servicio_key]
    return (
        f"{SAT_LANZADOR}"
        f"?url=/operacion/{svc['operacion']}/{svc['slug']}"
        f"&tipoLogeo=f"
        f"&target=principal"
        f"&hostServer={SAT_HOST}"
    )


# ═══════════════════════════════════════════════════════════
# Núcleo
# ═══════════════════════════════════════════════════════════

def _descargar_documento(
    servicio_key: str,
    rfc: str,
    cer_path: str,
    key_path: str,
    password: str,
    output_dir: Path,
) -> Optional[Path]:
    from playwright.sync_api import sync_playwright

    svc = SERVICIOS[servicio_key]
    nombre = svc["nombre"]
    lanzador = _build_lanzador_url(servicio_key)

    log.info(f"Descargando: {nombre}")
    log.info(f"  RFC: {rfc}")
    output_dir.mkdir(parents=True, exist_ok=True)

    cer = Path(cer_path)
    key = Path(key_path)
    if not cer.exists():
        log.error(f"  .cer no encontrado: {cer_path}")
        return None
    if not key.exists():
        log.error(f"  .key no encontrado: {key_path}")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            accept_downloads=True,
            locale="es-MX",
            timezone_id="America/Mexico_City",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            # ── 1. Establecer sesión en portal SAT ──
            log.info("  Paso 1: Portal SAT...")
            page.goto("https://www.sat.gob.mx/portal/public/tramites/constancia-de-situacion-fiscal",
                      wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)

            # ── 2. Lanzador → FIEL login ──
            log.info("  Paso 2: Lanzador FIEL...")
            page.goto(lanzador, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(3)
            log.info(f"  Login: {page.url}")

            # ── 3. Llenar FIEL ──
            log.info("  Paso 3: FIEL auth...")
            page.locator("#fileCertificate").set_input_files(str(cer.resolve()))
            log.info("    .cer ✓")
            time.sleep(0.3)
            page.locator("#filePrivateKey").set_input_files(str(key.resolve()))
            log.info("    .key ✓")
            time.sleep(0.3)
            page.locator("#privateKeyPassword").fill(password)
            log.info("    contraseña ✓")
            time.sleep(0.3)
            try:
                page.evaluate(f"document.querySelector('#rfc').value = '{rfc.upper()}'")
            except Exception:
                pass

            # Enviar
            page.locator("#submit").click()
            log.info("  Enviado, esperando auth...")

            # Esperar salir de login
            try:
                page.wait_for_url(lambda u: "login.siat" not in u, timeout=45_000)
            except Exception:
                log.warning("  Timeout saliendo de login")

            # Esperar accesoF → servicio
            try:
                page.wait_for_url(
                    lambda u: "operacion" in u and "accesoF" not in u,
                    timeout=30_000)
            except Exception:
                pass

            time.sleep(5)
            log.info(f"  Servicio: {page.url} — {page.title()}")

            # ── 3.5: Verificar que la pagina cargo correctamente ──
            if "Página no encontrada" in page.inner_text("body"):
                log.error(f"  ❌ Servicio no disponible: {page.url}")
                log.error(f"  Es posible que la operación no exista en esta URL.")
                page.screenshot(path=str(
                    output_dir / f"debug_{servicio_key}_404.png"))
                return None

            # ── 4. Buscar iframe del servicio ──
            log.info("  Paso 4: Buscando iframe...")
            target = page
            svc_frame = None
            for frame in page.frames:
                url = frame.url
                if frame != page.main_frame and ("rfcampc" in url or "PTSC" in url
                                                    or "Reimpresion" in url
                                                    or "Consulta" in url):
                    svc_frame = frame
                    log.info(f"    Iframe: {url[:120]}")
                    break
            if svc_frame:
                try:
                    svc_frame.wait_for_load_state("domcontentloaded", timeout=15_000)
                except Exception:
                    pass
                target = svc_frame

            # ── 5. Click generar ──
            log.info("  Paso 5: Buscando botón generar...")
            time.sleep(2)
            clicked = False

            # Por selectores específicos
            for sel in svc["boton_generar"]:
                try:
                    btn = target.wait_for_selector(sel, timeout=8_000, state="visible")
                    if btn:
                        log.info(f"    Click: {sel}")
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        btn.click()
                        clicked = True
                        break
                except Exception:
                    continue

            # Búsqueda genérica
            if not clicked:
                for txt in ["Generar Constancia", "Generar", "Descargar",
                             "Obtener", "Imprimir"]:
                    try:
                        btn = target.locator(
                            f"button:has-text('{txt}'), input[type='submit']:has-text('{txt}')"
                        ).first
                        if btn.is_visible():
                            log.info(f"    Click genérico: '{txt}'")
                            btn.click()
                            clicked = True
                            break
                    except Exception:
                        continue

            if not clicked:
                log.warning("  ⚠ No se encontró botón de generación")
                target.screenshot(path=str(
                    output_dir / f"debug_{servicio_key}_no_button.png"))

            time.sleep(3)

            # ── 6. Capturar PDF ──
            log.info("  Paso 6: Esperando PDF...")
            pdf_path = None

            # Descarga automática
            try:
                with page.expect_download(timeout=120_000) as dl:
                    pass
                download = dl.value
                filename = download.suggested_filename or f"{rfc}_{servicio_key}.pdf"
                dest = output_dir / filename
                download.save_as(str(dest))
                pdf_path = dest
                log.info(f"    PDF: {dest}")
            except Exception:
                pass

            # Link de descarga
            if not pdf_path:
                for sel in ["a[href$='.pdf']", "a:has-text('PDF')",
                             "a:has-text('Descargar')", "button:has-text('Descargar')"]:
                    try:
                        link = target.wait_for_selector(sel, timeout=3_000, state="visible")
                        if link:
                            with page.expect_download(timeout=60_000) as dl:
                                link.click()
                            download = dl.value
                            dest = output_dir / (
                                download.suggested_filename or f"{rfc}_{servicio_key}.pdf")
                            download.save_as(str(dest))
                            pdf_path = dest
                            log.info(f"    PDF vía link: {dest}")
                            break
                    except Exception:
                        continue

            # Nueva pestaña
            if not pdf_path:
                for p in context.pages:
                    if p != page and ".pdf" in p.url.lower():
                        log.info(f"    PDF en pestaña: {p.url}")
                        try:
                            import re as _re
                            data_url = p.evaluate("""async () => {
                                const r = await fetch(window.location.href);
                                const blob = await r.blob();
                                const reader = new FileReader();
                                return new Promise(resolve => {
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.readAsDataURL(blob);
                                });
                            }""")
                            if data_url:
                                b64 = _re.sub(r'^data:.+;base64,', '', str(data_url))
                                dest = output_dir / f"{rfc}_{servicio_key}.pdf"
                                dest.write_bytes(base64.b64decode(b64))
                                pdf_path = dest
                                log.info(f"    PDF de pestaña: {dest}")
                        except Exception:
                            pass

            # Validar
            if pdf_path and pdf_path.exists() and pdf_path.stat().st_size > 500:
                log.info(f"  ✅ {nombre}: {pdf_path} ({pdf_path.stat().st_size} bytes)")
                return pdf_path
            else:
                if pdf_path:
                    log.warning(f"  PDF sospechoso ({pdf_path.stat().st_size} bytes)")
                else:
                    log.error(f"  ❌ No se pudo descargar {nombre}")
                target.screenshot(path=str(
                    output_dir / f"debug_{servicio_key}_end.png"))
                return None

        except Exception as e:
            log.error(f"  Error en {nombre}: {e}")
            try:
                page.screenshot(path=str(
                    output_dir / f"debug_{servicio_key}_error.png"))
            except Exception:
                pass
            return None

        finally:
            browser.close()


# ═══════════════════════════════════════════════════════════
# API Pública
# ═══════════════════════════════════════════════════════════

def descargar_constancia_fiscal(
    rfc: str, cer_path: str, key_path: str, password: str, output_dir: Path
) -> Optional[Path]:
    """Descarga la Constancia de Situación Fiscal del SAT."""
    return _descargar_documento("constancia", rfc, cer_path, key_path, password, output_dir)


def descargar_opinion_cumplimiento(
    rfc: str, cer_path: str, key_path: str, password: str, output_dir: Path
) -> Optional[Path]:
    """Descarga la Opinión de Cumplimiento 32-D del SAT."""
    return _descargar_documento("opinion", rfc, cer_path, key_path, password, output_dir)


def descargar_documentos_sat(
    rfc: str, cer_path: str, key_path: str, password: str, output_dir: Path
) -> dict:
    """
    Descarga ambos documentos: CSF + Opinión 32-D.
    Returns: {"rfc", "constancia_fiscal", "opinion_cumplimiento", "errores"}
    """
    errores = []
    c = o = None
    try:
        c = descargar_constancia_fiscal(rfc, cer_path, key_path, password, output_dir)
    except Exception as e:
        errores.append(f"CSF: {e}")
    try:
        o = descargar_opinion_cumplimiento(rfc, cer_path, key_path, password, output_dir)
    except Exception as e:
        errores.append(f"Opinión: {e}")
    return {"rfc": rfc, "constancia_fiscal": c, "opinion_cumplimiento": o, "errores": errores}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rfc", required=True)
    ap.add_argument("--cer", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default=".")
    ap.add_argument("--tipo", choices=["constancia", "opinion", "ambos"], default="ambos")
    args = ap.parse_args()
    out = Path(args.out)
    if args.tipo in ("constancia", "ambos"):
        p = descargar_constancia_fiscal(args.rfc, args.cer, args.key, args.password, out)
        print(f"CSF: {p}")
    if args.tipo in ("opinion", "ambos"):
        p = descargar_opinion_cumplimiento(args.rfc, args.cer, args.key, args.password, out)
        print(f"Opinión: {p}")
