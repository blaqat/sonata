---
name: plan-ticket
description: Generate or fill out a Dev Plan for a specific ticket. Use this when a ticket is in New or Planning and needs a detailed implementation plan.
---

# Instructions

/plan [SONA-{n}]

1. Fetch the specified Notion ticket

2. If no Dev Plan child exists, create one (`Type=Plan`, Parent = ticket)

3. Fill out the Dev Plan based on ticket context, acceptance criteria, and
   codebase understanding

4. Set Dev Plan → `Ready`

5. If ticket was in `New`, move it → `Planning`

6. Output a summary of the plan created
