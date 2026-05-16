# ACTION PLAN — taxcrawler-dm

---

# OBJECTIVE

Define the execution plan based on specification-driven development.

---

# PRINCIPLE

Implementation must follow specification. No development should occur without defined behavior.

---

# PHASE 1 — CORE CLI (COMPLETED)

Objective: Build the download engine and cache system as a single-file CLI.

Completed:

- SAT Web Service v1.5 integration
- Metadata download with monthly split and 5004 handling
- CFDI download with datetime offset bypass (error 5002 prevention)
- Encrypted cache: attempt history, pending requests, RFC profile
- Pending request system with resume capability
- RFC profile auto-save and auto-load
- Descriptive logging to stdout and sat_descarga.log
- Interactive mode with real-time validation
- CLI with grouped arguments and help text

---

# PHASE 2 — EXCEL WORKING PAPER (COMPLETED)

Objective: Generate accounting working papers from downloaded Metadata TXT files.

Completed:

- 6 fixed sheets matching accounting reference format
- Income and expense grouping by month with subtotals
- IVA estimation at 16% of monto
- ISR calculation using RESICO table
- Despacho name resolution (3 priority sources)
- ISR table resolution (3 priority sources)
- --flujo-completo end-to-end command

---

# PHASE 3 — PROJECT RESTRUCTURE (NEXT)

Objective: Reorganize the codebase into segments (core, services, cli, api, ui) to support multiple interfaces without rewriting business logic.

Activities:

- Move existing modules to core/
- Rename descarga_masiva.py to cli/main.py
- Create services/ with download_service.py, excel_service.py, cache_service.py
- Refactor cli/main.py to call services/ instead of core/ directly
- Update all libs/ path resolution to use parent.parent pattern
- Verify CLI behavior is identical after restructure

Constraint: No new features during restructure. CLI behavior must be identical before and after. All existing tests must pass.

---

# PHASE 4 — SERVICE LAYER (PLANNED)

Objective: Define clean function signatures in services/ usable by CLI, API, and UI.

Activities:

- Implement download_service.download_metadata()
- Implement download_service.download_cfdi()
- Implement download_service.full_flow()
- Implement excel_service.generate_from_metadata()
- Implement excel_service.generate_from_cfdi() (requires xml_parser.py)
- Implement cache_service.get_profile()
- Implement cache_service.get_pending()
- Implement cache_service.get_history()

Constraint: Services must not contain business logic. Services must not call sys.exit(). All service functions must have explicit typed parameters.

---

# PHASE 5 — FASTAPI (PLANNED)

Objective: Expose services/ as HTTP endpoints for UI and future integrations.

Activities:

- Create api/main.py with FastAPI app
- Implement routes/download.py
- Implement routes/excel.py
- Implement routes/cache.py
- Add fastapi and uvicorn to libs/ install command
- Define api-contract.md before any implementation

Constraint: No API implementation before api-contract.md is complete. API routes must only call services/ — never core/ directly.

---

# PHASE 6 — CUSTOMTKINTER UI (PLANNED)

Objective: Provide a graphical interface for non-technical users (accountants).

Activities:

- Implement ui/main.py with 3-screen flow
- Screen 1: Configuration (RFC, FIEL, dates, despacho)
- Screen 2: Progress (live log panel, phase indicator, cancel)
- Screen 3: Results (file list, open Excel, pending requests)
- Anti-block semaphore (green/yellow/red based on cache)
- ui/ calls services/ directly without going through api/

Constraint: No UI implementation before ui-spec.md is complete. UI must not contain business logic.

---

# PHASE 7 — EXCEL FROM CFDI XML (PLANNED)

Objective: Generate Excel with exact tax breakdown from downloaded CFDI XML files.

Activities:

- Implement core/xml_parser.py
- Implement excel_service.generate_from_cfdi()
- Add --excel-desde-cfdi to cli/main.py
- Add /excel/from-cfdi route to api/

Constraint: No implementation before accounting team defines exact field mapping. xml_parser.py must support both CFDI 3.3 and 4.0.

---

# PHASE 8 — TEST MODE AND BATCH (PLANNED)

Objective: Validate FIEL without SAT requests and support multi-RFC batch processing.

Activities:

- Implement --test mode in cli/main.py
- Implement --batch rfcs.txt in cli/main.py
- Add corresponding service functions and API routes

---

# PHASE 9 — REACT + TAURI UI (FUTURE)

Objective: Replace CustomTkinter with a modern React UI packaged with Tauri.

Activities:

- Build React frontend consuming api/ endpoints
- Package with Tauri as native executable
- Distribute as macOS .app and Windows .exe

Constraint: Requires stable api/ before starting. CustomTkinter UI remains available during transition.

---

# PHASE 10 — POO AND DESIGN PATTERNS (FUTURE)

Objective: Apply object-oriented design and patterns to core/ modules without breaking existing service contracts.

Activities:

- Define class interfaces without changing function signatures
- Apply patterns where complexity justifies it
- Introduce virtual environments

Constraint: Service function signatures must remain identical. CLI, API, and UI behavior must be unchanged.

---

# EXECUTION RULES

- Specification is the source of truth
- No feature without user story
- No implementation without contract
- No segment skips a layer
- Code in English, comments in Spanish (ASCII only)
- Every user-visible action must produce a log entry

---

# FINAL RULE

Implementation must strictly follow defined system behavior.