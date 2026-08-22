---
name: beautifying-review
description: Reviews code for architecture, design patterns, refactoring
  opportunities, and data structure improvements, then produces a detailed
  development plan for implementing them. Asks the user about preferences
  when multiple good approaches exist. Use when the user asks for a code
  review focused on structure and design rather than bugs.
---

# Architecture-Focused Code Review → Dev Plan

You are performing a design-focused code review whose end product is a
**detailed, actionable development plan** — not a list of nitpicks.

## Priorities (highest to lowest)

1. **Architecture** — layering, module boundaries, coupling/cohesion,
   dependency direction, separation of concerns
2. **Code patterns** — misused or missing patterns, duplicated logic that
   suggests an abstraction, inconsistent idioms across the codebase
3. **Refactoring opportunities** — long functions, deep nesting, god
   objects, feature envy, primitive obsession, shotgun surgery
4. **Code design** — API ergonomics, naming, interface clarity,
   testability, SOLID violations, over/under-abstraction
5. **Data structures** — wrong structure for access patterns, redundant
   state, denormalized data drifting out of sync, missing invariants

## Explicitly deprioritized

- Bugs and security: mention only if severe, in a short "Other Notes"
  section. They must not dominate the review.
- Style nits (formatting, whitespace): skip entirely.

## Review process

1. **Understand first.** Read the code, identify intended responsibilities,
   and map dependencies between components before critiquing.
2. **Identify findings.** For each: what it is (file/line), why it costs
   (rigidity, duplication, coupling, poor scalability), and what change
   fixes it.
3. **Check for decision points.** Whenever a finding has multiple
   legitimate solutions (e.g., extract a service vs. introduce an event
   bus; composition vs. inheritance; normalize data vs. add a cache
   layer), STOP and ask the user which direction they prefer before
   baking it into the plan. Present each option with:
   - A one-paragraph description
   - Trade-offs (complexity, migration effort, long-term flexibility)
   - Your recommendation and why
   Batch these questions together rather than asking one at a time.
4. **Build the dev plan** once preferences are resolved (or using your
   recommended defaults if the user says "you decide").

## Output format

### 1. Design Assessment
A thorough narrative (several paragraphs) covering: overall architecture
health, dominant problems, root causes, and what's well-designed and
should be preserved.

### 2. Findings (detailed)
For each finding:
- **Title and severity** (High / Medium / Low impact on maintainability)
- **Location(s)**: files and lines
- **Problem**: full explanation of the design cost
- **Proposed change**: concrete description with code sketches showing
  before/after where helpful
- **Ripple effects**: what else must change as a result

### 3. Open Questions (if any)
The batched decision points from step 3. Wait for answers before
finalizing the plan if the user is available; otherwise proceed with
recommendations and clearly mark the assumptions made.

### 4. Development Plan
An ordered, phased implementation plan:
- **Phases** grouped so each leaves the codebase working (incremental,
  shippable steps — no big-bang rewrite unless requested)
- Per phase: goals, tasks with enough detail to hand to a developer,
  files touched, estimated relative effort (S/M/L), dependencies on
  earlier phases, and how to verify the refactor didn't change behavior
  (tests to add or run)
- **Sequencing rationale**: why this order (e.g., decouple X before
  extracting Y)
- **Risks and mitigations** for the riskier steps

### 5. Strengths
Good abstractions and decisions worth keeping.

### 6. Other Notes
Severe bugs/security issues only, briefly.

## Tone and depth

- Be thorough — this document should be usable as a standalone work plan.
- Prefer incremental refactors; avoid abstraction for its own sake.
- When sketching code, show enough to make the intent unambiguous, not
  full implementations.
