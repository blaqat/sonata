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
| **Name** | `TR: SONA-{n}, SONA-{n}` (feature IDs, not the TR ticket's own ID). Do **not** prefix with the TR's own `SONA-{n}:` — that rename is only for implementation tickets. |

Relations (duals — set one side, the other updates):

- On the **Test Request**: **Testing** → the feature/bug tickets under test
- On each of those tickets: **Tested By** → the Test Request
- On the **Test Request**: **PR** → the TR GitHub PR

**Manually link the PR** via the **PR** relation after creating the TR PR. The
TR's SONA number won't match the PR title (which uses feature IDs), so the PR
won't auto-link.

Do **not** use **Parent** for Test Requests (Parent is `limit: 1` and is for
Dev Plans). Do **not** create a Dev Plan child.

## Applying the template

**Fetch the template page before writing anything.** It gets edited over time,
so this skill deliberately does not hard-code its layout — the template is the
source of truth for headings, section names, and callout shape.

1. Fetch the `template_id` above and read its body.
2. Create the TR page passing `template_id`. Template apply is async, so do
   **not** send `content` in the same create.
3. Re-fetch the new page. If the template body materialised, fill the existing
   blocks in place.
4. If it is still blank after a retry, mirror the structure from step 1 by hand
   with `replace_content`, then set what the template would have supplied:
   `Type`, `Assign`, `Priority`, and the page icon.

Setting the icon has two traps. Pass the `icon` field a **string** — a nested
`{type, icon:{name, color}}` object is rejected. A coloured native icon needs
the full SVG URL, so the TR's yellow script is
`https://www.notion.so/icons/script_yellow.svg`; the bare `icons/script_yellow`
form is only for an uncoloured icon and mangles to `/icons/script_yellow`.
`update_properties` also rejects an icon-only call, so send `"properties": {}`
alongside it. Verify with a fetch: the page tag should read
`icon="icons/script_yellow"` with no leading slash. Full rules live in the
`notion-page-icons` skill.

---

## Writing Scenarios — QA Usability First

Scenarios are **strict step-by-step scripts** a QA tester follows to verify
behavior. Optimize for **testing usability**: easy to read, easy to copy
commands, easy to check off steps, easy to compare expected vs actual.

**Follow the template's structure exactly** — its heading levels, section
names, and callout shape. The rules below govern the *content* placed inside
that structure, never the layout. Where this skill and the template disagree
on structure, the template wins.

Read the template's placeholder text as instructions. It shows one example
scenario indicating heading levels, where code blocks belong, and whether
expected results are plain bullets or tickable checkboxes.

### Scenario Rules

1. **One testable flow per scenario** — not one scenario per ticket. A ticket
   may need several scenarios (happy path, then error case), and one scenario
   may cover several tickets if they share a flow.

2. **Setup lives in the template's setup section, not inside scenarios.** All
   preconditions, config values, and required state go there so the tester
   does them once.

3. **Pair each step checkbox with a code block**: a checkbox saying what the
   tester does, immediately followed by the exact command or input to
   copy-paste. Purely observational steps need no code block.

4. **One assertion per expected item** — keep them atomic.
   - Bad: `Command completes without errors and returns a URL`
   - Good: `Command completes without errors`, then `Returns a URL`

5. **Leave the result placeholder untouched** for the tester, in whatever form
   the template uses.

6. **Preserve ticket traceability on multi-ticket TRs.** If the template's
   scenario title does not already carry the ticket number, prefix it
   (`#148 - …`) so QA can map a failure back to a ticket. A single-ticket TR
   is already unambiguous from its name, so plain numbering is fine.

7. **Only script what a tester can actually do.** Failure modes that need
   induced network or API errors belong in unit tests; say so rather than
   writing a scenario nobody can run.

### Example: content that fails these rules

```
- [ ] Run each AI command path (g, o, c, x) once, note any model-not-found
      errors, then check config overrides in src/sonata_config.py
```

Expected: `Every AI path completes without errors; $imagine returns a URL`

The step bundles several actions, gives nothing to copy-paste, and the expected
line packs multiple assertions into one, so a tester cannot report which part
failed.

---

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
5. Fetch the Test Request template, create the ticket from it, and fill the
   scenarios into its structure; set **Testing** / **Tested By**
6. If not waiting: squash-merge the selected PRs into `testing`, open or
   update the `TR:` PR, **manually link the PR** via the PR relation, move
   the TR → `Ready`
7. Output the TR ticket link, `SONA-{n}`, selected features, and PR URL

## After QA (when the user says testing is complete)

Review the tester's **Result** notes and page comments **before** marking the
TR `Done` or merging. Compare each note to the **original tickets' ACs**.

Do **not** file a ticket for every comment.

### Fix on `testing` (no new ticket)

Quick patches that still belong to the work under test:

- Small miss that is **in** the original AC (the feature almost shipped)
- Small cleanup that is not worth tracking

Commit on `testing` and push if the user needs to re-run a failed scenario.
Live-test the **exact** failing input when you can. A mocked unit test is not
the same as the QA URL or command.

### Follow-up Story

New product work **outside** the original ACs. Example (SONA-146): Catbox no
longer embeds → post images as Discord attachments; persist `$read` into chat
memory like Prism. Those were not SONA-37 / SONA-52 ACs.

### Follow-up Bug

File a Bug only when a new ticket is the right container:

- The issue does **not** undermine the point of the original ACs (leftover
  edge case; the feature still did its job), **or**
- It is a crash, **or**
- The fix is large (do not sneak a big patch onto the TR)

If a bug **does** undermine the ACs but the fix is small, patch `testing`
instead of opening a ticket.

If the split is unclear, say so and ask. Do not default to creating tickets.

## Completion (when a TR is done)

When the user says a TR is complete **and** comments are reviewed (or its
`TR:` PR is merged to `master`):

1. Mark that Test Request `Done`
2. Fast-forward `testing` to `master` so the next queue starts clean
3. Find other Test Request tickets still `New`
4. If **one**: queue it (squash-merge its PRs, open `TR:` PR, → `Ready`)
5. If **several**: list them as `SONA-{n} {Name}` and ask which to queue next
