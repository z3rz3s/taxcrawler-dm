# Script Flows

This document describes every execution flow available in `descarga_masiva.py`.

---

## Flow 1 — Metadata Download

```bash
python descarga_masiva.py --rfc RFC --cer fiel.cer --key fiel.key \
  --inicio 2025-01-01 --fin 2025-12-31 --solicitud Metadata
```

1. Validates all parameters and `SAT_CACHE_SALT`
2. Creates output folder `results_RFC/metadata/YYYY-MM-DD/`
3. Loads and verifies the FIEL (e.firma)
4. For each month in the date range:
   - Submits request to SAT → polls for completion → downloads ZIP → extracts TXT → deletes ZIP
   - If the month has no CFDIs (SAT code 5004) → logs and continues to next month
5. Saves the RFC profile to `.cache/RFC.profile.enc` (only if at least one file was downloaded)
6. Prints human-readable summary with totals, monthly breakdown, and top issuers

**Key behavior:** The date range is automatically split month by month. Empty months are skipped without stopping the process. ZIPs are deleted after extraction. No blocking risk — Metadata has no duplicate request restrictions.

---

## Flow 2 — CFDI Download

```bash
python descarga_masiva.py --rfc RFC --cer fiel.cer --key fiel.key \
  --inicio 2025-12-01 --fin 2025-12-31 --solicitud CFDI --timeout 60
```

1. Validates all parameters and `SAT_CACHE_SALT`
2. Creates output folder `results_RFC/cfdi/YYYY-MM-DD/`
3. Loads and verifies the FIEL
4. Reads encrypted cache → calculates datetime offset to prevent SAT permanent blocking
5. Submits download request to SAT with offset-adjusted datetime
6. Registers request in `.cache/RFC.pending.enc` immediately after acceptance
7. Polls the SAT until response or timeout:
   - **Completed** → downloads ZIPs → extracts XMLs → renames ZIPs → removes from pending → saves RFC profile
   - **Timeout reached** → exits with `--retomar` instructions, request stays in pending
   - **Rejected / expired** → removes from pending → exits with error

**Key behavior:** The full date range is submitted as a single request (not split by month). Each run automatically applies a +1 second offset to prevent SAT duplicate blocking. Only active (non-cancelled) received CFDIs are downloadable — cancelled documents are only available via Metadata.

---

## Flow 3 — Full End-to-End Flow (Metadata + Excel)

```bash
python descarga_masiva.py --rfc RFC --cer fiel.cer --key fiel.key \
  --inicio 2025-01-01 --fin 2025-12-31 --flujo-completo
```

1. Validates `SAT_CACHE_SALT` and parameters
2. Loads and verifies the FIEL
3. **Step 1/3** — Downloads Metadata for emitidos (income)
4. **Step 2/3** — Downloads Metadata for recibidos (expenses)
5. **Step 3/3** — Generates Excel workbook via `excel_generator.py`:
   - Reads downloaded TXT files
   - Filters income / expense / payment records per month
   - Calculates IVA and ISR using the configured tax table
   - Writes monthly sheets + Summary + Calculos
6. Saves RFC profile on completion

**Optional flags:**

- `--excel resumen|detalle|completo` — controls which sheets are included (default: `completo`)
- `--regimen resico` — tax regime for ISR calculation (default: `resico`)
- `--acumulado-anual` — updates a running annual Excel instead of regenerating each time
- `--despacho "Name"` — accounting firm name shown in the workbook header
- `--tabla-isr path/to/tabla.csv` — custom ISR tax table CSV

**Key behavior:** This flow does not submit CFDI requests. It uses Metadata only. The Excel is regenerated from scratch on every run (unless `--acumulado-anual` is used). A double-check by the accountant is expected before sharing with the client.

---

## Flow 4 — View Pending Requests

```bash
python descarga_masiva.py --pendientes
```

1. Validates `SAT_CACHE_SALT`
2. Reads all `.pending.enc` files from `.cache/`
3. Displays RFC, request ID, date range, creation time, elapsed time, and resume command for each pending request

---

## Flow 5 — Resume a Single Request

```bash
python descarga_masiva.py --retomar ID
```

1. Validates `SAT_CACHE_SALT`
2. Searches for the ID across all `.pending.enc` files → retrieves RFC and original parameters
3. Reads the RFC profile to obtain FIEL file paths
4. Requests password (or reads from `SAT_PASSWORD_RFC` environment variable)
5. Resumes polling exactly from where Flow 2 left off at step 7

**Key behavior:** `--cer` and `--key` are not required if the RFC profile exists. The script reads them automatically from `.cache/RFC.profile.enc`.

---

## Flow 6 — Resume All Pending Requests

```bash
python descarga_masiva.py --retomar-todas all
python descarga_masiva.py --retomar-todas XAXX010101000
```

