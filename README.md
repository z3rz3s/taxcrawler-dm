# tax-crawler-dm

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
  - [Utility Mode — Reveal Cache](#utility-mode--reveal-cache)
  - [All Arguments](#all-arguments)
- [Output Structure](#output-structure)
- [Encrypted Cache](#encrypted-cache)
- [Duplicate Request Protection](#duplicate-request-protection)
- [Logging](#logging)
- [Error Handling](#error-handling)
- [Important SAT Constraints](#important-sat-constraints)
- [Disclaimer](#disclaimer)

---

## Overview

The SAT provides an official SOAP Web Service (v1.5, released May 2025) that allows registered taxpayers to download their issued and received CFDI in bulk. This script wraps that Web Service into a clean, single-file Python tool with:

- Interactive prompts when run without arguments
- Full CLI support for automation and scheduling
- Two download modes: **Metadata** (lightweight TXT summary) and **CFDI** (full XML files)
- Automatic monthly splitting in Metadata mode with graceful continuation on empty months
- Encrypted local cache to prevent permanent SAT period blocking (error 5002)
- Automatic datetime offset bypass — each request uses a slightly different timestamp to avoid duplicate detection
- Descriptive step-by-step logging to stdout and a persistent log file
- Automatic retries on transient network or SAT service failures
- Fail-fast validation before any SAT call is made
- Organized output separated by mode and execution date

---

## How It Works

The script follows the official SAT Web Service flow through independent functions:

```
1. _validar_salt         → Verify SAT_CACHE_SALT env variable is set
2. validar_parametros    → Validate all inputs before touching the SAT
3. resolver_output       → Create results_RFC/metadata|cfdi/YYYY-MM-DD/
4. cargar_fiel           → Load and verify your FIEL (e.firma) certificate
5. obtener_token         → Authenticate against the SAT, get a session token
6. consultar_historial   → Check encrypted cache for prior attempts (CFDI only)
7. registrar_intento     → Record attempt and calculate datetime offset (CFDI only)
8. solicitar_descarga    → Submit the download request, receive a request ID
9. verificar_solicitud   → Poll the SAT until the request is ready (minutes to hours)
10. descargar_paquete    → Download each ZIP package returned by the SAT
11. extraer_metadata     → Extract TXT, rename as YYYY-MM-RFC.txt, delete ZIP (Metadata)
    extraer_cfdi         → Extract XMLs, rename ZIP as YYYY-MM-RFC.zip, keep it (CFDI)
12. generar_resumen      → Print human-readable summary with totals and top issuers
```

**Metadata mode** processes the date range month by month, continuing automatically if a month has no CFDIs (SAT code 5004). This provides granular per-month logs and avoids timeouts on large ranges.

**CFDI mode** submits the full date range in a single request, using the encrypted cache to apply an automatic second-offset bypass on every attempt.

---

## Requirements

- Python 3.13 or upper (recommended — tested and verified)
- A valid **FIEL (e.firma)** issued by the SAT:
  - `.cer` — public certificate file
  - `.key` — private key file
  - Password for the private key
- Internet access to reach SAT Web Service endpoints

---

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/sat-descarga-masiva.git
cd sat-descarga-masiva

# Install dependencies into the local libs/ folder (no virtual environment needed)
python3.13 -m pip install cfdiclient openpyxl python-dotenv --target ./libs --break-system-packages
```

The script automatically detects and uses the `libs/` folder. No system-wide installation or virtual environment required.

---

## Environment Setup

The script uses an encrypted cache to protect request history. The encryption key is derived from an environment variable — never hardcoded.

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

Make sure `.env` is in your `.gitignore` — it should never be committed to the repository.

The script will fail with clear instructions if `SAT_CACHE_SALT` is not defined before any download attempt.

---

## Usage

### Interactive Mode

Run without arguments. The script will prompt for each parameter, validate file paths in real time, and hide the FIEL password input.

```bash
python descarga_masiva.py
```

### CLI Mode — Metadata

Downloads lightweight TXT summary files, one per month. ZIPs are automatically deleted after extraction. Safe to run repeatedly — no blocking risk.

```bash
python descarga_masiva.py \
  --rfc ABCD010203EF1 \
  --cer ~/certs/fiel.cer \
  --key ~/certs/fiel.key \
  --password "YOUR_PASSWORD" \
  --inicio 2024-01-01 \
  --fin 2024-12-31 \
  --tipo recibidos \
  --solicitud Metadata \
  --intervalo 30
```

### CLI Mode — CFDI

Downloads full XML files for the specified date range. The encrypted cache automatically applies a datetime offset on each run to prevent SAT permanent blocking. Only active (non-cancelled) received CFDIs are downloaded, as the SAT does not allow cancelled XMLs in bulk requests.

```bash
python descarga_masiva.py \
  --rfc ABCD010203EF1 \
  --cer ~/certs/fiel.cer \
  --key ~/certs/fiel.key \
  --inicio 2025-12-01 \
  --fin 2025-12-31 \
  --password "YOUR_PASSWORD" \
  --tipo recibidos \
  --solicitud CFDI \
  --intervalo 30
```

### Utility Mode — Reveal Cache

Decrypts and displays the request history for a specific RFC or all RFCs. Requires `SAT_CACHE_SALT` to be set. Does not require FIEL files.

```bash
# Single RFC
python descarga_masiva.py --reveal-cache ABCD010203EF1

# All RFCs in cache
python descarga_masiva.py --reveal-cache all
```

Example output:

```
=================================================================
CACHÉ DESCIFRADO — ABCD010203EF1
=================================================================
  Período  : 2025-12-01 → 2025-12-31 (recibidos)
  Intentos : 3
  Último   : 2026-04-03 16:53:22
  Próximo offset : +3s → inicio efectivo 2025-12-01 00:00:03
```

### All Arguments

| Argument         | Required | Default         | Description                                                                                             |
| ---------------- | -------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| `--rfc`          | ✔        | —               | RFC of the taxpayer                                                                                     |
| `--cer`          | ✔        | —               | Path to the FIEL `.cer` file                                                                            |
| `--key`          | ✔        | —               | Path to the FIEL `.key` file                                                                            |
| `--password`     |          | prompt          | FIEL password. If omitted, prompted securely (recommended for passwords with spaces)                    |
| `--inicio`       | ✔        | —               | Start date `YYYY-MM-DD`                                                                                 |
| `--fin`          | ✔        | —               | End date `YYYY-MM-DD`                                                                                   |
| `--tipo`         |          | `recibidos`     | `emitidos` or `recibidos`                                                                               |
| `--solicitud`    |          | `CFDI`          | `CFDI` (full XML) or `Metadata` (summary TXT)                                                           |
| `--excel`        |          | —               | `resumen`, `detalle`, or `completo` — generate Excel from downloaded XMLs (CFDI mode only, coming soon) |
| `--output`       |          | `./results_RFC` | Base output folder. Subfolders are created automatically                                                |
| `--intervalo`    |          | `60`            | Seconds between SAT polling attempts (minimum: 10)                                                      |
| `--reveal-cache` |          | —               | `RFC` or `all` — decrypt and display request history                                                    |

---

## Output Structure

```
results_ABCD010203EF1/
├── metadata/
│   └── 2026-04-03/
│       ├── 2025-01-ABCD010203EF1.txt
│       ├── 2025-02-ABCD010203EF1.txt
│       └── ...
└── cfdi/
    └── 2026-04-03/
        ├── 2025-12-ABCD010203EF1.zip    ← renamed, preserved
        └── 2025-12-VAVC930829LJ1/
            ├── uuid-1.xml
            ├── uuid-2.xml
            └── ...

.cache/
└── ABCD010203EF1.enc                    ← encrypted request history

sat_descarga.log                         ← full execution log
```

If the same date folder already exists (running the script twice on the same day), files are overwritten silently and a warning is logged.

---

## Encrypted Cache

The script maintains an encrypted request history in `.cache/RFC.enc` for each RFC. This file:

- Is encrypted with **Fernet (AES-128-CBC)** using a key derived via **PBKDF2-SHA256** from `SAT_CACHE_SALT` + the RFC
- Cannot be read or modified without knowing `SAT_CACHE_SALT`
- If tampered with manually, the script detects the corruption and resets it automatically
- Is never committed to the repository (add `.cache/` to `.gitignore`)

The recommended `.gitignore` entries:

```
.env
.cache/
libs/
results_*/
sat_descarga.log
```

---

## Duplicate Request Protection

The SAT permanently blocks a combination of `RFC + start date + end date + type` after 2 identical CFDI requests (error 5002). This script handles this automatically:

- The cache tracks how many times each period has been requested
- On each CFDI request, the start datetime is offset by +1 second per prior attempt:
  - Attempt 1: `2025-12-01 00:00:00`
  - Attempt 2: `2025-12-01 00:00:01`
  - Attempt 3: `2025-12-01 00:00:02`
- Since the SAT compares exact datetime values, each request is technically a new period
- This means the blocking risk is eliminated for normal usage

This protection only applies to CFDI mode. Metadata mode has no duplicate restrictions.

---

## Logging

Every step is logged with a timestamp, level, and descriptive message. Logs are written simultaneously to stdout and `sat_descarga.log`.

```
2026-04-03 16:50:42 │ INFO     │ SAT — DESCARGA MASIVA DE CFDI (XML)
2026-04-03 16:50:42 │ INFO     │ Validando parámetros antes de iniciar el proceso...
2026-04-03 16:50:42 │ INFO     │ ✔ Todos los parámetros son válidos.
2026-04-03 16:50:42 │ INFO     │ Caché: primera solicitud para este período.
2026-04-03 16:50:42 │ INFO     │   Período efectivo : 2025-12-01 00:00:00 → 2025-12-31 23:59:59
2026-04-03 16:50:43 │ INFO     │ ✔ Token obtenido. Sesión activa con el SAT.
2026-04-03 16:50:43 │ INFO     │ ✔ Solicitud aceptada. ID: 3a4341a7-81d6-4830-...
```

---

## Error Handling

| Scenario                                    | Behavior                                                   |
| ------------------------------------------- | ---------------------------------------------------------- |
| `SAT_CACHE_SALT` not defined                | Fail immediately with setup instructions                   |
| Invalid file paths or date ranges           | Fail-fast before any SAT call, list all errors             |
| Date range older than 6 years               | Fail-fast with the exact allowed start date                |
| Wrong FIEL password or corrupt files        | Clear error message, exit                                  |
| SAT authentication failure                  | Auto-retry up to 3 times with 5s delay                     |
| SAT request rejected (301 — cancelled XMLs) | Uses `estado_comprobante=Vigente` automatically            |
| SAT request rejected (5002 — duplicate)     | Prevented by automatic datetime offset bypass              |
| SAT request rejected (5004 — no CFDIs)      | Metadata: continues to next month. CFDI: exits cleanly     |
| Polling timeout or network error            | Retries indefinitely until SAT responds or user interrupts |
| Package download failure                    | Retries up to 3 times, skips and continues if exhausted    |
| Corrupt ZIP file                            | Logs the issue, skips extraction, continues                |
| Tampered cache file                         | Detected automatically, cache reset for that RFC           |
| `Ctrl+C` interrupt                          | Graceful exit, preserves all downloaded files              |
| Unhandled exception                         | Full stack trace in `sat_descarga.log`                     |

---

## Important SAT Constraints

> These are limitations imposed by the SAT Web Service, not by this script.

- **Date range limit:** The SAT only allows downloading CFDI from the last **6 years**. Requests older than that are rejected automatically before submission.
- **No sandbox:** There is no test environment. All requests use real FIEL credentials.
- **Processing time:** The SAT may take anywhere from a few minutes to 72 hours depending on server load. The script polls automatically.
- **Package size:** Each request can return up to 200,000 XML files split across multiple packages.
- **Cancelled received CFDIs:** For received CFDI, the SAT does not allow downloading cancelled XMLs in bulk — only `Metadata` is available for cancelled documents.
- **Metadata has no duplicate restrictions:** You can request the same Metadata period as many times as needed.

---

## Disclaimer

This tool consumes the SAT's official Web Service directly. It is your responsibility to use it in compliance with Mexican tax regulations. The authors are not liable for any misuse, data loss, or regulatory issues arising from the use of this script.

---

## License

[GNU GPL v3](./LICENSE)
