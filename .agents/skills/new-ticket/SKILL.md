---
name: new-ticket
description: Create a new ticket from scratch. Use this when you identify a bug, feature, or technical debt that needs to be tracked.
---

# Instructions

/create [title]

1. Ask clarifying questions if title/context is vague

2. Create a page in **SONA Tickets** via `notion-create-pages`:
   - `parent`: `{ "data_source_id": "fe024354-9f63-83db-87dc-07f92799408c" }`
   - Prefer `template_id` by ticket **Type**:

   | Type | Template | `template_id` |
   |------|----------|---------------|
   | `Story` | Feature Ticket | `bd624354-9f63-8237-99c9-015f6ae2a183` |
   | `Bug` | Bug Ticket | `f5024354-9f63-821a-ad85-81550fdbc659` |
   | `Spike` | Spike Ticket | `fad24354-9f63-839c-aa6d-01f45e181907` |
   | `Task` | Task Ticket | `71824354-9f63-8334-8649-01a2c41e7e0b` |
   | `Task` | Test Request | `3c424354-9f63-8060-aaca-c259a8d45cff` |

   **Never** use the Test Request template unless the user explicitly confirms
   they want one. If they do, stop and use the `test-request` skill instead
   (Type stays `Task`; ticket Name is `TR: SONA-{n}, …`).

   - `properties`: Name (plain title, no ID prefix — Notion assigns `ID`
     after create), Type, Status (`New`), Points, Milestones (when clear)

3. Fetch the new page, read `userDefined:ID` (`SONA-{n}`), and
   `notion-update-page` → `update_properties` →
   `Name` = `SONA-{n}: {original title}`. Notion search cannot find the
   ID property, so the prefix must be in the title. Do **not** do this
   for Test Requests (Name stays `TR: SONA-{n}, …`).

4. Fill **Description** and **Acceptance Criteria** (fetch the page first; re-fetch
   if template sections aren't there yet)

5. Create a child Dev Plan with `template_id`
   `65724354-9f63-8382-8898-810fd27b31e7` (`Type=Plan`, **Parent** = new ticket);
   fill **Goal**, **Plan**, **Validation**

6. Set parent → `Planning`, Dev Plan → `Ready`

7. Output the Notion ticket link, `SONA-{n}` ID, and summary
