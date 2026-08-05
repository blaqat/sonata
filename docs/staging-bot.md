# Staging bot (second Discord application)

## Decision

Use a **second Discord bot** (separate Discord application + separate Railway
service) for testing. Do **not** make the production process runtime-switchable
between tokens or environments.

This matches the ops preference: less risk of breaking prod, and Railway already
models isolation as separate services with their own env/volumes — not an
in-process flip.

## Why not runtime-switchable

| Constraint | Detail |
|---|---|
| Single login | `src/index.py` calls `sonata.start(settings.BOT_TOKEN)` once; identity is that token |
| Restart model | Hot changes go through `$restart` → `os.execv`; no multi-client lifecycle |
| Discord apps | Slash commands (`/cursor`, etc.) and OAuth identity are per application |
| Beacon | Chat memory, channel/guild policies, Cursor session state live on disk / Railway volume — sharing while “switching” would mix prod and test state |
| Railway | Env vars and volumes are per service; flipping identity inside one service still shares the volume and still risks taking prod offline |

## Recommended shape

```text
┌─────────────────────┐     ┌─────────────────────┐
│  Discord App: Prod  │     │ Discord App: Staging│
│  BOT_TOKEN (prod)   │     │ BOT_TOKEN (staging) │
└──────────┬──────────┘     └──────────┬──────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ Railway: sonata     │     │ Railway: sonata-stg │
│ volume: /beacon     │     │ volume: /beacon-stg │
│ sonata.config.json  │     │ staging config      │
└─────────────────────┘     └─────────────────────┘
```

Same git repo / image; different Discord app, service, env, and Beacon volume.

## Isolation checklist

### Must be separate

| Item | Why |
|---|---|
| Discord application + `BOT_TOKEN` | Bot identity, invites, slash-command registration |
| Railway (or host) service | Restarts, bad deploys, CPU/memory, `PORT` for term web |
| Beacon volume / `BEACON_RAILWAY_PATH` | Policies, chat memory, Cursor run logs |
| `BEACON_ENCRYPTION_KEY` (if used) | Encrypted Beacon blobs must not be readable across envs with the wrong key — use a **different** key for staging |
| `sonata.config.json` / `SONATA_CONFIG` | Cursor access lists, whitelist, model toggles |

### Usually OK to share

| Item | Notes |
|---|---|
| AI provider API keys | Quota/cost risk only |
| `CURSOR_API_KEY` | Shared org; staging still writes its own Beacon Cursor state |
| GIF / search / weather keys | Low risk |

### Guild / wake-word strategy

Wake matching is currently hardcoded in `chat.py` to `sonata` / `sona` / Japanese
variants plus `<@bot_user_id>`. If both bots are in the same guild:

1. Prefer a **dedicated staging guild** (simplest), and/or
2. Give the staging bot a distinct Discord username + avatar, and make wake
   names configurable for staging (e.g. `sona-stg` / `staging`) so “sonata”
   does not double-trigger.

## Railway sketch

1. Duplicate the prod Railway service → `sonata-staging` (or create new).
2. Attach a **new** volume; set `BEACON_RAILWAY_PATH` to that mount (e.g. `/beacon`).
3. Set staging `BOT_TOKEN`, `GOD`, and a staging `SONATA_CONFIG` path or file.
4. Point the staging service at the branch/image under test (or a staging deploy
   channel); keep prod on the release branch.
5. Invite the staging Discord app only to the test guild until wake isolation is
   solid.

`RAILWAY_ENVIRONMENT_NAME` is already used by Beacon to choose the Railway
volume path vs local `beacon-mainland` — both services can set it; isolation
comes from **different volumes / paths**, not from that flag alone.

## Minimal code follow-ups (optional but useful)

- Config-driven wake names (so staging does not answer “sonata” in shared guilds)
- Startup log line: environment label + bot user id (confirm which bot came up)
- Document staging env in `.env.template` comments (no secrets)

## Non-goals

- Hot-swapping `BOT_TOKEN` without process restart
- One Railway service serving both prod and staging Discord apps
- Sharing a Beacon volume between prod and staging
