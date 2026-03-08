---
name: review
description: Review a ticket or Dev Plan created by @blaqat. Use this to evaluate new tickets and plans for feasibility and completeness.
---

# Instructions

/review [TICKET_CODE]

1. Fetch the specified ticket and its Dev Plan subtask (if exists)

2. Evaluate the ticket for:
   - Clear, concise title

   - Sufficient description and context

   - Specific, testable acceptance criteria

   - Reasonable estimation

   - Appropriate tags

   - Dependencies or blockers identified

3. Evaluate the Dev Plan (if present) for:
   - Feasibility given the current codebase

   - Edge cases or gaps not accounted for

   - Scope creep risk

   - Alignment with acceptance criteria

   - Sensible breakdown of steps

4. Leave comments directly on the ticket/Dev Plan with What looks good,
   Questions or ambiguities, Concerns or risks, and or Suggestions for
   improvement.

5. Output a summary verdict:
   - Good to go — no issues found

   - Minor feedback — small suggestions, non-blocking

   - Needs revision — gaps or issues that should be addressed before moving
     forward

6. Update Dev Plan Status
   - If good to go or minor feedback move to done
   - If needs revision move back to todo

Response Guidelines:

- Simple language, Short and brief.
- Links should be in markdown format
