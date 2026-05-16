# UI SPEC — taxcrawler-dm (CustomTkinter)

---

# OBJECTIVE

Define the exact screens, components, and interactions for the CustomTkinter desktop UI.

This document is the behavioral contract for ui/main.py.

---

# PRINCIPLE

The UI is a visual wrapper over services/. It has no business logic. It calls services/ functions directly — not through api/.

---

# GENERAL RULES

- Every user action produces a log entry visible in the progress panel
- Long-running operations (SAT polling) run in a background thread
- The UI never blocks while waiting for SAT
- Passwords are never displayed after entry
- The cancel button is always active during SAT operations
- Error messages are shown inline — no modal dialogs for errors

---

# SCREEN FLOW

```
Screen 1: Configuration
    -> user fills form and clicks "Start"
    -> validates inputs
    -> transitions to Screen 2

Screen 2: Progress
    -> shows live log panel
    -> shows phase indicator
    -> cancel button active
    -> on completion: shows "View Results" button
    -> on completion: transitions to Screen 3

Screen 3: Results
    -> shows downloaded files list
    -> shows Excel path with "Open" button
    -> shows pending requests if any
    -> "New Download" button returns to Screen 1
```

---

# SCREEN 1 — CONFIGURATION

## Purpose

Collect all parameters needed for a download operation.

## Components

### RFC Field

- Label: "RFC"
- Input: text entry, uppercase enforced
- Validation: required, non-empty
- Auto-fill: if profile exists for entered RFC, fill remaining fields automatically

### FIEL .cer Field

- Label: ".cer (e.firma)"
- Input: text entry + "Browse" button
- Browse: opens file dialog filtered to .cer files
- Validation: required, file must exist on disk
- Auto-fill: from RFC profile if available

### FIEL .key Field

- Label: ".key (e.firma)"
- Input: text entry + "Browse" button
- Browse: opens file dialog filtered to .key files
- Validation: required, file must exist on disk
- Auto-fill: from RFC profile if available

### Password Field

- Label: "Contrasena FIEL"
- Input: password entry (masked)
- Validation: required, non-empty
- Never stored, never logged

### Start Date Field

- Label: "Fecha inicio"
- Input: text entry, format YYYY-MM-DD
- Validation: required, valid date, within last 6 years

### End Date Field

- Label: "Fecha fin"
- Input: text entry, format YYYY-MM-DD
- Validation: required, valid date, >= start date

### Operation Selector

- Label: "Operacion"
- Options:
    - Flujo completo (Metadata + Excel) <- default
    - Solo Metadata recibidos
    - Solo Metadata emitidos
    - Solo CFDI recibidos
    - Solo CFDI emitidos

### Despacho Field

- Label: "Nombre del despacho"
- Input: text entry
- Default: value from DESPACHO_NOMBRE env or DEFAULT_DESPACHO constant
- Only shown when operation includes Excel generation

### Anti-block Semaphore

- Shown only when operation is CFDI
- Green: no prior attempts for this RFC + period
- Yellow: 1 prior attempt
- Red: 2+ attempts — bypass offset active
- Reads from cache_service.get_history()

### Output Folder Field

- Label: "Carpeta de salida"
- Input: text entry + "Browse" button
- Default: ./results_RFC based on entered RFC
- Browse: opens folder dialog

### Polling Interval Field

- Label: "Intervalo (seg)"
- Input: numeric entry
- Default: 60
- Minimum: 10

### Timeout Field

- Label: "Timeout (min)"
- Input: numeric entry
- Default: 30
- Optional — leave blank for no limit

### Start Button

- Label: "Iniciar descarga"
- Action: validate all fields, then call appropriate service function
- Disabled while operation is in progress

---

# SCREEN 2 — PROGRESS

## Purpose

Show real-time progress during SAT operations.

## Components

### Phase Indicator

Shows current phase as text and progress bar:

- Phase 1/3: Descargando Metadata ingresos...
- Phase 2/3: Descargando Metadata gastos...
- Phase 3/3: Generando Excel...

### Log Panel

- Scrollable text area
- Receives log entries in real time from logging handler
- New entries auto-scroll to bottom
- Monospace font

### Cancel Button

- Label: "Cancelar"
- Always active during operation
- On click: sends stop signal to background thread
- Shows confirmation message: "Operacion cancelada. Las solicitudes pendientes se conservaron."

### View Results Button

- Hidden during operation
- Shown on successful completion
- Label: "Ver resultados"
- Action: transitions to Screen 3

---

# SCREEN 3 — RESULTS

## Purpose

Show what was downloaded and generated.

## Components

### Downloaded Files List

- Scrollable list
- Shows each file with name, size, and type icon
- Click on file opens it with system default app

### Excel Section

- Shown only if Excel was generated
- Label: "Papel de Trabajo generado"
- File name shown
- "Abrir Excel" button: opens file with system default app

### Pending Requests Panel

- Shown only if there are pending CFDI requests
- List of pending requests with RFC, period, elapsed time
- "Retomar" button per request: calls download_service and transitions to Screen 2

### New Download Button

- Label: "Nueva descarga"
- Action: clears form and transitions to Screen 1
- RFC field pre-filled with last used RFC

---

# INTERACTIONS

## Profile Auto-fill

When user finishes typing RFC and presses Tab:

1. Call cache_service.get_profile(rfc)
2. If profile exists: fill .cer, .key, output_dir, intervalo silently
3. Show status message: "Perfil cargado para RFC {rfc}"
4. Update semaphore based on cache history

## Semaphore Update

Every time RFC or date fields change:

1. Call cache_service.get_history(rfc)
2. Find matching period
3. Update semaphore color accordingly

## Background Thread

Long-running operations run in a separate thread:

1. Main thread: renders UI, responds to user
2. Background thread: calls service function
3. Background thread: posts log entries to log panel via queue
4. Background thread: posts completion event when done
5. Main thread: handles completion event, shows Screen 3

---

# ERROR HANDLING

|Scenario|UI Behavior|
|---|---|
|Required field empty|Red border on field, message below field|
|File not found|Red border, message: "Archivo no encontrado"|
|Invalid date|Red border, message: "Formato invalido. Use YYYY-MM-DD"|
|SAT authentication failure|Log panel shows error, operation stops|
|SAT request rejected|Log panel shows SAT code and message, operation stops|
|Timeout reached|Log panel shows message, pending badge shown, resume button appears|
|Ctrl+C or window close|Pending requests preserved, confirmation dialog shown|

---

# CUSTOMTKINTER IMPLEMENTATION NOTES

- Theme: dark mode by default, system default as fallback
- Font: system default, monospace for log panel
- Window size: 900 x 700 minimum, resizable
- All service calls wrapped in try/except with log entry on error
- Threading: use threading.Thread for background operations
- Queue: use queue.Queue for thread-safe log panel updates

---

# PLANNED UPGRADE

When React + Tauri replaces CustomTkinter:

- ui/main.py is replaced by a React app
- React consumes api/ endpoints instead of calling services/ directly
- CustomTkinter screens map 1:1 to React components
- All behavior defined here remains identical

---

# RELATION TO SPECIFICATION

- Services called: specification/system-modules.md (services/ segment)
- API not used by ui/ in MVP: specification/api-contract.md
- User stories covered: user-stories.md US-GUI-001 to US-GUI-005 (planned)