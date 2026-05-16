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
Phase 3 COMPLETED: Project restructure into core/, services/, cli/ segments
Phase 4 COMPLETED: FastAPI — all endpoints working and tested locally
Phase 5 COMPLETED: CustomTkinter UI — 3-screen desktop app calling API via HTTP
Phase 6 NEXT: Auth (Basic or JWT) — add authorization header to API and UI client

---

# FOLDER STRUCTURE (CURRENT)

```
taxcrawler-dm/
├── libs/                  <- all dependencies (shared, like node_modules)
├── core/                  <- business logic, no interface dependency
│   ├── config.py
│   ├── sat_client.py
│   ├── cache_manager.py
│   ├── file_handler.py
│   ├── metadata_parser.py
│   └── excel_generator.py
├── services/              <- flow orchestration, calls core/ only
│   ├── download_service.py
│   ├── excel_service.py
│   └── cache_service.py
├── cli/                   <- CLI entry point, calls services/ only
│   └── main.py
├── api/                   <- FastAPI (empty, next phase)
│   ├── main.py
│   └── routes/
├── ui/                    <- CustomTkinter (empty, future phase)
│   └── main.py
├── docs/
│   ├── readme.md
│   ├── foundation/
│   ├── specification/
│   └── process/
├── tabla_isr.csv
├── .env
├── .env.example
├── CLAUDE.md
├── AGENTS.md
├── .cursor/rules
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
- cli/main.py also adds \_root to sys.path so `python cli/main.py` works directly

## Running the CLI

- Mac/Linux: python3 cli/main.py --help
- Windows: python cli/main.py --help
- Module mode (alternative): python -m cli.main --help

## Dependencies

- Single libs/ folder at project root shared by all segments
- Single install: python -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn --target ./libs --break-system-packages

## Security

- SAT_CACHE_SALT always from .env — never hardcoded
- Passwords never stored — resolved from env var or getpass() at runtime
- All .cache/ files encrypted with Fernet AES-128-CBC (PBKDF2-SHA256)

## CFDI

- Datetime offset +1 second per attempt to avoid SAT blocking (error 5002)
- Metadata has no request limit — safe to repeat

## Excel

- Always 6 sheets in fixed order: ingresos, gastos, Impuestos, Papel de Trabajo, INGRESOS YYYY, Calculos
- IVA estimated at 16% of monto until xml_parser.py is implemented
- ISR retenido fixed at 0.0 until xml_parser.py reads it from XML
- PFAE regime left as TODO

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
- api/ and ui/ segments are empty placeholders

---

# WHAT TO DO NEXT — Phase 6: Auth (Basic or JWT)

Add authorization to the API and update the UI client to send the auth header.

Steps:

1. Decide on auth method: Basic Auth (simpler) or JWT (more secure)
2. Add FastAPI dependency: python-jose (JWT) or use HTTP Basic directly
3. Add auth middleware or decorator to api/main.py
4. Add auth header to api_post() and api_get() in ui/main.py
5. Update .env.example with auth variables (API_USERNAME, API_PASSWORD or SECRET_KEY)
6. Update api-contract.md with auth requirements
7. Test all endpoints with and without credentials

Key notes:

- Auth is only between UI and API (both run locally for MVP)
- core/ and services/ have no knowledge of auth — only api/ layer handles it
- ui/main.py has TODO comments marking where to add the auth header
- TODO markers are in api_post() and api_get() functions

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
SAT_PASSWORD_RFC=<password>                <- optional, avoids password prompt
DESPACHO_NOMBRE=<firm name>               <- optional, shown in Excel header
TABLA_ISR_PATH=<path to CSV>              <- optional, custom ISR table
```

---

# QUICK REFERENCE — CLI COMMANDS

```bash
# Full flow (recommended)
python3 cli/main.py --rfc RFC --inicio 2025-01-01 --fin 2025-12-31 --flujo-completo --despacho "Firm Name"

# Metadata only
python3 cli/main.py --rfc RFC --solicitud Metadata --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31

# CFDI download
python3 cli/main.py --rfc RFC --solicitud CFDI --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31 --timeout 30

# Utilities
python3 cli/main.py --pendientes
python3 cli/main.py --retomar ID
python3 cli/main.py --retomar-todas all
python3 cli/main.py --perfil RFC
python3 cli/main.py --reveal-cache RFC
```

---

# SPEC FILES TO LOAD PER TASK

| Task                     | Files to provide                                                       |
| ------------------------ | ---------------------------------------------------------------------- |
| Resume after token limit | llm-continuity.md + system-modules.md                                  |
| Implement UI             | ui-spec.md + system-modules.md (ui segment)                            |
| Fix API endpoint         | api-contract.md + system-modules.md (api segment)                      |
| xml_parser.py            | system-modules.md (Module 8) + user-stories.md (US-010)                |
| Bug fix in core/         | cli-contract.md + system-modules.md                                    |
| New CLI argument         | cli-contract.md + user-stories.md                                      |
| Excel changes            | system-modules.md (excel_generator) + user-stories.md (US-007, US-008) |
| Architecture decision    | architecture.md + spec-rules.md                                        |
