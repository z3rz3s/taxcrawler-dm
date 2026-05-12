# ARCHITECTURE — taxcrawler-dm

---

# OBJECTIVE

Define the high-level structure of the system, including modules, responsibilities, and interaction flow.

---

# PRINCIPLE

The system is a single-process CLI tool organized into focused modules.

- Each module has one responsibility
- No module duplicates logic from another
- descarga_masiva.py is the only entry point
- All SAT communication goes through sat_client.py
- All cache operations go through cache_manager.py

---

# MODULE MAP

```
descarga_masiva.py
    |
    |-- config.py              constants, logging, env, ISR table, despacho
    |-- cache_manager.py       encrypted cache: history, pending, profile
    |-- sat_client.py          SAT Web Service: token, request, polling, download
    |-- file_handler.py        ZIP extraction, output folder resolution
    |-- metadata_parser.py     TXT parsing, CFDI filters, monthly periods, summary
    |-- excel_generator.py     Excel workbook: 6 fixed sheets, IVA/ISR calculations
```

---

# MODULE RESPONSIBILITIES

## descarga_masiva.py

- CLI entry point
- Argument parsing
- Flow orchestration
- Calls module functions in defined order
- Never contains business logic

## config.py

- Global constants (SAT states, month names, retry limits)
- Logging setup (stdout + file)
- SAT_CACHE_SALT validation
- ISR table resolution (hardcoded -> env -> CLI)
- Despacho name resolution (hardcoded -> env -> CLI)
- Password resolution (env -> getpass)

## cache_manager.py

- Fernet encryption/decryption for all cache files
- Attempt history per period per RFC (bypass offset)
- Pending requests lifecycle (add, remove, read)
- RFC profile (FIEL paths, output, intervalo)
- Utility display functions (show_pending, show_profile, reveal_history)

## sat_client.py

- FIEL loading and validation
- SAT token acquisition with retry
- Download request submission
- Polling with configurable timeout
- ZIP package download with retry
- No knowledge of cache or filesystem

## file_handler.py

- Output folder creation (results_RFC/metadata|cfdi/YYYY-MM-DD/)
- Metadata ZIP extraction and rename to YYYY-MM-RFC.txt
- ZIP deletion after Metadata extraction
- CFDI ZIP extraction and rename to YYYY-MM-RFC.zip
- CFDI XML extraction to YYYY-MM-RFC/ subfolder

## metadata_parser.py

- TXT file reading and line parsing
- CFDI filtering by type and RFC role:
  ingresos: emisor == RFC, tipo I
  gastos: receptor == RFC, tipo I
  pagos: receptor == RFC, tipo P
- Cancelled CFDI exclusion
- Monthly period generation
- Record grouping by month for Excel
- Human-readable summary generation for logs

## excel_generator.py

- Exactly 6 fixed sheets per workbook
- Sheet 1: ingresos (income CFDIs grouped by month)
- Sheet 2: gastos (expense CFDIs + payment complements)
- Sheet 3: Impuestos (IVA/ISR per month + cumulative IVA balance)
- Sheet 4: Papel de Trabajo (ISR left, IVA right per month)
- Sheet 5: INGRESOS YYYY (full year income table)
- Sheet 6: Calculos (ISR tax table)
- All styles defined as module-level constants
- No business logic — only layout and calculation

---

# DATA FLOW

## Metadata Flow

```
CLI args
  -> validate_params()
  -> resolve_output_dir()       [file_handler]
  -> load_fiel()                [sat_client]
  -> for each month:
       get_token()              [sat_client]
       request_download()       [sat_client]
       verify_raw()             [sat_client]
       download_package()       [sat_client]
       extract_metadata()       [file_handler]
  -> write_profile()            [cache_manager]
  -> generate_metadata_summary()[metadata_parser]
```

## CFDI Flow

```
CLI args
  -> validate_params()
  -> resolve_output_dir()       [file_handler]
  -> load_fiel()                [sat_client]
  -> get_attempt_history()      [cache_manager]
  -> register_attempt()         [cache_manager]
  -> apply_date_offset()        [sat_client]
  -> get_token()                [sat_client]
  -> request_download()         [sat_client]
  -> add_pending()              [cache_manager]
  -> verify_with_timeout()      [sat_client]
  -> download_package()         [sat_client]
  -> extract_cfdi()             [file_handler]
  -> remove_pending()           [cache_manager]
  -> write_profile()            [cache_manager]
```

## Full Flow (--flujo-completo)

```
Metadata emitidos  -> run_metadata()
Metadata recibidos -> run_metadata()
Excel generation   -> generate_excel()   [excel_generator]
                      group_records_by_month() [metadata_parser]
                      _build_month_calcs()
                      6 sheet writers
```

---

# CACHE FILE STRUCTURE

```
.cache/
  RFC.enc          -> attempt history (period | offset | intentos | ultimo)
  RFC.pending.enc  -> pending requests (id -> rfc, tipo, solicitud, inicio, fin, output)
  RFC.profile.enc  -> RFC profile (cer, key, output, intervalo, guardado)
```

All files encrypted with Fernet AES-128-CBC.
Key derived via PBKDF2-SHA256 from SAT_CACHE_SALT + RFC.

---

# OUTPUT STRUCTURE

```
results_RFC/
  metadata/
    YYYY-MM-DD/
      YYYY-MM-RFC.txt
  cfdi/
    YYYY-MM-DD/
      YYYY-MM-RFC.zip
      YYYY-MM-RFC/
        uuid.xml
  RFC_YYYY-MM.xlsx
  RFC_YYYY-MM__YYYY-MM.xlsx
```

---

# DESIGN PRINCIPLES

- Single entry point (descarga_masiva.py)
- Single responsibility per module
- No business logic in CLI layer
- No SAT calls outside sat_client.py
- No cache operations outside cache_manager.py
- Fail-fast validation before any SAT call
- Every user-visible action produces a log entry
- Passwords never stored in any file or cache

---

# RELATION TO SPECIFICATION

Detailed behavior per module is defined in:

- system-modules.md
- cli-contract.md
- user-stories.md
- FLOWS.md
