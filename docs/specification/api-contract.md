# API CONTRACT — taxcrawler-dm

---

# OBJECTIVE

Define the exact behavior of every FastAPI endpoint.

This document is the behavioral contract for api/.
All implementations must follow this contract strictly.

---

# GENERAL RULES

- All endpoints call services/ only — never core/ directly
- All required fields are validated before calling any service
- All responses are JSON
- All errors return structured JSON with a message field
- Long-running operations (SAT polling) are handled asynchronously or with timeout
- Passwords are never logged or stored

---

# BASE URL

When running locally:

```
http://localhost:8000
```

---

# AUTHENTICATION

No authentication in MVP.
All endpoints are accessible locally only.
Future phases may add API key or session-based auth.

---

# ENDPOINTS

---

## POST /download/metadata

Purpose:
Download Metadata TXT files for an RFC and date range.

Request body:

```json
{
  "rfc": "TOLM010205CC2",
  "cer_path": "C:/path/to/fiel.cer",
  "key_path": "C:/path/to/fiel.key",
  "password": "TORRES10",
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "tipo": "recibidos",
  "output_dir": "C:/path/to/results",
  "intervalo": 30
}
```

Required fields: rfc, cer_path, key_path, password, start_date, end_date
Optional fields: tipo (default: recibidos), output_dir (default: ./results_RFC), intervalo (default: 60)

Response on success:

```json
{
  "status": "completed",
  "files": [
    "results_TOLM010205CC2/metadata/2026-05-16/2025-01-TOLM010205CC2.txt",
    "results_TOLM010205CC2/metadata/2026-05-16/2025-02-TOLM010205CC2.txt"
  ],
  "months_with_data": 3,
  "months_empty": 0,
  "total_cfdis": 25,
  "total_monto": 26294.81
}
```

Response on error:

```json
{
  "status": "error",
  "message": "Archivo .cer no encontrado: C:/path/to/fiel.cer"
}
```

Rules:

- cer_path and key_path must exist on disk
- start_date must be within last 6 years
- start_date must be <= end_date
- intervalo must be >= 10

---

## POST /download/cfdi

Purpose:
Download CFDI XML files for an RFC and date range.
Applies automatic datetime offset bypass.
Returns immediately after SAT acceptance with request ID.

Request body:

```json
{
  "rfc": "TOLM010205CC2",
  "cer_path": "C:/path/to/fiel.cer",
  "key_path": "C:/path/to/fiel.key",
  "password": "TORRES10",
  "start_date": "2025-01-01",
  "end_date": "2025-01-31",
  "tipo": "recibidos",
  "output_dir": "C:/path/to/results",
  "intervalo": 30,
  "timeout_min": 30
}
```

Required fields: rfc, cer_path, key_path, password, start_date, end_date
Optional fields: tipo, output_dir, intervalo, timeout_min (default: 30)

Response on completion:

```json
{
  "status": "completed",
  "request_id": "3a4341a7-81d6-4830-9210-bf02f46085e0",
  "xml_files": 23,
  "output_dir": "results_TOLM010205CC2/cfdi/2026-05-16"
}
```

Response on timeout:

```json
{
  "status": "pending",
  "request_id": "3a4341a7-81d6-4830-9210-bf02f46085e0",
  "message": "SAT still processing. Resume with /download/resume/{request_id}"
}
```

Response on terminal error:

```json
{
  "status": "error",
  "request_id": "3a4341a7-81d6-4830-9210-bf02f46085e0",
  "message": "Solicitud rechazada por el SAT. Codigo: 5004"
}
```

---

## POST /download/resume/{request_id}

Purpose:
Resume polling for a specific pending CFDI request.

Path parameter: request_id (UUID string)

Request body:

```json
{
  "timeout_min": 30
}
```

Optional fields: timeout_min (default: 30)

Response: same as /download/cfdi

Rules:

- request_id must exist in .cache/ pending files
- FIEL paths are loaded from RFC profile automatically
- Password is required in body (not stored in cache)

---

## POST /download/full-flow

Purpose:
Execute full end-to-end flow: Metadata income + Metadata expenses + Excel generation.

Request body:

```json
{
  "rfc": "TOLM010205CC2",
  "cer_path": "C:/path/to/fiel.cer",
  "key_path": "C:/path/to/fiel.key",
  "password": "TORRES10",
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "output_dir": "C:/path/to/results",
  "intervalo": 30,
  "despacho": "MI DESPACHO CONTABLE",
  "regimen": "resico"
}
```

Required fields: rfc, cer_path, key_path, password, start_date, end_date
Optional fields: output_dir, intervalo, despacho, regimen (default: resico)

Response on success:

```json
{
  "status": "completed",
  "income_files": 3,
  "expense_files": 3,
  "excel_path": "results_TOLM010205CC2/TOLM010205CC2_2025-01__2025-03.xlsx"
}
```

---

## POST /excel/from-metadata

Purpose:
Generate Excel working paper from already downloaded Metadata TXT files.

Request body:

```json
{
  "rfc": "TOLM010205CC2",
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "income_files": ["path/to/2025-01-RFC.txt"],
  "expense_files": ["path/to/2025-01-RFC.txt"],
  "output_dir": "C:/path/to/results",
  "despacho": "MI DESPACHO",
  "regimen": "resico"
}
```

Required fields: rfc, start_date, end_date, income_files, expense_files
Optional fields: output_dir, despacho, regimen

Response:

```json
{
  "status": "completed",
  "excel_path": "results_TOLM010205CC2/TOLM010205CC2_2025-01__2025-03.xlsx"
}
```

---

## POST /excel/from-cfdi

Purpose:
Generate Excel with exact tax breakdown from CFDI XML files.
PLANNED — Phase 7.

