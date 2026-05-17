# TEST CASES — taxcrawler-dm

This document defines how to manually test the system.
It is written for non-technical users who need to verify that the system works correctly.

Each test has a unique ID using this naming convention:
module_function_scenario_p0 <- p = positive (should work)
module_function_scenario_n0 <- n = negative (should fail gracefully)
The number at the end is the permutation index within the same scenario.

---

# BEFORE RUNNING ANY TEST

Required for every test:

- Project folder open in terminal
- .env file configured with SAT_CACHE_SALT
- Internet connection active
- FIEL files (.cer and .key) available on disk
- FIEL password known

Dummy data used in this document:

- RFC: XAXX010101000 (generic public RFC used by SAT in their own examples)
- Password: M1C0ntr4s3n4 (fictional, replace with real password)
- Despacho: Despacho Ejemplo SC

---

# 1. METADATA DOWNLOAD

---

## download_metadata_oneMonth_p0

What is being tested:
System downloads Metadata TXT for a single month using password prompt.

Steps:

1. Open terminal in project folder
2. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --inicio 2025-01-01 --fin 2025-01-31 --solicitud Metadata --tipo recibidos --intervalo 30
3. Type FIEL password when prompted (input is hidden)
4. Wait for completion

Expected result:

- Screen shows: "Token obtenido. Sesion activa con el SAT."
- Screen shows: "1 archivo(s) guardados"
- A .txt file appears in results_XAXX010101000/metadata/YYYY-MM-DD/
- Screen shows total CFDIs and amount in the summary

Should NOT happen:

- System freezes with no output
- Red error message appears
- No folder or file is created

---

## download_metadata_oneMonth_p1

What is being tested:
System downloads Metadata TXT for a single month with password passed as argument.

Steps:

1. Open terminal in project folder
2. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-01-01 --fin 2025-01-31 --solicitud Metadata --tipo recibidos --intervalo 30
3. Wait for completion

Expected result:

- Same as download_metadata_oneMonth_p0
- System does NOT ask for password

Should NOT happen:

- System asks for password again
- Any difference in behavior compared to p0

---

## download_metadata_multiMonth_p0

What is being tested:
System downloads Metadata TXT for multiple months, one file per month.

Steps:

1. Open terminal in project folder
2. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-01-01 --fin 2025-03-31 --solicitud Metadata --tipo recibidos --intervalo 30
3. Wait for completion

Expected result:

- Screen shows 3 months being processed: Enero, Febrero, Marzo
- 3 .txt files appear in results_XAXX010101000/metadata/YYYY-MM-DD/
- Summary shows total CFDIs and amount across all months

Should NOT happen:

- Only one file is created
- Process stops after first month

---

## download_metadata_noActivity_n0

What is being tested:
System handles months with no invoices gracefully without stopping.

Steps:

1. Run Metadata for a period you know has no activity:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2020-01-01 --fin 2020-01-31 --solicitud Metadata --tipo recibidos --intervalo 30

Expected result:

- Screen shows: "Sin CFDIs en este periodo — continuando."
- No .txt file is created for that month
- System finishes without error

Should NOT happen:

- System crashes or shows a red error
- System stops and requires user action

---

## download_metadata_invalidCer_n0

What is being tested:
System fails clearly when the .cer file path does not exist.

Steps:

1. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/wrong.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-01-01 --fin 2025-01-31 --solicitud Metadata --tipo recibidos

Expected result:

- Screen shows: "Archivo .cer no encontrado"
- System exits immediately without contacting the SAT
- No folder or file is created

Should NOT happen:

- System contacts the SAT before validating files
- System crashes with an unreadable error

---

## download_metadata_wrongPassword_n0

What is being tested:
System fails clearly when the FIEL password is incorrect.

Steps:

1. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password WrongPass123 --inicio 2025-01-01 --fin 2025-01-31 --solicitud Metadata --tipo recibidos

Expected result:

- Screen shows: "No se pudo cargar la FIEL"
- System exits immediately without contacting the SAT
- No SAT request is made

Should NOT happen:

- System contacts the SAT with invalid credentials
- Error message is unreadable or technical

---

## download_metadata_profileAutoFill_p0

What is being tested:
System loads .cer, .key, and output from saved profile on second run.

Pre-condition:
download_metadata_oneMonth_p0 must have run successfully at least once.

Steps:

1. Run without --cer, --key, or --output:
   python descarga_masiva.py --rfc XAXX010101000 --password M1C0ntr4s3n4 --inicio 2025-02-01 --fin 2025-02-28 --solicitud Metadata --tipo recibidos --intervalo 30

