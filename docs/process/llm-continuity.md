# LLM CONTINUITY — taxcrawler-dm

---

# PURPOSE

Quick-start summary for resuming work in a new LLM session.
Read this first, then load the full spec files as needed.

---

# PROJECT IN ONE SENTENCE

taxcrawler-dm is a Python tool that downloads CFDI invoices from the Mexican SAT
Web Service and generates accounting working papers (Papel de Trabajo) in Excel format,
accessible via CLI, REST API, and desktop GUI sharing the same core business logic.

---

# CURRENT STATE

Phase 1 COMPLETED: Core CLI — download engine, cache, pending requests, RFC profile
Phase 2 COMPLETED: Excel working paper with 6 fixed sheets from Metadata TXT files
Phase 3 COMPLETED: Project restructure into core/, services/, cli/, api/, ui/ segments
Phase 4 COMPLETED: FastAPI — all endpoints working and tested locally
Phase 5 COMPLETED: CustomTkinter UI — multi-component desktop app calling API via HTTP
Phase 6 NEXT: Auth (Basic or JWT) — add authorization header to API and UI client

---

# FOLDER STRUCTURE (CURRENT)

```
taxcrawler-dm/
├── libs/                  <- all dependencies (shared, like node_modules)
├── core/                  <- business logic, no interface dependency
│   ├── config.py          <- CACHE_DIR = parent.parent / ".cache" (project root)
│   ├── sat_client.py
│   ├── cache_manager.py   <- includes results history (add/get/remove)
│   ├── file_handler.py    <- extract_cfdi with keep_zip and unique name
│   ├── metadata_parser.py
│   └── excel_generator.py
├── services/              <- flow orchestration
│   ├── download_service.py <- download_metadata, download_cfdi, full_flow, resume_cfdi
│   ├── excel_service.py
│   └── cache_service.py
├── cli/                   <- CLI entry point
│   └── main.py
├── api/                   <- FastAPI
│   ├── main.py
│   └── routes/
│       ├── download.py    <- saves to history on complete; 400 for FIEL errors
│       ├── excel.py
│       └── cache.py       <- GET /cache/profiles, /cache/results, DELETE /cache/results/{id}
├── ui/                    <- CustomTkinter desktop app (5 files)
│   ├── main.py            <- navigation with pack/pack_forget (not CTkTabview)
│   ├── api_client.py      <- api_post, api_get, check_server; TODO: AUTH_HEADER
│   ├── widgets.py         <- DateWidget, SearchBar, FileCard, PendingCard, ProfileCard
│   ├── screen_download.py <- Tab Descarga: form + progress
│   └── screen_results.py  <- Tab Resultados: Archivos | Pendientes | Perfiles
├── docs/
├── tabla_isr.csv
├── .env
├── .env.example
├── CLAUDE.md
├── AGENTS.md
├── .cursor/rules
├── install.sh / install.bat
├── start.sh / start.bat
├── FLOWS.md
├── ROADMAP.md
└── README.md
```

---

# KEY DECISIONS MADE

## Architecture

- core/ contains all business logic — no interface dependency
- services/ orchestrates flows — calls core/ only
- cli/, api/, ui/ call services/ only — never core/ directly
- sys.exit() only in cli/main.py
- All segments resolve libs/ via: \_libs = Path(**file**).resolve().parent.parent / "libs"
- cli/main.py adds \_root to sys.path so `python3 cli/main.py` works directly

## CACHE_DIR

- Always at project root: Path(**file**).resolve().parent.parent / ".cache"
- Never inside core/ — this was a bug that was fixed

## UI Navigation

- Uses pack/pack_forget instead of CTkTabview for main navigation
- CTkTabview caused widget overlap when switching tabs dynamically
- pack_forget removes frame from layout without destroying it
- pack shows it again cleanly — no overlap possible

## UI Components (widgets.py)

- DateWidget: text field with auto-dash insertion + Cal button opening dark Calendar popup
- SearchBar: text field with clear button, calls on_change on every keystroke
- FileCard: shows icon, name, short path, fecha/RFC/operacion meta, Abrir + 🗑 buttons
- PendingCard: shows RFC, period, type, elapsed, Retomar + Ignorar buttons
- ProfileCard: shows RFC, FIEL status badge, output, saved date, Usar perfil button

## Results History

