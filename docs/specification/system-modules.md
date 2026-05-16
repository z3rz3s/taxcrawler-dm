# SYSTEM MODULES — taxcrawler-dm

---

# OBJECTIVE

Define all system modules with explicit responsibilities and boundaries.

---

# GENERAL RULES

- Each module has a single responsibility
- No module duplicates logic from another
- core/ modules have no knowledge of cli/, api/, or ui/
- services/ is the only layer that calls core/ directly
- cli/, api/, and ui/ call services/ only — never core/ directly
- sys.exit() is only called from cli/main.py

---

# SEGMENT: core/

## core/config.py

Responsibility:

- Define global constants
- Initialize logging (stdout + sat_descarga.log)
- Validate SAT_CACHE_SALT from environment
- Resolve ISR table (hardcoded -> TABLA_ISR_PATH env -> explicit path)
- Resolve despacho name (DEFAULT_DESPACHO -> DESPACHO_NOMBRE env -> explicit value)
- Resolve password (SAT_PASSWORD_RFC env -> getpass)

Constants:

- SAT_ESTADOS: dict mapping state codes to descriptions
- MESES_ES: dict mapping month numbers to Spanish names
- MAX_TOKEN_RETRIES: 3
- MAX_DOWNLOAD_RETRIES: 3
- RETRY_PAUSE_SEC: 5
- CACHE_DIR: .cache/ relative to project root
- RETOMAR_TIMEOUT_MIN: 30
- DEFAULT_DESPACHO: "TEST_DESPACHO_TEST"
- TABLA_ISR_RESICO_DEFAULT: list of tuples

---

## core/cache_manager.py

Responsibility:

- Encrypt and decrypt all .cache/ files using Fernet AES-128-CBC
- Manage attempt history per period (bypass offset)
- Manage pending requests lifecycle (add, remove, read)
- Manage RFC profile (FIEL paths, output, intervalo)
- Display utility functions for inspection

Operations:

- _read_enc(rfc, path) -> dict
- _write_enc(rfc, path, data) -> None
- get_attempt_history(rfc, start, end, tipo) -> dict
- register_attempt(rfc, start, end, tipo) -> int
- add_pending(rfc, request_id, params, dt_start, dt_end) -> None
- remove_pending(rfc, request_id, reason) -> None
- read_pending(rfc) -> dict
- read_profile(rfc) -> dict
- write_profile(rfc, cer, key, output, intervalo) -> None
- show_pending() -> None
- show_profile(rfc) -> None
- reveal_history(rfc_target) -> None

Constraint:

- Password must never be stored in any cache file

---

## core/sat_client.py

Responsibility:

- Load and validate FIEL
- Obtain SAT authentication token with retry
- Submit download requests to SAT Web Service
- Poll SAT for request status with configurable timeout
- Download ZIP packages from SAT

Operations:

- load_fiel(cer, key, password) -> Fiel
- get_token(fiel, attempt) -> str
- apply_date_offset(start, end, offset_sec) -> tuple[datetime, datetime]
- request_download(fiel, token, params, dt_start, dt_end) -> str | None
- verify_with_timeout(fiel, request_id, params, timeout_min) -> list[str] | str | None
- verify_raw(fiel, request_id, params) -> dict
- download_package(fiel, package_id, rfc, output_dir, number, total) -> Path | None

Return values for verify_with_timeout:

- list[str]: package IDs when SAT completes (estado 3)
- "rechazada": terminal state
- "vencida": terminal state
- None: timeout reached

Constraint:

- No cache operations inside sat_client.py
- No filesystem operations except download_package writing ZIP

---

## core/file_handler.py

Responsibility:

- Create output folder structure
- Extract Metadata TXT from ZIP and delete ZIP
- Extract CFDI XML from ZIP and rename ZIP

Operations:

- resolve_output_dir(params) -> Path
- resolve_retomar_output_dir(params) -> Path
- extract_metadata(zip_path, dest_name) -> list[Path]
- extract_cfdi(zip_path, dest_name) -> tuple[list[Path], Path | None]

Rules:

- Metadata ZIP deleted after extraction
- CFDI ZIP renamed to YYYY-MM-RFC.zip and preserved
- CFDI XMLs extracted to YYYY-MM-RFC/ subfolder

---

## core/metadata_parser.py

Responsibility:

- Parse TXT files from SAT Metadata format (tilde separated)
- Filter records by CFDI type and RFC role
- Exclude cancelled CFDIs
- Generate monthly periods for download loop
- Group records by month for Excel generation
- Generate human-readable summary for logs

Operations:

- parse_metadata_line(line) -> dict | None
- read_metadata_file(path) -> list[dict]
- filter_ingresos(records, rfc) -> list[dict]
- filter_gastos(records, rfc) -> list[dict]
- filter_pagos(records, rfc) -> list[dict]
- generate_monthly_periods(start, end) -> list[tuple[date, date]]
- group_records_by_month(files, rfc, record_type) -> dict[str, list[dict]]
- generate_metadata_summary(files, params) -> list[str]

