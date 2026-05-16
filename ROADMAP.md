# Roadmap

This document tracks the current state of the project and planned improvements.

---

## Status Legend

- ✅ Done
- 🔄 In Progress
- 📋 Planned
- 💡 Idea / Under Consideration

---

## v1.0 — Core CLI (Current)

### Completed ✅

**Download Engine**

- ✅ SAT Web Service v1.5 integration (SOAP)
- ✅ Metadata mode — monthly split, automatic 5004 handling, ZIP cleanup
- ✅ CFDI mode — full range request, active-only filter (`estado_comprobante=Vigente`)
- ✅ Automatic datetime offset bypass — prevents SAT permanent blocking (error 5002)
- ✅ Automatic retry on network failures (up to 3 attempts per operation)
- ✅ Configurable polling interval and optional timeout

**Output Organization**

- ✅ Structured output: `results_RFC/metadata|cfdi/YYYY-MM-DD/`
- ✅ Metadata: TXT files named `YYYY-MM-RFC.txt`, ZIPs deleted after extraction
- ✅ CFDI: XMLs extracted to `YYYY-MM-RFC/`, ZIPs renamed and preserved
- ✅ Overwrite warning when same-day folder already exists

**Pending Requests System**

- ✅ Encrypted `.cache/RFC.pending.enc` — requests registered immediately after SAT acceptance
- ✅ `--pendientes` — view all pending requests across all RFCs
- ✅ `--retomar ID` — resume a specific pending request
- ✅ `--retomar-todas RFC|all` — resume all pending requests sequentially
- ✅ Automatic cleanup: completed / rejected / expired requests removed from pending
- ✅ Cron-ready `--retomar-todas` for unattended automation
- ✅ Default 30-minute timeout for `--retomar` and `--retomar-todas`

**RFC Profile System**

- ✅ Encrypted `.cache/RFC.profile.enc` — stores FIEL paths and configuration
- ✅ Profile auto-saved on successful download (only if files were actually downloaded)
- ✅ Profile auto-loaded in subsequent runs — no need to pass `--cer`/`--key` again
- ✅ `--perfil RFC` — inspect saved profile and verify files exist on disk

**Security**

- ✅ Fernet (AES-128-CBC) encryption for all cache files
- ✅ PBKDF2-SHA256 key derivation using `SAT_CACHE_SALT` from `.env`
- ✅ Password resolution via `SAT_PASSWORD_RFC` env variable (optional, for automation)
- ✅ One password per RFC per session in `--retomar-todas`
- ✅ Password never stored in any file
- ✅ Tamper detection — corrupted cache files reset automatically

**Logging**

- ✅ Timestamped logs to stdout and `sat_descarga.log`
- ✅ Step-by-step descriptive logs for every operation
- ✅ Human-readable summary at the end of each run
- ✅ Metadata summary with totals, monthly breakdown, and top 5 issuers/receivers

**Developer Utilities**

- ✅ `--reveal-cache RFC|all` — inspect encrypted request history
- ✅ `--perfil RFC` — inspect encrypted RFC profile
- ✅ `.env.example` with all documented variables
- ✅ Local `libs/` dependency folder (no virtualenv required)
- ✅ Interactive mode with real-time validation and profile-assisted defaults
- ✅ `--help` with grouped arguments and usage examples

**Excel and Working Paper**

- ✅ `--flujo-completo` — end-to-end flow: Metadata (income + expenses) + Excel generation
- ✅ `excel_generator.py` — generates Papel de Trabajo workbook from downloaded TXT files
- ✅ 6 fixed sheets matching reference format: `ingresos`, `gastos`, `Impuestos`, `Papel de Trabajo`, `INGRESOS YYYY`, `Calculos`
- ✅ Multi-month ranges stack data blocks per month inside each sheet with visual separators
- ✅ Payment complements (tipo P) shown as reference section inside `gastos`, never summed
- ✅ ISR calculation using RESICO table (3 source priority: hardcoded → `.env` → `--tabla-isr`)
- ✅ Despacho name resolution (3 source priority: hardcoded default → `.env` → `--despacho`)
- ✅ `--regimen resico` (default) — PFAE left open with TODO marker
- ✅ `tabla_isr_resico.csv` — static reference table included in repo

**Spec-Driven Documentation**

- ✅ `docs/` folder with contributor onboarding index
- ✅ `docs/foundation/` — product definition, architecture, action plan
- ✅ `docs/specification/` — system modules, user stories, cli-contract, api-contract, ui-spec
- ✅ `docs/process/` — spec rules, llm-workflow, llm-continuity

---

## v1.1 — Project Restructure 🔄

Objective:
Reorganize codebase into segments to support multiple interfaces
without rewriting business logic.

