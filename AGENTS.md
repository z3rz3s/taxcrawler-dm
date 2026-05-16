# taxcrawler-dm — Agent Context

This file provides context for AI coding agents (Codex, OpenCode, OpenClaw, Cursor, etc.)
operating on this repository.

---

## FIRST — Read these files before any task

1. docs/process/llm-continuity.md <- current state and next steps
2. docs/specification/system-modules.md <- module responsibilities and boundaries
3. docs/specification/cli-contract.md <- exact CLI behavior contract
4. docs/process/spec-rules.md <- 15 rules that must never be violated

---

## PROJECT SUMMARY

taxcrawler-dm downloads CFDI invoices from the Mexican SAT Web Service (SOAP, v1.5)
and generates accounting working papers in Excel format.

Interfaces: CLI (working), FastAPI (planned), CustomTkinter GUI (planned).
All interfaces share the same business logic in core/.

Language: Python 3.13
Dependencies: installed in ./libs/ (shared, no virtualenv)

---

## SEGMENT HIERARCHY

```
cli/ api/ ui/  ->  services/  ->  core/
```

No segment may skip a layer or call a lower segment directly.
core/ has no knowledge of any other segment.

---

## CRITICAL RULES

1. Code in English. Comments and docstrings in Spanish (ASCII only).
2. sys.exit() only in cli/main.py.
3. Passwords never stored in any file, cache, or log.
4. SAT_CACHE_SALT never hardcoded — always from .env.
5. No behavior outside the specification.
6. No file in docs/ modified without explicit user approval.
7. No function signatures in core/ changed without explicit user approval.
8. No new dependencies added outside libs/.

Full rules: docs/process/spec-rules.md

---

## BEFORE ANY CODE CHANGE

State:

- Which user story (US-XXX) this belongs to
- Which test case (test ID) validates this change
- Which modules are affected and why

References:

- docs/specification/user-stories.md
- docs/specification/test-cases.md
- docs/specification/system-modules.md

---

## LIBS PATH RESOLUTION

Every file in core/, services/, cli/, api/, ui/ resolves libs/ as:

```python
_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))
```

---

## INSTALL

```bash
python -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn --target ./libs --break-system-packages
```

---

## CURRENT PHASE

Read docs/process/llm-continuity.md — it contains:

- Exact current state
- Key decisions already made
- Known limitations
- Next step to implement
- Which spec files to load per task type

---

## ACTIONS THAT REQUIRE EXPLICIT USER APPROVAL

- Any modification to docs/
- Deleting any file
- Changing a function signature in core/
- Adding a dependency to libs/
- Calling sys.exit() outside cli/main.py
- Any change that affects existing test cases

---

## FULL DOCUMENTATION INDEX

docs/readme.md contains the full ordered index for contributors.
Start there if you need to navigate the specification.

Key files:

- docs/process/llm-continuity.md <- start here every session
- docs/foundation/architecture.md <- segment map and data flow
- docs/specification/system-modules.md <- what each module does
- docs/specification/test-cases.md <- how to verify behavior
- docs/process/spec-rules.md <- rules that must never be violated
