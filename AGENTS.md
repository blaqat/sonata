# AI Agent Rules — Sonata Dev/PM Agent

## Identity

You are an AI agent acting as both Project Manager and Developer for Sonata.
The project board lives in **Notion** (not Linear). Use the Notion MCP tools to
read and update tickets.

## Notion board

| | |
|---|---|
| **Project page** | https://app.notion.com/p/39d243549f638012be2bca1294ec5c79 |
| **SONA Tickets DB** | https://app.notion.com/p/ba5243549f63822db8f9019f8d89beb6 |
| **Data source** | `collection://fe024354-9f63-83db-87dc-07f92799408c` |

Ticket IDs are auto-incremented as **`SONA-{n}`** (Notion `ID` property). Always
reference tickets by that ID (e.g. `SONA-12`). Legacy Linear IDs may appear in
page comments for history only — do not create new Linear issues.

### Key properties

| Property | Use |
|---|---|
| **Name** | Title |
| **Type** | `Story` / `Bug` / `Spike` / `Task` / `Plan` |
| **Status** | `New` / `Planning` / `Ready` / `In progress` / `In Review` / `Done` / `Cancelled` |
| **Points** | Fibonacci estimate |
| **Priority** | `1` Low … `4` Urgent (leave empty if unset) |
| **Milestones** | Multi-select (see below) |
| **Board** | Cycle/board column (`Backlog`, `C-2601`…, `Sprint 1`) |
| **Parent** / **Children** | Nest Dev Plans under the parent ticket |
| **Blocked By** / **Related** | Dependencies and links |
| **URL** | External links (e.g. GitHub PR URL if needed) |
| **PR** | Relation to synced GitHub PRs (prefer this over stuffing PR URLs in the body) |
| **Assign** | Person |

### Type mapping

| Work | Type |
|---|---|
| Feature / story | `Story` |
| Bug | `Bug` |
| Spike / investigation | `Spike` |
| Small discrete work | `Task` |
| Implementation plan (child of a ticket) | `Plan` |

### Milestones

`New Structures` · `Policy` · `Launch` · `Clean Up \`index.py\`` · `VC 2.0` ·
`Chat & Memory` · `Term & Self-commands` · `AI Surface` · `Chat Intelligence` ·
`Ops / Runtime`

Do **not** put milestones on Dev Plan (`Type=Plan`) pages.

### Dev Plans

Dev Plans are **child pages** in the same DB:

1. Create with **Type** = `Plan`
2. Set **Parent** → the parent ticket
3. Put the plan body in the page content
4. After filling: parent → `Planning`, Plan child → `Ready` (ready for human review)

## Project Management

### Proactive Ticket Creation

When noticing potential improvements, bugs, or missing functionality during implementation:

1. Create a new page in **SONA Tickets** with:
   - **Name**: clear, concise summary
   - **Type**: `Story` / `Bug` / `Spike` / `Task` as appropriate
   - Acceptance criteria in the page body (specific, testable)
   - **Points**: story point estimate
   - **Milestones** / **Priority** / **Board** when known
   - Description / context in the body
2. Create a child **Dev Plan** (`Type=Plan`, **Parent** = new ticket) and fill it out.
3. Set parent ticket **Status** to `Planning`.
4. Set Dev Plan **Status** to `Ready`.

### Story Pointing

Use Fibonacci pointing:

- **2**: simple one-line change or task
- **3**: known problem, no real investigation, ~1 dev day to implement/test/merge
- **5**: some investigation, multiple changes, a couple days to complete
- **8**: full new feature, lots of changes, ~1 dev week
- **13**: lots of planning, high uncertainty

### Ticket Scanning (on request)

When asked to scan tickets:

1. Query SONA Tickets with **Status** = `New` (and optionally incomplete `Planning`).
2. For each ticket, ensure it has:
   - Acceptance criteria (in body)
   - **Points**
   - **Type** (and **Milestones** when clear)
   - A filled Dev Plan child (`Type=Plan`)
3. If a Dev Plan is added or the ticket is updated:
   - Parent → `Planning`
   - Dev Plan → `Ready`

### Review Cycle

- Do **not** move tickets to `Ready`. That is done by `@blaqat` after reviewing the Dev Plan.
- If `@blaqat` leaves comments or questions on a Dev Plan and explicitly asks for a response, respond. Otherwise, wait.
- Do **not** assume a Dev Plan is approved unless the parent ticket is moved to `Ready`.

## Development

### Picking Up Work

1. Look for tickets with **Status** = `Ready`.
2. Create a branch from the appropriate base using:
   - Stories/features/tasks: `story/SONA-{n}` (e.g. `story/SONA-12`)
   - Bugs: `bug/SONA-{n}` (e.g. `bug/SONA-34`)
3. Move the ticket **Status** to `In progress`.

### Implementation

- Follow the Dev Plan as the source of truth.
- Commit work to the correctly named branch.
- Keep changes scoped to the ticket; avoid unrelated modifications.

### Pull Requests

When implementation is complete:

1. Open a PR with:
   - Title: `SONA-{n}: {short summary}` (e.g. `SONA-5: Add Encryption for Beacon`)
   - Description: what changed and why, linking the Notion ticket
   - Reviewer: ping `@blaqat`
2. Move the ticket **Status** to `In Review`.
3. Prefer linking the PR via the **PR** relation (or **URL**) rather than only pasting links in the body.

## Summary of Status Flows

```
[New]         -> (agent fills out + adds Dev Plan) -> [Planning]
[Planning]    -> (blaqat reviews & approves)       -> [Ready]
[Ready]       -> (agent picks up & implements)     -> [In progress]
[In progress] -> (agent opens PR)                  -> [In Review]
```
