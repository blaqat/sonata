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
- On the **Test Request**: **PR** → the TR GitHub PR

**Manually link the PR** via the **PR** relation after creating the TR PR. The
TR's SONA number won't match the PR title (which uses feature IDs), so the PR
won't auto-link.

Do **not** use **Parent** for Test Requests (Parent is `limit: 1` and is for
Dev Plans). Do **not** create a Dev Plan child.

Pass `template_id` on create. Template apply is async — do **not** send
`content` in the same create. Fetch the page, then fill the existing blocks.

---

## Writing Scenarios — QA Usability First

Scenarios are **strict step-by-step scripts** a QA tester follows to verify
behavior. Optimize for **testing usability**: easy to read, easy to copy
commands, easy to check off steps, easy to compare expected vs actual.

### Page Structure

```
## Environment Setup
- Setup requirement 1 (config files, env vars, preconditions)
- Setup requirement 2

## Test Script
---
<callout>
  #NN - Scenario 1: Short Description
  ...
</callout>

<callout>
  #NN - Scenario 2: Short Description
  ...
</callout>
```

**Environment Setup** comes BEFORE the Test Script. Put all preconditions,
config file checks, required state, or one-time setup here — not inside
individual scenarios.

### Scenario Callout Structure

Each scenario is a yellow callout (`icon="/icons/script_yellow.svg"`):

```
<callout icon="/icons/script_yellow.svg">
#### #NN - Scenario X: Short Description

#### Steps
- [ ] Step description (what the tester does)

\`\`\`
exact command or input to copy-paste
\`\`\`

- [ ] Next step description

\`\`\`
next command
\`\`\`

#### Expected
- One expected outcome per bullet
- Another expected outcome
- Keep bullets atomic — don't combine multiple checks

#### Result
- (Filled out by tester) {color="blue"}
</callout>
```

### Scenario Rules

1. **One testable flow per scenario** — not one scenario per ticket. A ticket
   may need multiple scenarios (e.g. Scenario 1: happy path, Scenario 2: error
   case). Or one scenario may cover multiple tickets if they share a flow.

2. **Title format**: `#NN - Scenario X: Description` where `NN` is the SONA
   ticket number the scenario relates to (e.g. `#37 - Scenario 1:`).

3. **Steps are checkboxes + code blocks**:
   - Checkbox with a description of what to do
   - Immediately followed by a **code block** with the exact command/input
   - Tester copies from the code block, checks the box when done
   - No code block needed if the step is purely observational

4. **Expected has multiple bullets** — one assertion per bullet:
   - Bad: `- Command completes without errors and returns a URL`
   - Good:
     - `- Command completes without errors`
     - `- Returns a URL`

5. **Result stays blue placeholder** — tester fills this in.

### Example: Good Scenario

```
<callout icon="/icons/script_yellow.svg">
#### #37 - Scenario 2: Image Generation Self Command Posts Image

#### Steps
- [ ] Run `$imagine` with a simple prompt and wait for the returned image link

\`\`\`
Sonata, generate an image of a cow jumping over a milk shaped moon
\`\`\`

#### Expected
- `$imagine` generates an image via `gpt-image-2`
- Returns an uploaded image URL
- The image is posted in the chat

#### Result
- (Filled out by tester) {color="blue"}
</callout>
```

### Example: Bad Scenario (don't do this)

```
<callout>
#### Scenario 1: AI commands use current default models (SONA-37)

#### Steps
- [ ] Run each registered AI command path (g, o, c, x, a) once and note any
      model-not-found errors
- [ ] Check sonata.config.json overrides against _DEFAULT_AI_MODELS in
      src/sonata_config.py (expect gpt-image-2, grok-4.6, gpt-5.6-terra,
      gemini-3.6-flash, gemini-3.1-flash-image)
- [ ] Run $imagine with a simple prompt and wait for the returned image link

#### Expected
- Every AI command path completes without model-not-found errors; $imagine
  generates an image via gpt-image-2 and returns an uploaded image URL
</callout>
```

Problems: no code blocks, steps are too vague, expected combines multiple
assertions, ticket ID is at the end instead of as `#NN -` prefix.

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
5. Create the ticket from the Test Request template; fill scenarios per the
   rules above; set **Testing** / **Tested By**
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
