"""
ui/main.py
----------
Interfaz grafica de escritorio para taxcrawler-dm.
Llama a la API (api/main.py) via HTTP — no llama a services/ ni core/ directamente.

Iniciar:
  1. Terminal 1: python3 -m uvicorn api.main:app --reload
  2. Terminal 2: python3 ui/main.py

Pantallas:
  1. Configuracion — RFC, FIEL, fechas, despacho
  2. Progreso       — logs en tiempo real, indicador de fase, cancelar
  3. Resultados     — archivos generados, abrir Excel, pendientes
"""

import queue
import sys
import threading
import subprocess
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_libs = _root / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

import customtkinter as ctk
import requests

# ---------------------------------------------------------------------------
# Configuracion de la API
# ---------------------------------------------------------------------------
API_BASE    = "http://localhost:8000"
# TODO: cuando se implemente auth (Basic o JWT), agregar aqui el header
# AUTH_HEADER = {"Authorization": "Bearer <token>"}
# Usar en cada llamada: headers=AUTH_HEADER
API_TIMEOUT = 300  # segundos — las descargas del SAT pueden tardar

# ---------------------------------------------------------------------------
# Tema
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ===========================================================================
# Cliente HTTP
# ===========================================================================

def api_post(endpoint: str, body: dict) -> dict:
    """
    Realiza un POST a la API y retorna el JSON de respuesta.
    Lanza Exception con mensaje legible si falla.
    TODO: agregar header de autorizacion cuando se implemente auth.
    """
    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.post(url, json=body, timeout=API_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        raise Exception(
            "No se pudo conectar con el servidor.\n"
            "Asegurate de que el servidor este corriendo:\n"
            "python3 -m uvicorn api.main:app --reload"
        )
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        raise Exception(f"Error del servidor: {detail}")
    except requests.exceptions.Timeout:
        raise Exception("El servidor tardo demasiado. El SAT puede estar lento — intenta de nuevo.")


def api_get(endpoint: str) -> dict:
    """
    Realiza un GET a la API y retorna el JSON de respuesta.
    TODO: agregar header de autorizacion cuando se implemente auth.
    """
    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        raise Exception(
            "No se pudo conectar con el servidor.\n"
            "Asegurate de que el servidor este corriendo:\n"
            "python3 -m uvicorn api.main:app --reload"
        )
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        raise Exception(f"Error del servidor: {detail}")


def check_server() -> bool:
    """Verifica que el servidor este activo antes de mostrar la UI."""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=3)
        return response.status_code == 200
    except Exception:
        return False


# ===========================================================================
# Aplicacion principal
# ===========================================================================

