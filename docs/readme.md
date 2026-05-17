# Documentation Index — taxcrawler-dm

Read in this order if you are new to the project.

---

## 1. Understand the product

Start here to understand the problem, the domain, and what the system does.

- [foundation/product-definition.md](./foundation/product-definition.md) What problem this solves, who uses it, domain definitions (RFC, FIEL, CFDI, Metadata, Papel de Trabajo, RESICO, PFAE), core capabilities, and constraints.

---

## 2. Understand the architecture

How the system is organized and why.

- [foundation/architecture.md](./foundation/architecture.md) Segment map (core, services, cli, api, ui), module responsibilities, data flow per segment, folder structure, dependency resolution, and design principles.

---

## 3. Understand the rules

What you must follow before writing any code.

- [process/spec-rules.md](./process/spec-rules.md) 14 rules covering source of truth, segment separation, code language conventions, logging requirements, password handling, and what constitutes a violation.

---

## 4. Understand what is done and what comes next

Where the project stands and where it is going.

- [foundation/action-plan.md](./foundation/action-plan.md) Phases 1-10 with completed, next, and planned status.
- [ROADMAP.md](https://claude.ai/ROADMAP.md) Same information in a more readable format for external contributors.

---

## 5. Understand the module contracts

Exact responsibilities and boundaries per module before touching any file.

- [specification/system-modules.md](./specification/system-modules.md) Every module in core/, services/, cli/, api/, and ui/ with its operations, inputs, outputs, and constraints.
- [specification/user-stories.md](./specification/user-stories.md) Functional requirements as testable stories with acceptance criteria and status. US-001 to US-013 covering all completed and planned features.
- [specification/test-cases.md](./specification/test-cases.md) Manual test cases for every feature. Written for non-technical users. Covers happy paths, sad paths, edge cases, data quality, environment, and regression.

---

## 6. Understand the interface contracts

What each interface accepts and returns.

- [specification/cli-contract.md](./specification/cli-contract.md) Every CLI argument, validation rule, output structure, and error behavior.
- [specification/api-contract.md](./specification/api-contract.md) Every FastAPI endpoint, request body, response structure, and error codes.
- [specification/ui-spec.md](./specification/ui-spec.md) Every screen, component, interaction, and error behavior for the desktop UI.

---

## 7. Understand how to work with LLMs

How to load context and switch between AI tools without losing consistency.

- [process/llm-continuity.md](./process/llm-continuity.md) Current project state, key decisions, known limitations, what to do next, and which spec files to load per task type. Start here when resuming work.
- [process/llm-workflow.md](./process/llm-workflow.md) Context loading template, full vs partial vs minimal context strategy, rules for using LLMs, and common mistakes to avoid.

---

## Reference files at repository root

Always available without navigating docs/.

- [README.md](../README.md) — project overview, installation, and usage examples
- [FLOWS.md](../FLOWS.md) — execution flow reference with decision map and module table
- [ROADMAP.md](../ROADMAP.md) — project status and planned features by version
