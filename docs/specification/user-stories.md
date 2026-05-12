# USER STORIES — taxcrawler-dm

---

# OBJECTIVE

Define functional requirements as explicit, testable user stories aligned with spec-driven development.

---

# EPIC 1 — Metadata Download

## US-001 — Download Metadata by Month

As an accountant
I want to download Metadata TXT files for a client RFC
So that I have a summary of invoices without risking CFDI download limits

Acceptance Criteria:

- Date range is automatically split by month
- Months with no CFDIs (SAT code 5004) are skipped without stopping the process
- Each ZIP is deleted after TXT extraction
- TXT file is named YYYY-MM-RFC.txt
- Summary is printed at the end with totals and top issuers
- RFC profile is saved after at least one file is downloaded

Status: COMPLETED
Modules: descarga_masiva.py, sat_client.py, file_handler.py, metadata_parser.py

---

## US-002 — Download Metadata Without Repeating FIEL Paths

As an accountant
I want to run Metadata downloads without specifying --cer and --key every time
So that I can work faster after the first run

Acceptance Criteria:

- RFC profile is saved after first successful download
- Subsequent runs auto-load .cer, .key, and output from profile
- If profile files are missing on disk, script warns and asks explicitly
- Password is never stored in profile

Status: COMPLETED
Modules: cache_manager.py, descarga_masiva.py

---

# EPIC 2 — CFDI Download

## US-003 — Download CFDI XMLs with Blocking Protection

As an accountant
I want to download CFDI XML files for a client RFC
So that I have full invoice evidence without triggering SAT permanent blocking

Acceptance Criteria:

- Each request applies a +1 second offset to the start datetime
- Offset is stored in encrypted cache and incremented per attempt
- Attempt history is displayed with --reveal-cache
- Only active (non-cancelled) received CFDIs are requested (estado_comprobante=Vigente)
- ZIP is renamed to YYYY-MM-RFC.zip and preserved
- XMLs are extracted to YYYY-MM-RFC/ subfolder

Status: COMPLETED
Modules: descarga_masiva.py, sat_client.py, cache_manager.py, file_handler.py

---

## US-004 — Handle SAT Processing Delay

As an accountant
I want the system to save CFDI requests as pending when the SAT takes too long
So that I do not lose the request if I close the terminal

Acceptance Criteria:

- Request is registered in pending immediately after SAT acceptance
- --timeout sets max wait time in minutes
- When timeout is reached, script exits with resume instructions
- Pending requests survive Ctrl+C
- --pendientes shows all pending requests with elapsed time
- --retomar ID resumes a specific request
- --retomar-todas all resumes all pending requests sequentially
- Completed requests are removed from pending automatically
- Rejected (estado 5) and expired (estado 6) requests are removed from pending

Status: COMPLETED
Modules: cache_manager.py, sat_client.py, descarga_masiva.py

---

# EPIC 3 — Cache and Security

## US-005 — Encrypted Cache

As a developer
I want all cache files to be encrypted
So that sensitive RFC and request data cannot be read if the .cache/ folder is compromised

Acceptance Criteria:

- All .cache/ files use Fernet AES-128-CBC encryption
- Key is derived per RFC via PBKDF2-SHA256 from SAT_CACHE_SALT
- SAT_CACHE_SALT is read from .env — never hardcoded
- Script fails with clear instructions if SAT_CACHE_SALT is not defined
- Tampered files are detected and reset automatically

Status: COMPLETED
Modules: cache_manager.py, config.py

---

## US-006 — Inspect Cache Contents

As a developer
I want to inspect the encrypted cache from the command line
So that I can debug attempt history and pending requests

Acceptance Criteria:

- --reveal-cache RFC shows attempt history for that RFC
- --reveal-cache all shows history for all RFCs
- --pendientes shows all pending requests across all RFCs
- --perfil RFC shows saved FIEL paths and configuration
- All display commands require SAT_CACHE_SALT to be set

Status: COMPLETED
Modules: cache_manager.py, descarga_masiva.py

---

# EPIC 4 — Excel Working Paper

## US-007 — Generate Excel from Metadata

As an accountant
I want to generate an Excel working paper from downloaded Metadata
So that I have a Papel de Trabajo ready for client review

Acceptance Criteria:

