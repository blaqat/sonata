---
description: Generate or fill out a Dev Plan for a specific ticket.
---

/plan [TICKET_CODE]

1. Fetch the specified ticket

2. If no Dev Plan subtask exists, create one using the Dev Plan template

3. Fill out the Dev Plan based on ticket context, acceptance criteria, and
   codebase understanding

4. Set Dev Plan subtask → Ready for Review

5. If ticket was in TODO, move it → Planning

6. Output a summary of the plan created
