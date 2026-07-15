---
name: pickup
description: Grab the next available ticket to implement. This triggers the process of starting work on a Ready ticket.
---

# Instructions

1. Fetch all SONA Tickets in Notion with Status = `Ready`

2. Select the highest Priority ticket (or let user specify `SONA-{n}`)

3. Create a branch: `story/SONA-{n}` or `bug/SONA-{n}`

4. Move ticket → `In progress`

5. Output the ticket summary, acceptance criteria, and Dev Plan for reference
