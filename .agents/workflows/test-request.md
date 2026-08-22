---
description: Create a Test Request for selected open PRs and open or update the TR PR.
---

/test-request

Never create a Test Request unless the user confirms they want one.

1. List open feature PRs as `SONA-{n} {Title}` (skip drafts and `TR:` PRs).
   User confirms which to include.

2. If another Test Request is in-flight (not Done, open `TR:` PR), ask:
   **combine** or **wait**.

3. Create a SONA ticket from the **Test Request** template
   (`3c424354-9f63-8060-aaca-c259a8d45cff`) — required, same template
   list as Bug / Feature / Task / Dev Plan / Spike. Type stays `Task`.
   Name: `TR: SONA-{n}, SONA-{n}`. Do not send `content` with
   `template_id` — fill the scenario callouts after template applies.

4. Set **Testing** on the TR → selected tickets; **Tested By** on each
   ticket → the TR. No Dev Plan. No Parent.

5. Fill scenarios using the format in the full skill:
   - **Environment Setup** section BEFORE Test Script (preconditions, config)
   - Each scenario in a yellow callout with title `#NN - Scenario X: Desc`
   - **Steps**: checkboxes + code blocks with exact commands to copy
   - **Expected**: multiple bullets, one assertion per bullet
   - **Result**: blue placeholder for tester
   - One testable flow per scenario (a ticket may have multiple scenarios)

6. **Wait:** Status stays `New`. Stop.

   **Combine / no in-flight:** squash-merge selected PRs into `testing`
   (`SONA-{n}: Title` + bullets). Open or update `testing` → `master` PR
   titled `TR: SONA-{n}, SONA-{n}` with a task list of TR ticket links.
   **Manually link the PR** via the PR relation. Status → `Ready`.

7. When a TR completes: mark `Done`, fast-forward `testing` to `master`,
   then queue the next `New` Test Request (ask if there are several).