Status: NOT IMPLEMENTED

---

## GET /cache/pending

Purpose:
Return all pending requests across all RFCs.

Response:

```json
{
  "total": 2,
  "requests": [
    {
      "rfc": "TOLM010205CC2",
      "request_id": "3a4341a7-...",
      "tipo": "recibidos",
      "solicitud": "CFDI",
      "start_date": "2025-01-01",
      "end_date": "2025-01-31",
      "created": "2026-05-02 19:15:49",
      "elapsed": "hace 2h 15m",
      "resume_command": "--retomar 3a4341a7-..."
    }
  ]
}
```

---

## GET /cache/pending/{rfc}

Purpose:
Return pending requests for a specific RFC.

Path parameter: rfc

Response: same structure as GET /cache/pending filtered by RFC.

---

## GET /cache/profile/{rfc}

Purpose:
Return saved RFC profile.

Path parameter: rfc

Response:

```json
{
  "rfc": "TOLM010205CC2",
  "cer_path": "C:/path/to/fiel.cer",
  "cer_exists": true,
  "key_path": "C:/path/to/fiel.key",
  "key_exists": true,
  "output_dir": "C:/path/to/results",
  "intervalo": 30,
  "saved_at": "2026-05-02 19:10:45"
}
```

Response if no profile:

```json
{
  "rfc": "TOLM010205CC2",
  "profile": null,
  "message": "No profile found for this RFC"
}
```

---

## GET /cache/history/{rfc}

Purpose:
Return encrypted attempt history for an RFC.

Path parameter: rfc

Response:

```json
{
  "rfc": "TOLM010205CC2",
  "periods": [
    {
      "start_date": "2025-01-01",
      "end_date": "2025-01-31",
      "tipo": "recibidos",
      "intentos": 2,
      "last_attempt": "2026-05-02 19:15:48",
      "next_offset_sec": 2
    }
  ]
}
```

---

## GET /cache/profiles

Purpose:
Return all saved RFC profiles from .cache/\*.profile.enc files.

Response:

```json
{
  "total": 2,
  "profiles": [
    {
      "rfc": "TOLM010205CC2",
      "cer": "/path/to/fiel.cer",
      "key": "/path/to/fiel.key",
      "output": "/path/to/results",
      "intervalo": 30,
      "guardado": "2026-05-17 13:57:22",
      "cer_exists": true,
      "key_exists": true
    }
  ]
}
```

---

## GET /cache/results

Purpose:
Return the encrypted results history (all completed operations).
Evaluates excel_exists in real time — not stored.
History is portable between PCs with the same SAT_CACHE_SALT.

Response:

```json
{
  "total": 3,
  "results": [
    {
      "id": "uuid",
      "rfc": "TOLM010205CC2",
      "fecha": "2026-05-17 11:00:00",
      "operacion": "full_flow",
      "excel_path": "results_TOLM010205CC2/TOLM010205CC2_2025-01__2025-03.xlsx",
      "excel_exists": true,
      "files": ["path/to/2025-01-TOLM010205CC2.txt"],
      "files_exist": [true],
      "xml_files": 0,
      "start_date": "2025-01-01",
      "end_date": "2025-03-31"
    }
  ]
}
```

---

## DELETE /cache/results/{id}

Purpose:
Remove an entry from the results history by ID.
Does NOT delete files from disk — only removes the registry entry.

Path parameter: id (UUID string)

Response on success:

```json
{ "status": "deleted", "id": "uuid" }
```

Response if not found:
HTTP 404

---

## POST /download/resume/{request_id}

Purpose:
Resume polling for a specific pending CFDI request.
FIEL paths are loaded from the saved RFC profile automatically.
Password must be provided in the request body.

Path parameter: request_id (UUID string)

Request body:

```json
{
  "timeout_min": 30,
  "password": "M1C0ntr4s3n4"
}
```

Response on completion:

```json
{
  "status": "completed",
  "rfc": "TOLM010205CC2",
  "xml_files": 136,
  "files": ["path/to/xml1.xml"],
  "output_dir": "results_TOLM010205CC2/cfdi/2026-05-17"
}
```

Response on timeout:

```json
{ "status": "pending", "request_id": "uuid", "xml_files": 0, "files": [] }
```

Response on terminal error:

```json
{
  "status": "terminal_error",
  "reason": "rechazada",
  "xml_files": 0,
  "files": []
}
```

Response if not found:

```json
{ "status": "not_found", "request_id": "uuid", "xml_files": 0, "files": [] }
```

Response if password needed but not provided:
HTTP 400 with message asking for password in body.

---

# ERROR HANDLING CONTRACT

All errors return HTTP 400 or 500 with this structure:

```json
{
  "status": "error",
  "message": "Human-readable description of what went wrong"
}
```

| Scenario                   | HTTP | Message                         |
| -------------------------- | ---- | ------------------------------- |
| Missing required field     | 400  | Field name and requirement      |
| .cer or .key not found     | 400  | Path shown                      |
| Invalid date range         | 400  | Both dates shown                |
| Date older than 6 years    | 400  | Allowed limit shown             |
| SAT authentication failure | 500  | Retry count and cause           |
| SAT request rejected       | 400  | SAT code and description        |
| Package download failure   | 500  | Package ID and retry count      |
| Unhandled exception        | 500  | Generic message, details in log |

---

# CONTRACT COMPLETENESS

This contract is complete when:

- All flows in FLOWS.md are exposed as endpoints
- All user stories with API scope are covered
- No undefined behavior exists in api/

---

# FINAL RULE

api/ routes must:

- Accept all inputs defined in this contract
- Produce responses matching defined structure
- Never call core/ directly
- Never store passwords
