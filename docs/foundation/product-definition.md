# PRODUCT DEFINITION — taxcrawler-dm

---

# MAIN PROBLEM

Mexican taxpayers and accounting firms face a critical operational limitation:

- The SAT portal does not provide a bulk download tool for CFDI invoices
- Downloading invoices one by one is impractical for tax compliance
- Third-party services charge recurring fees and require uploading sensitive FIEL credentials to external servers
- Accountants spend significant time manually collecting and organizing invoice data before generating working papers

---

# OBJECTIVE

Define a system that enables:

- Bulk download of CFDI invoices directly from the SAT official Web Service
- Generation of accounting working papers (Papel de Trabajo) in Excel format
- Support for multiple taxpayer clients (RFCs) from a single installation
- Full auditability of all downloaded data
- Operation without third-party APIs or recurring costs
- Multiple interfaces: CLI, API, and desktop GUI sharing the same business logic

---

# TARGET USERS

## Primary User — Accountant or Tax Advisor

- Manages multiple client RFCs
- Needs monthly working papers per client
- Requires evidence (XML files) to support tax declarations
- Uses Windows or macOS
- May use CLI, GUI, or both depending on technical comfort

## Secondary User — Business Owner or Taxpayer

- Wants to download and review their own invoices
- May not have accounting knowledge
- Prefers graphical interface over CLI

---

# PRODUCT DEFINITION

This system is not a generic invoice viewer.

It is:

> A multi-interface tool that connects directly to the SAT Web Service, downloads CFDI metadata and XML files per RFC, and generates accounting working papers in Excel format ready for client review and tax declaration.

---

# DOMAIN DEFINITIONS

## RFC

Registro Federal de Contribuyentes. Unique tax identifier for each taxpayer in Mexico.

## FIEL (e.firma)

Digital certificate issued by SAT. Required to authenticate against the Web Service. Composed of: .cer file + .key file + password.

## CFDI

Comprobante Fiscal Digital por Internet. Official electronic invoice format in Mexico.

## Metadata

Lightweight TXT summary of CFDIs. Contains UUID, RFC, amounts, dates, and status. Downloaded without CFDI attempt limit. Used for Excel generation.

## CFDI XML

Full invoice file with complete tax breakdown including SubTotal, IVA, ISR, IEPS. Counts against SAT duplicate request limits. Used as audit evidence.

## Papel de Trabajo

Accounting working paper. Excel document generated from Metadata showing income, expenses, IVA and ISR calculations. Reviewed and authorized by the client before the accountant files the tax declaration.

## Solicitud Pendiente

A CFDI download request submitted to the SAT that has not yet been processed. The SAT may take minutes to 72 hours to prepare the response.

## RESICO

Regimen Simplificado de Confianza. Tax regime for small taxpayers with simplified ISR rates.

## PFAE

Personas Fisicas con Actividad Empresarial. Tax regime with progressive ISR calculation. Currently not implemented — pending accounting team definition.

---

# CORE CAPABILITIES

## 1. Metadata Download

- Download lightweight TXT summaries per month per RFC
- No duplicate request limit
- Safe to run repeatedly

## 2. CFDI Download

- Download full XML files per RFC
- Automatic datetime offset bypass to prevent SAT blocking (error 5002)
- Pending request system for long SAT processing times

## 3. Pending Request Management

- Register requests immediately after SAT acceptance
- Resume pending requests after timeout or interruption
- Automatic cleanup on completion or terminal error

## 4. RFC Profile System

- Save FIEL paths and configuration after first run
- Auto-load profile on subsequent runs
- Encrypted storage per RFC

## 5. Encrypted Cache

- Store attempt history and pending requests encrypted
- Fernet AES-128-CBC with PBKDF2-SHA256 key derivation
- SAT_CACHE_SALT from environment variable — never hardcoded

## 6. Excel Working Paper Generation

- Generate Papel de Trabajo from downloaded Metadata TXT files
- 6 fixed sheets matching accounting reference format
- ISR calculation using RESICO table
- IVA estimation at 16% of monto (exact values planned via XML parser)

## 7. Multiple Interfaces (planned)

- CLI: command-line for technical users and automation
- API: FastAPI for UI integration and future integrations
- GUI: CustomTkinter desktop app for non-technical users

---

# CONSTRAINTS

- The system must never store FIEL passwords in any file
- The system must never submit duplicate CFDI requests without offset
- No business logic outside core/
- No interface logic inside core/
- All SAT calls must be logged with timestamps
- All cache files must be encrypted

---

# SUCCESS CRITERIA

The system is considered successful when:

- An accountant can download all Metadata for a client RFC with a single command
- The generated Excel opens without errors and matches the reference working paper format
- CFDI XML files are preserved as audit evidence
- Pending requests survive interruptions and can be resumed
- The system runs on Windows and macOS without additional configuration
- A non-technical user can complete the full flow using the desktop GUI

---

# POSITION IN SYSTEM DESIGN

This document defines domain concepts, product scope, and system boundaries.

Detailed behavior is defined in:

- specification/system-modules.md
- specification/user-stories.md
- specification/cli-contract.md
- specification/api-contract.md
- specification/ui-spec.md