Expected result:

- Screen shows: "Perfil encontrado para RFC XAXX010101000"
- Screen shows: ".cer tomado del perfil"
- Screen shows: ".key tomado del perfil"
- Download completes normally without specifying file paths

Should NOT happen:

- System asks for --cer or --key
- System ignores the saved profile

---

# 2. CFDI DOWNLOAD

---

## download_cfdi_firstAttempt_p0

What is being tested:
System downloads CFDI XML files for a period on the first attempt.

Steps:

1. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-01-01 --fin 2025-01-31 --solicitud CFDI --tipo recibidos --intervalo 30 --timeout 30
2. Wait for completion or timeout

Expected result:

- Screen shows: "Cache: primera solicitud para este periodo."
- Screen shows: "Periodo efectivo: 2025-01-01 00:00:00"
- Screen shows: "Solicitud registrada en pendientes"
- If SAT responds in time: XML files appear in results_XAXX010101000/cfdi/YYYY-MM-DD/
- If timeout: screen shows "--retomar" instructions

Should NOT happen:

- System submits the request without logging it as pending
- System crashes if SAT takes longer than expected

---

## download_cfdi_secondAttempt_p0

What is being tested:
System applies +1 second offset on second attempt for same period.

Pre-condition:
download_cfdi_firstAttempt_p0 must have run for the same period.

Steps:

1. Run same command as download_cfdi_firstAttempt_p0

Expected result:

- Screen shows: "Cache: 1 intento(s) previo(s) detectado(s)."
- Screen shows: "Bypass activado: offset de +1s"
- Screen shows: "Periodo efectivo: 2025-01-01 00:00:01"

Should NOT happen:

- System uses the same datetime as the first attempt
- Screen shows "primera solicitud" again

---

## download_cfdi_timeoutPending_n0

What is being tested:
System saves request as pending when SAT takes longer than timeout.

Steps:

1. Run with a very short timeout:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-06-01 --fin 2025-06-30 --solicitud CFDI --tipo recibidos --intervalo 30 --timeout 5
2. Wait for timeout message

Expected result:

- Screen shows: "Timeout de 5 min alcanzado"
- Screen shows a --retomar command with the request ID
- Running --pendientes shows the request listed
- No crash or error

Should NOT happen:

- Request is lost after timeout
- System crashes
- System keeps running after timeout

---

# 3. PENDING REQUESTS

---

## pending_showAll_p0

What is being tested:
System shows all pending requests clearly.

Pre-condition:
At least one CFDI request must have timed out (run download_cfdi_timeoutPending_n0 first).

Steps:

1. Run:
   python descarga_masiva.py --pendientes

Expected result:

- Screen shows RFC, request ID, date range, creation time, and elapsed time
- Screen shows the exact --retomar command to use
- Screen shows total number of pending requests

Should NOT happen:

- Empty output when there are pending requests
- System crashes

---

## pending_resumeSingle_p0

What is being tested:
System resumes a specific pending request and downloads the files.

Pre-condition:
A pending request ID must be available from --pendientes output.

Steps:

1. Copy the request ID from --pendientes output
2. Run:
   python descarga_masiva.py --retomar 3a4341a7-81d6-0000-0000-000000000000
3. Type FIEL password when prompted
4. Wait for completion or timeout

Expected result:

- System finds the pending request
- Polling resumes from where it left off
- If SAT responds: XML files downloaded, request removed from pending
- If timeout again: request stays in pending with new instructions

Should NOT happen:

- System cannot find the request ID
- Request disappears from pending without being downloaded

---

## pending_resumeAll_p0

What is being tested:
System resumes all pending requests for all RFCs sequentially.

Pre-condition:
At least one pending request exists.

Steps:

1. Run:
   python descarga_masiva.py --retomar-todas all
2. Type FIEL password for each RFC when prompted

Expected result:

- System processes each pending request one by one
- Password is asked once per RFC, not once per request
- Summary shows: completed / still pending / terminal error
- Completed requests are removed from --pendientes

Should NOT happen:

- Password asked for every single request
- One failed RFC stops the entire process

---

## pending_wrongPassword_n0

What is being tested:
System skips an RFC gracefully when wrong password is provided during --retomar-todas.

Steps:

1. Run:
   python descarga_masiva.py --retomar-todas all
2. Enter wrong password when prompted for one of the RFCs

Expected result:

- Screen shows: "Contrasena incorrecta para RFC — saltando"
- System continues with the next RFC
- Wrong RFC requests remain in pending

