---
name: test-request
description: >-
  Create a Notion Test Request for selected open PRs, merge those branches
  into testing, and open or update the TR PR for QA. Use when the user asks
  for a test request, QA request, /test-request, or to queue the next Test
  Request after one is completed.
---

# Test Request

Never create a Test Request ticket unless the user **explicitly confirms** they
want one. Do not create one from scan, new-ticket, or proactive ticket creation.

Test Requests are **Type = `Task`** (there is no Type option named Test
Request). They **must** be created with the **Test Request** database
template (same template list as Bug Ticket, Feature Ticket, Task Ticket,
Dev Plan, Spike Ticket). Identify them by Name starting with `TR:` and/or
a populated **Testing** relation.

## Notion

| | |
|---|---|
| **Template** | Test Request (required — do not create a blank Task) |
| **template_id** | `3c424354-9f63-8060-aaca-c259a8d45cff` |
| **Type** | `Task` (template default — do not invent `Type=Test Request`) |
| **Name** | `TR: SONA-{n}, SONA-{n}` (feature IDs, not the TR ticket's own ID) |

Relations (duals — set one side, the other updates):

- On the **Test Request**: **Testing** → the feature/bug tickets under test
- On each of those tickets: **Tested By** → the Test Request
- On the **Test Request**: **PR** → the TR GitHub PR (the same PR when combining)

Do **not** use **Parent** for Test Requests (Parent is `limit: 1` and is for
Dev Plans). Do **not** create a Dev Plan child.

Pass `template_id` on create. Template apply is async — do **not** send
`content` in the same create. Fetch the page, then copy/fill the existing
blocks.

### Template body to copy

Duplicate the whole callout once per scenario. Fill Scenario / Steps /
Expected from each selected ticket's acceptance criteria. Leave **Result**
for the tester.

```
### Test Script
---
<callout icon="/icons/script_yellow.svg">
	#### Scenario #: Quick Scenario Description
	#### Steps
	- [ ]
	#### Expected
	-
	### Result
	- (Filled out by tester) {color="blue"}
</callout>
```

Minimum one scenario per selected ticket. Number them `Scenario 1`, `Scenario 2`, …

## Git

- Feature PRs target **`testing`**, not `master`
- Squash-merge each selected feature PR into `testing` with:

```
SONA-{n}: {Title}

- relevant change
- relevant change
```

- Then open (or update) a PR **`testing` → `master`**:
  - Title: `TR: SONA-{n}, SONA-{n}` (same feature IDs)
  - Description: a task list of Test Request ticket links only, e.g.

```
- [ ] https://app.notion.com/p/…
```

## In-flight rule

All Test Requests QA on `testing`. An **in-flight** TR is one that is not
`Done`/`Cancelled` and already has an open `TR:` PR.

If one exists, **stop and ask** the user: **combine** with the current TR, or
**wait**.

| Choice | What to do |
|---|---|
| **Combine** | Create/fill the new TR ticket. Squash-merge the newly selected PRs into `testing`. Point **both** TR tickets at the **same** PR (`PR` relation). Update that PR title to include every feature `SONA-{n}` and add the new TR link to the task list. New TR → `Ready`. |
| **Wait** | Create/fill the new TR ticket and set **Testing** / **Tested By**. Status stays **`New`**. Do not merge branches. Do not open a second TR PR. |

## Status

| When | Status |
|---|---|
| Ticket created but previous TR is still in-flight and user chose wait | `New` |
| Branches squash-merged into `testing`, ticket filled, TR PR open (or combined onto the existing PR) | `Ready` |
| QA finished / TR PR merged to `master` | `Done` |

`Ready` here means ready for QA, not ready for implementation. Do not move a
Test Request through Planning / In progress / In Review.

## New request

1. Confirm the user wants a Test Request
2. List open feature PRs as `SONA-{n} {Title}` (skip drafts, skip `TR:` PRs)
3. User confirms which PRs to include
4. Check for an in-flight TR → combine or wait (see above)
5. Create the ticket from the Test Request template; fill scenarios; set
   **Testing** / **Tested By**
6. If not waiting: squash-merge the selected PRs into `testing`, open or
   update the `TR:` PR, link **PR**, move the TR → `Ready`
7. Output the TR ticket link, `SONA-{n}`, selected features, and PR URL

## Completion (when a TR is done)

When the user says a TR is complete, or its `TR:` PR is merged to `master`:

1. Mark that Test Request `Done`
2. Fast-forward `testing` to `master` so the next queue starts clean
3. Find other Test Request tickets still `New`
4. If **one**: queue it (squash-merge its PRs, open `TR:` PR, → `Ready`)
5. If **several**: list them as `SONA-{n} {Name}` and ask which to queue next
