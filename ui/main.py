"""
ui/main.py
----------
Entry point de la interfaz grafica de taxcrawler-dm.
Ventana principal con 2 tabs:
  Tab 1 — Descarga  : formulario de descarga y progreso
  Tab 2 — Resultados: archivos, pendientes y perfiles

Iniciar:
  Terminal 1: python3 -m uvicorn api.main:app --reload
  Terminal 2: python3 ui/main.py
  O combinado: ./start.sh
"""

import sys
from pathlib import Path
from tkinter import messagebox

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_libs = _root / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

import customtkinter as ctk

from ui.api_client import check_server
from ui.screen_download import DownloadTab
from ui.screen_results import ResultsTab

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TaxCrawlerApp(ctk.CTk):
    """
    Ventana principal de taxcrawler-dm.
    Dos tabs permanentes: Descarga y Resultados.
    """

    def __init__(self):
        super().__init__()
        self.title("taxcrawler-dm")
        self.geometry("960x792")
        self.minsize(840, 704)
        self.resizable(True, True)

        # Header
        header = ctk.CTkFrame(self, height=52, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="taxcrawler-dm",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(
            side="left", padx=20, pady=12)

        self._server_dot = ctk.CTkLabel(header, text="●",
                                         font=ctk.CTkFont(size=14))
        self._server_dot.pack(side="right", padx=(0, 8))
        ctk.CTkLabel(header, text="Servidor:",
                     font=ctk.CTkFont(size=11),
                     text_color="gray").pack(side="right", padx=(20, 4))

        # Navegacion manual — 2 botones de tab + 2 frames independientes
        # Evita el problema de superposicion de CTkTabview
        nav = ctk.CTkFrame(self, height=40, fg_color="#1A1A1A", corner_radius=0)
        nav.pack(fill="x", padx=10, pady=(0, 0))

        self._btn_download = ctk.CTkButton(
            nav, text="Descarga", width=120, height=30,
            corner_radius=6,
            command=lambda: self._show_tab("descarga"))
        self._btn_download.pack(side="left", padx=(8, 4), pady=5)

        self._btn_results = ctk.CTkButton(
            nav, text="Resultados", width=120, height=30,
            corner_radius=6,
            fg_color="gray30", hover_color="gray25",
            command=lambda: self._show_tab("resultados"))
        self._btn_results.pack(side="left", padx=4, pady=5)

        # Contenedor de pantallas
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        # Instanciar screens una sola vez — ambas en el mismo contenedor
        self._download_tab = DownloadTab(
            self._content,
            on_result=self._on_download_result,
        )

        self._results_tab = ResultsTab(
            self._content,
            on_use_profile=self._on_use_profile,
        )

        # Mostrar descarga por defecto
        self._current_tab = None
        self._show_tab("descarga")

        # Verificar servidor periodicamente
        self._check_server()

    def _check_server(self):
        """Actualiza el indicador de servidor cada 10 segundos."""
        if check_server():
            self._server_dot.configure(text="●", text_color="green")
        else:
            self._server_dot.configure(text="●", text_color="red")
        self.after(10_000, self._check_server)

    def _on_download_result(self, result: dict):
        """
        Callback cuando una descarga completa.
        Carga el resultado en el tab Resultados y cambia a el.
        """
        self._results_tab.load_result(result)
        self._tabview.set("Resultados")

    def _show_tab(self, tab: str):
        """
        Muestra el tab indicado y oculta el otro.
        Usa pack/pack_forget para evitar superposicion de widgets.
        """
        if self._current_tab == tab:
            return

        # Ocultar todo
        self._download_tab.pack_forget()
        self._results_tab.pack_forget()

        # Mostrar el tab seleccionado
        if tab == "descarga":
            self._download_tab.pack(fill="both", expand=True)
            self._btn_download.configure(fg_color=["#3B8ED0", "#1F6AA5"])
            self._btn_results.configure(fg_color="gray30")
        else:
            self._results_tab.pack(fill="both", expand=True)
            self._results_tab.refresh_all()
            self._btn_results.configure(fg_color=["#3B8ED0", "#1F6AA5"])
            self._btn_download.configure(fg_color="gray30")

        self._current_tab = tab

    def _on_use_profile(self, profile: dict):
        """
        Rellena el formulario con el perfil y navega al tab Descarga.
        pack/pack_forget garantiza render limpio sin superposicion.
        """
        self._show_tab("descarga")
        self._download_tab.fill_from_profile(profile)


if __name__ == "__main__":
    if not check_server():
        root = ctk.CTk()
        root.withdraw()
        messagebox.showwarning(
            "Servidor no disponible",
            "El servidor de taxcrawler-dm no esta corriendo.\n\n"
            "Abre una terminal y ejecuta:\n"
            "python3 -m uvicorn api.main:app --reload\n\n"
            "Luego vuelve a abrir la aplicacion.\n\n"
            "O usa: ./start.sh"
        )
        root.destroy()
        sys.exit(0)

    app = TaxCrawlerApp()
    app.mainloop()