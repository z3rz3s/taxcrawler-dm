# LLM WORKFLOW — taxcrawler-dm

---

# OBJECTIVE

Define how to use project documentation with different LLM tools (Claude, ChatGPT, Cursor, Copilot, etc.)
while maintaining consistency across sessions and tools.

---

# CORE PRINCIPLE

LLMs do not remember previous context.

Always provide the system specification explicitly when starting a new session.

---

# REQUIRED CONTEXT FILES

Every time you switch chats or tools, provide:

Priority order (if token limit is a concern):

1. cli-contract.md <- defines exact behavior
2. system-modules.md <- defines module responsibilities
3. user-stories.md <- defines what is done and what is planned
4. architecture.md <- defines module map and data flow
5. product-definition.md <- defines domain concepts and terminology

---

# CONTEXT LOADING TEMPLATE

Use this prompt when starting a new session:

---

You are working on taxcrawler-dm, a Python CLI tool that bulk-downloads CFDI invoices
from the Mexican SAT Web Service and generates accounting working papers in Excel format.

Use the following documents as the source of truth:

[PASTE cli-contract.md]

[PASTE system-modules.md]

[PASTE user-stories.md]

Instructions:

- Do not invent behavior outside the specification
- Do not assume missing requirements
- Code must be in English
- Comments and docstrings must be in Spanish (ASCII only, no accents or tildes)
- sys.exit() is only called from descarga_masiva.py
- Every user-visible action must produce a log entry
- Passwords must never be stored in any file
- SAT_CACHE_SALT must never be hardcoded

Task:
[INSERT TASK HERE]

---

# CONTEXT STRATEGY

## Full Context Mode

Use when:

- Designing a new module
- Modifying cli-contract.md
- Adding a new user story
- Reviewing architecture

Provide: all 5 files listed above

---

## Partial Context Mode

Use when:

- Implementing a specific function in one module
- Fixing a bug in an existing module
- Writing tests for a specific flow

Provide: cli-contract.md + relevant module from system-modules.md

---

## Minimal Context Mode

Use when:

- Token limit is critical
- Task is isolated and well-defined

Provide: cli-contract.md only + explicit task description

---

# SWITCHING TOOLS

When switching from Claude to ChatGPT or Cursor:

1. Copy the context loading template
2. Paste cli-contract.md + system-modules.md
3. Describe the exact task
4. Reference the user story ID (e.g. US-010)
5. Paste the current state of the file being modified

---

# RULES WHEN USING LLM

- Never rely on memory between sessions
- Always re-provide specs
- Do not summarize specs when precision is required
- Do not allow the LLM to guess behavior
- If LLM output contradicts spec, reject it and clarify

---

# COMMON MISTAKES

- Starting a session without providing context files
- Letting the LLM assume module responsibilities
- Mixing old and new specs in the same session
- Skipping validation against cli-contract.md after implementation

---

# SUCCESS CRITERIA

- LLM responses match cli-contract.md exactly
- No undefined behavior is introduced
- Output is consistent whether using Claude, ChatGPT, or Cursor

---

# FINAL RULE

The specification is the single source of truth.
The LLM is a tool to implement it — not to define it.
