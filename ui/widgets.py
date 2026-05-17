"""
widgets.py
----------
Componentes reutilizables de la UI de taxcrawler-dm.
"""

import sys
from datetime import date
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_libs = _root / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

import customtkinter as ctk

try:
    from tkcalendar import DateEntry
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False


class DateWidget(ctk.CTkFrame):
    """
    Campo de fecha con escritura directa (auto-inserta guiones) y boton de calendario.
    Formato: YYYY-MM-DD
    """

    def __init__(self, master, default: str = "", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.columnconfigure(0, weight=1)

        self._var   = ctk.StringVar(value=default)
        self._entry = ctk.CTkEntry(self, textvariable=self._var,
                                   placeholder_text="YYYY-MM-DD")
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        if HAS_CALENDAR:
            ctk.CTkButton(self, text="Cal", width=48,
                          command=self._open_calendar).grid(row=0, column=1)

        vcmd = (self._entry.register(self._on_key), "%P", "%d", "%i")
        self._entry._entry.configure(validate="key", validatecommand=vcmd)

    def _on_key(self, new_value: str, action: str, index: str) -> bool:
        if action == "0":
            return True
        char = new_value[int(index)] if int(index) < len(new_value) else ""
        if not char.isdigit():
            return False
        digits_only = new_value.replace("-", "")
        if len(digits_only) > 8:
            return False
        formatted = self._format(digits_only)
        if formatted != new_value:
            self.after_idle(lambda f=formatted: self._set(f))
        return True

    def _format(self, digits: str) -> str:
        if len(digits) <= 4:
            return digits
        elif len(digits) <= 6:
            return digits[:4] + "-" + digits[4:]
        return digits[:4] + "-" + digits[4:6] + "-" + digits[6:8]

    def _set(self, value: str):
        self._var.set(value)
        self._entry._entry.icursor(len(value))

    def _open_calendar(self):
        import tkinter as tk
        from tkcalendar import Calendar as Cal

        current = self._var.get().strip()
        try:
            d = date.fromisoformat(current)
        except ValueError:
            d = date.today()

        popup = tk.Toplevel(self)
        popup.title("Seleccionar fecha")
        popup.resizable(False, False)
        popup.configure(bg="#2B2B2B")
        popup.grab_set()
        popup.lift()
        popup.focus_force()

        # Centrar sobre la ventana padre
        self.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() // 2 - 160
        y = self.winfo_rooty() + self.winfo_height() // 2 - 120
        popup.geometry(f"320x260+{x}+{y}")

        cal = Cal(
            popup,
            selectmode="day",
            year=d.year, month=d.month, day=d.day,
            date_pattern="yyyy-mm-dd",
            background="#1F1F1F",
            foreground="white",
            bordercolor="#3B3B3B",
            headersbackground="#1A1A1A",
            headersforeground="#AAAAAA",
            selectbackground="#1F6AA5",
            selectforeground="white",
            normalbackground="#2B2B2B",
            normalforeground="white",
            weekendbackground="#2B2B2B",
            weekendforeground="#AAAAAA",
            othermonthbackground="#222222",
            othermonthforeground="#555555",
            font=("Arial", 10),
        )
        cal.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        def _confirm():
            self._var.set(cal.get_date())
            popup.destroy()

        btn_f = tk.Frame(popup, bg="#2B2B2B")
        btn_f.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkButton(btn_f, text="Confirmar",
                      command=_confirm).pack(side="right", padx=4)
        ctk.CTkButton(btn_f, text="Cancelar",
                      fg_color="gray30", hover_color="gray20",
                      command=popup.destroy).pack(side="right")

        cal.bind("<<CalendarSelected>>", lambda e: _confirm())

    def get(self) -> str:
        return self._var.get().strip()

    def set(self, value: str):
        self._var.set(value)


class SearchBar(ctk.CTkFrame):
    """
    Barra de busqueda con campo de texto y boton limpiar.
    Llama a on_change(text) cada vez que el usuario escribe.
    """

    def __init__(self, master, placeholder: str = "Buscar...",
                 on_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.columnconfigure(0, weight=1)
        self._on_change = on_change

        self._var = ctk.StringVar()
        self._var.trace_add("write", self._on_write)

        self._entry = ctk.CTkEntry(
            self, textvariable=self._var,
            placeholder_text=placeholder,
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(self, text="✕", width=32,
                      fg_color="gray30", hover_color="gray20",
                      command=self._clear).grid(row=0, column=1)

    def _on_write(self, *_):
        if self._on_change:
            self._on_change(self._var.get())

    def _clear(self):
        self._var.set("")

    def get(self) -> str:
        return self._var.get()


class FileCard(ctk.CTkFrame):
    """
    Tarjeta visual para mostrar un archivo del historial.
    Muestra icono, nombre, fecha, estado de existencia en disco
    y botones Abrir y Eliminar de lista.
    """

    ICONS = {
        ".xlsx": "📊",
        ".xml":  "📄",
        ".txt":  "📋",
        ".zip":  "📦",
    }

    def __init__(self, master, filepath: str, fecha: str = "",
                 operacion: str = "", rfc: str = "",
                 file_exists: bool = True,
                 on_open=None, on_delete=None, **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.columnconfigure(1, weight=1)

        path  = Path(filepath)
        icon  = self.ICONS.get(path.suffix.lower(), "📁")
        color = "white" if file_exists else "#888888"

        # Icono
        ctk.CTkLabel(self, text=icon,
                     font=ctk.CTkFont(size=20)).grid(
            row=0, column=0, rowspan=2, padx=(12, 8), pady=10, sticky="n")

        # Info principal
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 2))

        ctk.CTkLabel(info, text=path.name,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=color, anchor="w").pack(anchor="w")

        # Ruta corta
        display = str(path)
        if len(display) > 72:
            display = "..." + display[-69:]
        ctk.CTkLabel(info, text=display,
                     font=ctk.CTkFont(family="Courier", size=9),
                     text_color="gray", anchor="w").pack(anchor="w")

        # Meta — fecha, RFC, operacion
        meta_parts = []
        if fecha:      meta_parts.append(fecha)
        if rfc:        meta_parts.append(f"RFC: {rfc}")
        if operacion:  meta_parts.append(operacion)
        if meta_parts:
            ctk.CTkLabel(self, text="  ".join(meta_parts),
                         font=ctk.CTkFont(size=10),
                         text_color="#666666").grid(
                row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))

        # Advertencia si no existe en disco
        if not file_exists:
            ctk.CTkLabel(self, text="⚠ Archivo no encontrado en este equipo",
                         font=ctk.CTkFont(size=10),
                         text_color="orange").grid(
                row=2, column=1, sticky="w", padx=(0, 8), pady=(0, 8))

        # Botones
        btn_col = ctk.CTkFrame(self, fg_color="transparent")
        btn_col.grid(row=0, column=2, rowspan=3, padx=(0, 10), pady=8, sticky="e")

        if on_open and file_exists:
            ctk.CTkButton(btn_col, text="Abrir", width=70,
                          command=lambda: on_open(filepath)).pack(pady=(0, 4))

        if on_delete:
            ctk.CTkButton(btn_col, text="🗑", width=40,
                          fg_color="gray30", hover_color="#8B0000",
                          command=on_delete).pack()


class PendingCard(ctk.CTkFrame):
    """
    Tarjeta visual para mostrar una solicitud pendiente.
    Incluye indicador de estado, info del periodo y botones Retomar/Ignorar.
    """

    def __init__(self, master, req: dict,
                 on_resume=None, on_ignore=None, **kwargs):
        super().__init__(master, corner_radius=8, **kwargs)
        self.columnconfigure(0, weight=1)

        # Fila superior — RFC + elapsed
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))
        top.columnconfigure(1, weight=1)

        ctk.CTkLabel(top,
                     text=f"🟡  {req.get('rfc', '?')}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="orange").grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(top,
                     text=req.get("elapsed", ""),
                     font=ctk.CTkFont(size=11),
                     text_color="gray").grid(row=0, column=1, sticky="e")

        # Periodo y tipo
        ctk.CTkLabel(self,
                     text=(f"{req.get('inicio', '?')} → {req.get('fin', '?')}  |  "
                           f"{req.get('tipo', '?')}  |  {req.get('solicitud', '?')}"),
                     font=ctk.CTkFont(size=11),
                     text_color="#AAAAAA").pack(anchor="w", padx=12, pady=(0, 2))

        # ID corto
        req_id = req.get("request_id", "")
        ctk.CTkLabel(self,
                     text=f"ID: {req_id[:24]}{'...' if len(req_id) > 24 else ''}",
                     font=ctk.CTkFont(family="Courier", size=10),
                     text_color="#666666").pack(anchor="w", padx=12, pady=(0, 8))

        # Botones
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        if on_resume:
            ctk.CTkButton(btn_row, text="Retomar", width=100,
                          command=lambda: on_resume(req)).pack(side="left", padx=(0, 8))
        if on_ignore:
            ctk.CTkButton(btn_row, text="Ignorar", width=80,
                          fg_color="gray30", hover_color="gray20",
                          command=lambda: on_ignore(req)).pack(side="left")


