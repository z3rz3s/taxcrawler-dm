# LLM CONTINUITY — taxcrawler-dm

---

# PURPOSE

Quick-start summary for resuming work in a new LLM session. Read this first, then load the full spec files as needed.

---

# PROJECT IN ONE SENTENCE

taxcrawler-dm is a Python tool that downloads CFDI invoices from the Mexican SAT Web Service and generates accounting working papers (Papel de Trabajo) in Excel format, accessible via CLI, REST API, and desktop GUI, all sharing the same core business logic.

---

# CURRENT STATE

Phase 1 COMPLETED: Core CLI — download engine, cache, pending requests, RFC profile Phase 2 COMPLETED: Excel working paper with 6 fixed sheets from Metadata TXT files Phase 3 NEXT: Project restructure into core/, services/, cli/, api/, ui/ segments

---

# FOLDER STRUCTURE (TARGET)

```
taxcrawler-dm/
├── libs/                  <- all dependencies (shared, like node_modules)
├── core/                  <- business logic (config, sat_client, cache_manager,
│                             file_handler, metadata_parser, excel_generator)
├── services/              <- flow orchestration (download_service, excel_service,
│                             cache_service)
├── cli/                   <- CLI entry point (main.py, renamed from descarga_masiva.py)
├── api/                   <- FastAPI (main.py + routes/)
├── ui/                    <- CustomTkinter (main.py)
├── docs/                  <- spec-driven documentation
│   ├── readme.md
│   ├── foundation/        <- product-definition, architecture, action-plan
│   ├── specification/     <- system-modules, user-stories, cli-contract,
│   │                         api-contract, ui-spec
│   └── process/           <- spec-rules, llm-workflow, llm-continuity
├── tabla_isr_resico.csv
├── .env
├── .env.example
├── README.md
├── FLOWS.md
└── ROADMAP.md
```

---

# CURRENT FILE LOCATIONS (before restructure)

All files currently live at project root:

- descarga_masiva.py -> will move to cli/main.py
- config.py -> will move to core/config.py
- cache_manager.py -> will move to core/cache_manager.py
- sat_client.py -> will move to core/sat_client.py
- file_handler.py -> will move to core/file_handler.py
- metadata_parser.py -> will move to core/metadata_parser.py
- excel_generator.py -> will move to core/excel_generator.py

---

# KEY DECISIONS MADE

## Architecture

- core/ contains all business logic — no interface dependency
- services/ orchestrates flows — calls core/ only
- cli/, api/, ui/ call services/ only — never core/ directly
- sys.exit() only in cli/main.py

## Dependencies

- Single libs/ folder at project root shared by all segments
- Path resolution: _libs = Path(**file**).resolve().parent.parent / "libs"
- Single pip install command for all dependencies including fastapi and uvicorn

## Security

- SAT_CACHE_SALT always from .env — never hardcoded
- Passwords never stored — resolved from env var or getpass() at runtime
- All .cache/ files encrypted with Fernet AES-128-CBC (PBKDF2-SHA256)

## CFDI

- Datetime offset +1 second per attempt to avoid SAT blocking (error 5002)
- Metadata has no request limit — safe to repeat

## Excel

- Always 6 sheets in fixed order matching accounting reference format
- IVA estimated at 16% of monto until xml_parser.py is implemented
- ISR retenido fixed at 0.0 until xml_parser.py reads it from XML
- PFAE regime left as TODO

## UI

- CustomTkinter as first GUI — functional over aesthetic
- React + Tauri planned as upgrade after logic is stable
- ui/ calls services/ directly — not through api/

## Code conventions

- Code in English
- Comments and docstrings in Spanish (ASCII only — no accents or tildes)

---

# KNOWN LIMITATIONS

- IVA and ISR in Excel are estimates from Metadata, not exact XML values
- ISR retenido hardcoded to 0.0
- PFAE regime not implemented
- --acumulado-anual declared but has no effect
- --excel resumen|detalle|completo declared but all modes generate the same output
- services/, api/, ui/ segments not yet created

---

# WHAT TO DO NEXT (Phase 3)

Restructure without changing behavior:

1. Create core/ folder, move existing modules there
2. Update libs/ path in each file: parent -> parent.parent
3. Create cli/ folder, rename descarga_masiva.py to cli/main.py
4. Update imports in cli/main.py to use core.module_name
5. Verify CLI works identically after restructure
6. Create services/ with empty service files
7. Implement service functions calling core/ functions
8. Refactor cli/main.py to call services/ instead of core/

---

# ENVIRONMENT SETUP

```bash
# Install all dependencies
python -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn --target ./libs --break-system-packages

# Configure environment
cp .env.example .env
# Set SAT_CACHE_SALT in .env
```

Environment variables:

```
SAT_CACHE_SALT=<random 32+ char string>    <- required
SAT_PASSWORD_RFC=<password>                <- optional
DESPACHO_NOMBRE=<firm name>               <- optional
TABLA_ISR_PATH=<path to CSV>              <- optional
```

---

# QUICK REFERENCE — CURRENT CLI COMMANDS

```bash
# Full flow
python descarga_masiva.py --rfc RFC --cer fiel.cer --key fiel.key --password PASS --inicio 2025-01-01 --fin 2025-12-31 --flujo-completo --despacho "FIRM NAME"

# Metadata only
python descarga_masiva.py --rfc RFC --solicitud Metadata --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31

# CFDI download
python descarga_masiva.py --rfc RFC --solicitud CFDI --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31 --timeout 30

# Utilities
python descarga_masiva.py --pendientes
python descarga_masiva.py --retomar ID
python descarga_masiva.py --retomar-todas all
python descarga_masiva.py --perfil RFC
python descarga_masiva.py --reveal-cache RFC
```

---

# SPEC FILES TO LOAD PER TASK

| Task                       | Files to provide                                                       |
| -------------------------- | ---------------------------------------------------------------------- |
| Restructure to core/       | architecture.md + system-modules.md                                    |
| Create services/           | system-modules.md (services segment) + user-stories.md                 |
| Implement FastAPI          | api-contract.md + system-modules.md (api segment)                      |
| Implement CustomTkinter UI | ui-spec.md + system-modules.md (ui segment)                            |
| xml_parser.py              | system-modules.md (Module 8) + user-stories.md (US-010)                |
| Bug fix in core/ module    | cli-contract.md + system-modules.md                                    |
| New CLI argument           | cli-contract.md + user-stories.md                                      |
| Excel changes              | system-modules.md (excel_generator) + user-stories.md (US-007, US-008) |