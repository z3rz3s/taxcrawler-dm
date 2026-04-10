# taxcrawler-dm

A zero-cost, open-source Python script to bulk-download CFDI (XML invoices) directly from the Mexican Tax Administration Service (SAT) Web Service v1.5 — no third-party APIs, no subscriptions, no recurring fees.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Environment Setup](#environment-setup)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode)
  - [CLI Mode — Metadata](#cli-mode--metadata)
  - [CLI Mode — CFDI](#cli-mode--cfdi)
  - [Utility Modes](#utility-modes)
  - [All Arguments](#all-arguments)
- [Output Structure](#output-structure)
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

The SAT provides an official SOAP Web Service (v1.5, released May 2025) that allows registered taxpayers to download their issued and received CFDI in bulk. This script wraps that Web Service into a clean, single-file Python tool with:

- Two download modes: **Metadata** (lightweight TXT summary) and **CFDI** (full XML files)
- Automatic monthly splitting in Metadata mode with graceful continuation on empty months
- Encrypted local cache to prevent permanent SAT period blocking (error 5002)
- Automatic datetime offset bypass — each CFDI request uses a slightly different timestamp to avoid duplicate detection
- RFC profile system — FIEL paths auto-saved after first run, no need to pass `--cer`/`--key` again
- Pending requests system — timeout-safe, resumes where it left off
- Descriptive step-by-step logging to stdout and a persistent log file
- Automatic retries on transient network or SAT service failures
- Fail-fast validation before any SAT call is made

---

## How It Works

The script follows the official SAT Web Service flow through independent functions:

```
1. _validar_salt          → Verify SAT_CACHE_SALT env variable is configured
2. validar_parametros     → Validate all inputs before touching the SAT
3. resolver_output        → Create results_RFC/metadata|cfdi/YYYY-MM-DD/
4. cargar_fiel            → Load and verify your FIEL (e.firma) certificate
5. obtener_token          → Authenticate against the SAT, get a session token
6. consultar_historial    → Check encrypted cache for prior attempts (CFDI only)
7. registrar_intento      → Record attempt and calculate datetime offset (CFDI only)
8. agregar_pendiente      → Register request in encrypted pending file (CFDI only)
9. solicitar_descarga     → Submit the download request, receive a request ID
10. verificar_con_timeout → Poll the SAT until ready or timeout reached
11. descargar_paquete     → Download each ZIP package returned by the SAT
12. extraer_metadata      → Extract TXT, rename YYYY-MM-RFC.txt, delete ZIP (Metadata)
    extraer_cfdi          → Extract XMLs, rename ZIP YYYY-MM-RFC.zip, keep it (CFDI)
13. eliminar_pendiente    → Remove from pending on completion or terminal error
14. _escribir_perfil      → Save RFC profile with FIEL paths for future runs
```

**Metadata mode** processes the date range month by month, skipping months with no CFDIs automatically.

**CFDI mode** submits the full date range as one request, using the encrypted cache to apply an automatic second-offset on every attempt to prevent blocking.

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

```bash
# Clone the repository
git clone https://github.com/cvaldezscse/taxcrawler-dm.git
cd taxcrawler-dm

# Install all dependencies into the local libs/ folder (no virtualenv needed)
python3.13 -m pip install cfdiclient openpyxl python-dotenv --target ./libs --break-system-packages
```

The script automatically detects and uses `libs/`. No system-wide installation or virtual environment required.

---

## Environment Setup

The script uses an encrypted cache to protect request history and RFC profiles. The encryption key is derived from an environment variable — never hardcoded.

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` and set your own secret salt:

```
SAT_CACHE_SALT=your_long_random_secret_value_here
```

To generate a strong random value:

```bash
openssl rand -base64 32
```

**Optional — password automation for cron jobs:**

```
SAT_PASSWORD_XAXX010101000=your_fiel_password
```

If defined, the script uses it automatically instead of prompting. The password is never stored in any file — only read from the environment at runtime.

Make sure `.env` is in your `.gitignore` — it should never be committed to the repository. A `.env.example` file is included as a template.

The script will fail with clear setup instructions if `SAT_CACHE_SALT` is not defined.

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

| Argument | Required | Default | Description |
|---|---|---|---|
| `--rfc` | ✔ | — | RFC of the taxpayer |
| `--cer` | ✔ first run | from profile | Path to the FIEL `.cer` file |
| `--key` | ✔ first run | from profile | Path to the FIEL `.key` file |
| `--password` | | prompt / env | FIEL password. If omitted, prompted securely or read from `SAT_PASSWORD_RFC` |
| `--inicio` | ✔ | — | Start date `YYYY-MM-DD` |
| `--fin` | ✔ | — | End date `YYYY-MM-DD` |
| `--tipo` | | `recibidos` | `emitidos` or `recibidos` |
| `--solicitud` | | `CFDI` | `CFDI` (full XML) or `Metadata` (summary TXT) |
| `--timeout` | | no limit | Max minutes to wait for SAT response before saving as pending |
| `--excel` | | — | `resumen`, `detalle`, or `completo` — Excel export (CFDI only, coming soon) |
| `--output` | | `./results_RFC` | Base output folder |
| `--intervalo` | | `60` | Seconds between SAT polling attempts (min: 10) |
| `--pendientes` | | — | Show all pending requests |
| `--retomar` | | — | Resume a pending request by ID |
| `--retomar-todas` | | — | Resume all pending requests for `RFC` or `all` |
| `--perfil` | | — | Show saved RFC profile |
| `--reveal-cache` | | — | Decrypt and display request history for `RFC` or `all` |

---

## Output Structure

```
results_XAXX010101000/
├── metadata/
│   └── 2026-04-09/
│       ├── 2025-01-XAXX010101000.txt
│       ├── 2025-02-XAXX010101000.txt
│       └── ...
└── cfdi/
    └── 2026-04-09/
        ├── 2025-12-XAXX010101000.zip    ← renamed, preserved
        └── 2025-12-XAXX010101000/
            ├── uuid-1.xml
            └── ...

.cache/
├── XAXX010101000.enc            ← encrypted request history
├── XAXX010101000.pending.enc    ← encrypted pending requests
└── XAXX010101000.profile.enc    ← encrypted RFC profile

sat_descarga.log                 ← full execution log
```

If the same date folder already exists, files are overwritten silently with a warning logged.

---

## RFC Profile System

After the first successful download, the script saves a profile for each RFC at `.cache/RFC.profile.enc`. The profile contains:

- Paths to `.cer` and `.key` files
- Default output folder
- Default polling interval
- Date of last save

On subsequent runs, `--cer`, `--key`, and `--output` are filled automatically from the profile. The password is **never** stored.

To inspect a saved profile:

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
- Blocking risk is effectively eliminated for normal usage

This protection applies to CFDI mode only. Metadata mode has no duplicate restrictions.

---

## Pending Requests System

CFDI requests are registered as pending immediately after SAT acceptance. This ensures no request is lost even if the process is interrupted.

**Request lifecycle:**

```
SAT accepts request → saved to RFC.pending.enc
         ↓
Polling with optional --timeout
         ↓
Completed (state 3)  → download + extract → removed from pending ✔
Timeout / Ctrl+C     → stays in pending, resume with --retomar ⚠
Rejected (state 5)   → removed from pending ✗
Expired  (state 6)   → removed from pending ✗
```

To automate resumption without manual intervention, add a cron job:

```bash
# Resume all pending requests every hour
0 * * * * cd /path/to/taxcrawler-dm && python descarga_masiva.py --retomar-todas all
```

---

## Logging

Every step is logged with a timestamp, level, and descriptive message. Logs go simultaneously to stdout and `sat_descarga.log`.

```
2026-04-09 00:50:42 │ INFO     │ SAT — DESCARGA MASIVA DE CFDI (XML)
2026-04-09 00:50:42 │ INFO     │ ✔ Todos los parámetros son válidos.
2026-04-09 00:50:42 │ INFO     │   Perfil encontrado para RFC XAXX010101000.
2026-04-09 00:50:42 │ INFO     │   Caché: primera solicitud para este período.
2026-04-09 00:50:42 │ INFO     │   Período efectivo : 2025-12-01 00:00:00 → 2025-12-31 23:59:59
2026-04-09 00:50:43 │ INFO     │ ✔ Token obtenido. Sesión activa con el SAT.
2026-04-09 00:50:43 │ INFO     │ ✔ Solicitud aceptada. ID: 3a4341a7-81d6-4830-...
2026-04-09 00:50:43 │ INFO     │   ✔ Solicitud registrada en pendientes: 3a4341a7-...
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `SAT_CACHE_SALT` not defined | Fail immediately with setup instructions |
| Invalid file paths or date ranges | Fail-fast before any SAT call, list all errors |
| Date range older than 6 years | Fail-fast with the exact allowed start date |
| Wrong FIEL password or corrupt files | Clear error message, exit |
| RFC in `--cer` does not match `--rfc` | Detected at FIEL load, clear error |
| SAT authentication failure | Auto-retry up to 3 times with 5s delay |
| SAT request rejected (301 — cancelled XMLs) | `estado_comprobante=Vigente` applied automatically |
| SAT request rejected (5002 — duplicate) | Prevented by automatic datetime offset bypass |
| SAT request rejected (5004 — no CFDIs) | Metadata: continues to next month. CFDI: exits cleanly |
| Polling timeout | Saves request as pending, exits with `--retomar` instructions |
| Package download failure | Retries up to 3 times, skips and continues |
| Corrupt ZIP file | Logs the issue, skips extraction, continues |
| Tampered cache file | Detected automatically, cache reset for that RFC |
| Profile FIEL files moved or deleted | Warns and asks for `--cer`/`--key` explicitly |
| Incorrect password in `--retomar-todas` | Skips all requests for that RFC, continues with others |
| `Ctrl+C` interrupt | Graceful exit, pending requests preserved |
| Unhandled exception | Full stack trace in `sat_descarga.log` |

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

Additional documentation is available in the repository:

| File | Description |
|---|---|
| [FLOWS.md](FLOWS.md) | Step-by-step breakdown of every execution flow with examples and a decision map |
| [ROADMAP.md](ROADMAP.md) | Current status, planned features, and future ideas |
| [LICENSE](LICENSE) | This project license |

---

## Disclaimer

This tool consumes the SAT's official Web Service directly. It is your responsibility to use it in compliance with Mexican tax regulations. The authors are not liable for any misuse, data loss, or regulatory issues arising from the use of this script.

---

## License

GNU GPL v3