- Stored in .cache/results_history.enc — encrypted with shared Fernet key from SAT_CACHE_SALT
- Portable between PCs with the same SAT_CACHE_SALT
- excel_exists evaluated in real time when loading — not stored
- Max 200 entries, most recent first
- DELETE /cache/results/{id} removes from history without deleting files from disk

## Running the CLI

- Mac/Linux: python3 cli/main.py --help
- Windows: python cli/main.py --help

## Dependencies

- Single libs/ folder at project root shared by all segments
- Install: python3 -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn customtkinter requests tkcalendar --target ./libs --break-system-packages
- uvicorn also installed system-wide: python3 -m pip install uvicorn --break-system-packages

## Security

- SAT_CACHE_SALT always from .env — never hardcoded
- Passwords never stored — resolved from env var or getpass() at runtime
- All .cache/ files encrypted with Fernet AES-128-CBC (PBKDF2-SHA256)
- FIEL errors return HTTP 400 (not 500) — classified by keyword matching

## CFDI

- Datetime offset +1 second per attempt to avoid SAT blocking (error 5002)
- keep_zip parameter: True preserves ZIP with unique name (\_2, \_3...), False deletes it
- Metadata has no request limit — safe to repeat

## Excel

- Always 6 sheets in fixed order
- IVA estimated at 16% of monto until xml_parser.py is implemented (Phase 7)
- ISR retenido fixed at 0.0 until xml_parser.py reads it from XML

## Code conventions

- Code in English
- Comments and docstrings in Spanish (ASCII only — no accents or tildes)

---

# KNOWN LIMITATIONS

- IVA and ISR in Excel are estimates from Metadata — exact values require CFDI XML (Phase 7)
- ISR retenido hardcoded to 0.0
- PFAE regime not implemented
- --acumulado-anual and --excel modes declared but have no effect
- api/ and ui/ have no authentication yet (Phase 6)
- widgets.py exceeds 300 lines — consider splitting when adding new components

---

# WHAT TO DO NEXT — Phase 6: Auth (Basic or JWT)

Steps:

1. Decide on auth method: Basic Auth (simpler) or JWT (more secure)
2. Add auth middleware or decorator to api/main.py
3. Update api_client.py: add AUTH_HEADER to api_post() and api_get() (TODO markers present)
4. Add API_USERNAME, API_PASSWORD or SECRET_KEY to .env.example
5. Update api-contract.md with auth requirements
6. Test all endpoints with and without credentials

Constraint:

- core/ and services/ must have no knowledge of auth
- Auth is handled exclusively in api/ layer
- ui/api_client.py is the only file that needs the auth header

---

# ENVIRONMENT SETUP

```bash
# Install all dependencies
python3 -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn customtkinter requests tkcalendar --target ./libs --break-system-packages
python3 -m pip install uvicorn --break-system-packages

# Configure environment
cp .env.example .env
# Set SAT_CACHE_SALT in .env

# Start server + UI
./start.sh
```

---

# QUICK REFERENCE — CLI COMMANDS

```bash
python3 cli/main.py --rfc RFC --inicio 2025-01-01 --fin 2025-12-31 --flujo-completo --despacho "Firm Name"
python3 cli/main.py --rfc RFC --solicitud Metadata --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31
python3 cli/main.py --rfc RFC --solicitud CFDI --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31 --timeout 30
python3 cli/main.py --pendientes
python3 cli/main.py --retomar ID
python3 cli/main.py --retomar-todas all
python3 cli/main.py --perfil RFC
python3 cli/main.py --reveal-cache RFC
```

---

# SPEC FILES TO LOAD PER TASK

| Task                     | Files to provide                                        |
| ------------------------ | ------------------------------------------------------- |
| Resume after token limit | llm-continuity.md + system-modules.md                   |
| Implement auth (Phase 6) | api-contract.md + system-modules.md (api + ui segments) |
| Fix UI component         | ui-spec.md + system-modules.md (ui segment)             |
| Fix API endpoint         | api-contract.md + system-modules.md (api segment)       |
| xml_parser.py (Phase 7)  | system-modules.md + user-stories.md (US-010)            |
| New CLI argument         | cli-contract.md + user-stories.md                       |
| Excel changes            | system-modules.md (excel_generator) + user-stories.md   |
| Architecture decision    | architecture.md + spec-rules.md                         |
