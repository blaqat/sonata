---
description: Audit all New tickets for completeness.
---

1. Fetch all SONA Tickets in Notion with Status = `New`

2. **Skip Test Request tickets** (Name starts with `TR:` and/or
   **Testing** is set). Do not add a Dev Plan or move them to `Planning`.

3. For each other ticket, check for:
   - Acceptance criteria

   - Points (estimation)

   - Type / Milestones when clear

   - Dev Plan child (`Type=Plan`)

4. If anything is missing, fill it out

5. Once complete: parent → `Planning`, Dev Plan → `Ready`

6. Output a summary of what was updated and what was already complete
