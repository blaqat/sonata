---
name: scan
description: Audit all New tickets for completeness. Use this to ensure backlog tickets have acceptance criteria, estimation, and a Dev Plan.
---

# Instructions

1. Fetch all SONA Tickets in Notion with Status = `New`

2. **Skip Test Request tickets** (Name starts with `TR:` and/or
   **Testing** is set). Do not add a Dev Plan, do not move them to
   `Planning`, and do not create a Test Request.

3. For each other ticket, check for:
   - **Name** is `{ID}: {title}` (e.g. `SONA-12: Add widget caching`).
     If missing, fetch `userDefined:ID` and rename. Do not prefix TRs.

   - Acceptance criteria

   - Points (estimation)

   - Type / Milestones when clear

   - Dev Plan child (`Type=Plan`, Dev Plan template
     `65724354-9f63-8382-8898-810fd27b31e7`)

4. If anything is missing, fill it out. Use the Feature / Bug / Task / Spike
   templates from the map in `AGENTS.md` when creating missing pages.

5. Once complete: parent → `Planning`, Dev Plan → `Ready`

6. Output a summary of what was updated and what was already complete
