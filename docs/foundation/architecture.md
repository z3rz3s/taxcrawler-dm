# ARCHITECTURE — taxcrawler-dm

---

# OBJECTIVE

Define the high-level structure of the system including segments, modules, responsibilities, and interaction flow.

---

# PRINCIPLE

The system is organized into independent segments. Each segment has a single entry point and calls the layer below it. No segment skips a layer to call a lower one directly.

```
ui/       -> calls services/ only
api/      -> calls services/ only
cli/      -> calls services/ only
services/ -> calls core/ only
core/     -> no knowledge of ui, api, cli, or services
```

---

# FOLDER STRUCTURE

```
taxcrawler-dm/
├── libs/                       <- all dependencies (single install, shared by all segments)
│
├── core/                       <- business logic, no interface dependency
│   ├── config.py
│   ├── sat_client.py
│   ├── cache_manager.py
│   ├── file_handler.py
│   ├── metadata_parser.py
│   └── excel_generator.py
│
├── services/                   <- flow orchestration, calls core/ functions
│   ├── download_service.py
│   ├── excel_service.py
│   └── cache_service.py
│
├── cli/                        <- CLI entry point, calls services/
│   └── main.py
│
├── api/                        <- FastAPI, calls services/
│   ├── main.py
│   └── routes/
│       ├── download.py
│       ├── excel.py
│       └── cache.py
│
├── ui/                         <- CustomTkinter, calls services/ directly
│   └── main.py
│
├── docs/                       <- spec-driven documentation
│   ├── readme.md
│   ├── foundation/
│   ├── specification/
│   └── process/
│
├── tabla_isr_resico.csv        <- static ISR RESICO table
├── .env                        <- environment variables (not committed)
├── .env.example                <- template
├── README.md                   <- project overview (GitHub-facing)
├── FLOWS.md                    <- execution flow reference
└── ROADMAP.md                  <- project status and plans
```

---

# SEGMENT DEFINITIONS

## core/

Contains all business logic. Has no knowledge of CLI, API, or UI. All functions receive explicit typed parameters — no dict of CLI args. This is the single source of truth for system behavior.

Modules:

- config.py — constants, logging, env validation, ISR table, despacho, password
- sat_client.py — SAT Web Service: token, request, polling, download
- cache_manager.py — encrypted cache: history, pending requests, RFC profile
- file_handler.py — ZIP extraction, output folder resolution
- metadata_parser.py — TXT parsing, CFDI filters, grouping, summary
- excel_generator.py — 6-sheet Excel workbook generation

---

## services/

Orchestrates flows by calling core/ functions in the correct order. Exposes clean function signatures usable by CLI, API, and UI without modification. No business logic — only sequencing and error handling.

Modules:

- download_service.py — download_metadata(), download_cfdi(), full_flow()
- excel_service.py — generate_from_metadata(), generate_from_cfdi()
- cache_service.py — get_profile(), get_pending(), get_history()

---

## cli/

Single entry point for command-line usage. Parses arguments and calls services/. Contains no business logic. Renamed from descarga_masiva.py to cli/main.py for structural consistency.

---

## api/

FastAPI application that exposes services/ as HTTP endpoints. Runs locally as a lightweight server. Consumed by ui/ or any external client. Dependencies installed in libs/ alongside CLI dependencies.

Routes:

- /download/metadata
- /download/cfdi
- /download/full-flow
- /excel/from-metadata
- /excel/from-cfdi
- /cache/pending
- /cache/profile
- /cache/history

---

## ui/

CustomTkinter desktop application. Calls services/ directly — does not go through api/. First visual interface — functional over aesthetic. React + Tauri planned as upgrade in a future phase.

Screens:

- Configuration (RFC, FIEL paths, password, date range)
- Progress (live log panel, phase indicator, cancel button)
- Results (file list, open Excel button, pending requests panel)

---

# DEPENDENCY RESOLUTION

All segments resolve libs/ from the project root:

```python
_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))
```

Files in core/ use parent.parent (two levels up to root). Files in services/, cli/, api/, ui/ use the same pattern.

Single install command for all segments:

```bash
python -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn --target ./libs --break-system-packages
```

---

# DATA FLOW

## CLI Flow

```
cli/main.py
  -> parse arguments
  -> services/download_service.download_metadata()
       -> core/sat_client.get_token()
       -> core/sat_client.request_download()
       -> core/sat_client.verify_raw()
       -> core/sat_client.download_package()
       -> core/file_handler.extract_metadata()
       -> core/cache_manager.write_profile()
  -> services/excel_service.generate_from_metadata()
       -> core/metadata_parser.group_records_by_month()
       -> core/excel_generator.generate_excel()
```

## API Flow

```
api/routes/download.py
  -> validate request body
  -> services/download_service.download_metadata()
       -> (same as CLI flow)
  -> return result
```

## UI Flow

```
ui/main.py
  -> user fills form
  -> services/download_service.download_metadata()
       -> (same as CLI flow)
  -> update progress panel from logs
```

---

# DESIGN PRINCIPLES

- Single entry point per segment (cli/main.py, api/main.py, ui/main.py)
- No business logic outside core/
- No interface logic inside core/
- Services/ is the only caller of core/
- All segments share the same libs/ folder
- Passwords never stored — resolved at runtime
- SAT_CACHE_SALT always from .env
- Every user-visible action produces a log entry

---

# PLANNED UPGRADES (future phases)

- POO and design patterns applied to core/ modules
- React + Tauri replacing CustomTkinter UI
- Virtual environments replacing shared libs/
- Multi-user support in api/

---

# RELATION TO SPECIFICATION

Detailed behavior per module is defined in:

- specification/system-modules.md
- specification/cli-contract.md
- specification/api-contract.md
- specification/ui-spec.md
- specification/user-stories.md