"""
screen_download.py
------------------
Tab de descarga: formulario de configuracion y pantalla de progreso.
Llama a api_client.py — no toca core/ ni services/ directamente.
"""

import json
import queue
import subprocess
import sys
import threading
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

from ui.api_client import api_post, api_get, check_server
from ui.widgets import DateWidget


class DownloadTab(ctk.CTkFrame):
    """
    Tab completo de descarga.
    Contiene el formulario de configuracion y la pantalla de progreso.
    on_result(data): callback llamado cuando se completa una operacion exitosa.
    """

    def __init__(self, master, on_result=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_result  = on_result
        self._cancel_flag = threading.Event()
        self._log_queue:  queue.Queue = queue.Queue()
        self._showing_progress = False

        self._build_form()

    # =======================================================================
    # Formulario de configuracion
    # =======================================================================

    def _build_form(self):
        """Construye el formulario de configuracion."""
        self._clear()
        self._showing_progress = False

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        scroll.columnconfigure(1, weight=1)

        row = 0

        # Operacion
        ctk.CTkLabel(scroll, text="Operacion",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._op_var = ctk.StringVar(value="full_flow")
        op_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        op_frame.grid(row=row, column=1, columnspan=2, sticky="w", padx=8, pady=6)
        for val, lbl in [("full_flow", "Flujo completo"),
                          ("metadata",  "Solo Metadata"),
                          ("cfdi",      "Solo CFDI")]:
            ctk.CTkRadioButton(op_frame, text=lbl,
                               variable=self._op_var, value=val,
                               command=self._on_op_change).pack(side="left", padx=10)
        row += 1

        # RFC
        ctk.CTkLabel(scroll, text="RFC *").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._rfc_var = ctk.StringVar()
        rfc_e = ctk.CTkEntry(scroll, textvariable=self._rfc_var,
                              placeholder_text="XAXX010101000")
        rfc_e.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        rfc_e.bind("<FocusOut>", self._on_rfc_focusout)
        row += 1

        # .cer
        ctk.CTkLabel(scroll, text=".cer (FIEL) *").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._cer_var = ctk.StringVar()
        ctk.CTkEntry(scroll, textvariable=self._cer_var,
                     placeholder_text="/ruta/fiel.cer").grid(
            row=row, column=1, sticky="ew", padx=8, pady=6)
        ctk.CTkButton(scroll, text="Buscar", width=80,
                      command=lambda: self._browse_file(
                          self._cer_var, [("Certificado", "*.cer")])).grid(
            row=row, column=2, padx=8, pady=6)
        row += 1

        # .key
        ctk.CTkLabel(scroll, text=".key (FIEL) *").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._key_var = ctk.StringVar()
        ctk.CTkEntry(scroll, textvariable=self._key_var,
                     placeholder_text="/ruta/fiel.key").grid(
            row=row, column=1, sticky="ew", padx=8, pady=6)
        ctk.CTkButton(scroll, text="Buscar", width=80,
                      command=lambda: self._browse_file(
                          self._key_var, [("Clave privada", "*.key")])).grid(
            row=row, column=2, padx=8, pady=6)
        row += 1

        # Password
        ctk.CTkLabel(scroll, text="Contrasena *").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._pwd_var = ctk.StringVar()
        ctk.CTkEntry(scroll, textvariable=self._pwd_var, show="*",
                     placeholder_text="Contrasena de la FIEL").grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        row += 1

        # Fecha inicio
        ctk.CTkLabel(scroll, text="Fecha inicio *").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._date_inicio = DateWidget(scroll, default="2025-01-01")
        self._date_inicio.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        row += 1

        # Fecha fin
        ctk.CTkLabel(scroll, text="Fecha fin *").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._date_fin = DateWidget(scroll, default=str(date.today()))
        self._date_fin.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        row += 1

        # Tipo emitidos/recibidos
        ctk.CTkLabel(scroll, text="Tipo").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._tipo_var = ctk.StringVar(value="recibidos")
        tipo_f = ctk.CTkFrame(scroll, fg_color="transparent")
        tipo_f.grid(row=row, column=1, columnspan=2, sticky="w", padx=8, pady=6)
        for val, lbl in [("recibidos", "Recibidos"), ("emitidos", "Emitidos")]:
            ctk.CTkRadioButton(tipo_f, text=lbl,
                               variable=self._tipo_var, value=val).pack(
                side="left", padx=10)
        row += 1

        # Despacho — solo visible en full_flow
        self._despacho_row = row
        self._despacho_lbl = ctk.CTkLabel(scroll, text="Despacho")
        self._despacho_lbl.grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self._despacho_var = ctk.StringVar()
        self._despacho_entry = ctk.CTkEntry(
            scroll, textvariable=self._despacho_var,
            placeholder_text="Nombre del despacho (opcional)")
        self._despacho_entry.grid(row=row, column=1, columnspan=2,
                                   sticky="ew", padx=8, pady=6)
        row += 1

        # Timeout — solo CFDI
        self._timeout_lbl = ctk.CTkLabel(scroll, text="Timeout (min)")
        self._timeout_lbl.grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self._timeout_var = ctk.StringVar(value="30")
        self._timeout_entry = ctk.CTkEntry(scroll, textvariable=self._timeout_var)
        self._timeout_entry.grid(row=row, column=1, columnspan=2,
                                  sticky="ew", padx=8, pady=6)
        row += 1

        # Mantener ZIPs — solo CFDI
        self._keep_zip_var = ctk.BooleanVar(value=True)
        self._keep_zip_chk = ctk.CTkCheckBox(
            scroll, text="Mantener ZIPs originales",
            variable=self._keep_zip_var)
        self._keep_zip_chk.grid(row=row, column=1, columnspan=2,
                                 sticky="w", padx=8, pady=6)
        row += 1

        # Regimen
        ctk.CTkLabel(scroll, text="Regimen").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._regimen_var = ctk.StringVar(value="resico")
        ctk.CTkOptionMenu(scroll, variable=self._regimen_var,
                          values=["resico", "pfae"]).grid(
            row=row, column=1, columnspan=2, sticky="w", padx=8, pady=6)
        row += 1

        # Carpeta de salida
        ctk.CTkLabel(scroll, text="Carpeta de salida").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self._output_var = ctk.StringVar()
        ctk.CTkEntry(scroll, textvariable=self._output_var,
                     placeholder_text="Default: ./results_RFC").grid(
            row=row, column=1, sticky="ew", padx=8, pady=6)
        ctk.CTkButton(scroll, text="Buscar", width=80,
                      command=self._browse_folder).grid(
            row=row, column=2, padx=8, pady=6)
        row += 1

        # Estado del servidor
        self._server_lbl = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=11))
        self._server_lbl.pack(pady=(4, 2))
        self._refresh_server_status()

        # Boton iniciar
        ctk.CTkButton(self, text="Iniciar",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      height=42, command=self._on_start).pack(
            fill="x", padx=8, pady=(4, 8))

        self._on_op_change()

    def _on_op_change(self):
        """Muestra u oculta campos segun la operacion seleccionada."""
        op = self._op_var.get()

        # Despacho solo en full_flow
        if op == "full_flow":
            self._despacho_lbl.grid()
            self._despacho_entry.grid()
        else:
            self._despacho_lbl.grid_remove()
            self._despacho_entry.grid_remove()

        # Timeout y keep_zip solo en CFDI
        if op == "cfdi":
            self._timeout_lbl.grid()
            self._timeout_entry.grid()
            self._keep_zip_chk.grid()
        else:
            self._timeout_lbl.grid_remove()
            self._timeout_entry.grid_remove()
            self._keep_zip_chk.grid_remove()

    def _on_rfc_focusout(self, event=None):
        """Autofill desde perfil guardado al salir del campo RFC."""
        rfc = self._rfc_var.get().strip().upper()
        if not rfc:
            return
        try:
            data    = api_get(f"/cache/profile/{rfc}")
            profile = data.get("profile")
            if profile:
                if profile.get("cer_exists") and not self._cer_var.get():
                    self._cer_var.set(profile.get("cer", ""))
                if profile.get("key_exists") and not self._key_var.get():
                    self._key_var.set(profile.get("key", ""))
                if not self._output_var.get():
                    self._output_var.set(profile.get("output", ""))
        except Exception:
            pass

    def fill_from_profile(self, profile: dict):
        """
        Reconstruye el formulario limpio y rellena con datos del perfil.
        Llamado desde main.py despues de que el tab Descarga ya es visible.
        """
        self._build_form()
        self.update_idletasks()
        try:
            self._rfc_var.set(profile.get("rfc", ""))
            if profile.get("cer_exists"):
                self._cer_var.set(profile.get("cer", ""))
            if profile.get("key_exists"):
                self._key_var.set(profile.get("key", ""))
            self._output_var.set(profile.get("output", ""))
        except Exception:
            pass

    def _refresh_server_status(self):
        if check_server():
            self._server_lbl.configure(
                text="Servidor activo en http://localhost:8000",
                text_color="green")
        else:
            self._server_lbl.configure(
                text="Servidor no disponible — inicia: python3 -m uvicorn api.main:app --reload",
                text_color="orange")

    def _browse_file(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            var.set(path)

    def _browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self._output_var.set(path)

    def _validate(self) -> dict | None:
        errors = []
        rfc      = self._rfc_var.get().strip().upper()
        cer      = self._cer_var.get().strip()
        key      = self._key_var.get().strip()
        password = self._pwd_var.get()
        inicio   = self._date_inicio.get()
        fin      = self._date_fin.get()

        if not rfc:      errors.append("RFC es obligatorio.")
        if not cer:      errors.append("Archivo .cer es obligatorio.")
        elif not Path(cer).exists(): errors.append(f"Archivo .cer no encontrado: {cer}")
        if not key:      errors.append("Archivo .key es obligatorio.")
        elif not Path(key).exists(): errors.append(f"Archivo .key no encontrado: {key}")
        if not password: errors.append("Contrasena es obligatoria.")
        try:
            date.fromisoformat(inicio)
        except ValueError:
            errors.append("Fecha inicio invalida (YYYY-MM-DD).")
        try:
            date.fromisoformat(fin)
        except ValueError:
            errors.append("Fecha fin invalida (YYYY-MM-DD).")

        if errors:
            messagebox.showerror("Errores de validacion", "\n".join(errors))
            return None

        timeout     = int(self._timeout_var.get()) if self._timeout_var.get().isdigit() else 30
        despacho    = self._despacho_var.get().strip() or None
        output      = self._output_var.get().strip() or None

        return {
            "rfc":        rfc,
            "cer_path":   cer,
            "key_path":   key,
            "password":   password,
            "start_date": inicio,
            "end_date":   fin,
            "tipo":       self._tipo_var.get(),
            "despacho":   despacho,
            "output_dir": output,
            "regimen":    self._regimen_var.get(),
            "intervalo":  60,
            "timeout_min":timeout,
            "keep_zip":   self._keep_zip_var.get(),
            "operation":  self._op_var.get(),
        }

    def _on_start(self):
        if not check_server():
            messagebox.showerror(
                "Servidor no disponible",
                "El servidor no esta corriendo.\n\n"
                "Abre otra terminal y ejecuta:\n"
                "python3 -m uvicorn api.main:app --reload"
            )
            return
        params = self._validate()
        if params:
            self._show_progress(params)

    # =======================================================================
    # Pantalla de progreso
    # =======================================================================

    def _show_progress(self, params: dict):
        """Reemplaza el formulario con la pantalla de progreso."""
        self._clear()
        self._showing_progress = True
        self._cancel_flag.clear()

        ctk.CTkLabel(self, text="Procesando...",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(12, 4))

        self._phase_lbl = ctk.CTkLabel(self, text="Conectando con el SAT...",
                                        font=ctk.CTkFont(size=11), text_color="gray")
        self._phase_lbl.pack(pady=(0, 6))

        self._progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self._progress.pack(fill="x", padx=12, pady=(0, 6))
        self._progress.start()

        log_f = ctk.CTkFrame(self)
        log_f.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self._log_box = ctk.CTkTextbox(
            log_f, font=ctk.CTkFont(family="Courier", size=10),
            state="disabled", wrap="word")
        self._log_box.pack(fill="both", expand=True, padx=4, pady=4)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))
        btn_row.columnconfigure((0, 1), weight=1)

        self._cancel_btn = ctk.CTkButton(
            btn_row, text="Cancelar",
            fg_color="gray30", hover_color="gray20",
            command=self._on_cancel)
        self._cancel_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(btn_row, text="Nueva descarga",
                      fg_color="gray40", hover_color="gray30",
                      command=self._build_form).grid(
            row=0, column=1, padx=(4, 0), sticky="ew")

        self._log(f"RFC      : {params['rfc']}")
        self._log(f"Periodo  : {params['start_date']} -> {params['end_date']}")
        self._log(f"Operacion: {params['operation']}")
        self._log("-" * 50)

        threading.Thread(target=self._run, args=(params,), daemon=True).start()
        self._poll_logs()

    def _log(self, msg: str):
        self._log_queue.put(msg)

    def _poll_logs(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._log_box.configure(state="normal")
                self._log_box.insert("end", msg + "\n")
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
        except queue.Empty:
            pass
        if self._showing_progress:
            self.after(100, self._poll_logs)

    def _run(self, params: dict):
        """Ejecuta la operacion en background."""
        try:
            def _iso(d):
                return date.fromisoformat(d.replace("/", "-")).isoformat()

            start_iso = _iso(params["start_date"])
            end_iso   = _iso(params["end_date"])
            op        = params["operation"]

            if op == "full_flow":
                self.after(0, lambda: self._phase_lbl.configure(
                    text="Paso 1/3 — Descargando Metadata de ingresos..."))
                body = {
                    "rfc":        params["rfc"],
                    "cer_path":   params["cer_path"],
                    "key_path":   params["key_path"],
                    "password":   "***",
                    "start_date": start_iso,
                    "end_date":   end_iso,
                    "output_dir": params["output_dir"],
                    "intervalo":  params["intervalo"],
                    "despacho":   params["despacho"],
                    "regimen":    params["regimen"],
                }
                self._log("POST /download/full-flow")
                self._log(json.dumps(body, indent=2))
                body["password"] = params["password"]
                result = api_post("/download/full-flow", body)

            elif op == "metadata":
                self.after(0, lambda: self._phase_lbl.configure(
                    text="Descargando Metadata..."))
                body = {
                    "rfc":        params["rfc"],
                    "cer_path":   params["cer_path"],
                    "key_path":   params["key_path"],
                    "password":   "***",
                    "start_date": start_iso,
                    "end_date":   end_iso,
                    "tipo":       params["tipo"],
                    "output_dir": params["output_dir"],
                    "intervalo":  params["intervalo"],
                }
                self._log("POST /download/metadata")
                self._log(json.dumps(body, indent=2))
                body["password"] = params["password"]
                result = api_post("/download/metadata", body)

            elif op == "cfdi":
                self.after(0, lambda: self._phase_lbl.configure(
                    text="Esperando respuesta del SAT..."))
                body = {
                    "rfc":         params["rfc"],
                    "cer_path":    params["cer_path"],
                    "key_path":    params["key_path"],
                    "password":    "***",
                    "start_date":  start_iso,
                    "end_date":    end_iso,
                    "tipo":        params["tipo"],
                    "output_dir":  params["output_dir"],
                    "intervalo":   params["intervalo"],
                    "timeout_min": params["timeout_min"],
                    "keep_zip":    params["keep_zip"],
                }
                self._log("POST /download/cfdi")
                self._log(json.dumps(body, indent=2))
                body["password"] = params["password"]
                result = api_post("/download/cfdi", body)
            else:
                raise Exception(f"Operacion desconocida: {op}")

            self._log("")
            self._log("=" * 50)
            self._log("COMPLETADO")
            if result.get("excel_path"):
                self._log(f"Excel : {result['excel_path']}")
            if result.get("files_count") is not None:
                self._log(f"Archivos TXT : {result['files_count']}")
            if result.get("xml_files") is not None:
                self._log(f"XMLs  : {result['xml_files']}")
            if result.get("status") == "pending_or_empty":
                self._log("Solicitud en pendientes o sin CFDIs.")
            self._log("=" * 50)

            result["params"] = params
            self.after(0, lambda r=result: self._on_completed(r))

        except Exception as e:
            msg = str(e) or "Error desconocido. Revisa los logs del servidor."
            self._log(f"\nERROR: {msg}")
            self.after(0, lambda m=msg: self._on_error(m))

    def _on_cancel(self):
        self._cancel_flag.set()
        self._cancel_btn.configure(text="Cancelando...", state="disabled")
        self._log("\nCancelando — solicitudes pendientes conservadas.")

    def _on_completed(self, result: dict):
        self._showing_progress = False
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(1.0)
        self._phase_lbl.configure(text="Proceso completado.", text_color="green")
        if self._on_result:
            self._on_result(result)

    def _on_error(self, msg: str):
        self._showing_progress = False
        self._progress.stop()

        # Clasificar el error para dar un mensaje mas claro
        msg_lower = msg.lower()
        if any(k in msg_lower for k in ["contrasena", "password", "fiel", "corrupto", "pkcs"]):
            title    = "Error de FIEL o contrasena"
            friendly = ("No se pudo cargar la FIEL.\n\n"
                        "Verifica que:\n"
                        "  1. La contrasena sea correcta\n"
                        "  2. Los archivos .cer y .key correspondan al mismo RFC\n"
                        "  3. Los archivos no esten corruptos\n\n"
                        f"Detalle: {msg}")
        elif "conectar" in msg_lower or "servidor" in msg_lower:
            title    = "Servidor no disponible"
            friendly = ("No se pudo conectar con el servidor.\n\n"
                        "Asegurate de que uvicorn este corriendo:\n"
                        "python3 -m uvicorn api.main:app --reload")
        else:
            title    = "Error en el proceso"
            friendly = msg or "Error desconocido. Revisa los logs del servidor."

        self._phase_lbl.configure(text=title, text_color="red")
        messagebox.showerror(title, friendly)

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()