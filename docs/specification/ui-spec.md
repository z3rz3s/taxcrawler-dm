# UI SPEC — taxcrawler-dm (CustomTkinter)

---

# OBJECTIVE

Define the exact screens, components, and interactions for the CustomTkinter desktop UI.

---

# PRINCIPLE

The UI calls api/ via HTTP using api_client.py.
It has no business logic and no direct access to core/ or services/.
Navigation uses pack/pack_forget — not CTkTabview — to avoid widget overlap.

---

# FILE STRUCTURE

```
ui/
├── main.py           <- window, navigation, server indicator
├── api_client.py     <- api_post, api_get, check_server
├── widgets.py        <- reusable components
├── screen_download.py <- Tab Descarga
└── screen_results.py  <- Tab Resultados
```

---

# WINDOW

- Title: taxcrawler-dm
- Size: 960x792 minimum, resizable
- Theme: dark mode
- Header: title left, server status dot right (green=active, red=unavailable, updates every 10s)
- Navigation: 2 buttons below header (Descarga | Resultados)
  - Active tab: blue button
  - Inactive tab: gray button

---

# NAVIGATION

## Mechanism

pack/pack_forget — both frames always exist, only one is visible at a time.

## Behavior

- App opens on Descarga tab
- Clicking Resultados hides Descarga frame, shows Resultados frame, calls refresh_all()
- Clicking Descarga hides Resultados frame, shows Descarga frame
- Usar perfil in Resultados: calls \_show_tab("descarga") then fill_from_profile()

---

# TAB DESCARGA

## Form mode

### Operation selector

Radio buttons: Flujo completo | Solo Metadata | Solo CFDI

- Flujo completo: shows Despacho field, hides Timeout and keep_zip
- Solo Metadata: hides Despacho, Timeout, keep_zip
- Solo CFDI: hides Despacho, shows Timeout and keep_zip

### RFC field

- Required
- On FocusOut: calls GET /cache/profile/{rfc} and autofills .cer, .key, output if found

### .cer field

- Required, file must exist on disk
- Browse button opens file dialog filtered to \*.cer

### .key field

- Required, file must exist on disk
- Browse button opens file dialog filtered to \*.key

### Password field

- Required, masked (show=\*)

### Date fields (DateWidget)

- Format: YYYY-MM-DD
- Text entry: accepts only digits, auto-inserts dashes after position 4 and 6
- Cal button: opens dark Calendar popup centered on window, click on date confirms

### Tipo

Radio buttons: Recibidos | Emitidos

### Despacho (full_flow only)

- Optional text field
- If empty: API uses DEFAULT_DESPACHO from config

### Timeout in minutes (CFDI only)

- Default: 30

### Keep ZIPs checkbox (CFDI only)

- Default: checked (True)
- If checked: ZIP preserved with unique name (adds \_2, \_3 suffix if name exists)
- If unchecked: ZIP deleted after extraction

### Regimen

Dropdown: resico | pfae

### Output folder

- Optional, Browse button opens folder dialog
- If empty: API uses ./results_RFC

### Server status label

- Green: Servidor activo en http://localhost:8000
- Orange: Servidor no disponible — inicia: python3 -m uvicorn api.main:app --reload

### Iniciar button

- Validates all required fields before calling API
- Shows error dialog listing all validation errors
- If server unavailable: shows error dialog with start instructions

## Progress mode (replaces form)

### Phase label

- Updates per operation step

### Progress bar

- Indeterminate mode during operation
- Determinate (100%) on completion

### Log panel

- Monospace font, scrollable
- Shows: RFC, period, operation, request body (password masked), API response logs
- Updates in real time via queue.Queue from background thread

### Cancelar button

- Always active during operation

### Nueva descarga button

- Always visible, rebuilds form

## Error handling

| Scenario              | Behavior                                                        |
| --------------------- | --------------------------------------------------------------- |
| FIEL / password error | Dialog: "Error de FIEL o contrasena" with 3 verification points |
| Server unavailable    | Dialog with uvicorn start command                               |
| Unknown error         | Dialog with raw error message                                   |

---

# TAB RESULTADOS

## Subtabs: Archivos | Pendientes | Perfiles

Each subtab has:

- Search bar (SearchBar widget) filtering active tab content
- Refresh button reloading data from API

---

## Subtab Archivos

Data source: GET /cache/results (encrypted history, portable between PCs)

### FileCard (Excel)

- Icon: 📊
- File name (bold)
- Short path (monospace, gray)
- Meta: fecha | RFC | operacion
- ⚠ warning if file not found on disk
- Abrir button (disabled if file not found)
- 🗑 button: calls DELETE /cache/results/{id}, refreshes list

### FileCard (folder for XMLs)

- Icon: 📁
- "{count} XMLs descargados"
- Short path
- Meta: fecha | RFC
- Abrir carpeta button (disabled if folder not found)
- 🗑 button: same as above

### FileCard (TXT Metadata)

- Icon: 📋
- Same structure as Excel card

### Search

Filters by: RFC, filename, operacion, fecha (combined into search_key per card)

---

## Subtab Pendientes

Data source: GET /cache/pending

### PendingCard

- 🟡 RFC (bold, orange) + elapsed time (right)
- Period → tipo | solicitud
- Short ID (monospace)
- Retomar button: opens password dialog, then progress window with polling
- Ignorar button: refreshes list (request stays in cache)

### Retomar flow

1. Password dialog (CTkToplevel with grab_set)
2. Progress window with log panel
3. POST /download/resume/{request_id} with password in body
4. On complete: shows xml_files count and output_dir
5. Refreshes pending list

### Search

Filters by RFC

---

## Subtab Perfiles

Data source: GET /cache/profiles (reads all .profile.enc files)

### ProfileCard

- Header (dark): 🏢 RFC + status badge
  - Badge green: ✓ FIEL lista (both .cer and .key exist)
  - Badge orange: ⚠ FIEL incompleta (one or both missing)
- Body: .cer ✓/✗ | .key ✓/✗ | output path | saved date
- Usar perfil button
- Double-click anywhere on card: same as Usar perfil

### Usar perfil behavior

1. \_show_tab("descarga") — switches to Descarga tab
2. fill_from_profile(profile) — rebuilds form and fills RFC, .cer, .key, output

### Search

Filters by RFC

---

# GENERAL RULES

- Every long-running SAT operation runs in a background thread
- Log panel updated via queue.Queue (thread-safe)
- Password never shown, never logged
- Request body logged with password replaced by \*\*\*
- Server availability checked every 10 seconds (header dot)
- On server unavailable before start: error dialog shown, operation blocked

---

# PLANNED UPGRADE

When React + Tauri replaces CustomTkinter:

- ui/ is replaced by React app consuming api/ endpoints
- Same 2-tab structure: Descarga | Resultados
- All behavior in this spec remains identical
- Auth header added to React HTTP client instead of api_client.py

---

# TODO MARKERS IN CODE

- ui/api_client.py: api_post() and api_get() — AUTH_HEADER for Phase 6