1. Validates `SAT_CACHE_SALT`
2. Collects all pending requests across all RFCs (or a specific RFC)
3. For each RFC — requests password once and reuses it for all pending requests of that RFC
4. For each request — executes Flow 5 sequentially
5. Prints final summary: completed / terminal error / still pending

**Key behavior:** One password per RFC per session. If a password is incorrect for a given RFC, all requests for that RFC are skipped and the process continues with the next RFC. Suitable for cron job automation.

```bash
# Cron example: check pending every hour
0 * * * * cd /path/to/project && python descarga_masiva.py --retomar-todas all
```

---

## Flow 7 — Reveal Request History (Cache)

```bash
python descarga_masiva.py --reveal-cache XAXX010101000
python descarga_masiva.py --reveal-cache all
```

1. Validates `SAT_CACHE_SALT`
2. Decrypts `.cache/RFC.enc`
3. Displays each requested period, number of attempts, last attempt date, and next datetime offset to be used

---

## Flow 8 — View RFC Profile

```bash
python descarga_masiva.py --perfil XAXX010101000
```

1. Validates `SAT_CACHE_SALT`
2. Decrypts `.cache/RFC.profile.enc`
3. Displays `.cer` path, `.key` path, output folder, polling interval, and last saved date
4. Indicates whether each file still exists on disk

---

## Flow 9 — Interactive Mode

```bash
python descarga_masiva.py
```

1. Prompts for each parameter one by one with real-time validation
2. If a profile exists for the entered RFC, automatically fills in FIEL paths and output folder
3. Continues with Flow 1, 2, or 3 depending on the selected options

---

## Decision Map

```
Run script
│
├── No arguments → Flow 9 (Interactive)
│
├── --pendientes      → Flow 4
├── --reveal-cache    → Flow 7
├── --perfil          → Flow 8
├── --retomar ID      → Flow 5
├── --retomar-todas   → Flow 6
│
└── With --rfc, --inicio, --fin
    ├── --flujo-completo    → Flow 3 (Metadata x2 + Excel)
    ├── --solicitud Metadata → Flow 1
    └── --solicitud CFDI     → Flow 2
```

---

## Module Reference

The project is split into focused modules. Each module has a single responsibility.

| Module               | Responsibility                                                     |
| -------------------- | ------------------------------------------------------------------ |
| `descarga_masiva.py` | CLI entry point, argument parsing, flow orchestration              |
| `config.py`          | Constants, logging setup, env validation, ISR table, despacho name |
| `cache_manager.py`   | Encrypted cache — history, pending requests, RFC profile           |
| `sat_client.py`      | SAT Web Service — token, request, polling, package download        |
| `file_handler.py`    | ZIP extraction, output folder resolution                           |
| `metadata_parser.py` | TXT parsing, CFDI filters, monthly periods, summary generation     |
| `excel_generator.py` | Excel workbook generation — sheets, formulas, ISR/IVA calculations |

---

## Cache File Reference

| File                     | Purpose                                                     |
| ------------------------ | ----------------------------------------------------------- |
| `.cache/RFC.enc`         | Encrypted request history and datetime offsets per period   |
| `.cache/RFC.pending.enc` | Encrypted pending requests awaiting SAT processing          |
| `.cache/RFC.profile.enc` | Encrypted RFC profile (FIEL paths, output folder, interval) |

All cache files use Fernet (AES-128-CBC) encryption with a key derived from `SAT_CACHE_SALT` + RFC via PBKDF2-SHA256.

---

## Excel Output Reference

The workbook always contains exactly 6 sheets in this order, regardless of the date range.
For a single month the sheets contain data for that month only.
For a multi-month range each sheet stacks data blocks per month with visual separators.

| Sheet              | Position | Content                                                                               |
| ------------------ | -------- | ------------------------------------------------------------------------------------- |
| `ingresos`         | 1        | Income CFDIs (tipo I, emisor = RFC) grouped by month with subtotals                   |
| `gastos`           | 2        | Expense CFDIs (tipo I, receptor = RFC) grouped by month + payment complements section |
| `Impuestos`        | 3        | Left: IVA/ISR breakdown per month. Right: cumulative IVA balance                      |
| `Papel de Trabajo` | 4        | ISR section (left) and IVA section (right) per month — client-ready                   |
| `INGRESOS YYYY`    | 5        | Full-year income table. Months with data show real amounts, rest blank                |
| `Calculos`         | 6        | ISR tax table (RESICO regime) with update note                                        |

**Notes:**

- Payment complements (tipo P) appear inside `gastos` as a reference section and are never summed.
- Cancelled CFDIs (estatus = Cancelado) are excluded from all sheets.
- IVA is estimated at 16% of monto — exact breakdown requires CFDI XML (planned v1.1).
- ISR is calculated using the RESICO table. PFAE regime is planned for v1.1.
