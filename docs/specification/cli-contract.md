# CLI CONTRACT — taxcrawler-dm

---

# OBJECTIVE

Define the exact behavior of every CLI argument and utility mode.

This document is the behavioral contract for descarga_masiva.py.
All implementations must follow this contract strictly.

---

# GENERAL RULES

- All arguments are validated before any SAT call
- Errors are collected and reported together (fail-fast)
- sys.exit(0) for clean exits, sys.exit(1) for errors
- Every operation produces at least one log entry
- Passwords are never stored — only resolved at runtime
- SAT_CACHE_SALT must be set in .env or the script exits immediately

---

# ARGUMENT GROUPS

## Download Arguments

### --rfc RFC

Required for all download modes.
Must be uppercase. Validated as present.

### --cer RUTA

Path to .cer FIEL file.
Optional if RFC profile exists with valid path.
If profile path is missing on disk, warns and requires explicit --cer.

### --key RUTA

Path to .key FIEL file.
Same rules as --cer.

### --password PASS

FIEL password.
If omitted: resolved from SAT_PASSWORD_RFC env var first, then getpass().
Never stored in any file or cache.

### --inicio YYYY-MM-DD

Start date of download period.
Must be within last 6 years.
Must be <= --fin.

### --fin YYYY-MM-DD

End date of download period.
Must be >= --inicio.

### --tipo emitidos|recibidos

Default: recibidos.
Determines which CFDIs to request.

### --solicitud CFDI|Metadata

Default: CFDI.
CFDI: full XML download. Applies offset bypass.
Metadata: TXT summary download. No limit, no offset.

### --timeout MINUTOS

Optional. Minimum 5.
Max minutes to wait for SAT response before saving as pending.
Default for --retomar and --retomar-todas: 30 minutes.
Default for normal download: no limit.

### --output RUTA

Optional. Default: ./results_RFC.
Base output folder. Subfolders created automatically.

### --intervalo SEG

Default: 60. Minimum: 10.
Seconds between SAT polling attempts.

---

## Excel Arguments

### --flujo-completo

Triggers full end-to-end flow:

1. Download Metadata emitidos (ingresos)
2. Download Metadata recibidos (gastos)
3. Generate Excel with 6 fixed sheets

Does not require --solicitud or --tipo.
--cer and --key optional if profile exists.

### --excel resumen|detalle|completo

Optional. Default: completo when used with --flujo-completo.
Currently all modes generate the same 6-sheet workbook.
Reserved for future sheet selection control.

### --regimen resico|pfae

Default: resico.
Determines ISR calculation method.
pfae: not implemented — shows warning and falls back to resico.

### --acumulado-anual

Flag. Default: False.
Reserved for Option B (running annual Excel update).
Currently has no effect on output.

### --despacho "NOMBRE"

Optional. Must be in double quotes if contains spaces.
Overrides DESPACHO_NOMBRE env var and DEFAULT_DESPACHO constant.
Shown in Papel de Trabajo sheet header.

### --tabla-isr RUTA

Optional. Path to CSV file with ISR tax table.
CSV format: limite_inferior, limite_superior, cuota_fija, tasa
Overrides TABLA_ISR_PATH env var and built-in table.
If file not found: warning logged, built-in table used.

---

## Utility Modes

### --pendientes

Shows all pending CFDI requests across all RFCs.
Requires SAT_CACHE_SALT.
Does not require FIEL.
Output per request: RFC, ID, period, tipo, solicitud, created, elapsed, resume command.

### --retomar ID

Resumes polling for a specific pending request.
Searches all .pending.enc files for the ID.
Loads FIEL paths from RFC profile automatically.
Requires password (env or getpass).
Default timeout: 30 minutes (configurable with --timeout).
On completion: downloads packages, extracts XMLs, removes from pending.
On timeout: keeps in pending, shows resume command.
On terminal error (estado 5 or 6): removes from pending.

### --retomar-todas RFC|all

