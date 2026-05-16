# SPEC RULES — taxcrawler-dm

---

# Source of Truth

The following documents define system behavior:

- specification/system-modules.md
- specification/user-stories.md
- specification/cli-contract.md
- specification/api-contract.md
- specification/ui-spec.md
- FLOWS.md

---

# Rule 1

If a behavior is not defined in these documents: -> It must not be implemented

---

# Rule 2

If documents conflict: -> cli-contract.md has priority for CLI behavior -> api-contract.md has priority for API behavior -> ui-spec.md has priority for UI behavior -> system-modules.md has priority for module responsibilities

---

# Rule 3

User stories define requirements Contracts define exact behavior

---

# Rule 4

No assumptions are allowed during implementation

---

# Rule 5

All implementations must trace back to a defined user story

---

# Rule 6

Code must be in English Comments and docstrings must be in Spanish (ASCII only — no accents, no tildes)

---

# Rule 7

sys.exit() is only called from cli/main.py All other modules raise exceptions

---

# Rule 8

Every user-visible action must produce a log entry Silent failures are not allowed

---

# Rule 9

Passwords must never be stored in any file, cache, log, or API response

---

# Rule 10

SAT_CACHE_SALT must never be hardcoded It must always come from the environment

---

# Rule 11 — Segment Separation

No segment skips a layer:

- cli/, api/, ui/ call services/ only
- services/ calls core/ only
- core/ has no knowledge of cli/, api/, ui/, or services/

---

# Rule 12 — Single libs/ Folder

All dependencies install to the root libs/ folder No segment has its own dependency folder All segments resolve libs/ using parent.parent path from their own location

---

# Rule 13 — No Business Logic Outside core/

Business logic means:

- SAT communication rules
- CFDI filtering rules
- ISR and IVA calculation rules
- Cache encryption and key derivation
- File naming and organization rules

Any of these found in services/, cli/, api/, or ui/ is a violation

---

# Rule 14 — No Interface Logic Inside core/

Interface logic means:

- CLI argument parsing
- HTTP request/response handling
- UI widget rendering
- User prompts (getpass is allowed in config.py only)

Any of these found in core/ is a violation