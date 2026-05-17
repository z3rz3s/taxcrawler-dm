# taxcrawler-dm — Claude Code Context

---

## FIRST — Read these files before any task

1. docs/process/llm-continuity.md <- current state and next steps
2. docs/specification/system-modules.md <- module responsibilities
3. docs/specification/cli-contract.md <- exact CLI behavior
4. docs/process/spec-rules.md <- rules that must never be violated

---

## PROJECT IN ONE SENTENCE

taxcrawler-dm is a Python tool that downloads CFDI invoices from the Mexican SAT
Web Service and generates accounting working papers in Excel format, accessible via
CLI, REST API, and desktop GUI sharing the same core business logic.

---

## CURRENT PHASE

Check docs/process/llm-continuity.md for exact current state.

---

## FOLDER STRUCTURE (TARGET)

```
taxcrawler-dm/
├── libs/          <- all dependencies (shared, like node_modules)
├── core/          <- business logic, no interface dependency
├── services/      <- flow orchestration, calls core/ only
├── cli/           <- CLI entry point, calls services/ only
├── api/           <- FastAPI, calls services/ only
├── ui/            <- CustomTkinter, calls services/ only
└── docs/          <- spec-driven documentation
    ├── foundation/
    ├── specification/
    └── process/
```

---

## CODE CONVENTIONS

- Code in English (variable names, function names, module names, constants)
- Comments and docstrings in Spanish (ASCII only — no accents, no tildes)
- sys.exit() only in cli/main.py — all other modules raise exceptions
- Every user-visible action must produce a log entry
- Passwords must never be stored in any file, cache, or log
- SAT_CACHE_SALT must never be hardcoded — always from .env

---

## LAYER RULES (NEVER VIOLATE)

```
cli/    -> calls services/ only
api/    -> calls services/ only
ui/     -> calls services/ only
services/ -> calls core/ only
core/   -> no knowledge of cli/, api/, ui/, or services/
```

---

## BEFORE MAKING ANY CHANGE

1. State which user story (US-XXX) this change belongs to
   Reference: docs/specification/user-stories.md

2. State which test case validates this change
   Reference: docs/specification/test-cases.md

3. Confirm the change does not break any regression test
   Reference: docs/specification/test-cases.md section 9

4. Confirm the change follows all rules in docs/process/spec-rules.md

---

## NEVER DO WITHOUT EXPLICIT APPROVAL

- Modify any file inside docs/
- Delete any existing file
- Change function signatures in core/ modules
- Add new dependencies outside libs/
- Call sys.exit() outside cli/main.py
- Store passwords or SAT_CACHE_SALT in any file
- Skip a layer in the segment hierarchy

---

## LIBS PATH RESOLUTION

All files resolve libs/ from project root using:

```python
_libs = Path(__file__).resolve().parent.parent / "libs"
if _libs.exists() and str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))
```

Files in core/, services/, cli/, api/, ui/ use parent.parent (two levels to root).

---

## INSTALL COMMAND

```bash
python -m pip install cfdiclient openpyxl python-dotenv cryptography fastapi uvicorn --target ./libs --break-system-packages
```

---

## WHEN TOKENS RUN LOW

Before ending the session:

1. Update docs/process/llm-continuity.md with current state
2. Commit all changes to git
3. Note the exact next step in llm-continuity.md

The next session (any tool) will resume from llm-continuity.md.

---

## FULL SPEC REFERENCE

- docs/foundation/product-definition.md <- domain and product scope
- docs/foundation/architecture.md <- segment map and data flow
- docs/foundation/action-plan.md <- phases and execution plan
- docs/specification/system-modules.md <- module responsibilities
- docs/specification/user-stories.md <- functional requirements
- docs/specification/cli-contract.md <- CLI behavioral contract
- docs/specification/api-contract.md <- API behavioral contract
- docs/specification/ui-spec.md <- UI behavioral contract
- docs/specification/test-cases.md <- manual test cases
- docs/process/spec-rules.md <- rules that must never be violated
- docs/process/llm-workflow.md <- how to switch tools
- docs/process/llm-continuity.md <- current state and next steps
