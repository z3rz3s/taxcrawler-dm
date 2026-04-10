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

## Flow 3 — View Pending Requests

```bash
python descarga_masiva.py --pendientes
```

1. Validates `SAT_CACHE_SALT`
2. Reads all `.pending.enc` files from `.cache/`
3. Displays RFC, request ID, date range, creation time, elapsed time, and resume command for each pending request

---

## Flow 4 — Resume a Single Request

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

## Flow 5 — Resume All Pending Requests

```bash
python descarga_masiva.py --retomar-todas all
python descarga_masiva.py --retomar-todas VAVC930829LJ1
```

1. Validates `SAT_CACHE_SALT`
2. Collects all pending requests across all RFCs (or a specific RFC)
3. For each RFC — requests password once and reuses it for all pending requests of that RFC
4. For each request — executes Flow 4 sequentially
5. Prints final summary: completed / terminal error / still pending

**Key behavior:** One password per RFC per session. If a password is incorrect for a given RFC, all requests for that RFC are skipped and the process continues with the next RFC. Suitable for cron job automation.

```bash
# Cron example: check pending every hour
0 * * * * cd /path/to/project && python descarga_masiva.py --retomar-todas all
```

---

## Flow 6 — Reveal Request History (Cache)

```bash
python descarga_masiva.py --reveal-cache VAVC930829LJ1
python descarga_masiva.py --reveal-cache all
```

1. Validates `SAT_CACHE_SALT`
2. Decrypts `.cache/RFC.enc`
3. Displays each requested period, number of attempts, last attempt date, and next datetime offset to be used

---

## Flow 7 — View RFC Profile

```bash
python descarga_masiva.py --perfil VAVC930829LJ1
```

1. Validates `SAT_CACHE_SALT`
2. Decrypts `.cache/RFC.profile.enc`
3. Displays `.cer` path, `.key` path, output folder, polling interval, and last saved date
4. Indicates whether each file still exists on disk

---

## Flow 8 — Interactive Mode

```bash
python descarga_masiva.py
```

1. Prompts for each parameter one by one with real-time validation
2. If a profile exists for the entered RFC, automatically fills in FIEL paths and output folder
3. Continues with Flow 1 or Flow 2 depending on the selected download type

---

## Decision Map

```
Run script
│
├── No arguments → Flow 8 (Interactive)
│
├── --pendientes → Flow 3
├── --reveal-cache → Flow 6
├── --perfil → Flow 7
├── --retomar ID → Flow 4
├── --retomar-todas → Flow 5
│
└── With --rfc, --inicio, --fin
    ├── --solicitud Metadata → Flow 1
    └── --solicitud CFDI → Flow 2
```

---

## Cache File Reference

| File                     | Purpose                                                     |
| ------------------------ | ----------------------------------------------------------- |
| `.cache/RFC.enc`         | Encrypted request history and datetime offsets per period   |
| `.cache/RFC.pending.enc` | Encrypted pending requests awaiting SAT processing          |
| `.cache/RFC.profile.enc` | Encrypted RFC profile (FIEL paths, output folder, interval) |

All cache files use Fernet (AES-128-CBC) encryption with a key derived from `SAT_CACHE_SALT` + RFC via PBKDF2-SHA256.
