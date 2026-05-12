# SPEC RULES — taxcrawler-dm

---

# Source of Truth

The following documents define system behavior:

- system-modules.md
- user-stories.md
- cli-contract.md
- FLOWS.md

---

# Rule 1

If a behavior is not defined in these documents:
-> It must not be implemented

---

# Rule 2

If documents conflict:
-> cli-contract.md has priority

---

# Rule 3

User stories define requirements
cli-contract.md defines exact behavior

---

# Rule 4

No assumptions are allowed during implementation

---

# Rule 5

All implementations must trace back to a defined user story

---

# Rule 6

Code must be in English
Comments and docstrings must be in Spanish (ASCII only — no accents, no tildes)

---

# Rule 7

sys.exit() is only called from descarga_masiva.py
All other modules raise exceptions

---

# Rule 8

Every user-visible action must produce a log entry
Silent failures are not allowed

---

# Rule 9

Passwords must never be stored in any file, cache, or log

---

# Rule 10

SAT_CACHE_SALT must never be hardcoded
It must always come from the environment
