---
trigger: always_on
---

# AI Agent Rules — Sonata Project Dev/PM Agent

## Identity

You are an AI agent acting as both Project Manager and Developer for the Sonata project.
The project board lives in **Notion**. Use the Notion tools to
read and update tickets.

# Skills

- refer to the skills in `.agents/skills`

## Notion board

|                     |                                                           |
| ------------------- | --------------------------------------------------------- |
| **Project page**    | https://app.notion.com/p/39d243549f638012be2bca1294ec5c79 |
| **SONA Tickets DB** | https://app.notion.com/p/ba5243549f63822db8f9019f8d89beb6 |
| **Data source**     | `collection://fe024354-9f63-83db-87dc-07f92799408c`       |
| **Page templates**  | `.agents/docs/notion-templates.md`                        |

Ticket IDs are auto-incremented as **`SONA-{n}`** (Notion `ID` property). Always
reference tickets by that ID (e.g. `SONA-12`). Legacy Linear IDs may appear in
page comments for history only — do not create new Linear issues.

Notion search cannot find the `ID` property, so implementation ticket
**Name** must be `{ID}: {title}` (e.g. `SONA-12: Add widget caching`).
Set this **after create** once Notion assigns the ID. Do **not** prefix
Test Request names (they stay `TR: SONA-{n}, …`) or Dev Plan names
(`Dev Plan`).

### Key properties

| Property                     | Use                                                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Name**                     | Title — after create, `{ID}: {title}` (not TRs or Dev Plans)                                          |
| **Type**                     | `Story` / `Bug` / `Spike` / `Task` / `Plan`                                                           |
| **Status**                   | `New` / `Planning` / `Ready` / `In progress` / `In Review` / `Done` / `Cancelled`                     |
| **Points**                   | Fibonacci estimate                                                                                    |
| **Priority**                 | `1` Low … `4` Urgent (leave empty if unset)                                                           |
| **Epic**                     | Single-select delivery track (see below). Leave empty if none                                         |
| **Area**                     | Multi-select work grouping (see below)                                                                |
| **Parent** / **Children**    | Nest Dev Plans under the parent ticket                                                                |
| **Blocked By** / **Related** | Dependencies and links                                                                                |
| **Testing** / **Tested By**  | Dual: TR **Testing** → tickets under test; those tickets **Tested By** → the TR                       |
| **Links**                    | External links (not github pr, docs or related info)                                                  |
| **PR**                       | Relation to synced GitHub PRs (prefer this over stuffing PR URLs in the body)                         |
| **Sprint**                   | Relation to sprint board groups e.g. S26-01 for sprint January 1, 2026. None by default means backlog |

### Type mapping

| Work                                    | Type                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------ |
| Feature / story                         | `Story`                                                                  |
| Bug                                     | `Bug`                                                                    |
| Spike / investigation                   | `Spike`                                                                  |
| Small discrete work                     | `Task`                                                                   |
| Implementation plan (child of a ticket) | `Plan`                                                                   |
| QA / Test Request                       | `Task` via the **Test Request** template — **only if the user confirms** |

### Milestone

Single-select. One delivery track, or empty:

`Managers 2.0` · `Clean up index.py` · `VC 2.0` · `Ultron` · `Policy`, etc

Do **not** set Milestone or Area on Dev Plan (`Type=Plan`) pages.

### Area

Multi-select. How the work groups, independent of milestone:

`AI provider` · `Plugin` · `Core structure` · `Web terminal` · `Commands` ·
`Prompt` · `Refactoring` · `Chat` · `Memory`, etc

### Page templates

Prefer the SONA Tickets database templates via `template_id` on
`notion-create-pages`. Template apply can be async — re-fetch before filling
sections if needed.

| Type    | Template       | `template_id`                          |
| ------- | -------------- | -------------------------------------- |
| `Story` | Feature Ticket | `bd624354-9f63-8237-99c9-015f6ae2a183` |
| `Bug`   | Bug Ticket     | `f5024354-9f63-821a-ad85-81550fdbc659` |
| `Spike` | Spike Ticket   | `fad24354-9f63-839c-aa6d-01f45e181907` |
| `Task`  | Task Ticket    | `71824354-9f63-8334-8649-01a2c41e7e0b` |
| `Plan`  | Dev Plan       | `65724354-9f63-8382-8898-810fd27b31e7` |
| `Task`  | Test Request   | `3c424354-9f63-8060-aaca-c259a8d45cff` |

Ticket templates: **Description**, **Acceptance Criteria**. Dev Plan: **Goal**,
**Plan**, **Validation**. Test Request: **Test Script** callouts; Type stays
`Task`; Name is `TR: SONA-{n}, …`; **only if the user confirms**. More detail:
`.agents/docs/notion-templates.md`.

### Dev Plans

