---
name: plan-ticket
description: Generate or fill out a Dev Plan for a specific ticket. Use this when a ticket is in New or Planning and needs a detailed implementation plan.
---

# Instructions

/plan [SONA-{n}]

1. Fetch the specified Notion ticket

2. If no Dev Plan child exists, create one via `notion-create-pages`:
   - `parent`: `{ "data_source_id": "fe024354-9f63-83db-87dc-07f92799408c" }`
   - `template_id`: `65724354-9f63-8382-8898-810fd27b31e7` (Dev Plan — **required**)
   - `properties`: Name (`Dev Plan`), Type (`Plan`), Parent = ticket URL
   - Do **not** pass `content`

3. Fill **Goal**, **Plan**, and **Validation** via `notion-update-page`
   based on ticket context, acceptance criteria, and codebase understanding

4. Set Dev Plan → `Ready`

5. If ticket was in `New`, move it → `Planning`

6. Output a summary of the plan created