Resumes all pending requests for a specific RFC or all RFCs.
Processes sequentially — one RFC at a time.
Requests password once per RFC per session.
If password is incorrect for a RFC: skips that RFC, continues with others.
Default timeout per request: 30 minutes.
Prints summary at end: completed / terminal error / still pending.

### --perfil RFC

Shows saved RFC profile.
Requires SAT_CACHE_SALT.
Output: .cer path, .key path, output folder, intervalo, last saved date.
Indicates whether files still exist on disk.

### --reveal-cache RFC|all

Decrypts and shows attempt history.
Requires SAT_CACHE_SALT.
Output per period: period dates, tipo, intentos, last attempt date, next offset.

---

# VALIDATION RULES

Validated before any SAT call:

| Rule                                   | Error                        |
| -------------------------------------- | ---------------------------- |
| .cer file not found                    | exit with path               |
| .key file not found                    | exit with path               |
| inicio > fin                           | exit with both dates         |
| inicio < 6 years ago                   | exit with allowed limit date |
| intervalo < 10                         | exit                         |
| timeout < 5 (if set)                   | exit                         |
| --excel without CFDI or flujo-completo | exit                         |
| SAT_CACHE_SALT not set                 | exit with setup instructions |

---

# OUTPUT STRUCTURE

Created automatically. Never requires manual folder creation.

```
results_RFC/
  metadata/
    YYYY-MM-DD/
      YYYY-MM-RFC.txt          <- Metadata TXT (ZIP deleted)
  cfdi/
    YYYY-MM-DD/
      YYYY-MM-RFC.zip          <- CFDI ZIP (renamed, preserved)
      YYYY-MM-RFC/
        uuid.xml               <- CFDI XML files
  RFC_YYYY-MM.xlsx             <- single month Excel
  RFC_YYYY-MM__YYYY-MM.xlsx    <- range Excel

.cache/
  RFC.enc                      <- attempt history
  RFC.pending.enc              <- pending requests
  RFC.profile.enc              <- RFC profile
```

---

# ENVIRONMENT VARIABLES

Defined in .env (never committed to repository).

| Variable         | Required | Description                                                       |
| ---------------- | -------- | ----------------------------------------------------------------- |
| SAT_CACHE_SALT   | YES      | Salt for cache encryption. Generate with: openssl rand -base64 32 |
| SAT_PASSWORD_RFC | NO       | FIEL password for RFC. Avoids getpass() prompt.                   |
| DESPACHO_NOMBRE  | NO       | Accounting firm name for Excel header.                            |
| TABLA_ISR_PATH   | NO       | Path to custom ISR table CSV file.                                |

---

# ERROR HANDLING CONTRACT

| Scenario                  | Behavior                                                   |
| ------------------------- | ---------------------------------------------------------- |
| SAT_CACHE_SALT not set    | exit(1) with setup instructions                            |
| .cer or .key not found    | exit(1) with path shown                                    |
| Wrong FIEL password       | exit(1) with clear message                                 |
| SAT authentication fails  | retry 3 times with 5s delay, then exit(1)                  |
| SAT request rejected 301  | exit(1) — estado_comprobante=Vigente applied automatically |
| SAT request rejected 5002 | prevented by offset bypass                                 |
| SAT request rejected 5004 | Metadata: continue to next month. CFDI: exit(0)            |
| Polling timeout           | save to pending, exit(0) with resume command               |
| Package download fails    | retry 3 times, skip package, continue                      |
| Corrupt ZIP               | log warning, skip extraction, continue                     |
| Tampered cache file       | log warning, reset cache for that RFC                      |
| Ctrl+C                    | exit(0), pending requests preserved                        |
| Unhandled exception       | log full stack trace to sat_descarga.log, exit(1)          |

---

# CONTRACT COMPLETENESS

This contract is complete when:

- All flows in FLOWS.md are supported
- All user stories are covered
- No undefined behavior exists in descarga_masiva.py

---

# FINAL RULE

descarga_masiva.py must:

- Accept all arguments defined in this contract
- Produce output matching defined structure
- Never introduce behavior not defined here