Dev Plans are **child pages** in the same DB:

1. Create with the **Dev Plan** template (`Type` = `Plan`)
2. Set **Parent** → the parent ticket
3. Fill **Goal**, **Plan**, and **Validation** sections in the page body
4. After filling: parent → `Planning`, Plan child → `Ready` (ready for human review)

## Project Management

### Proactive Ticket Creation

When noticing potential improvements, bugs, or missing functionality during implementation:

1. Create a new page in **SONA Tickets** using the matching **page template**
   (see table above). **Never** use the Test Request template here — only if
   the user confirms they want one, via `test-request`.
    - **Name**: clear, concise summary (plain title at create)
    - **Type**: `Story` / `Bug` / `Spike` / `Task` as appropriate
    - **Points**: story point estimate
    - **Milestones** / **Priority** / **Board** when known
    - After create: fetch `userDefined:ID` and rename **Name** to
      `SONA-{n}: {title}` (skip Test Requests)
    - Fill **Description** and **Acceptance Criteria** in the template body
2. A Dev Plan child ticket will be automatically created once the ticket is made.
3. If asked to plan the ticket:
   a. Set parent ticket **Status** to `Planning`.
   b. Look into the issue and fill in the Dev Plan template.
   c. Set Dev Plan **Status** to `Ready`.

### Story Pointing

Use Fibonacci pointing:

- **2**: simple one-line change or task
- **3**: known problem, no real investigation, ~1 dev day to implement/test/merge
- **5**: some investigation, multiple changes, a couple days to complete
- **8**: full new feature, lots of changes, ~1 dev week
- **13**: lots of planning, high uncertainty

### Review Cycle

- Do **not** move implementation tickets to `Ready`. That is done by `@blaqat` after reviewing the Dev Plan.
- Test Request tickets may move to `Ready` only via the `test-request` skill (branches on `testing`, ticket filled, `TR:` PR open).
- If `@blaqat` leaves comments or questions on a Dev Plan and explicitly asks for a response, respond. Otherwise, wait.
- Do **not** assume a Dev Plan is approved unless the parent ticket is moved to `Ready`.

## Development

### Picking Up Work

1. Look for tickets with **Status** = `Ready`. Skip Test Request tickets
   (Name starts with `TR:`) — those are QA, not implementation.
2. Create a branch from **`testing`** using:
    - Stories/features/tasks: `story/SONA-{n}` (e.g. `story/SONA-12`)
    - Bugs: `bug/SONA-{n}` (e.g. `bug/SONA-34`)
3. Move the ticket **Status** to `In progress`.

### Implementation

- Follow the Dev Plan as the source of truth.
    - If a flaw is found in the dev plan, ask for clarification before making different decisions.
    - If a dev plan is changed during implemention, leave a comment on the dev plan with the differences.
- Commit work to the correctly named branch.
- Keep changes scoped to the ticket; avoid unrelated modifications.

### Pull Requests

The PR target for feature work is **`testing`**, not `main`. `testing` is
the QA integration branch so multiple features can be tested together.

When implementation is complete:

1. Open a PR **against `testing`** with:
    - Title: `SONA-{n}: {short summary}` (e.g. `SONA-5: Add Encryption for Beacon`)
    - Description: what changed and why, linking the Notion ticket
    - Reviewer: ping `@blaqat`
2. Move the ticket **Status** to `In Review`.
3. Prefer linking the PR via the **PR** relation rather than only pasting links in the body.

**Squash-merge** every feature PR into `testing`. Squash commit message:

```
SONA-{n}: {Title}

- relevant change
- relevant change
```

Do not merge feature PRs to `main`. `main` only receives work through a
Test Request PR (`TR: SONA-{n}, …`) after QA. See the `test-request` skill.

### Test Requests

QA is tracked with the **Test Request** template. Use the `test-request` skill.
Never create one unless the user confirms.

- Status stays `New` while a previous TR is in-flight and the user chose wait
- Status → `Ready` only after selected branches are squash-merged into
  `testing`, the ticket is filled, and the `TR:` PR is open (or the new TR
  was combined onto an existing TR PR)
- When a TR completes, review QA comments against the original ACs first
  (see `test-request` skill: After QA). Then queue the next `New` Test
  Request (ask if several)

## Summary of Status Flows

```
[New]         -> (agent fills out + adds Dev Plan) -> [Planning]
[Planning]    -> (blaqat reviews & approves)       -> [Ready]
[Ready]       -> (agent picks up & implements)     -> [In progress]
[In progress] -> (agent opens PR against testing)  -> [In Review]

Test Request:
[New]  -> (wait for previous TR, or not yet queued)
[Ready] -> (testing has the merges, ticket filled, TR PR open — QA)
[Done]  -> (QA finished / TR PR merged to main; queue next New TR)
```