class ProfileCard(ctk.CTkFrame):
    """
    Tarjeta visual para mostrar un perfil de RFC guardado.
    Incluye estado de archivos, contorno redondeado y boton Usar perfil.
    """

    def __init__(self, master, profile: dict, on_use=None, **kwargs):
        # Contenedor exterior con borde visible
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", "#3A3A3A")
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)

        rfc      = profile.get("rfc", "?")
        cer_ok   = profile.get("cer_exists", False)
        key_ok   = profile.get("key_exists", False)
        guardado = profile.get("guardado", "?")
        output   = profile.get("output", "?")
        all_ok   = cer_ok and key_ok

        # Header — RFC + badge de estado
        header = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=0)
        header.pack(fill="x", padx=0, pady=(0, 0))
        header.columnconfigure(0, weight=1)

        ctk.CTkLabel(header,
                     text=f"🏢  {rfc}",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 10))

        badge_color = "#1A4A1A" if all_ok else "#4A2A1A"
        badge_text  = "✓ FIEL lista" if all_ok else "⚠ FIEL incompleta"
        badge_fg    = "#4CAF50" if all_ok else "#FF9800"
        badge = ctk.CTkFrame(header, fg_color=badge_color, corner_radius=6)
        badge.grid(row=0, column=1, padx=(0, 12), pady=(10, 8))
        ctk.CTkLabel(badge, text=badge_text,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=badge_fg).pack(padx=8, pady=3)

        # Cuerpo
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(10, 0))

        # Estado archivos
        ctk.CTkLabel(body,
                     text=(f".cer: {'✓' if cer_ok else '✗'}    "
                           f".key: {'✓' if key_ok else '✗'}"),
                     font=ctk.CTkFont(size=11),
                     text_color="#4CAF50" if all_ok else "#FF9800").pack(
            anchor="w", pady=(0, 4))

        # Output
        display_output = output if len(output) <= 58 else "..." + output[-55:]
        ctk.CTkLabel(body,
                     text=f"Salida: {display_output}",
                     font=ctk.CTkFont(size=10),
                     text_color="#888888").pack(anchor="w", pady=(0, 2))

        ctk.CTkLabel(body,
                     text=f"Guardado: {guardado}",
                     font=ctk.CTkFont(size=10),
                     text_color="#888888").pack(anchor="w", pady=(0, 0))

        # Footer — boton
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(10, 12))

        if on_use:
            ctk.CTkButton(footer, text="Usar perfil", width=120,
                          command=lambda p=profile: on_use(p)).pack(side="left")

        # Doble clic en cualquier parte de la card
        if on_use:
            for widget in [self, header, body, footer]:
                widget.bind("<Double-Button-1>", lambda e, p=profile: on_use(p))