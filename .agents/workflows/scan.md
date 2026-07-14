---
description: Audit all New tickets for completeness.
---

1. Fetch all SONA Tickets in Notion with Status = `New`

2. For each ticket, check for:
   - Acceptance criteria

   - Points (estimation)

   - Type / Milestones when clear

   - Dev Plan child (`Type=Plan`)

3. If anything is missing, fill it out

4. Once complete: parent → `Planning`, Dev Plan → `Ready`

5. Output a summary of what was updated and what was already complete
