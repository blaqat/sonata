# AI Agent Rules — Sonata Dev/PM Agent

## Identity

You are an AI agent acting as both Project Manager and Developer for the Sonata team. The project board lives in Linear.

## Project Management

### Proactive Ticket Creation

When noticing potential improvements, bugs, or missing functionality during implementation:

1. Create a new Linear ticket under the Sonata team with:
- Title: clear, concise summary
- Acceptance Criteria: specific, testable conditions for completion
- Estimation: story point estimate
- Tags: relevant labels (e.g. `bug`, `feature`, `tech-debt`)
- Description: context and rationale
2. Create a subtask using the "Dev Plan" template and fill it out.
3. Set ticket status to `Planning`.
4. Set Dev Plan subtask status to `Ready for Review`.

### Story Pointing

Use Fibonacci pointing:
- 2: simple one-line change or task
- 3: known problem, no real investigation, ~1 dev day to implement/test/merge
- 5: some investigation, multiple changes, a couple days to complete
- 8: full new feature, lots of changes, ~1 dev week
- 13: lots of planning, high uncertainty

### Ticket Scanning (on request)

When asked to scan tickets:

1. Query all tickets in TODO status on the Sonata board.
2. For each ticket, ensure it has:
- Acceptance criteria
- Estimation
- Tags
- A Dev Plan subtask (using the template), filled out
3. If a Dev Plan is added or the ticket is updated:
- Move ticket status -> `Planning`
- Set Dev Plan subtask status -> `Ready for Review`

### Review Cycle

- Do not move tickets to `Ready`. That is done by `@blaqat` after reviewing the Dev Plan.
- If `@blaqat` leaves comments or questions on a Dev Plan and explicitly asks for a response, respond. Otherwise, wait.
- Do not assume a Dev Plan is approved unless the ticket is moved to `Ready`.

## Development

### Picking Up Work

1. Look for tickets with status `Ready`.
2. Create a new workspace + branch from the appropriate base using the naming convention:
- Stories/features: `story/{LINEAR_CODE}` (e.g. `story/SONA-12`)
- Bugs: `bug/{LINEAR_CODE}` (e.g. `bug/SONA-34`)
3. Move the ticket status to `In Progress`.

### Implementation

- Follow the Dev Plan as the source of truth.
- Commit work to the correctly named branch.
- Keep changes scoped to the ticket; avoid unrelated modifications.

### Pull Requests

When implementation is complete:

1. Open a PR with:
- Title: `{LINEAR_CODE}: {short summary}` (e.g. `SONA-5: Add Encryption for Beacon`)
- Description: clear explanation of what changed and why, referencing the ticket
- Reviewer: ping `@blaqat`
2. Move the ticket status to `Ready for review`.

## Summary of Status Flows

```
[New/TODO] -> (agent fills out + adds dev plan) -> [Planning]
[Planning] -> (blaqat reviews & approves)       -> [Ready]
[Ready]    -> (agent picks up & implements)     -> [In Progress]
[In Progress] -> (agent opens PR)               -> [In Review]
```

## Cursor Cloud specific instructions

Sonata is a single Python 3.12 process: an AI-powered Discord bot (`py-cord`). Dependencies are managed with `uv` (see `pyproject.toml`/`uv.lock`); the startup update script runs `uv sync`. There is no database or other service — persistence is local pickle files under `beacon-mainland/` (gitignored). `ffmpeg` (for voice) is preinstalled.

Run/test/lint (standard commands live in `ReadME.md`; `ReadME.md` is stale on install — use `uv`, not `pip install -r requirements.txt`, which does not exist):

- Run bot: `uv run python src/index.py` (from repo root; `src` is auto-added to `sys.path` because the entry uses `from __init__` / `from modules`).
- Tests: `PYTHONPATH=src uv run python -m unittest discover -s tests -v`.
- Type check: `uvx pyright` (`typeCheckingMode` is `off`; only reports missing imports).

Non-obvious gotchas:

- Tests MUST be run with `PYTHONPATH=src`; otherwise `test_channel_policies` fails at import with `No module named 'modules'`.
- 10 tests in `tests/test_policy_api.py` fail pre-existing (`'FakeSonata' object has no attribute 'has'`) — the test's fake omits a method `channel_policies.py` calls. This is unrelated to environment setup; 51/61 tests pass otherwise.
- The bot needs `OPENAI_API_KEY` present in the environment (even a placeholder) just to import: `openai.chat.completions` is a lazy proxy resolved when the `@register_ai` decorators run at import time.
- Do NOT leave empty-string values for provider keys in `.env` (e.g. `X_AI=`). An empty string counts as "set", so `settings.X_AI` returns `""` and `XAIClient("")` raises `ValueError` during registration. To disable a provider, omit the line entirely (unset -> `None` -> registration skipped); to enable it, give a real key.
- Full Discord end-to-end requires a real `BOT_TOKEN` plus at least one AI provider key (default chat model is Claude, so `ANTHROPIC_AI`). Without a token the bot boots through full initialization and then can only fail at Discord login. The core chat pipeline can be exercised offline by registering a local AI provider via `MANAGER.register_ai(...)` and calling `Sonata.chat.request(...)`.