Filter rules:

- ingresos: rfc_emisor == RFC, tipo == "I", estatus != "Cancelado"
- gastos: rfc_receptor == RFC, tipo == "I", estatus != "Cancelado"
- pagos: rfc_receptor == RFC, tipo == "P"

---

## core/excel_generator.py

Responsibility:

- Generate Excel workbook with exactly 6 fixed sheets
- Calculate IVA and ISR per month from Metadata records
- Write all sheets with consistent styles

Operations:

- generate_excel(rfc, start_date, end_date, income_files, expense_files, output_dir, isr_table, despacho, regimen, acumulado_anual, excel_mode) -> Path

Sheet order (always fixed):

1. ingresos
2. gastos
3. Impuestos
4. Papel de Trabajo
5. INGRESOS YYYY
6. Calculos

Current limitations:

- IVA estimated at 16% of monto
- ISR retenido fixed at 0.0
- PFAE regime not implemented (TODO)

---

## core/xml_parser.py — PLANNED (Phase 7)

Responsibility:

- Read CFDI XML files from disk
- Extract exact tax breakdown per invoice
- Support CFDI 3.3 and 4.0

Fields to extract:

- Version, UUID, Fecha, Serie, Folio
- RFC and name of emisor and receptor
- SubTotal, Descuento, Total
- IVA trasladado 16%, IVA trasladado 0%, IVA retenido
- ISR retenido, IEPS trasladado
- MetodoPago, FormaPago, Moneda, TipoCambio
- Conceptos (descripcion + importe)

Status: NOT IMPLEMENTED

---

# SEGMENT: services/

## services/download_service.py

Responsibility:

- Orchestrate Metadata and CFDI download flows
- Provide clean function signatures for cli/, api/, and ui/
- Handle pending request registration and profile saving

Operations:

- download_metadata(rfc, cer_path, key_path, password, start_date, end_date, tipo, output_dir, intervalo) -> list[Path]
- download_cfdi(rfc, cer_path, key_path, password, start_date, end_date, tipo, output_dir, intervalo, timeout_min) -> list[Path]
- full_flow(rfc, cer_path, key_path, password, start_date, end_date, output_dir, intervalo, timeout_min, despacho, tabla_isr, regimen) -> Path

Constraint:

- Must not contain business logic
- Must not call sys.exit()
- Must call core/ functions only

---

## services/excel_service.py

Responsibility:

- Orchestrate Excel generation from Metadata or CFDI XML files
- Provide clean function signatures for cli/, api/, and ui/

Operations:

- generate_from_metadata(rfc, start_date, end_date, income_files, expense_files, output_dir, isr_table, despacho, regimen) -> Path
- generate_from_cfdi(rfc, start_date, end_date, xml_dir, output_dir, isr_table, despacho, regimen) -> Path <- PLANNED (Phase 7)

---

## services/cache_service.py

Responsibility:

- Expose cache inspection operations for cli/, api/, and ui/
- Provide clean typed returns instead of raw dicts

Operations:

- get_profile(rfc) -> dict
- get_pending(rfc) -> dict
- get_history(rfc) -> dict
- get_all_pending() -> dict

---

# SEGMENT: cli/

## cli/main.py

Responsibility:

- Parse CLI arguments
- Validate parameters before any service call
- Call services/ functions with resolved parameters
- Print final summaries and exit codes

Constraint:

- Must not call core/ directly
- Must not contain business logic
- sys.exit() is only called here

---

# SEGMENT: api/

## api/main.py

Responsibility:

- Initialize FastAPI application
- Register all routes
- Configure CORS and middleware

## api/routes/download.py

Responsibility:

- Expose download_service operations as HTTP endpoints
- Validate request bodies
- Return structured JSON responses

Endpoints:

- POST /download/metadata
- POST /download/cfdi
- POST /download/full-flow

## api/routes/excel.py

Endpoints:

- POST /excel/from-metadata
- POST /excel/from-cfdi <- PLANNED

## api/routes/cache.py

Endpoints:

- GET /cache/pending
- GET /cache/pending/{rfc}
- GET /cache/profile/{rfc}
- GET /cache/history/{rfc}

Constraint:

- Routes must only call services/ — never core/ directly

---

# SEGMENT: ui/

## ui/main.py

Responsibility:

- Initialize CustomTkinter application
- Render 3 screens
- Call services/ functions on user interaction
- Display logs in real time

Screens:

- Configuration: RFC, FIEL paths, password, date range, despacho
- Progress: live log panel, phase indicator, cancel button
- Results: file list, open Excel button, pending requests panel

Constraint:

- Must not call core/ directly
- Must not contain business logic
- Calls services/ directly (not through api/)