Should NOT happen:

- System crashes
- System skips all RFCs because one password was wrong

---

# 4. RFC PROFILE

---

## profile_showSaved_p0

What is being tested:
System shows saved RFC profile with file status.

Pre-condition:
At least one successful Metadata download must have completed.

Steps:

1. Run:
   python descarga_masiva.py --perfil XAXX010101000

Expected result:

- Screen shows .cer path with "existe" status
- Screen shows .key path with "existe" status
- Screen shows output folder, interval, and save date

Should NOT happen:

- Empty output
- System crashes

---

## profile_missingFile_n0

What is being tested:
System warns when a file in the saved profile no longer exists on disk.

Steps:

1. Rename or delete the .cer file temporarily
2. Run:
   python descarga_masiva.py --perfil XAXX010101000

Expected result:

- Screen shows .cer path with "NO encontrado en disco" status
- Screen shows warning: pass --cer explicitly to update the profile
- System does not crash

Should NOT happen:

- System silently ignores missing files
- System crashes

---

# 5. CACHE INSPECTION

---

## cache_revealHistory_p0

What is being tested:
System decrypts and shows CFDI attempt history for an RFC.

Pre-condition:
At least one CFDI request must have been submitted.

Steps:

1. Run:
   python descarga_masiva.py --reveal-cache XAXX010101000

Expected result:

- Screen shows period dates, number of attempts, last attempt date
- Screen shows next offset in seconds
- Content is human-readable

Should NOT happen:

- Raw encrypted content shown
- System crashes

---

## cache_noHistory_n0

What is being tested:
System shows clear message when no CFDI history exists for an RFC.

Steps:

1. Run with an RFC that has never had a CFDI request:
   python descarga_masiva.py --reveal-cache XAXX010101000

Expected result:

- Screen shows: "No existe historial todavia"
- System exits cleanly

Should NOT happen:

- Error or crash
- Confusing output

---

## cache_missingSalt_n0

What is being tested:
System fails clearly when SAT_CACHE_SALT is not set in .env

Steps:

1. Remove or comment out SAT_CACHE_SALT from .env
2. Run any command:
   python descarga_masiva.py --pendientes

Expected result:

- Screen shows: "Variable de entorno SAT_CACHE_SALT no definida"
- Screen shows setup instructions
- System exits without doing anything

Should NOT happen:

- System runs with no encryption
- Cryptic Python error appears

---

# 6. EXCEL GENERATION

---

## excel_fullFlow_singleMonth_p0

What is being tested:
System generates Excel working paper for a single month.

Steps:

1. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-03-01 --fin 2025-03-31 --flujo-completo --despacho "Despacho Ejemplo SC"
2. Wait for completion
3. Open the .xlsx file in Microsoft Excel

Expected result:

- Excel file appears in results_XAXX010101000/
- File opens without warnings or errors
- File has exactly 6 sheets: ingresos, gastos, Impuestos, Papel de Trabajo, INGRESOS YYYY, Calculos
- "Despacho Ejemplo SC" appears in Papel de Trabajo header

Should NOT happen:

- Excel shows "We found a problem" warning
- File has more or fewer than 6 sheets
- Despacho name is missing

---

## excel_fullFlow_multiMonth_p0

What is being tested:
System generates Excel with data for multiple months stacked in each sheet.

Steps:

1. Run:
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-01-01 --fin 2025-03-31 --flujo-completo --despacho "Despacho Ejemplo SC"
2. Open the generated .xlsx file

Expected result:

- File named XAXX010101000_2025-01\_\_2025-03.xlsx
- ingresos sheet shows Enero, Febrero, Marzo blocks with separators
- gastos sheet shows same monthly structure
- INGRESOS YYYY sheet shows 12 months, January to March with data, rest blank

Should NOT happen:

- Only one month of data in each sheet
- Separate files per month

---

## excel_emptyIncome_n0

What is being tested:
Excel generates correctly when RFC has no issued invoices (empty ingresos).

Steps:

1. Run flujo-completo for an RFC that only receives invoices (no emissions):
   python descarga_masiva.py --rfc XAXX010101000 --cer certs/XAXX010101000/fiel.cer --key certs/XAXX010101000/fiel.key --password M1C0ntr4s3n4 --inicio 2025-01-01 --fin 2025-01-31 --flujo-completo --despacho "Despacho Ejemplo SC"
2. Open the generated .xlsx file

Expected result:

