---
description: Create a new ticket from scratch.
---

/create [title]

1. Ask clarifying questions if title/context is vague

2. Create a page in **SONA Tickets** via `notion-create-pages`; prefer matching
   `template_id`:

   | Type | Template | `template_id` |
   |------|----------|---------------|
   | `Story` | Feature Ticket | `bd624354-9f63-8237-99c9-015f6ae2a183` |
   | `Bug` | Bug Ticket | `f5024354-9f63-821a-ad85-81550fdbc659` |
   | `Spike` | Spike Ticket | `fad24354-9f63-839c-aa6d-01f45e181907` |
   | `Task` | Task Ticket | `71824354-9f63-8334-8649-01a2c41e7e0b` |
   | `Task` | Test Request | `3c424354-9f63-8060-aaca-c259a8d45cff` |

   **Never** use Test Request unless the user confirms they want one — then
   use the `test-request` skill instead (Type stays `Task`; Name is
   `TR: SONA-{n}, …`).

   Create with a plain **Name** (no ID prefix). Notion assigns `ID` after
   create.

3. Fetch the page, read `userDefined:ID`, and rename **Name** to
   `SONA-{n}: {original title}` so Notion search can find it. Skip this
   for Test Requests.

4. Fill **Description** and **Acceptance Criteria** (re-fetch if template
   sections aren't there yet)

5. Create a child Dev Plan with `template_id`
   `65724354-9f63-8382-8898-810fd27b31e7`; fill **Goal**, **Plan**, **Validation**

6. Set parent → `Planning`, Dev Plan → `Ready`

7. Output the Notion ticket link, `SONA-{n}` ID, and summary
