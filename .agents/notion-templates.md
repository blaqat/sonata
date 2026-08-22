# SONA Tickets — Notion page templates

Prefer these database templates when creating tickets and Dev Plans.

**Data source:** `collection://fe024354-9f63-83db-87dc-07f92799408c`

## Template mapping

| Type | Template name | Template ID |
|------|---------------|-------------|
| `Story` | Feature Ticket | `bd624354-9f63-8237-99c9-015f6ae2a183` |
| `Bug` | Bug Ticket | `f5024354-9f63-821a-ad85-81550fdbc659` |
| `Spike` | Spike Ticket | `fad24354-9f63-839c-aa6d-01f45e181907` |
| `Task` | Task Ticket | `71824354-9f63-8334-8649-01a2c41e7e0b` |
| `Plan` | Dev Plan | `65724354-9f63-8382-8898-810fd27b31e7` |
| `Task` | Test Request | `3c424354-9f63-8060-aaca-c259a8d45cff` |

**Test Request** stays **Type = `Task`**. Always create it with the Test
Request template, never a blank Task or Task Ticket. Ticket **Name** is
`TR: SONA-{n}, …`. **Only if the user confirms they want one** — use the
`test-request` skill. Do not create from scan, new-ticket, or proactive
ticket creation.

## Template body sections

| Template | Sections |
|----------|----------|
| Feature / Bug / Spike / Task | **Description**, **Acceptance Criteria** |
| Dev Plan | **Goal**, **Plan**, **Validation** |
| Test Request | **Test Script** scenario callouts (Scenario / Steps / Expected / Result) |

## MCP usage

1. **Fetch templates** (optional refresh): `notion-fetch` on the data source URL or
   `collection://fe024354-9f63-83db-87dc-07f92799408c` — check the `<templates>`
   section if IDs change.

2. **Create with template** — `notion-create-pages`:
   - `parent`: `{ "data_source_id": "fe024354-9f63-83db-87dc-07f92799408c" }`
   - Per page: set `template_id` to the ID for the ticket **Type**
   - Set `properties` (`Name`, `Type`, `Status`, `Points`, `Milestones`, `Parent`, …)
   - Template application can be async; the page may look blank briefly

3. **Fill body content** — fetch the page, then `notion-update-page` with
   `command: "update_content"` to fill the template sections. If headings are not
   there yet, re-fetch and try again.

4. **Apply template to existing page**: `notion-update-page` with
   `command: "apply_template"` and `template_id` — appends template content.

## Example: create a Story + Dev Plan

```json
{
  "parent": { "data_source_id": "fe024354-9f63-83db-87dc-07f92799408c" },
  "pages": [
    {
      "template_id": "bd624354-9f63-8237-99c9-015f6ae2a183",
      "properties": {
        "Name": "Add widget caching",
        "Type": "Story",
        "Status": "New",
        "Points": 5
      }
    }
  ]
}
```

Then create the Dev Plan child with `template_id`:
`65724354-9f63-8382-8898-810fd27b31e7`, `Type: "Plan"`, and `Parent` set to the
parent ticket URL.
