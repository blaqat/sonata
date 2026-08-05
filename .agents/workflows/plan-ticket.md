---
description: Generate or fill out a Dev Plan for a specific ticket.
---

/plan [SONA-{n}]

1. Fetch the specified Notion ticket

2. If no Dev Plan child exists, create one with `template_id`
   `65724354-9f63-8382-8898-810fd27b31e7` (Dev Plan — **required**);
   set Parent = ticket URL; do not pass `content`

3. Fill **Goal**, **Plan**, and **Validation** via `notion-update-page`

4. Set Dev Plan → `Ready`

5. If ticket was in `New`, move it → `Planning`

6. Output a summary of the plan created
