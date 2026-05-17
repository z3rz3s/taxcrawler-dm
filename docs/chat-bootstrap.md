# Chat Bootstrap

Docs used to kickstart a new project in AI Chats

## Claude — Projects

Create a new project on claude.ai
In “Project Instructions,” paste the contents of llm-continuity.md and spec-rules.md
Upload the files from the docs/ directory as project files:

```
system-modules.md
cli-contract.md
user-stories.md
test-cases.md
architecture.md
```

In the instructions, add the context template from `llm-workflow.md` at the end.
Result: Any chat within that project starts with the full context without having to paste anything.

## ChatGPT — Custom GPT

Create a new GPT on chatgpt.com
In “Instructions,” paste llm-continuity.md + spec-rules.md + the template
In “Knowledge,” upload the same files from docs/
Set: “Only use knowledge from uploaded files”

Result: Same effect as Claude Projects.

## Gemini

Google AI Studio lets you upload files as context:

- Go to aistudio.google.com
- Create a new prompt
- Upload the files from the `docs/` folder as attachments
- In the system prompt, paste the contents of `AGENTS.md`

Gemini Advanced at gemini.google.com doesn't have a robust project system yet—for now, paste the template from `llm-workflow.md` at the start of each session.

## Other AI Chats with no projects feature (Deepseek, Qwen, Grok, etc)

Message 1: Paste the entire AGENTS.md file
Message 2: Paste llm-continuity.md
Message 3: Paste system-modules.md, api-contract,md and cli-contract.md
Message 4: Describe the task