class TaxCrawlerApp(ctk.CTk):
    """
    Aplicacion principal con 3 pantallas:
      Screen 1: Configuracion
      Screen 2: Progreso
      Screen 3: Resultados
    """

    def __init__(self):
        super().__init__()

        self.title("taxcrawler-dm")
        self.geometry("900x680")
        self.minsize(800, 600)
        self.resizable(True, True)

        # Estado compartido entre pantallas
        self._cancel_flag  = threading.Event()
        self._log_queue:  queue.Queue = queue.Queue()
        self._result_data: dict       = {}

        # Contenedor principal
        self._container = ctk.CTkFrame(self)
        self._container.pack(fill="both", expand=True, padx=10, pady=10)

        self._show_screen1()

    # =======================================================================
    # PANTALLA 1 — Configuracion
    # =======================================================================

    def _show_screen1(self):
        """Muestra la pantalla de configuracion."""
        self._clear_container()

        # Titulo
        ctk.CTkLabel(
            self._container,
            text="taxcrawler-dm",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self._container,
            text="Descarga masiva de CFDI del SAT",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack(pady=(0, 20))

        # Frame del formulario
        form = ctk.CTkFrame(self._container)
        form.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        form.columnconfigure(1, weight=1)

        row = 0

        # RFC
        ctk.CTkLabel(form, text="RFC *").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._rfc_var = ctk.StringVar()
        rfc_entry = ctk.CTkEntry(form, textvariable=self._rfc_var, placeholder_text="XAXX010101000")
        rfc_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        rfc_entry.bind("<FocusOut>", self._on_rfc_focusout)
        row += 1

        # .cer
        ctk.CTkLabel(form, text=".cer (FIEL) *").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._cer_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self._cer_var, placeholder_text="/ruta/a/fiel.cer").grid(
            row=row, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(form, text="Buscar", width=80,
                      command=lambda: self._browse_file(self._cer_var, [("Certificado", "*.cer")])).grid(
            row=row, column=2, padx=8, pady=8)
        row += 1

        # .key
        ctk.CTkLabel(form, text=".key (FIEL) *").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._key_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self._key_var, placeholder_text="/ruta/a/fiel.key").grid(
            row=row, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(form, text="Buscar", width=80,
                      command=lambda: self._browse_file(self._key_var, [("Clave privada", "*.key")])).grid(
            row=row, column=2, padx=8, pady=8)
        row += 1

        # Password
        ctk.CTkLabel(form, text="Contrasena FIEL *").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._password_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self._password_var, show="*",
                     placeholder_text="Contrasena de la FIEL").grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        row += 1

        # Fecha inicio
        ctk.CTkLabel(form, text="Fecha inicio *").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._inicio_var = ctk.StringVar(value="2025-01-01")
        ctk.CTkEntry(form, textvariable=self._inicio_var, placeholder_text="YYYY-MM-DD").grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        row += 1

        # Fecha fin
        ctk.CTkLabel(form, text="Fecha fin *").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._fin_var = ctk.StringVar(value=str(date.today()))
        ctk.CTkEntry(form, textvariable=self._fin_var, placeholder_text="YYYY-MM-DD").grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        row += 1

        # Despacho
        ctk.CTkLabel(form, text="Nombre del despacho").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._despacho_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self._despacho_var,
                     placeholder_text="Mi Despacho Contable SC").grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        row += 1

        # Carpeta de salida
        ctk.CTkLabel(form, text="Carpeta de salida").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._output_var = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self._output_var,
                     placeholder_text="Default: ./results_RFC").grid(
            row=row, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(form, text="Buscar", width=80,
                      command=self._browse_folder).grid(
            row=row, column=2, padx=8, pady=8)
        row += 1

        # Regimen
        ctk.CTkLabel(form, text="Regimen fiscal").grid(row=row, column=0, sticky="w", padx=16, pady=8)
        self._regimen_var = ctk.StringVar(value="resico")
        ctk.CTkOptionMenu(form, variable=self._regimen_var,
                          values=["resico", "pfae"]).grid(
            row=row, column=1, columnspan=2, sticky="w", padx=8, pady=8)
        row += 1

        # Mensaje de estado del servidor
        self._server_label = ctk.CTkLabel(
            self._container,
            text="",
            font=ctk.CTkFont(size=11),
        )
        self._server_label.pack(pady=(0, 4))
        self._check_server_status()

        # Boton de inicio
        self._start_btn = ctk.CTkButton(
            self._container,
            text="Iniciar flujo completo",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            command=self._on_start,
        )
        self._start_btn.pack(pady=(0, 20), padx=20, fill="x")

    def _check_server_status(self):
        """Verifica el estado del servidor y actualiza el label."""
        if check_server():
            self._server_label.configure(
                text="Servidor activo en http://localhost:8000",
                text_color="green",
            )
        else:
            self._server_label.configure(
                text="Servidor no disponible — inicia: python3 -m uvicorn api.main:app --reload",
                text_color="orange",
            )

    def _on_rfc_focusout(self, event=None):
        """Al salir del campo RFC, intenta cargar el perfil guardado."""
        rfc = self._rfc_var.get().strip().upper()
        if not rfc:
            return
        try:
            data = api_get(f"/cache/profile/{rfc}")
            profile = data.get("profile")
            if profile:
                if profile.get("cer_exists") and not self._cer_var.get():
                    self._cer_var.set(profile.get("cer", ""))
                if profile.get("key_exists") and not self._key_var.get():
                    self._key_var.set(profile.get("key", ""))
                if not self._output_var.get():
                    self._output_var.set(profile.get("output", ""))
        except Exception:
            pass  # Sin perfil o servidor no disponible — continuar sin autofill

    def _browse_file(self, var: ctk.StringVar, filetypes: list):
        """Abre un dialogo para seleccionar un archivo."""
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _browse_folder(self):
        """Abre un dialogo para seleccionar una carpeta."""
        path = filedialog.askdirectory()
        if path:
            self._output_var.set(path)

    def _validate_form(self) -> dict | None:
        """
        Valida los campos del formulario.
        Retorna el dict de parametros si es valido, None si hay errores.
        """
        errors = []

        rfc = self._rfc_var.get().strip().upper()
        if not rfc:
            errors.append("RFC es obligatorio.")

        cer = self._cer_var.get().strip()
        if not cer:
            errors.append("Archivo .cer es obligatorio.")
        elif not Path(cer).exists():
            errors.append(f"Archivo .cer no encontrado: {cer}")

        key = self._key_var.get().strip()
        if not key:
            errors.append("Archivo .key es obligatorio.")
        elif not Path(key).exists():
            errors.append(f"Archivo .key no encontrado: {key}")

        password = self._password_var.get()
        if not password:
            errors.append("Contrasena es obligatoria.")

        inicio = self._inicio_var.get().strip()
        fin    = self._fin_var.get().strip()
        try:
            date.fromisoformat(inicio)
        except ValueError:
            errors.append("Fecha inicio invalida. Usa formato YYYY-MM-DD.")
        try:
            date.fromisoformat(fin)
        except ValueError:
            errors.append("Fecha fin invalida. Usa formato YYYY-MM-DD.")

        if errors:
            messagebox.showerror("Errores de validacion", "\n".join(errors))
            return None

        return {
            "rfc":        rfc,
            "cer_path":   cer,
            "key_path":   key,
            "password":   password,
            "start_date": inicio,
            "end_date":   fin,
            "despacho":   self._despacho_var.get().strip() or None,
            "output_dir": self._output_var.get().strip() or None,
            "regimen":    self._regimen_var.get(),
            "intervalo":  60,
        }

    def _on_start(self):
        """Valida el formulario y transiciona a la pantalla de progreso."""
        if not check_server():
            messagebox.showerror(
                "Servidor no disponible",
                "El servidor no esta corriendo.\n\n"
                "Abre otra terminal y ejecuta:\n"
                "python3 -m uvicorn api.main:app --reload"
            )
            return

        params = self._validate_form()
        if params:
            self._show_screen2(params)

    # =======================================================================
    # PANTALLA 2 — Progreso
    # =======================================================================

    def _show_screen2(self, params: dict):
        """Muestra la pantalla de progreso y lanza el proceso en background."""
        self._clear_container()
        self._cancel_flag.clear()

        # Titulo
        ctk.CTkLabel(
            self._container,
            text="Procesando...",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(20, 4))

        self._phase_label = ctk.CTkLabel(
            self._container,
            text="Iniciando conexion con el SAT...",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._phase_label.pack(pady=(0, 12))

        # Barra de progreso indeterminada
        self._progress = ctk.CTkProgressBar(self._container, mode="indeterminate")
        self._progress.pack(fill="x", padx=20, pady=(0, 12))
        self._progress.start()

        # Panel de logs
        log_frame = ctk.CTkFrame(self._container)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        self._log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Courier", size=11),
            state="disabled",
            wrap="word",
        )
        self._log_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Boton cancelar
        self._cancel_btn = ctk.CTkButton(
            self._container,
            text="Cancelar",
            fg_color="gray30",
            hover_color="gray20",
            command=self._on_cancel,
        )
        self._cancel_btn.pack(pady=(0, 20), padx=20, fill="x")

        # Lanzar proceso en background
        self._append_log(f"RFC: {params['rfc']}")
        self._append_log(f"Periodo: {params['start_date']} -> {params['end_date']}")
        self._append_log("-" * 50)

        thread = threading.Thread(
            target=self._run_full_flow,
            args=(params,),
            daemon=True,
        )
        thread.start()

        # Iniciar loop de actualizacion de logs
        self._poll_logs()

    def _append_log(self, message: str):
        """Agrega un mensaje al panel de logs desde cualquier hilo via queue."""
        self._log_queue.put(message)

    def _poll_logs(self):
        """Revisa la queue de logs y actualiza el panel. Se llama cada 100ms."""
        try:
            while True:
                message = self._log_queue.get_nowait()
                self._log_text.configure(state="normal")
                self._log_text.insert("end", message + "\n")
                self._log_text.see("end")
                self._log_text.configure(state="disabled")
        except queue.Empty:
            pass
        # Repetir cada 100ms mientras la pantalla este activa
        if hasattr(self, "_log_text"):
            self.after(100, self._poll_logs)

    def _run_full_flow(self, params: dict):
        """
        Ejecuta el flujo completo via API en un hilo de background.
        Actualiza la UI via queue — nunca toca widgets directamente.
        """
        try:
            self._append_log("PASO 1/3 — Conectando con el SAT...")
            self.after(0, lambda: self._phase_label.configure(
                text="Paso 1/3 — Descargando Metadata de ingresos..."
            ))

            if self._cancel_flag.is_set():
                self._append_log("Operacion cancelada por el usuario.")
                self.after(0, self._on_cancelled)
                return

            result = api_post("/download/full-flow", params)

            self._append_log("")
            self._append_log("=" * 50)
            self._append_log("PROCESO COMPLETADO")
            self._append_log("=" * 50)
            self._append_log(f"RFC         : {result.get('rfc')}")
            self._append_log(f"Periodo     : {result.get('start_date')} -> {result.get('end_date')}")
            self._append_log(f"Despacho    : {result.get('despacho')}")
            self._append_log(f"Excel       : {result.get('excel_path')}")
            self._append_log("")

            self._result_data = result
            self.after(0, self._on_completed)

        except Exception as e:
            self._append_log("")
            self._append_log(f"ERROR: {e}")
            self.after(0, lambda: self._on_error(str(e)))

    def _on_cancel(self):
        """Marca el flag de cancelacion."""
        self._cancel_flag.set()
        self._cancel_btn.configure(text="Cancelando...", state="disabled")
        self._append_log("")
        self._append_log("Cancelando — las solicitudes pendientes se conservan.")

    def _on_cancelled(self):
        """UI despues de cancelar."""
        self._progress.stop()
        self._phase_label.configure(text="Operacion cancelada.", text_color="orange")
        self._cancel_btn.configure(
            text="Nueva descarga",
            state="normal",
            fg_color=["#3B8ED0", "#1F6AA5"],
            command=self._show_screen1,
        )

    def _on_completed(self):
        """UI cuando el proceso termina exitosamente."""
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(1.0)
        self._phase_label.configure(text="Proceso completado.", text_color="green")
        self._cancel_btn.configure(
            text="Ver resultados",
            state="normal",
            fg_color=["#3B8ED0", "#1F6AA5"],
            command=self._show_screen3,
        )

    def _on_error(self, message: str):
        """UI cuando el proceso falla."""
        self._progress.stop()
        self._phase_label.configure(text="Error en el proceso.", text_color="red")
        self._cancel_btn.configure(
            text="Volver al inicio",
            state="normal",
            fg_color="gray30",
            command=self._show_screen1,
        )
        messagebox.showerror("Error", message)

    # =======================================================================
    # PANTALLA 3 — Resultados
    # =======================================================================

    def _show_screen3(self):
        """Muestra la pantalla de resultados."""
        self._clear_container()

        ctk.CTkLabel(
            self._container,
            text="Proceso completado",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            self._container,
            text=f"RFC: {self._result_data.get('rfc', '')}  |  "
                 f"{self._result_data.get('start_date', '')} -> {self._result_data.get('end_date', '')}",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(pady=(0, 20))

        # Excel generado
        excel_path = self._result_data.get("excel_path")
        if excel_path:
            excel_frame = ctk.CTkFrame(self._container)
            excel_frame.pack(fill="x", padx=20, pady=(0, 12))

            ctk.CTkLabel(
                excel_frame,
                text="Excel generado:",
                font=ctk.CTkFont(weight="bold"),
            ).pack(anchor="w", padx=16, pady=(12, 4))

            ctk.CTkLabel(
                excel_frame,
                text=excel_path,
                font=ctk.CTkFont(family="Courier", size=11),
                text_color="gray",
                wraplength=800,
            ).pack(anchor="w", padx=16, pady=(0, 8))

            ctk.CTkButton(
                excel_frame,
                text="Abrir Excel",
                command=lambda: self._open_file(excel_path),
            ).pack(anchor="w", padx=16, pady=(0, 12))

        # Solicitudes pendientes
        pending_frame = ctk.CTkFrame(self._container)
        pending_frame.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            pending_frame,
            text="Solicitudes pendientes:",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=16, pady=(12, 4))

        try:
            data    = api_get("/cache/pending")
            pending = data.get("requests", [])
            if pending:
                for req in pending:
                    ctk.CTkLabel(
                        pending_frame,
                        text=f"  {req.get('rfc')} — {req.get('inicio')} -> {req.get('fin')} "
                             f"({req.get('elapsed', '')})",
                        font=ctk.CTkFont(size=11),
                        text_color="orange",
                    ).pack(anchor="w", padx=16)
            else:
                ctk.CTkLabel(
                    pending_frame,
                    text="  Sin solicitudes pendientes.",
                    font=ctk.CTkFont(size=11),
                    text_color="gray",
                ).pack(anchor="w", padx=16)
        except Exception:
            ctk.CTkLabel(
                pending_frame,
                text="  No se pudo consultar el servidor.",
                font=ctk.CTkFont(size=11),
                text_color="gray",
            ).pack(anchor="w", padx=16)

        ctk.CTkLabel(pending_frame, text="").pack(pady=4)

        # Botones de accion
        btn_frame = ctk.CTkFrame(self._container, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(8, 20))
        btn_frame.columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame,
            text="Nueva descarga",
            command=self._show_screen1,
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="Salir",
            fg_color="gray30",
            hover_color="gray20",
            command=self.quit,
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def _open_file(self, path: str):
        """Abre un archivo con la aplicacion por defecto del sistema."""
        import platform
        try:
            if platform.system() == "Darwin":
                subprocess.run(["open", path], check=True)
            elif platform.system() == "Windows":
                subprocess.run(["start", path], shell=True, check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el archivo:\n{e}")

    # =======================================================================
    # Utilidades
    # =======================================================================

    def _clear_container(self):
        """Elimina todos los widgets del contenedor principal."""
        for widget in self._container.winfo_children():
            widget.destroy()


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    if not check_server():
        root = ctk.CTk()
        root.withdraw()
        messagebox.showwarning(
            "Servidor no disponible",
            "El servidor de taxcrawler-dm no esta corriendo.\n\n"
            "Abre una terminal y ejecuta:\n"
            "python3 -m uvicorn api.main:app --reload\n\n"
            "Luego vuelve a abrir la aplicacion."
        )
        root.destroy()
        sys.exit(0)

    app = TaxCrawlerApp()
    app.mainloop()