- Excel opens without errors
- ingresos sheet shows: "Sin ingresos registrados en el periodo."
- All other sheets have correct data

Should NOT happen:

- Excel shows formula error in ingresos sheet
- Excel fails to open

---

## excel_cancelledExcluded_n0

What is being tested:
Cancelled CFDIs do not appear in any Excel sheet.

Steps:

1. Generate Excel for a period that has both active and cancelled invoices
2. Open the .xlsx file
3. Check the gastos sheet for any row with "Cancelado" in the Estatus column

Expected result:

- No rows with "Cancelado" appear in ingresos or gastos sheets
- Totals reflect only active invoices

Should NOT happen:

- Cancelled invoices appear in any data sheet
- Cancelled invoices are included in totals

---

## excel_paymentComplements_n0

What is being tested:
Payment complements (tipo P) appear only as reference in gastos, never in totals.

Steps:

1. Generate Excel for a period that has payment complements
2. Open gastos sheet
3. Check the subtotal row at the end of each month block

Expected result:

- Payment complements appear in a separate section labeled "reference only"
- Subtotal does NOT include complement amounts
- Total row does NOT include complement amounts

Should NOT happen:

- Complement amounts are added to the subtotal
- Complements appear in the ingresos sheet

---

# 7. SAT DATA QUALITY

---

## data_zeroAmountCfdi_p0

What is being tested:
CFDIs with zero amount appear in sheets without breaking calculations.

Steps:

1. Generate Excel for a period that may contain zero-amount CFDIs
2. Open ingresos or gastos sheet
3. Look for rows with 0.00 in the Monto column

Expected result:

- Zero-amount rows appear in the sheet
- Subtotal and total calculate correctly (zero adds nothing)

Should NOT happen:

- Zero-amount CFDIs are excluded
- Total shows an error or unexpected value

---

## data_uppercaseLowercaseUuid_p0

What is being tested:
System handles UUIDs in any case format without duplication.

Steps:

1. Generate Excel for any period
2. Open ingresos or gastos sheet
3. Check UUID column for duplicates

Expected result:

- Each invoice appears exactly once regardless of UUID case format
- No duplicate rows

Should NOT happen:

- Same invoice appears twice with different UUID casing

---

# 8. ENVIRONMENT AND SETUP

---

## setup_freshInstall_p0

What is being tested:
System installs and runs correctly from a clean state.

Steps:

1. Clone the repository to a new folder
2. Run:
   python -m pip install cfdiclient openpyxl python-dotenv cryptography --target ./libs --break-system-packages
3. Copy .env.example to .env and set SAT_CACHE_SALT
4. Run:
   python descarga_masiva.py --help

Expected result:

- No installation errors
- Help text displays with all argument groups
- No import errors

Should NOT happen:

- Any module import error
- Help text is empty or malformed

---

## setup_missingLibs_n0

What is being tested:
System fails clearly when libs/ folder is missing.

Steps:

1. Rename libs/ to libs_backup/
2. Run any command:
   python descarga_masiva.py --help

Expected result:

- Python shows a clear ImportError indicating which library is missing
- Message is readable

Should NOT happen:

- System runs silently with wrong behavior
- Cryptic error with no indication of cause

---

## setup_pathWithSpaces_p0

What is being tested:
System works correctly when project folder path contains spaces. (Windows specific)

Steps:

1. Copy project to a folder with spaces in the path, e.g.: C:\My Projects\taxcrawler-dm
2. Run:
   python descarga_masiva.py --help

Expected result:

- Help text displays normally
- No path-related errors

Should NOT happen:

- System fails to find libs/ or other files
- Any path error

---

# 9. REGRESSION CHECKLIST — Phase 3 Restructure

Run these after moving files to core/, services/, and cli/ to confirm behavior is identical.

---

## regression_cliHelp_p0

Steps:
python cli/main.py --help

Expected: identical output to python descarga_masiva.py --help

---

## regression_metadataDownload_p0

Steps:
Run same Metadata command using cli/main.py instead of descarga_masiva.py

Expected: identical files created, identical log output

---

## regression_profileSaved_p0

Steps:
Run Metadata, then check --perfil

Expected: profile saved and readable after restructure

---

## regression_pendingCreated_p0

Steps:
Run CFDI with short timeout, then check --pendientes

Expected: request appears in pending after restructure

---

## regression_excelGenerated_p0

Steps:
Run --flujo-completo using cli/main.py

## Expected: identical Excel file generated, opens without errors

# 10. RESULTS HISTORY

---

## history_saveOnComplete_p0

