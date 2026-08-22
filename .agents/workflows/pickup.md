---
description: Grab the next available ticket to implement.
---

1. Fetch all SONA Tickets in Notion with Status = `Ready`

2. Skip Test Request tickets (Name starts with `TR:`)

3. Select the highest Priority ticket (or let user specify `SONA-{n}`)

4. Create a branch from **`testing`**: `story/SONA-{n}` or `bug/SONA-{n}`

5. Move ticket → `In progress`

6. Output the ticket summary, acceptance criteria, and Dev Plan for reference

PRs target **`testing`**. Squash-merge as `SONA-{n}: Title` plus bullets.