- 🔄 Move existing modules to `core/`
- 🔄 Rename `descarga_masiva.py` to `cli/main.py`
- 🔄 Create `services/` with `download_service.py`, `excel_service.py`, `cache_service.py`
- 🔄 Refactor `cli/main.py` to call `services/` instead of `core/` directly
- 🔄 Update `libs/` path resolution to `parent.parent` pattern in all modules
- 🔄 Verify CLI behavior is identical after restructure

Constraint: No new features during restructure. CLI behavior must remain identical.

---

## v1.2 — Excel Improvements 📋

- 📋 Excel from CFDI XML files (`--excel-desde-cfdi`) using `core/xml_parser.py`
- 📋 Exact IVA, ISR, and IEPS values from XML instead of Metadata estimates
- 📋 IVA carry-forward across months (saldo acumulado)
- 📋 Multi-currency support (currently MXN only)
- 📋 PFAE tax regime — pending accounting team definition
- 📋 Auto-update ISR table from SAT public source when legislation changes

---

## v1.3 — Test Mode and Batch 📋

- 📋 `--test` mode — validates FIEL, password, RFC match, and SAT token without submitting requests
- 📋 `--batch rfcs.txt` — run full flow for a list of RFCs from a file
- 📋 Consolidated summary report across all RFCs at the end

---

## v2.0 — FastAPI 📋

Objective:
Expose `services/` as HTTP endpoints for UI integration and future use.

- 📋 `api/main.py` — FastAPI application
- 📋 `POST /download/metadata` — Metadata download
- 📋 `POST /download/cfdi` — CFDI download with pending management
- 📋 `POST /download/resume/{id}` — resume pending request
- 📋 `POST /download/full-flow` — end-to-end flow
- 📋 `POST /excel/from-metadata` — Excel from TXT files
- 📋 `POST /excel/from-cfdi` — Excel from XML files (requires v1.2)
- 📋 `GET /cache/pending`, `/cache/profile/{rfc}`, `/cache/history/{rfc}`
- 📋 Dependencies installed in shared `libs/` folder

---

## v2.1 — Desktop GUI (CustomTkinter) ✅

Objective:
Provide a graphical interface for non-technical users (accountants).
Calls `api/` via HTTP — same auth layer as any future client.

- ✅ Screen 1 — Configuration: RFC, FIEL file pickers, password, date range, despacho
- ✅ Screen 2 — Progress: live log panel, phase indicator, cancel button
- ✅ Screen 3 — Results: Excel path with open button, pending requests panel
- ✅ RFC profile auto-fill when RFC is entered (via GET /cache/profile/{rfc})
- ✅ Server availability check on startup and before each operation
- ✅ Long-running SAT operations run in background thread
- ✅ TODO markers for auth header (Basic or JWT) when auth is implemented
- ✅ install.sh / install.bat — one-command installation
- ✅ start.sh / start.bat — one-command startup (server + UI)
- 📋 Anti-block semaphore (green/yellow/red) — planned improvement

---

## v2.2 — API Authentication 📋

Objective:
Secure the API with Basic Auth or JWT before exposing it beyond localhost.

- 📋 Decide on auth method: Basic Auth (simpler) or JWT (more secure)
- 📋 Add auth middleware to `api/main.py`
- 📋 Update `ui/main.py` to send auth header (TODO markers already in place)
- 📋 Update `.env.example` with `API_USERNAME`, `API_PASSWORD` or `SECRET_KEY`
- 📋 Update `api-contract.md` with auth requirements

---

## v2.3 — React + Tauri UI 💡

Objective:
Replace CustomTkinter with a modern React UI packaged as a native executable.
Consumes `api/` endpoints instead of calling `services/` directly.

- 💡 React frontend with Chakra UI component library
- 💡 Tauri shell for native macOS `.app` and Windows `.exe`
- 💡 Same 3-screen flow as CustomTkinter — same behavior, modern look
- 💡 No Python installation required for end users

Constraint: Requires stable `api/` before starting.

---

## v3.0 — Advanced Features 💡

- 💡 POO and design patterns applied to `core/` modules
- 💡 Virtual environments replacing shared `libs/`
- 💡 Multi-user support in `api/`
- 💡 Built-in scheduler (`--schedule daily|weekly`)
- 💡 Client authorization flow (email + approval before tax filing)
- 💡 Desktop notification when pending downloads complete

---

## Known Limitations

- The SAT has no sandbox — all requests use real FIEL credentials
- CFDI mode only downloads active received CFDIs — cancelled ones only via Metadata
- SAT processing time: minutes to 72 hours depending on server load
- Date range limited to last 6 years by SAT policy
- Metadata mode has no duplicate restrictions — CFDI uses offset bypass
- IVA and ISR in Excel are estimates from Metadata — exact values require CFDI XML (v1.2)
- PFAE tax regime not implemented — pending accounting team definition
- `services/`, `api/`, and `ui/` segments not yet created (Phase 3 in progress)

---

## Contributing

Pull requests and issues are welcome.
Please open an issue before submitting a large change so we can discuss the approach first.
Read [docs/readme.md](docs/readme.md) for contributor onboarding.
