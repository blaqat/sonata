---
description: Orchestrate work via subagents only — parent thinks/reviews, never edits.
---

# /delegate

Parent model is orchestrator-only: plan, review, and create subagents until done.
Do not run tools or edit files yourself — only use `Task`.

## Model routing

- Needs thinking / judgment / debugging → **Cursor Grok 4.5 High Fast** (`cursor-grok-4.5-high-fast`)
- Well-defined or simple work → **Composer 2.5 Fast** (`composer-2.5-fast`)
- If unsure → Grok

## Loop

1. Decompose the user task into clear subagent jobs
2. Launch `Task` subagents with full context (children inherit none)
3. Review outputs against acceptance criteria
4. Spawn follow-ups / `resume` until complete
5. Summarize results for the user

Full instructions: `.agents/skills/delegate/SKILL.md`
