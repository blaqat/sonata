---
name: rereview
description: Re-evaluate a ticket/Dev Plan after @blaqat addresses previous feedback. Use this to verify if previous concerns have been resolved.
---

# Instructions

/rereview [TICKET_CODE]

1. Fetch the specified ticket, Dev Plan subtask, and all previous review
   comments left by the agent

2. Read @blaqat's responses to each prior comment

3. Compare the updated Dev Plan against the previous review:
   - Were raised concerns addressed?
   - Were questions answered sufficiently?
   - Were suggestions incorporated (or reasonably declined)?
   - Did any changes introduce new gaps or issues?

4. Leave follow-up comments on the ticket/Dev Plan with what's resolved, what's
   still outstanding, and any new observations.

5. Output a summary verdict:
   - Good to go — all feedback addressed, no new issues
   - Minor feedback — small remaining notes, non-blocking
   - Needs revision — outstanding issues still unresolved or new concerns found

6. Update Dev Plan status:
   - If good to go or minor feedback → Done
   - If needs revision → TODO

Response guidelines:

- Simple language, short and brief
- Links should be in markdown format
- Reference specific previous comments when noting resolved/unresolved items
- Don't re-raise concerns that were already addressed
