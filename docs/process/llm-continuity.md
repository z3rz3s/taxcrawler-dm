# LLM CONTINUITY — taxcrawler-dm

---

# PURPOSE

This file is a quick-start summary for resuming work in a new LLM session.
Read this first, then load the full spec files as needed.

---

# PROJECT IN ONE SENTENCE

taxcrawler-dm is a Python CLI tool that downloads CFDI invoices from the Mexican SAT
Web Service and generates accounting working papers (Papel de Trabajo) in Excel format
for multiple client RFCs, with encrypted local cache and pending request management.

---

# CURRENT STATE

Phase 1 COMPLETED: Core CLI — download engine, cache, pending requests, RFC profile
Phase 2 COMPLETED: Excel working paper with 6 fixed sheets from Metadata TXT files
Phase 3 IN PROGRESS: Excel from CFDI XML files (xml_parser.py not yet implemented)

---

# FILE MAP

```
descarga_masiva.py   <- CLI entry point, argument parsing, flow orchestration
config.py            <- constants, logging, env validation, ISR table, despacho
cache_manager.py     <- encrypted cache: history, pending requests, RFC profile
sat_client.py        <- SAT Web Service: token, request, polling, download
file_handler.py      <- ZIP extraction, output folder resolution
metadata_parser.py   <- TXT parsing, CFDI filters, grouping, summary
excel_generator.py   <- 6-sheet Excel workbook generation
tabla_isr_resico.csv <- static ISR RESICO table
.env.example         <- environment variable template
docs/                <- specification documents
```

---

# KEY DECISIONS ALREADY MADE

- All cache files encrypted with Fernet AES-128-CBC (PBKDF2-SHA256 + SAT_CACHE_SALT)
- SAT_CACHE_SALT always from .env — never hardcoded
- Passwords never stored — resolved from env var or getpass() at runtime
- CFDI requests use +1 second datetime offset per attempt to avoid SAT blocking (error 5002)
- Metadata has no request limit — safe to repeat
- Excel always generates exactly 6 sheets in fixed order
- IVA estimated at 16% of monto until xml_parser.py is implemented
- PFAE regime left as TODO — pending accounting team definition
- sys.exit() only in descarga_masiva.py — all other modules raise exceptions
- Code in English, comments/docstrings in Spanish (ASCII only)

---

# KNOWN LIMITATIONS (current)

- IVA and ISR values in Excel are estimates from Metadata, not exact XML values
- ISR retenido is hardcoded to 0.0 until xml_parser.py reads it from XML
- PFAE tax regime not implemented
- --acumulado-anual flag declared but has no effect yet
- --excel resumen|detalle|completo flags declared but all modes generate the same output

---

# WHAT TO IMPLEMENT NEXT (US-010)

--excel-desde-cfdi utility mode:

1. Search for XMLs in results_RFC/cfdi/ for the given RFC and period
2. If found: parse with xml_parser.py and generate Excel with exact values
3. If not found: check .cache/RFC.pending.enc
4. If pending: attempt to resume download (reuse verify_with_timeout)
5. If SAT not ready: log message and exit(0)
6. If no pending and no XMLs: log instructions to run --solicitud CFDI first

New file needed: xml_parser.py (see system-modules.md Module 8)

---

# ENVIRONMENT SETUP

```
SAT_CACHE_SALT=<random 32+ char string>    <- required
SAT_PASSWORD_RFC=<password>                <- optional, avoids getpass
DESPACHO_NOMBRE=<firm name>                <- optional, shows in Excel
TABLA_ISR_PATH=<path to CSV>               <- optional, custom ISR table
```

Install dependencies:

```
python -m pip install cfdiclient openpyxl python-dotenv cryptography --target ./libs --break-system-packages
```

---

# QUICK REFERENCE — MAIN COMMANDS

```bash
# Full flow for a client (recommended)
python descarga_masiva.py --rfc RFC --cer fiel.cer --key fiel.key --password PASS --inicio 2025-01-01 --fin 2025-12-31 --flujo-completo --despacho "FIRM NAME"

# Metadata only (income or expenses)
python descarga_masiva.py --rfc RFC --solicitud Metadata --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31

# CFDI XML download with timeout
python descarga_masiva.py --rfc RFC --solicitud CFDI --tipo recibidos --inicio 2025-01-01 --fin 2025-12-31 --timeout 30

# Utilities
python descarga_masiva.py --pendientes
python descarga_masiva.py --retomar ID
python descarga_masiva.py --retomar-todas all
python descarga_masiva.py --perfil RFC
python descarga_masiva.py --reveal-cache RFC
```

---

# SPEC FILES TO LOAD FOR EACH TASK

| Task                       | Files to provide                                                |
| -------------------------- | --------------------------------------------------------------- |
| New module implementation  | cli-contract.md + system-modules.md + user-stories.md           |
| Bug fix in existing module | cli-contract.md + system-modules.md                             |
| New CLI argument           | cli-contract.md + user-stories.md                               |
| Excel changes              | system-modules.md (Module 7) + user-stories.md (US-007, US-008) |
| xml_parser.py              | system-modules.md (Module 8) + user-stories.md (US-010)         |
| Cache changes              | system-modules.md (Module 3) + cli-contract.md                  |
