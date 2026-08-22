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

3. Fill **Description** and **Acceptance Criteria** (re-fetch if template
   sections aren't there yet)

4. Create a child Dev Plan with `template_id`
   `65724354-9f63-8382-8898-810fd27b31e7`; fill **Goal**, **Plan**, **Validation**

5. Set parent → `Planning`, Dev Plan → `Ready`

6. Output the Notion ticket link, `SONA-{n}` ID, and summary
