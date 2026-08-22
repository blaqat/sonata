---
name: project-status
description: Get a snapshot of the current board state. Use this to get an overview of Sonata progress and identify blockers.
---

# Instructions

/status

1. Fetch ticket counts by Status from **SONA Tickets** in Notion

2. Report:
   - Tickets in `New` (ungroomed)

   - Tickets in `Planning` (awaiting Dev Plan review)

   - Tickets in `Ready` (available to pick up)

   - Tickets in `In progress` (actively being worked)

   - Tickets in `In Review` (PRs open against `testing`)

3. Separately report **Test Request** tickets (Name starts with
   `TR:` and/or **Testing** is set):
   - `New` (queued / waiting on an in-flight TR)
   - `Ready` (QA — `TR:` PR open)
   - Whether a `TR:` PR is currently open

4. Flag any blockers or stale tickets (e.g. In progress for 3+ days with no
   commits)