- Excel contains exactly 6 sheets in fixed order
- Sheet 1 (ingresos): income CFDIs grouped by month with subtotals
- Sheet 2 (gastos): expense CFDIs + payment complements section
- Sheet 3 (Impuestos): IVA/ISR per month + cumulative IVA balance
- Sheet 4 (Papel de Trabajo): ISR left, IVA right per month
- Sheet 5 (INGRESOS YYYY): full year table, blank months shown
- Sheet 6 (Calculos): ISR tax table with update note
- Excel opens without errors or warnings in Microsoft Excel
- Payment complements (tipo P) appear as reference only, never summed
- Cancelled CFDIs are excluded from all sheets

Status: COMPLETED
Modules: excel_generator.py, metadata_parser.py

---

## US-008 — Full End-to-End Flow

As an accountant
I want a single command that downloads Metadata for income and expenses and generates the Excel
So that I can process a client with one command

Acceptance Criteria:

- --flujo-completo downloads Metadata emitidos (ingresos)
- --flujo-completo downloads Metadata recibidos (gastos)
- Excel is generated from both Metadata files
- Despacho name is shown in Excel header
- Command works without --solicitud or --tipo flags
- RFC profile is saved after successful completion

Status: COMPLETED
Modules: descarga_masiva.py, excel_generator.py, metadata_parser.py

---

## US-009 — Configurable Despacho and ISR Table

As an accountant
I want to configure the accounting firm name and ISR table per installation
So that the Excel header and calculations match my firm and current legislation

Acceptance Criteria:

- Despacho name resolved in order: DEFAULT_DESPACHO -> DESPACHO_NOMBRE env -> --despacho CLI
- ISR table resolved in order: built-in -> TABLA_ISR_PATH env -> --tabla-isr CLI
- CSV format: limite_inferior, limite_superior, cuota_fija, tasa
- If CSV file is missing, built-in table is used with a warning

Status: COMPLETED
Modules: config.py, excel_generator.py

---

# EPIC 5 — Planned Features

## US-010 — Generate Excel from CFDI XML Files (PLANNED v1.1)

As an accountant
I want to generate Excel with exact tax breakdown from downloaded CFDI XML files
So that the working paper uses real IVA, ISR, and IEPS values instead of estimates

Acceptance Criteria:

- --excel-desde-cfdi searches for XMLs in results_RFC/cfdi/ first
- If XMLs exist, parse them and generate Excel with exact values
- If no XMLs on disk, check pending requests
- If pending, attempt to resume download
- If SAT not ready, show message and exit
- If no pending and no XMLs, show instructions to run --solicitud CFDI first
- Excel format remains the same 6-sheet structure

Status: PLANNED
Modules: xml_parser.py (new), excel_generator.py (update), descarga_masiva.py (new flow)

---

## US-011 — FIEL Validation Without SAT Request (PLANNED v1.2)

As an accountant
I want to verify that my FIEL credentials are correct before running any download
So that I do not waste time if the password is wrong

Acceptance Criteria:

- --test validates .cer and .key files exist on disk
- --test loads FIEL with provided password
- --test verifies RFC in certificate matches --rfc argument
- --test obtains SAT token (no download request submitted)
- Each step is logged as pass or fail
- No cache writes, no output folder created

Status: PLANNED
Modules: sat_client.py, descarga_masiva.py

---

## US-012 — Batch Processing Multiple RFCs (PLANNED v1.3)

As an accountant
I want to run downloads for multiple client RFCs from a single command
So that I can process all my clients at once

Acceptance Criteria:

- --batch rfcs.txt reads one RFC per line
- Each RFC uses its own profile and cache files
- Summary report at the end shows status per RFC
- One RFC failure does not stop the rest

Status: PLANNED
Modules: descarga_masiva.py

---

## US-013 — PFAE Tax Regime (PLANNED v1.4)

As an accountant
I want to generate Excel with ISR calculation for PFAE regime
So that I can serve clients registered under that regime

Acceptance Criteria:

- --regimen pfae uses PFAE ISR calculation
- PFAE table and formula defined with accounting team
- Excel output remains the same 6-sheet format
- Calculos sheet shows PFAE table when PFAE is selected

Status: PLANNED — pending accounting team definition
Modules: excel_generator.py, config.py
