# taxcrawler-dm

A zero-cost, open-source Python script to bulk-download CFDI (XML invoices) directly from the Mexican Tax Administration Service (SAT) Web Service — no third-party APIs, no subscriptions, no recurring fees.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Interactive Mode](#interactive-mode)
  - [CLI Mode](#cli-mode)
  - [All Arguments](#all-arguments)
- [Output Structure](#output-structure)
- [Logging](#logging)
- [Error Handling](#error-handling)
- [Important SAT Constraints](#important-sat-constraints)
- [Disclaimer](#disclaimer)

---

## Overview

The SAT provides an official SOAP Web Service (v1.5, released May 2025) that allows registered taxpayers to download their issued and received CFDI in bulk. This script wraps that Web Service into a clean, single-file Python tool with:

- Interactive prompts when run without arguments
- Full CLI support for automation and scheduling
- Descriptive step-by-step logging to stdout and a log file
- Automatic retries on transient network or service failures
- Fail-fast validation before any SAT call is made
- Organized output: one subfolder per downloaded package

---

## How It Works

The script follows the 4-step flow defined by the SAT Web Service, exposed as independent functions:

```
1. validar_parametros     → Validate all inputs before touching the SAT
2. cargar_fiel            → Load and verify your FIEL (e.firma) certificate
3. obtener_token          → Authenticate against the SAT and get a session token
4. solicitar_descarga     → Submit the download request, receive a request ID
5. verificar_solicitud    → Poll the SAT until the request is ready (minutes to hours)
6. descargar_paquete      → Download each ZIP package returned by the SAT
7. extraer_xmls           → Extract individual XML files from each ZIP
8. imprimir_resumen       → Print a final summary with totals and duration
```

Each function is responsible for a single step, logs exactly what it is attempting, and handles its own errors with human-readable explanations.

---

## Requirements

- Python 3.10+
- A valid **FIEL (e.firma)** issued by the SAT, composed of:
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

# Install the only dependency
pip install cfdiclient
```

No virtual environment is strictly required, but recommended:

```bash
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows

pip install cfdiclient
```

---

## Usage

### Interactive Mode

Run without arguments and the script will prompt you for each parameter, validating input in real time. The FIEL password is entered securely (hidden input).

```bash
python sat_descarga_masiva.py
```

Example session:

```
  → RFC del contribuyente: TURF010101ABC
  → Ruta al archivo .cer de la FIEL: /certs/fiel.cer
  → Ruta al archivo .key de la FIEL: /certs/fiel.key
  → Contraseña de la FIEL (oculta):
  → Fecha inicio (YYYY-MM-DD) [2024-01-01]:
  → Fecha fin    (YYYY-MM-DD) [2025-03-28]:
  → Tipo de descarga [emitidos / recibidos] [recibidos]:
  → Tipo de solicitud [CFDI / Metadata] [CFDI]:
  → Carpeta de salida [./xml_sat]:
  → Segundos entre verificaciones [60]:
```

### CLI Mode

Pass all parameters as arguments. Suitable for cron jobs, CI pipelines, or any scheduled execution.

```bash
python sat_descarga_masiva.py \
  --rfc   TURF010101ABC \
  --cer   /certs/fiel.cer \
  --key   /certs/fiel.key \
  --password "your_fiel_password" \
  --inicio  2024-01-01 \
  --fin     2024-12-31 \
  --tipo    recibidos \
  --output  ./xml_sat
```

### All Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--rfc` | ✔ | — | RFC of the taxpayer |
| `--cer` | ✔ | — | Path to the FIEL `.cer` file |
| `--key` | ✔ | — | Path to the FIEL `.key` file |
| `--password` | ✔ | — | FIEL private key password |
| `--inicio` | ✔ | — | Start date `YYYY-MM-DD` |
| `--fin` | ✔ | — | End date `YYYY-MM-DD` |
| `--tipo` | | `recibidos` | `emitidos` or `recibidos` |
| `--solicitud` | | `CFDI` | `CFDI` (full XML) or `Metadata` (summary TXT) |
| `--output` | | `./xml_sat` | Output folder path |
| `--intervalo` | | `60` | Seconds between verification polling attempts |

---

## Output Structure

```
xml_sat/
├── <package_id_1>.zip
│   └── <package_id_1>/
│       ├── uuid-1.xml
│       ├── uuid-2.xml
│       └── ...
├── <package_id_2>.zip
│   └── <package_id_2>/
│       └── ...
└── ...
```

- Each SAT package is saved as a `.zip` file.
- XML files are extracted into a subfolder named after the package ID.
- File names match the UUID of each CFDI for easy lookup.

---

## Logging

Every step is logged with a timestamp, level, and descriptive message. Logs are written simultaneously to:

- **stdout** — visible in the terminal in real time
- **`sat_descarga.log`** — persisted in the working directory for auditing

Log format:

```
2025-03-28 14:05:01 │ INFO     │ Solicitando token de autenticación al SAT (intento 1/3)...
2025-03-28 14:05:02 │ INFO     │ ✔ Token obtenido. La sesión con el SAT está activa.
2025-03-28 14:05:03 │ INFO     │ Enviando solicitud al Web Service del SAT...
2025-03-28 14:05:04 │ INFO     │ ✔ Solicitud aceptada por el SAT.
2025-03-28 14:05:04 │ INFO     │   ID de solicitud : abc123-...
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Invalid file paths or date ranges | Fail-fast before any SAT call |
| Wrong FIEL password or corrupt files | Clear error message, exit |
| SAT authentication failure | Auto-retry up to 3 times with delay |
| SAT request rejected (error 5002) | Explains the duplicate period rule |
| Package download failure | Retries up to 3 times, skips and continues if exhausted |
| Corrupt ZIP file | Logs the issue, skips extraction, continues |
| `Ctrl+C` interrupt | Graceful exit, preserves already-downloaded files |
| Unhandled exception | Full stack trace in `sat_descarga.log` |

---

## Important SAT Constraints

> These are limitations imposed by the SAT Web Service, not by this script.

- **Date range limit:** The SAT only allows downloading CFDI from the last **6 years**. Requests older than that will be rejected.
- **Duplicate period rule:** Do **not** submit the same RFC + date range combination more than twice. On the third attempt the SAT permanently blocks that period with error `5002`. If you hit this, shift the start or end date by at least one second.
- **No sandbox:** There is no test environment. All requests use real FIEL credentials and count against your SAT quota.
- **Processing time:** The SAT may take anywhere from a few minutes to 72 hours to process a request, depending on server load. The script polls automatically.
- **Package size:** Each request can return up to 200,000 XML files split across multiple packages. For very large date ranges, consider splitting into monthly requests.
- **Received + cancelled:** For received CFDI, the SAT only provides `Metadata` for cancelled documents — not the full XML.

---

## Disclaimer

This tool consumes the SAT's official Web Service directly. It is your responsibility to use it in compliance with Mexican tax regulations. The authors are not liable for any misuse, data loss, or regulatory issues arising from the use of this script.

---

## License

MIT
