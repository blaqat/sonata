---
name: pickup
description: Grab the next available ticket to implement. This triggers the process of starting work on a Ready ticket.
---

# Instructions

1. Fetch all SONA Tickets in Notion with Status = `Ready`

2. Skip Test Request tickets (Name starts with `TR:`). Those are
   QA — use `test-request`, not pickup.

3. Select the highest Priority ticket (or let user specify `SONA-{n}`)

4. Create a branch from **`testing`**: `story/SONA-{n}` or `bug/SONA-{n}`

5. Move ticket → `In progress`

6. Output the ticket summary, acceptance criteria, and Dev Plan for reference

PRs for this work target **`testing`**, not `master`. Squash-merge into
`testing` as `SONA-{n}: Title` plus bullets of the relevant changes.
