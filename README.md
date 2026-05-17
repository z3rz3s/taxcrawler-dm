# taxcrawler-dm

A zero-cost, open-source Python tool to bulk-download CFDI (XML invoices) directly from the Mexican Tax Administration Service (SAT) Web Service v1.5 and generate accounting working papers (Papel de Trabajo) — no third-party APIs, no subscriptions, no recurring fees.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Environment Setup](#environment-setup)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode)
  - [CLI Mode — Metadata](#cli-mode--metadata)
  - [CLI Mode — CFDI](#cli-mode--cfdi)
  - [Full End-to-End Flow](#full-end-to-end-flow)
  - [Utility Modes](#utility-modes)
  - [All Arguments](#all-arguments)
- [Output Structure](#output-structure)
- [Excel Working Paper](#excel-working-paper)
- [RFC Profile System](#rfc-profile-system)
- [Encrypted Cache](#encrypted-cache)
- [Duplicate Request Protection](#duplicate-request-protection)
- [Pending Requests System](#pending-requests-system)
- [Logging](#logging)
- [Error Handling](#error-handling)
- [Important SAT Constraints](#important-sat-constraints)
- [Documentation](#documentation)
- [Disclaimer](#disclaimer)

---

## Overview

The SAT provides an official SOAP Web Service (v1.5) that allows registered taxpayers to download their issued and received CFDI in bulk. This project wraps that Web Service into a modular Python CLI tool with:

- Two download modes: **Metadata** (lightweight TXT summary) and **CFDI** (full XML files)
- **Full end-to-end flow** — downloads Metadata for income and expenses, then generates an Excel Papel de Trabajo ready for client review
- Automatic monthly splitting in Metadata mode with graceful continuation on empty months
- Encrypted local cache to prevent permanent SAT period blocking (error 5002)
- Automatic datetime offset bypass — each CFDI request uses a slightly different timestamp to avoid duplicate detection
- RFC profile system — FIEL paths auto-saved after first run, no need to pass `--cer`/`--key` again
- Pending requests system — timeout-safe, resumes where it left off
- Descriptive step-by-step logging to stdout and a persistent log file
- Automatic retries on transient network or SAT service failures
- Fail-fast validation before any SAT call is made

---

## Project Structure

> Phase 3 in progress: codebase is being reorganized into segments.
> Current files live at root. Target structure shown below.

**Current (flat, working):**

```
taxcrawler-dm/
├── descarga_masiva.py     ← CLI entry point (will move to cli/main.py)
├── config.py              ← constants, logging, env, ISR table (will move to core/)
├── cache_manager.py       ← encrypted cache (will move to core/)
├── sat_client.py          ← SAT Web Service (will move to core/)
├── file_handler.py        ← ZIP extraction (will move to core/)
├── metadata_parser.py     ← TXT parsing and filters (will move to core/)
├── excel_generator.py     ← Excel generation (will move to core/)
├── tabla_isr_resico.csv   ← static ISR tax table (RESICO)
├── libs/                  ← all dependencies (shared, like node_modules)
├── .env.example           ← environment variable template
├── FLOWS.md               ← execution flow reference
├── ROADMAP.md             ← project status and planned features
└── docs/                  ← spec-driven documentation
```

**Target (multi-interface):**

```
taxcrawler-dm/
├── libs/                  ← all dependencies (single install, shared by all segments)
├── core/                  ← business logic — no interface dependency
│   ├── config.py
│   ├── sat_client.py
│   ├── cache_manager.py
│   ├── file_handler.py
│   ├── metadata_parser.py
│   └── excel_generator.py
├── services/              ← flow orchestration — calls core/ only
│   ├── download_service.py
│   ├── excel_service.py
│   └── cache_service.py
├── cli/                   ← CLI entry point — calls services/ only
│   └── main.py
├── api/                   ← FastAPI — calls services/ only
│   ├── main.py
│   └── routes/
├── ui/                    ← CustomTkinter desktop app — calls services/ only
│   └── main.py
├── docs/                  ← spec-driven documentation
│   ├── readme.md          ← contributor onboarding index
│   ├── foundation/
│   ├── specification/
│   └── process/
├── tabla_isr_resico.csv
├── .env.example
├── FLOWS.md
└── ROADMAP.md
```

---

## How It Works

The project is split into focused modules. Each module has a single responsibility.

**Download flow (per module):**

```
config.py          → validate SAT_CACHE_SALT, resolve ISR table and despacho name
cache_manager.py   → read RFC profile, check attempt history, register pending request
sat_client.py      → obtain token, submit request, poll SAT, download ZIP packages
file_handler.py    → extract TXT or XML from ZIPs, organize output folders
metadata_parser.py → parse TXT files, filter by type, generate human-readable summary
excel_generator.py → read parsed records, calculate IVA/ISR, write Excel workbook
```

**Metadata mode** processes the date range month by month, skipping months with no CFDIs automatically.

**CFDI mode** submits the full date range as one request, using the encrypted cache to apply an automatic second-offset on every attempt to prevent blocking.

**Full flow** runs Metadata for income and expenses, then generates the Excel in a single command.

---

## Requirements

- Python 3.13 (recommended — tested and verified)
- A valid **FIEL (e.firma)** issued by the SAT:
  - `.cer` — public certificate file
  - `.key` — private key file
  - Password for the private key
- Internet access to reach SAT Web Service endpoints

---

## Installation

### Mac / Linux

```bash
git clone https://github.com/cvaldezscse/taxcrawler-dm.git
cd taxcrawler-dm
chmod +x install.sh start.sh
./install.sh
```

### Windows

```bat
git clone https://github.com/cvaldezscse/taxcrawler-dm.git
cd taxcrawler-dm
install.bat
```

The install script:

- Installs all dependencies into `./libs/` (no virtualenv required, like `node_modules`)
- Installs `uvicorn` system-wide (needed to run the API server)
- Installs `tkinter` via Homebrew on Mac if not available (required for desktop UI)
- Creates `.env` from `.env.example` with an auto-generated `SAT_CACHE_SALT`

> **Windows note:** `SAT_CACHE_SALT` cannot be auto-generated on Windows. After running `install.bat`, open `.env` and set it manually to any long random string.

### Manual installation (any OS)

```bash
python3 -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn customtkinter requests --target ./libs --break-system-packages
python3 -m pip install uvicorn --break-system-packages
cp .env.example .env
# Edit .env and set SAT_CACHE_SALT
```

---

## Environment Setup

The script uses an encrypted cache to protect request history and RFC profiles. The encryption key is derived from an environment variable — never hardcoded.

```bash
cp .env.example .env
```

Edit `.env` and set your values:

```
# Required — salt for cache encryption
SAT_CACHE_SALT=your_long_random_secret_value_here

# Optional — FIEL password per RFC (for cron automation)
SAT_PASSWORD_XAXX010101000=your_fiel_password

# Optional — accounting firm name shown in the Excel header
DESPACHO_NOMBRE=Your Accounting Firm Name

# Optional — path to a custom ISR tax table CSV
TABLA_ISR_PATH=/path/to/custom_tabla_isr.csv
```

To generate a strong random salt:

```bash
openssl rand -base64 32
```

Make sure `.env` is in your `.gitignore` — it should never be committed to the repository. A `.env.example` file is included as a template.

---

## Starting the Application

### Desktop UI + API Server (recommended)

```bash
# Mac/Linux
./start.sh

# Windows
start.bat
```

This starts the API server in the background and opens the desktop UI.

### Other modes

```bash
./start.sh --api    # API server only (access docs at http://localhost:8000/docs)
./start.sh --cli    # CLI interactive mode
```

---

## Usage

### Interactive Mode

Run without arguments. The script prompts for each parameter, validates file paths in real time, hides the FIEL password, and auto-fills values from a saved RFC profile if one exists.

```bash
python descarga_masiva.py
```

### CLI Mode — Metadata

Downloads lightweight TXT summary files, one per month. ZIPs are automatically deleted after extraction. Safe to run repeatedly — no blocking risk.

```bash
python descarga_masiva.py \
  --rfc XAXX010101000 \
  --cer ~/certs/fiel.cer \
  --key ~/certs/fiel.key \
  --inicio 2024-01-01 \
  --fin 2024-12-31 \
  --tipo recibidos \
  --solicitud Metadata \
  --intervalo 30
```

### CLI Mode — CFDI

Downloads full XML files. The encrypted cache automatically applies a datetime offset on each run to prevent SAT permanent blocking.

```bash
python descarga_masiva.py \
  --rfc XAXX010101000 \
  --cer ~/certs/fiel.cer \
  --key ~/certs/fiel.key \
  --inicio 2025-12-01 \
  --fin 2025-12-31 \
  --tipo recibidos \
  --solicitud CFDI \
  --timeout 60 \
  --intervalo 30
```

After the first successful run, `--cer`, `--key`, and `--output` are optional — the script reads them from the saved RFC profile:

```bash
python descarga_masiva.py \
  --rfc XAXX010101000 \
  --inicio 2025-01-01 \
  --fin 2025-06-30
```

### Full End-to-End Flow

Downloads Metadata for both income and expenses, then generates the Excel Papel de Trabajo in a single command. This is the recommended workflow for accountants.

```bash
python descarga_masiva.py \
  --rfc XAXX010101000 \
  --cer ~/certs/fiel.cer \
  --key ~/certs/fiel.key \
  --inicio 2025-01-01 \
  --fin 2025-12-31 \
  --flujo-completo
```

Optional Excel flags:

```bash
# Choose which sheets to generate
--excel resumen     # Papel de Trabajo + Summary + Calculos only
--excel detalle     # income/expense/payment sheets per month + Calculos
--excel completo    # everything (default)

# Accounting firm name in the workbook header
--despacho "Your Firm Name"

# Custom ISR tax table CSV
--tabla-isr /path/to/tabla.csv

# Keep a running annual Excel instead of regenerating each time
--acumulado-anual
```

### Utility Modes

```bash
# View all pending requests across all RFCs
python descarga_masiva.py --pendientes

# Resume a specific pending request by ID
python descarga_masiva.py --retomar 3a4341a7-81d6-4830-9210-bf02f46085e0

# Resume all pending requests (one RFC at a time, one password per RFC)
python descarga_masiva.py --retomar-todas all
python descarga_masiva.py --retomar-todas XAXX010101000

# Inspect saved RFC profile
python descarga_masiva.py --perfil XAXX010101000

# Inspect encrypted request history
python descarga_masiva.py --reveal-cache XAXX010101000
python descarga_masiva.py --reveal-cache all
```

### All Arguments

| Argument            | Required    | Default         | Description                                                                  |
| ------------------- | ----------- | --------------- | ---------------------------------------------------------------------------- |
| `--rfc`             | ✔           | —               | RFC of the taxpayer                                                          |
| `--cer`             | ✔ first run | from profile    | Path to the FIEL `.cer` file                                                 |
| `--key`             | ✔ first run | from profile    | Path to the FIEL `.key` file                                                 |
| `--password`        |             | prompt / env    | FIEL password. If omitted, prompted securely or read from `SAT_PASSWORD_RFC` |
| `--inicio`          | ✔           | —               | Start date `YYYY-MM-DD`                                                      |
| `--fin`             | ✔           | —               | End date `YYYY-MM-DD`                                                        |
| `--tipo`            |             | `recibidos`     | `emitidos` or `recibidos`                                                    |
| `--solicitud`       |             | `CFDI`          | `CFDI` (full XML) or `Metadata` (summary TXT)                                |
| `--timeout`         |             | no limit        | Max minutes to wait for SAT response before saving as pending                |
| `--output`          |             | `./results_RFC` | Base output folder                                                           |
| `--intervalo`       |             | `60`            | Seconds between SAT polling attempts (min: 10)                               |
| `--flujo-completo`  |             | —               | Run full end-to-end flow: Metadata (income + expenses) + Excel               |
| `--excel`           |             | `completo`      | `resumen`, `detalle`, or `completo` — controls Excel sheets generated        |
| `--regimen`         |             | `resico`        | Tax regime for ISR calculation (`resico` implemented, `pfae` planned)        |
| `--acumulado-anual` |             | —               | Update a running annual Excel instead of regenerating each time              |
| `--despacho`        |             | env / default   | Accounting firm name shown in the Excel header                               |
| `--tabla-isr`       |             | env / built-in  | Path to a custom ISR tax table CSV                                           |
| `--pendientes`      |             | —               | Show all pending requests                                                    |
| `--retomar`         |             | —               | Resume a pending request by ID                                               |
| `--retomar-todas`   |             | —               | Resume all pending requests for `RFC` or `all`                               |
| `--perfil`          |             | —               | Show saved RFC profile                                                       |
| `--reveal-cache`    |             | —               | Decrypt and display request history for `RFC` or `all`                       |

---

## Output Structure

```
results_XAXX010101000/
├── metadata/
│   └── 2026-04-09/
│       ├── 2025-01-XAXX010101000.txt
│       ├── 2025-02-XAXX010101000.txt
│       └── ...
├── cfdi/
│   └── 2026-04-09/
│       ├── 2025-12-XAXX010101000.zip    ← renamed, preserved
│       └── 2025-12-XAXX010101000/
│           ├── uuid-1.xml
│           └── ...
└── XAXX010101000_2025-01__2025-12.xlsx  ← generated by --flujo-completo

.cache/
├── XAXX010101000.enc            ← encrypted request history
├── XAXX010101000.pending.enc    ← encrypted pending requests
└── XAXX010101000.profile.enc    ← encrypted RFC profile

sat_descarga.log                 ← full execution log
```

---

## Excel Working Paper

The `--flujo-completo` command generates an Excel workbook that replicates the Papel de Trabajo format used by Mexican accounting firms. The workbook is intended to be reviewed and authorized by the client before the accountant files the tax declaration.

The workbook always contains exactly **6 sheets in a fixed order**, matching the reference format. For a single month each sheet contains data for that month only. For a multi-month range each sheet stacks data blocks per month with visual separators.

**Workbook structure:**

| Position | Sheet              | Content                                                                               |
| -------- | ------------------ | ------------------------------------------------------------------------------------- |
| 1        | `ingresos`         | Income CFDIs (tipo I, emisor = RFC) grouped by month with subtotals                   |
| 2        | `gastos`           | Expense CFDIs (tipo I, receptor = RFC) grouped by month + payment complements section |
| 3        | `Impuestos`        | Left: IVA/ISR breakdown per month. Right: cumulative IVA balance                      |
| 4        | `Papel de Trabajo` | ISR section (left) and IVA section (right) per month — client-ready                   |
| 5        | `INGRESOS YYYY`    | Full-year income table. Months with data show real amounts, rest blank                |
| 6        | `Calculos`         | ISR tax table (RESICO regime) with update note                                        |

**Notes:**

- Payment complements (tipo P) appear inside `gastos` as a reference section and are never summed
- Cancelled CFDIs are excluded from all sheets
- IVA is estimated at 16% of monto — exact breakdown requires CFDI XML (planned v1.1)
- ISR is calculated using the RESICO table — PFAE regime planned for v1.1

**ISR tax table resolution order:**

1. Built-in table in `config.py` (extracted from reference workbook, RESICO regime)
2. Environment variable `TABLA_ISR_PATH` pointing to a CSV file
3. CLI argument `--tabla-isr /path/to/tabla.csv`

**Despacho name resolution order:**

1. Default value `TEST_DESPACHO_TEST` (hardcoded in `config.py`)
2. Environment variable `DESPACHO_NOMBRE`
3. CLI argument `--despacho "Your Firm Name"`

**File naming:**

- Single month: `RFC_YYYY-MM.xlsx`
- Date range: `RFC_YYYY-MM__YYYY-MM.xlsx`

---

## RFC Profile System

After the first successful download, the script saves a profile for each RFC at `.cache/RFC.profile.enc`. The profile contains paths to `.cer` and `.key` files, the default output folder, and the default polling interval. The password is **never** stored.

On subsequent runs, `--cer`, `--key`, and `--output` are filled automatically from the profile.

```bash
python descarga_masiva.py --perfil XAXX010101000
```

If the FIEL files are moved or deleted, the script warns and asks for the paths explicitly. The profile is updated automatically on the next successful download.

---

## Encrypted Cache

All files in `.cache/` are encrypted with **Fernet (AES-128-CBC)** using a key derived per RFC via **PBKDF2-SHA256** from `SAT_CACHE_SALT`. This means:

- Files cannot be read without knowing `SAT_CACHE_SALT`
- Each RFC has its own encryption key — one leaked file does not compromise others
- If a file is tampered with manually, the script detects the corruption and resets it

Recommended `.gitignore` entries:

```
.env
.cache/
libs/
results_*/
sat_descarga.log
```

---

## Duplicate Request Protection

The SAT permanently blocks an `RFC + start date + end date + type` combination after 2 identical CFDI requests (error 5002). This script handles it automatically:

- The cache tracks how many times each period has been requested
- Each new CFDI request applies a +1 second offset to the start datetime:
  - Attempt 1: `2025-12-01 00:00:00`
  - Attempt 2: `2025-12-01 00:00:01`
  - Attempt 3: `2025-12-01 00:00:02`
- Since the SAT compares exact datetime values, each request is a technically different period

This protection applies to CFDI mode only. Metadata mode has no duplicate restrictions.

---

## Pending Requests System

CFDI requests are registered as pending immediately after SAT acceptance. This ensures no request is lost even if the process is interrupted.

```
SAT accepts request → saved to RFC.pending.enc
         ↓
Polling with optional --timeout
         ↓
Completed (state 3)  → download + extract → removed from pending
Timeout / Ctrl+C     → stays in pending, resume with --retomar
Rejected (state 5)   → removed from pending
Expired  (state 6)   → removed from pending
```

Automate resumption with a cron job:

```bash
0 * * * * cd /path/to/taxcrawler-dm && python descarga_masiva.py --retomar-todas all
```

---

## Logging

Every step is logged with a timestamp, level, and descriptive message. Logs go simultaneously to stdout and `sat_descarga.log`. The logging system is designed to support future UI integration — the same log calls work in both CLI and GUI contexts.

```
2026-04-09 00:50:42 | INFO     | SAT — DESCARGA MASIVA DE CFDI (XML) | taxcrawler-dm
2026-04-09 00:50:42 | INFO     |   Perfil encontrado para RFC XAXX010101000.
2026-04-09 00:50:42 | INFO     |   Cache: primera solicitud para este periodo.
2026-04-09 00:50:42 | INFO     |   Periodo efectivo : 2025-12-01 00:00:00 -> 2025-12-31 23:59:59
2026-04-09 00:50:43 | INFO     |   Token obtenido. Sesion activa con el SAT.
2026-04-09 00:50:43 | INFO     |   Solicitud aceptada. ID: 3a4341a7-81d6-4830-...
```

---

## Error Handling

| Scenario                                    | Behavior                                                      |
| ------------------------------------------- | ------------------------------------------------------------- |
| `SAT_CACHE_SALT` not defined                | Fail immediately with setup instructions                      |
| Invalid file paths or date ranges           | Fail-fast before any SAT call, list all errors                |
| Date range older than 6 years               | Fail-fast with the exact allowed start date                   |
| Wrong FIEL password or corrupt files        | Clear error message, exit                                     |
| SAT authentication failure                  | Auto-retry up to 3 times with 5s delay                        |
| SAT request rejected (301 — cancelled XMLs) | `estado_comprobante=Vigente` applied automatically            |
| SAT request rejected (5002 — duplicate)     | Prevented by automatic datetime offset bypass                 |
| SAT request rejected (5004 — no CFDIs)      | Metadata: continues to next month. CFDI: exits cleanly        |
| Polling timeout                             | Saves request as pending, exits with `--retomar` instructions |
| Package download failure                    | Retries up to 3 times, skips and continues                    |
| Corrupt ZIP file                            | Logs the issue, skips extraction, continues                   |
| Tampered cache file                         | Detected automatically, cache reset for that RFC              |
| Profile FIEL files moved or deleted         | Warns and asks for `--cer`/`--key` explicitly                 |
| Incorrect password in `--retomar-todas`     | Skips all requests for that RFC, continues with others        |
| `Ctrl+C` interrupt                          | Graceful exit, pending requests preserved                     |
| Unhandled exception                         | Full stack trace in `sat_descarga.log`                        |

---

## Important SAT Constraints

> These are limitations imposed by the SAT Web Service, not by this script.

- **Date range limit:** The SAT only allows downloading CFDI from the last **6 years**.
- **No sandbox:** There is no test environment. All requests use real FIEL credentials.
- **Processing time:** The SAT may take anywhere from a few minutes to 72 hours depending on server load. The script polls automatically and can resume via `--retomar`.
- **Package size:** Each request can return up to 200,000 XML files split across multiple packages.
- **Cancelled received CFDIs:** The SAT does not allow downloading cancelled XMLs in bulk — only Metadata is available for cancelled documents.
- **Metadata has no duplicate restrictions:** You can request the same Metadata period as many times as needed.

---

## Documentation

| File                     | Description                                                                                  |
| ------------------------ | -------------------------------------------------------------------------------------------- |
| [FLOWS.md](FLOWS.md)     | Step-by-step breakdown of every execution flow, module reference, and Excel output reference |
| [ROADMAP.md](ROADMAP.md) | Current status, planned features, and future ideas                                           |
| [docs/](docs/readme.md)  | Spec-driven documentation index for contributors                                             |
| [LICENSE](LICENSE)       | Project license                                                                              |

---

## Disclaimer

This tool consumes the SAT's official Web Service directly. It is your responsibility to use it in compliance with Mexican tax regulations. The authors are not liable for any misuse, data loss, or regulatory issues arising from the use of this script.

---

## License

GNU GPL v3
