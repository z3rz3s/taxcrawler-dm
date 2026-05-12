# ACTION PLAN — taxcrawler-dm

---

# OBJECTIVE

Define the execution plan for building the system based on specification-driven development.

---

# PRINCIPLE

Implementation must follow specification.

No development should occur without defined behavior.

---

# PHASE 1 — CORE CLI (COMPLETED)

Objective:
Build the download engine and cache system

Completed:

- SAT Web Service v1.5 integration
- Metadata download with monthly split
- CFDI download with datetime offset bypass
- Encrypted cache (history, pending, profile)
- Pending request system with resume capability
- RFC profile auto-save and auto-load
- Descriptive logging to stdout and file
- Interactive mode with real-time validation
- CLI with grouped arguments and help text

---

# PHASE 2 — EXCEL WORKING PAPER (COMPLETED)

Objective:
Generate accounting working papers from downloaded Metadata

Completed:

- 6 fixed sheets matching reference format
- Income and expense grouping by month
- IVA estimation at 16% of monto
- ISR calculation using RESICO table
- Despacho name resolution (3 priority sources)
- ISR table resolution (3 priority sources)
- --flujo-completo end-to-end command

---

# PHASE 3 — EXCEL FROM CFDI XML (NEXT)

Objective:
Generate Excel with exact tax breakdown from CFDI XML files

Activities:

- Implement xml_parser.py module
- Extract SubTotal, IVA, ISR, IEPS from XML nodes
- Add --excel-desde-cfdi utility mode
- Search XML files on disk first, then pending
- Fall back to Metadata if no XML available

Constraint:
No XML parsing before xml_parser.py is defined in system-modules.md

---

# PHASE 4 — VALIDATION AND TEST MODE

Objective:
Allow FIEL and SAT connectivity validation without submitting requests

Activities:

- Implement --test mode
- Validate .cer and .key files exist
- Validate FIEL loads with password
- Validate RFC matches certificate
- Obtain SAT token (no request submitted)
- Report each step pass/fail

---

# PHASE 5 — BATCH MODE

Objective:
Run downloads for multiple RFCs from a single command

Activities:

- Implement --batch rfcs.txt
- Each RFC uses its own profile and cache
- Consolidated summary report at end

---

# PHASE 6 — DESKTOP GUI

Objective:
Provide a graphical interface for non-technical users

Activities:

- CustomTkinter 4-screen flow
- Anti-block semaphore (green/yellow/red)
- Live log panel
- Pending requests panel with resume button
- PyInstaller packaging (macOS .app, Windows .exe)

---

# PHASE 7 — PFAE TAX REGIME

Objective:
Support Personas Fisicas con Actividad Empresarial ISR calculation

Activities:

- Define calculation logic with accounting team
- Implement \_lookup_isr_pfae() in excel_generator.py
- Add --regimen pfae as working option

Constraint:
No implementation before accounting team defines the calculation rules

---

# EXECUTION RULES

- Specification is the source of truth
- No feature without user story
- No implementation without cli-contract entry
- No undefined behavior
- All code in English, comments in Spanish (ASCII only)
- Every user-visible action must produce a log entry

---

# FINAL RULE

Implementation must strictly follow defined system behavior.
