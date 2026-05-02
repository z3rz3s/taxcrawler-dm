# Roadmap

This document tracks the current state of the project and planned improvements.

---

## Status Legend

- ✅ Done
- 🔄 In Progress
- 📋 Planned
- 💡 Idea / Under Consideration

---

## v1.0 — Core CLI (Current)

### Completed ✅

**Project Structure**

- ✅ Refactored into focused modules: `config.py`, `cache_manager.py`, `sat_client.py`, `file_handler.py`, `metadata_parser.py`, `excel_generator.py`
- ✅ `descarga_masiva.py` as the single CLI entry point and flow orchestrator
- ✅ Code in English, comments and docs in Spanish (no special characters)
- ✅ `tabla_isr_resico.csv` — static ISR tax table extracted from reference workbook

**Download Engine**

- ✅ SAT Web Service v1.5 integration (SOAP)
- ✅ Metadata mode — monthly split, automatic 5004 handling, ZIP cleanup
- ✅ CFDI mode — full range request, active-only filter (`estado_comprobante=Vigente`)
- ✅ Automatic datetime offset bypass — prevents SAT permanent blocking (error 5002)
- ✅ Automatic retry on network failures (up to 3 attempts per operation)
- ✅ Configurable polling interval and optional timeout

**Output Organization**

- ✅ Structured output: `results_RFC/metadata|cfdi/YYYY-MM-DD/`
- ✅ Metadata: TXT files named `YYYY-MM-RFC.txt`, ZIPs deleted after extraction
- ✅ CFDI: XMLs extracted to `YYYY-MM-RFC/`, ZIPs renamed and preserved
- ✅ Overwrite warning when same-day folder already exists

**Pending Requests System**

- ✅ Encrypted `.cache/RFC.pending.enc` — requests registered immediately after SAT acceptance
- ✅ `--pendientes` — view all pending requests across all RFCs
- ✅ `--retomar ID` — resume a specific pending request
- ✅ `--retomar-todas RFC|all` — resume all pending requests sequentially
- ✅ Automatic cleanup: completed / rejected / expired requests removed from pending
- ✅ Cron-ready `--retomar-todas` for unattended automation
- ✅ Default 30-minute timeout for `--retomar` and `--retomar-todas`

**RFC Profile System**

- ✅ Encrypted `.cache/RFC.profile.enc` — stores FIEL paths and configuration
- ✅ Profile auto-saved on successful download (only if files were actually downloaded)
- ✅ Profile auto-loaded in subsequent runs — no need to pass `--cer`/`--key` again
- ✅ `--perfil RFC` — inspect saved profile and verify files exist on disk

**Security**

- ✅ Fernet (AES-128-CBC) encryption for all cache files
- ✅ PBKDF2-SHA256 key derivation using `SAT_CACHE_SALT` from `.env`
- ✅ Password resolution via `SAT_PASSWORD_RFC` env variable (optional, for automation)
- ✅ One password per RFC per session in `--retomar-todas`
- ✅ Password never stored in any file
- ✅ Tamper detection — corrupted cache files reset automatically

**Logging**

- ✅ Timestamped logs to stdout and `sat_descarga.log`
- ✅ Step-by-step descriptive logs for every operation
- ✅ Human-readable summary at the end of each run
- ✅ Metadata summary with totals, monthly breakdown, and top 5 issuers/receivers
- ✅ Logging designed for future UI integration — same log calls work in CLI and GUI

**Developer Utilities**

- ✅ `--reveal-cache RFC|all` — inspect encrypted request history
- ✅ `--perfil RFC` — inspect encrypted RFC profile
- ✅ `.env.example` with all documented variables
- ✅ Local `libs/` dependency folder (no virtualenv required)
- ✅ Interactive mode with real-time validation and profile-assisted defaults
- ✅ `--help` with grouped arguments and usage examples

**Excel and Working Paper**

