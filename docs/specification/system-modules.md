# SYSTEM MODULES — taxcrawler-dm

---

# OBJECTIVE

Define all system modules with explicit responsibilities and boundaries.

---

# GENERAL RULE

Each module:

- Has a single responsibility
- Does not duplicate logic from another module
- Does not depend on interface implementation
- sys.exit() is only called from descarga_masiva.py

---

# MODULE DEFINITIONS

## 1. CLI Orchestrator (descarga_masiva.py)

Responsibility:

- Parse CLI arguments
- Validate parameters before any SAT call
- Orchestrate flow by calling module functions in order
- Print final summaries

Must NOT:

- Contain business logic
- Call SAT directly
- Read or write cache files directly
- Parse XML or TXT files

---

## 2. Config (config.py)

Responsibility:

- Define global constants
- Initialize logging (stdout + sat_descarga.log)
- Validate SAT_CACHE_SALT from environment
- Resolve ISR table (hardcoded -> TABLA_ISR_PATH env -> --tabla-isr CLI)
- Resolve despacho name (DEFAULT_DESPACHO -> DESPACHO_NOMBRE env -> --despacho CLI)
- Resolve password (SAT_PASSWORD_RFC env -> getpass)

Constants defined:

- SAT_ESTADOS: dict mapping state codes to descriptions
- MESES_ES: dict mapping month numbers to Spanish names
- MAX_TOKEN_RETRIES: 3
- MAX_DOWNLOAD_RETRIES: 3
- RETRY_PAUSE_SEC: 5
- CACHE_DIR: .cache/ relative to script
- RETOMAR_TIMEOUT_MIN: 30
- DEFAULT_DESPACHO: "TEST_DESPACHO_TEST"
- TABLA_ISR_RESICO_DEFAULT: list of tuples

---

## 3. Cache Manager (cache_manager.py)

Responsibility:

- Encrypt and decrypt all .cache/ files using Fernet AES-128-CBC
- Manage attempt history per period (bypass offset)
- Manage pending requests lifecycle
- Manage RFC profile

Operations:

- \_read_enc(rfc, path) -> dict
- \_write_enc(rfc, path, data) -> None
- get_attempt_history(rfc, start, end, tipo) -> dict
- register_attempt(rfc, start, end, tipo) -> int (offset seconds)
- add_pending(rfc, request_id, params, dt_start, dt_end) -> None
- remove_pending(rfc, request_id, reason) -> None
- read_pending(rfc) -> dict
- read_profile(rfc) -> dict
- write_profile(rfc, cer, key, output, intervalo) -> None
- show_pending() -> None (display utility)
- show_profile(rfc) -> None (display utility)
- reveal_history(rfc_target) -> None (display utility)

Constraint:

- Password must never be stored in any cache file

---

## 4. SAT Client (sat_client.py)

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
- "rechazada": terminal state, remove from pending
- "vencida": terminal state, remove from pending
- None: timeout reached, keep in pending

Constraint:

- No cache operations inside sat_client.py
- No filesystem operations except download_package writing ZIP

---

## 5. File Handler (file_handler.py)

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

## 6. Metadata Parser (metadata_parser.py)

Responsibility:

- Parse TXT files from SAT Metadata format (~ separated)
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
- pagos: rfc_receptor == RFC, tipo == "P" (reference, never summed)

TXT columns (~ separated, 0-indexed):

- 0: UUID
- 1: RfcEmisor
- 2: NombreEmisor
- 3: RfcReceptor
- 4: NombreReceptor
- 6: FechaEmision
- 8: Monto
- 9: EfectoComprobante (tipo: I, E, P, N)
- 10: Estatus

---

## 7. Excel Generator (excel_generator.py)

Responsibility:

- Generate Excel workbook with exactly 6 fixed sheets
- Calculate IVA and ISR per month from Metadata records
- Write all sheets with consistent styles

Operations:

- generate_excel(rfc, start_date, end_date, income_files, expense_files,
  output_dir, isr_table, despacho, regimen, acumulado_anual,
  excel_mode) -> Path

Internal sheet writers (private):

- \_write_ingresos(ws, grouped)
- \_write_gastos(ws, grouped_gastos, grouped_pagos)
- \_write_impuestos(ws, month_calcs)
- \_write_papel(ws, rfc, client_name, despacho, month_calcs)
- \_write_ingresos_historico(ws, rfc, year, month_calcs)
- \_write_calculos(ws, isr_table)

Calculation functions:

- \_lookup_isr(income, tabla) -> dict
- \_build_month_calcs(income_recs, expense_recs, isr_table) -> dict

Sheet order (always fixed):

1. ingresos
2. gastos
3. Impuestos
4. Papel de Trabajo
5. INGRESOS YYYY
6. Calculos

File naming:

- Single month: RFC_YYYY-MM.xlsx
- Range: RFC_YYYY-MM\_\_YYYY-MM.xlsx

Current limitations (TODO):

- IVA estimated at 16% of monto — exact values require XML parser
- ISR retenido fixed at 0.0 — requires XML parser
- PFAE regime not implemented

---

## 8. XML Parser (xml_parser.py) — PLANNED v1.1

Responsibility:

- Read CFDI XML files from disk
- Extract exact tax breakdown per invoice

Fields to extract:

- Version (3.3 or 4.0)
- UUID, Fecha, Serie, Folio
- RFC and name of emisor and receptor
- SubTotal, Descuento, Total
- IVA trasladado 16%, IVA trasladado 0%, IVA retenido
- ISR retenido
- IEPS trasladado
- MetodoPago, FormaPago, Moneda, TipoCambio
- Conceptos (descripcion + importe)

Constraint:

- Must support both CFDI 3.3 and 4.0
- Must not modify XML files on disk

Status: NOT IMPLEMENTED — pending Phase 3