What is being tested:
A completed operation is automatically saved to the encrypted results history.

Steps:

1. Run a full flow or metadata download via UI or CLI
2. Open the Resultados tab in the UI
3. Click on the Archivos subtab

Expected result:

- The downloaded files appear as cards with icon, name, date, RFC, and operation
- Excel card shows Abrir button
- TXT or XML cards show correct icons

Should NOT happen:

- Tab is empty after a completed download
- Cards show no metadata (date, RFC, operation)

---

## history_fileExistsCheck_p0

What is being tested:
Cards correctly show whether the file exists on disk.

Steps:

1. Complete a download to generate history entries
2. Rename or move the generated Excel file
3. Refresh the Archivos tab

Expected result:

- Card shows: ⚠ Archivo no encontrado en este equipo
- Abrir button is disabled or hidden

Should NOT happen:

- Card shows Abrir button for a file that does not exist
- App crashes when file is missing

---

## history_deleteEntry_p0

What is being tested:
Deleting a history entry removes it from the list without deleting the file.

Steps:

1. Open Archivos tab with at least one entry
2. Click the 🗑 button on a card
3. Check that the file still exists on disk

Expected result:

- Card disappears from the list after delete
- File still exists on disk at its original path
- Refreshing the tab does not show the deleted entry

Should NOT happen:

- File is deleted from disk
- Entry reappears after refresh

---

## history_multipleRFCs_p0

What is being tested:
History shows entries from multiple RFCs, not just the last one.

Pre-condition:
At least 2 different RFCs must have completed downloads.

Steps:

1. Open Archivos tab
2. Check that entries from both RFCs appear

Expected result:

- Cards from RFC 1 and RFC 2 both visible
- Each card shows its own RFC in the meta section

Should NOT happen:

- Only the most recent RFC appears
- Older entries are overwritten

---

## history_portableCache_p0

What is being tested:
Results history is readable on another PC with the same SAT_CACHE_SALT.

Steps:

1. Copy .cache/results_history.enc to another PC
2. Set the same SAT_CACHE_SALT in .env on the other PC
3. Open the UI and check the Archivos tab

Expected result:

- History entries appear correctly
- Files marked as ⚠ if paths do not exist on the new PC

Should NOT happen:

- Decryption fails with same salt
- App crashes when opening foreign cache file

---

# 11. PROFILES LIST

---

## profiles_showAll_p0

What is being tested:
Perfiles tab shows all saved RFC profiles.

Pre-condition:
At least 2 RFCs must have completed downloads (profiles auto-saved).

Steps:

1. Open Resultados tab
2. Click Perfiles subtab

Expected result:

- All saved profiles appear as ProfileCards
- Each card shows RFC, FIEL status badge, output path, saved date

Should NOT happen:

- Only the most recent RFC profile appears
- Tab is empty when profiles exist

---

## profiles_useProfile_p0

What is being tested:
Clicking Usar perfil fills the download form and navigates to Descarga tab.

Steps:

1. Open Perfiles tab
2. Click Usar perfil on any card
3. Check that the Descarga tab is now active

Expected result:

- Descarga tab becomes active
- RFC, .cer, .key, and output folder are filled from the selected profile
- No widget overlap or rendering issue

Should NOT happen:

- Tab does not change
- Form fields are empty after selecting profile
- Widgets from Resultados tab appear over the form

---

## profiles_fielsStatusBadge_p0

What is being tested:
Profile badge correctly reflects FIEL file existence on disk.

Steps:

1. Move or rename the .cer file for one RFC
2. Refresh the Perfiles tab

Expected result:

- Badge changes to orange: ⚠ FIEL incompleta
- .cer shows ✗ in the card body

Should NOT happen:

- Badge stays green when .cer is missing

---

# 12. REGRESSION CHECKLIST — UI Components

Run after any change to ui/ files.

---

## regression_tabNavigation_p0

Steps:

1. Open the UI
2. Click Resultados tab
3. Click Descarga tab

Expected: no widget overlap, clean render each time

---

## regression_profileFill_p0

Steps:

1. Open Perfiles tab
2. Click Usar perfil
3. Check Descarga tab

Expected: form filled, no overlap, Iniciar button visible

---

## regression_pendingResume_p0

Steps:

1. Have at least one pending CFDI request
2. Open Pendientes tab
3. Click Retomar, enter password

Expected: progress window opens, polling starts

---

## regression_historyPersists_p0

Steps:

1. Complete a download
2. Close and reopen the UI
3. Open Archivos tab

Expected: previous download appears in history