- ✅ `--flujo-completo` — end-to-end flow: Metadata (income + expenses) + Excel generation
- ✅ `excel_generator.py` — generates Papel de Trabajo workbook from downloaded TXT files
- ✅ Sheets: `ingresos`, `gastos`, `pagos` (complements), `impuestos`, `papel` per month + `Summary` + `Calculos`
- ✅ Modes: `--excel resumen | detalle | completo`
- ✅ ISR calculation using RESICO table (3 source priority: hardcoded → `.env` → `--tabla-isr`)
- ✅ Despacho name resolution (3 source priority: hardcoded default → `.env` → `--despacho`)
- ✅ `--acumulado-anual` flag for running annual Excel (Option B)
- ✅ `--regimen resico` (default) — PFAE left open with TODO marker
- ✅ `tabla_isr_resico.csv` — static reference table included in repo

---

## v1.1 — Excel Improvements

### Planned 📋

- 📋 Cross-sheet Excel formulas linking `papel` to `impuestos` and `ingresos` sheets
- 📋 IVA carry-forward across months (saldo acumulado)
- 📋 Multi-currency support (currently MXN only)
- 📋 PFAE tax regime calculation — pending definition from accounting team
- 📋 Auto-update ISR table from SAT public source when legislation changes
- 📋 Client authorization signature section in Papel de Trabajo

---

## v1.2 — Test Mode

### Planned 📋

- 📋 `--test` mode — validates FIEL, password, RFC match, and SAT connectivity without submitting any request
- 📋 Step-by-step output: files exist → FIEL loads → RFC matches certificate → SAT token obtained
- 📋 No cache writes, no SAT requests, no output folder creation

---

## v1.3 — Batch Mode

### Planned 📋

- 📋 `--batch rfcs.txt` — run Metadata or full flow for a list of RFCs from a file
- 📋 Each RFC uses its own profile and pending file
- 📋 Consolidated summary report across all RFCs at the end

---

## v2.0 — Desktop GUI (CustomTkinter)

### Planned 📋

**4-screen flow**

- 📋 Screen 1 — Configuration: file pickers for `.cer`/`.key`, RFC input, password field, FIEL verify button
- 📋 Screen 2 — Request: date pickers, type selectors, anti-block semaphore (green/yellow/red based on cache)
- 📋 Screen 3 — Progress: phase progress bar, live log panel (reusing existing log calls), cancel button
- 📋 Screen 4 — Results: Metadata preview table, download CFDI button, open Excel button

**Anti-block semaphore**

- 📋 Green — no prior attempts for this period
- 📋 Yellow — 1 prior attempt (1 remaining before bypass activates)
- 📋 Red — 2+ attempts — bypass active, offset applied automatically

**Pending requests panel**

- 📋 List of pending requests with status and resume button per row
- 📋 Auto-refresh on open

**Packaging**

- 📋 Single executable via PyInstaller (macOS `.app`, Windows `.exe`)
- 📋 No Python installation required for end users

---

## v2.1 — Scheduler

### Ideas 💡

- 💡 Built-in scheduler — configure recurring downloads without cron
- 💡 `--schedule daily|weekly` — auto-run `--retomar-todas` at a set interval
- 💡 Optional desktop notification when downloads complete

---

## v2.2 — Client Authorization Flow

### Ideas 💡

- 💡 Auto-generate email with Excel attached for client review
- 💡 Client approval token or simple reply-based confirmation
- 💡 Audit trail of approvals per period per RFC

---

## Known Limitations

- The SAT has no sandbox environment — all requests use real credentials
- CFDI mode only downloads active received CFDIs — cancelled ones are only available via Metadata
- SAT processing time varies from minutes to 72 hours depending on server load
- Date range is limited to the last 6 years by SAT policy
- Metadata mode has no duplicate request restrictions; CFDI mode uses offset bypass
- ISR calculation currently supports RESICO only — PFAE pending accounting team definition
- Excel cross-sheet formulas not yet linked (values written directly, not as cell references)

---

## Contributing

Pull requests and issues are welcome. Please open an issue before submitting a large change so we can discuss the approach first.
