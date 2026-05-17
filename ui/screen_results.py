"""
screen_results.py
-----------------
Tab de resultados con tres subtabs: Archivos, Pendientes, Perfiles.
Llama a api_client.py — no toca core/ ni services/ directamente.
"""

import platform
import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import messagebox

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_libs = _root / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

import customtkinter as ctk

from ui.api_client import api_post, api_get
from ui.widgets import FileCard, PendingCard, ProfileCard, SearchBar


class ResultsTab(ctk.CTkFrame):
    """
    Tab de resultados con subtabs: Archivos | Pendientes | Perfiles.
    on_use_profile(profile): callback para rellenar formulario de descarga.
    """

    def __init__(self, master, on_use_profile=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._use_profile_cb = on_use_profile
        self._last_result: dict = {}

        # Subtabs
        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=4, pady=4)

        self._tab_files    = self._tabview.add("Archivos")
        self._tab_pending  = self._tabview.add("Pendientes")
        self._tab_profiles = self._tabview.add("Perfiles")

        self._build_files_tab()
        self._build_pending_tab()
        self._build_profiles_tab()

    def load_result(self, result: dict):
        """
        Carga un resultado nuevo (de una descarga completada).
        Cambia automaticamente al subtab Archivos.
        """
        self._last_result = result
        self._refresh_files()
        self._tabview.set("Archivos")

    def refresh_all(self):
        """Recarga todos los subtabs."""
        self._refresh_files()
        self._refresh_pending()
        self._refresh_profiles()

    # =======================================================================
    # Tab Archivos
    # =======================================================================

    def _build_files_tab(self):
        tab = self._tab_files

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)

        self._files_search = SearchBar(top, placeholder="Buscar archivo, RFC u operacion...",
                                        on_change=self._filter_files)
        self._files_search.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(top, text="Actualizar", width=100,
                      command=self._refresh_files).grid(row=0, column=1)

        self._files_summary = ctk.CTkLabel(tab, text="",
                                            font=ctk.CTkFont(size=11), text_color="gray")
        self._files_summary.pack(anchor="w", padx=8, pady=(0, 4))

        self._files_frame = ctk.CTkScrollableFrame(tab)
        self._files_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._all_file_cards: list[tuple[str, ctk.CTkFrame]] = []
        self._refresh_files()

    def _refresh_files(self):
        """Recarga la lista de archivos desde GET /cache/results."""
        for w in self._files_frame.winfo_children():
            w.destroy()
        self._all_file_cards.clear()

        try:
            data    = api_get("/cache/results")
            entries = data.get("results", [])
        except Exception as e:
            ctk.CTkLabel(self._files_frame,
                         text=f"Error al cargar historial: {e}",
                         text_color="red").pack(anchor="w", padx=8, pady=8)
            return

        if not entries:
            ctk.CTkLabel(self._files_frame,
                         text="Sin resultados todavia.\nEjecuta una descarga para ver el historial.",
                         font=ctk.CTkFont(size=11), text_color="gray").pack(
                anchor="w", padx=8, pady=16)
            self._files_summary.configure(text="0 entradas en el historial")
            return

        self._files_summary.configure(text=f"{len(entries)} entrada(s) en el historial")

        for entry in entries:
            self._render_history_entry(entry)

    def _render_history_entry(self, entry: dict):
        """Renderiza una entrada del historial como grupo de cards."""
        entry_id  = entry.get("id", "")
        rfc       = entry.get("rfc", "")
        fecha     = entry.get("fecha", "")
        operacion = entry.get("operacion", "")
        excel     = entry.get("excel_path")
        files     = entry.get("files", [])
        xml_count = entry.get("xml_files", 0)

        def _delete_entry(eid=entry_id):
            try:
                import requests
                from ui.api_client import API_BASE
                r = requests.delete(f"{API_BASE}/cache/results/{eid}", timeout=10)
                r.raise_for_status()
                self._refresh_files()
            except Exception as ex:
                from tkinter import messagebox
                messagebox.showerror("Error", f"No se pudo eliminar: {ex}")

        # Card de Excel si existe
        if excel:
            exists = entry.get("excel_exists", False)
            card = FileCard(
                self._files_frame, excel,
                fecha=fecha, operacion=operacion, rfc=rfc,
                file_exists=exists,
                on_open=self._open_file if exists else None,
                on_delete=_delete_entry,
            )
            card.pack(fill="x", pady=3)
            search_key = f"{excel} {rfc} {operacion} {fecha}".lower()
            self._all_file_cards.append((search_key, card))

        # Card de carpeta XML si hay XMLs
        if xml_count > 0 and files:
            xml_files = [f for f in files if f.endswith(".xml")]
            if xml_files:
                folder = str(Path(xml_files[0]).parent)
                folder_card = self._make_folder_card(
                    folder, xml_count, fecha=fecha, rfc=rfc,
                    on_delete=_delete_entry)
                folder_card.pack(fill="x", pady=3)
                search_key = f"{folder} {rfc} {operacion} {fecha}".lower()
                self._all_file_cards.append((search_key, folder_card))

        # Cards de TXTs individuales
        txt_files = [f for f in files if f.endswith(".txt")]
        for filepath in txt_files:
            exists = Path(filepath).exists()
            card = FileCard(
                self._files_frame, filepath,
                fecha=fecha, operacion=operacion, rfc=rfc,
                file_exists=exists,
                on_open=self._open_file if exists else None,
                on_delete=_delete_entry,
            )
            card.pack(fill="x", pady=3)
            search_key = f"{filepath} {rfc} {operacion} {fecha}".lower()
            self._all_file_cards.append((search_key, card))

    def _make_folder_card(self, folder: str, count: int,
                           fecha: str = "", rfc: str = "",
                           on_delete=None) -> ctk.CTkFrame:
        """Card especial para carpeta de XMLs."""
        card = ctk.CTkFrame(self._files_frame, corner_radius=6)
        card.columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="📁",
                     font=ctk.CTkFont(size=20)).grid(
            row=0, column=0, rowspan=2, padx=(12, 8), pady=10, sticky="n")

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=(10, 2))

        ctk.CTkLabel(info, text=f"{count} XMLs descargados",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").pack(anchor="w")

        display = folder if len(folder) <= 72 else "..." + folder[-69:]
        ctk.CTkLabel(info, text=display,
                     font=ctk.CTkFont(family="Courier", size=9),
                     text_color="gray", anchor="w").pack(anchor="w")

        meta_parts = []
        if fecha: meta_parts.append(fecha)
        if rfc:   meta_parts.append(f"RFC: {rfc}")
        if meta_parts:
            ctk.CTkLabel(card, text="  ".join(meta_parts),
                         font=ctk.CTkFont(size=10),
                         text_color="#666666").grid(
                row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))

        btn_col = ctk.CTkFrame(card, fg_color="transparent")
        btn_col.grid(row=0, column=2, rowspan=2, padx=(0, 10), pady=8, sticky="e")

        folder_exists = Path(folder).exists()
        if folder_exists:
            ctk.CTkButton(btn_col, text="Abrir", width=70,
                          command=lambda f=folder: self._open_folder(f)).pack(pady=(0, 4))

        if on_delete:
            ctk.CTkButton(btn_col, text="🗑", width=40,
                          fg_color="gray30", hover_color="#8B0000",
                          command=on_delete).pack()

        return card

    def _filter_files(self, query: str):
        """Filtra las cards por RFC, nombre de archivo, operacion o fecha."""
        query = query.lower()
        for search_key, card in self._all_file_cards:
            if query in search_key:
                card.pack(fill="x", pady=3)
            else:
                card.pack_forget()

    # =======================================================================
    # Tab Pendientes
    # =======================================================================

    def _build_pending_tab(self):
        tab = self._tab_pending

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)

        self._pending_search = SearchBar(top, placeholder="Buscar por RFC...",
                                          on_change=self._filter_pending)
        self._pending_search.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(top, text="Actualizar", width=100,
                      command=self._refresh_pending).grid(row=0, column=1)

        self._pending_summary = ctk.CTkLabel(tab, text="",
                                              font=ctk.CTkFont(size=11), text_color="gray")
        self._pending_summary.pack(anchor="w", padx=8, pady=(0, 4))

        self._pending_frame = ctk.CTkScrollableFrame(tab)
        self._pending_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._all_pending_cards: list[tuple[str, ctk.CTkFrame]] = []
        self._refresh_pending()

    def _refresh_pending(self):
        for w in self._pending_frame.winfo_children():
            w.destroy()
        self._all_pending_cards.clear()

        try:
            data    = api_get("/cache/pending")
            pending = data.get("requests", [])
        except Exception as e:
            ctk.CTkLabel(self._pending_frame,
                         text=f"Error al consultar: {e}",
                         text_color="red").pack(anchor="w", padx=8, pady=8)
            return

        self._pending_summary.configure(
            text=f"{len(pending)} solicitud(es) pendiente(s)")

        if not pending:
            ctk.CTkLabel(self._pending_frame,
                         text="Sin solicitudes pendientes.",
                         font=ctk.CTkFont(size=12),
                         text_color="gray").pack(anchor="w", padx=8, pady=16)
            return

        for req in pending:
            card = PendingCard(
                self._pending_frame, req,
                on_resume=self._on_resume,
                on_ignore=lambda r, f=self._pending_frame: self._on_ignore(r, f),
            )
            card.pack(fill="x", pady=4)
            rfc = req.get("rfc", "")
            self._all_pending_cards.append((rfc, card))

    def _filter_pending(self, query: str):
        query = query.lower()
        for rfc, card in self._all_pending_cards:
            if query in rfc.lower():
                card.pack(fill="x", pady=4)
            else:
                card.pack_forget()

    def _on_resume(self, req: dict):
        """Abre dialogo de contrasena y retoma la solicitud."""
        req_id = req.get("request_id", "")
        rfc    = req.get("rfc", "")

        dialog = ctk.CTkToplevel(self)
        dialog.title("Contrasena FIEL")
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(dialog,
                     text=f"Contrasena de la FIEL para {rfc}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(20, 6))
        ctk.CTkLabel(dialog,
                     text="Requerida para retomar la solicitud pendiente.",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 12))

        pwd_var   = ctk.StringVar()
        pwd_entry = ctk.CTkEntry(dialog, textvariable=pwd_var,
                                  show="*", placeholder_text="Contrasena")
        pwd_entry.pack(fill="x", padx=24, pady=(0, 12))
        pwd_entry.focus()

        def _confirm():
            password = pwd_var.get().strip()
            if not password:
                messagebox.showerror("Error", "La contrasena es obligatoria.", parent=dialog)
                return
            dialog.destroy()
            self._run_resume(req_id, req, password)

        pwd_entry.bind("<Return>", lambda e: _confirm())
        ctk.CTkButton(dialog, text="Retomar", command=_confirm).pack(pady=(0, 16))

    def _run_resume(self, request_id: str, req: dict, password: str):
        """Muestra ventana de progreso y hace polling del request_id via API."""
        win = ctk.CTkToplevel(self)
        win.title("Retomando solicitud")
        win.geometry("600x400")
        win.grab_set()

        ctk.CTkLabel(win, text="Retomando solicitud...",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))

        phase_lbl = ctk.CTkLabel(win, text="Verificando con el SAT...",
                                   font=ctk.CTkFont(size=11), text_color="gray")
        phase_lbl.pack(pady=(0, 6))

        prog = ctk.CTkProgressBar(win, mode="indeterminate")
        prog.pack(fill="x", padx=16, pady=(0, 6))
        prog.start()

        log_f = ctk.CTkFrame(win)
        log_f.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        log_box = ctk.CTkTextbox(log_f, font=ctk.CTkFont(family="Courier", size=10),
                                  state="disabled", wrap="word")
        log_box.pack(fill="both", expand=True, padx=4, pady=4)

        log_q: queue.Queue = queue.Queue()

        def _log(msg: str):
            log_q.put(msg)

        def _poll():
            try:
                while True:
                    msg = log_q.get_nowait()
                    log_box.configure(state="normal")
                    log_box.insert("end", msg + "\n")
                    log_box.see("end")
                    log_box.configure(state="disabled")
            except queue.Empty:
                pass
            if win.winfo_exists():
                win.after(100, _poll)

        def _run():
            try:
                _log(f"RFC     : {req.get('rfc', '?')}")
                _log(f"Periodo : {req.get('inicio', '?')} -> {req.get('fin', '?')}")
                _log(f"ID      : {request_id}")
                _log("-" * 50)
                _log(f"POST /download/resume/{request_id}")

                result = api_post(f"/download/resume/{request_id}", {
                    "timeout_min": 30,
                    "password":    password,
                })

                _log("")
                _log("=" * 50)
                status = result.get("status")
                if status == "completed":
                    _log(f"COMPLETADO — {result.get('xml_files', 0)} XMLs descargados")
                    _log(f"Carpeta: {result.get('output_dir', '')}")
                    win.after(0, lambda: phase_lbl.configure(
                        text="Descarga completada.", text_color="green"))
                elif status == "pending":
                    _log("SAT aun procesando — sigue en pendientes.")
                    win.after(0, lambda: phase_lbl.configure(
                        text="Aun pendiente.", text_color="orange"))
                elif status == "terminal_error":
                    _log(f"ERROR TERMINAL: {result.get('reason', '')}")
                    win.after(0, lambda: phase_lbl.configure(
                        text="Error terminal.", text_color="red"))
                else:
                    _log(f"Estado: {status}")
                _log("=" * 50)

                win.after(0, lambda: prog.stop())
                self._refresh_pending()

            except Exception as e:
                _log(f"\nERROR: {e}")
                win.after(0, lambda: prog.stop())
                win.after(0, lambda: phase_lbl.configure(
                    text="Error.", text_color="red"))

        ctk.CTkButton(win, text="Cerrar",
                      command=win.destroy).pack(pady=(0, 12))

        threading.Thread(target=_run, daemon=True).start()
        _poll()

    def _on_ignore(self, req: dict, frame):
        if messagebox.askyesno(
            "Ignorar solicitud",
            "Se ocultara esta solicitud de la lista.\n"
            "Seguira en el cache y puede retomarse despues.\n\n"
            "Continuar?"
        ):
            self._refresh_pending()

    # =======================================================================
    # Tab Perfiles
    # =======================================================================

    def _build_profiles_tab(self):
        tab = self._tab_profiles

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)

        self._profiles_search = SearchBar(top, placeholder="Buscar por RFC...",
                                           on_change=self._filter_profiles)
        self._profiles_search.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(top, text="Actualizar", width=100,
                      command=self._refresh_profiles).grid(row=0, column=1)

        self._profiles_summary = ctk.CTkLabel(tab, text="",
                                               font=ctk.CTkFont(size=11), text_color="gray")
        self._profiles_summary.pack(anchor="w", padx=8, pady=(0, 4))

        self._profiles_frame = ctk.CTkScrollableFrame(tab)
        self._profiles_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._all_profile_cards: list[tuple[str, ctk.CTkFrame]] = []
        self._refresh_profiles()

    def _refresh_profiles(self):
        for w in self._profiles_frame.winfo_children():
            w.destroy()
        self._all_profile_cards.clear()

        # Usar el endpoint que lee todos los .profile.enc del cache
        try:
            data = api_get("/cache/profiles")
            profiles_found = data.get("profiles", [])
        except Exception as e:
            ctk.CTkLabel(self._profiles_frame,
                         text=f"Error al consultar perfiles: {e}",
                         text_color="red").pack(anchor="w", padx=8, pady=8)
            return

        self._profiles_summary.configure(
            text=f"{len(profiles_found)} perfil(es) encontrado(s)")

        if not profiles_found:
            ctk.CTkLabel(self._profiles_frame,
                         text="No se encontraron perfiles guardados.\n"
                              "Los perfiles se crean al completar una descarga.",
                         font=ctk.CTkFont(size=11), text_color="gray").pack(
                anchor="w", padx=8, pady=16)
            return

        for profile in profiles_found:
            card = ProfileCard(
                self._profiles_frame, profile,
                on_use=self._on_use_profile,
            )
            card.pack(fill="x", pady=4)
            rfc = profile.get("rfc", "")
            self._all_profile_cards.append((rfc, card))

    def _filter_profiles(self, query: str):
        query = query.lower()
        for rfc, card in self._all_profile_cards:
            if query in rfc.lower():
                card.pack(fill="x", pady=4)
            else:
                card.pack_forget()

    def _on_use_profile(self, profile: dict):
        if self._use_profile_cb:
            self._use_profile_cb(profile)

    # =======================================================================
    # Utilidades
    # =======================================================================

    def _open_file(self, path: str):
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", path], check=True)
            elif system == "Windows":
                subprocess.run(["start", path], shell=True, check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir:\n{e}")

    def _open_folder(self, path: str):
        self._open_file(path)