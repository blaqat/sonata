"""
Discord ``$policy`` command surface.

Registers a prefix command on the bot at plugin extend time (same pattern as
cursor ``$agent``). Mutations go through ``policy_cli`` → ``policy_admin``.
"""

from discord.ext import commands

from modules.AI_manager import AI_Manager
from modules.channel_policies import has_manage_guild_permission
from modules.policy_admin import PolicyAdminError, get_or_create_policy_admin
from modules.policy_cli import dispatch_policy_command

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(lazy=True)
__plugin_name__ = "policy"
__dependencies__ = ["chat"]


async def _ctx_reply(ctx, text, reply=True):
    message = str(text or "")[:2000]
    try:
        _ = ctx.author
        if reply:
            await ctx.reply(message, mention_author=False)
        else:
            await ctx.send(message)
    except AttributeError:
        await ctx.send(message)


async def _ctx_reply_chunks(ctx, text, reply=True):
    remaining = str(text or "")
    if not remaining:
        return
    first = True
    while remaining:
        chunk = remaining[:2000]
        if len(remaining) > 2000:
            split_at = chunk.rfind("\n")
            if split_at > 1000:
                chunk = chunk[:split_at]
        await _ctx_reply(ctx, chunk, reply=reply and first)
        remaining = remaining[len(chunk) :].lstrip("\n")
        first = False


def _resolve_discord_id_csv(raw, resolver):
    if raw is None or raw == "-":
        return raw
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    return ",".join(resolver(part) for part in parts)


def _resolve_discord_user_id(raw):
    raw = str(raw).strip()
    if raw.startswith("<@&") and raw.endswith(">"):
        raise PolicyAdminError(f"Expected a user mention, got role mention `{raw}`.")
    if raw.startswith("<@") and raw.endswith(">"):
        inner = raw[2:-1]
        if inner.startswith("!"):
            inner = inner[1:]
        return inner
    return raw


def _resolve_discord_role_id(raw):
    raw = str(raw).strip()
    if raw.startswith("<@&") and raw.endswith(">"):
        return raw[3:-1]
    if raw.startswith("<@") and raw.endswith(">"):
        raise PolicyAdminError(f"Expected a role mention, got user mention `{raw}`.")
    return raw


def _resolve_discord_target(ctx, scope, raw_target):
    """Resolve Discord-specific target references like 'here', <#channel>, <@user>."""
    raw = str(raw_target).strip()
    scope_lower = scope.lower()

    if raw.lower() == "here" and scope_lower == "channel":
        return str(ctx.channel.id)

    if raw.lower() == "here" and scope_lower == "guild":
        guild = getattr(ctx, "guild", None)
        if guild:
            return str(guild.id)

    if raw.startswith("<#") and raw.endswith(">"):
        return raw[2:-1]

    if raw.startswith("<@&") and raw.endswith(">"):
        return raw[3:-1]

    if raw.startswith("<@") and raw.endswith(">"):
        inner = raw[2:-1]
        if inner.startswith("!"):
            inner = inner[1:]
        return inner

    return raw


async def _validate_discord_target(ctx, scope, target_id, *, role_check=False):
    guild = getattr(ctx, "guild", None)
    if guild is None:
        raise PolicyAdminError("Policy commands must be used in a server.")

    scope_lower = scope.lower()
    tid = str(target_id)

    if role_check:
        if not tid.isdigit():
            raise PolicyAdminError(f"Invalid role id `{tid}`.")
        role = guild.get_role(int(tid))
        if role is None:
            raise PolicyAdminError(f"Role `{tid}` is not in this server.")
        return tid

    if scope_lower == "guild":
        if tid != str(guild.id):
            raise PolicyAdminError("Guild target must be this server. Use `here`.")
        return tid

    if scope_lower == "channel":
        if not tid.isdigit():
            raise PolicyAdminError(f"Invalid channel id `{tid}`.")
        channel = guild.get_channel(int(tid))
        if channel is None:
            get_thread = getattr(guild, "get_thread", None)
            channel = get_thread(int(tid)) if callable(get_thread) else None
        if channel is None:
            raise PolicyAdminError(f"Channel `{tid}` is not in this server.")
        return tid

    if scope_lower == "user":
        if not tid.isdigit():
            raise PolicyAdminError(f"Invalid user id `{tid}`.")
        member = guild.get_member(int(tid))
        if member is None:
            try:
                member = await guild.fetch_member(int(tid))
            except Exception:
                member = None
        if member is None:
            raise PolicyAdminError(f"User `{tid}` is not a member of this server.")
        return tid

    return tid


async def _resolve_and_validate_discord_target(ctx, scope, raw_target):
    target = _resolve_discord_target(ctx, scope, raw_target)
    return await _validate_discord_target(ctx, scope, target)


def _register_policy_command(bot, sonata):
    if getattr(bot, "_policy_prefix_registered", False):
        return
    if not hasattr(bot, "add_command") or not hasattr(bot, "get_command"):
        return
    if bot.get_command("policy") is not None:
        bot._policy_prefix_registered = True
        return

    @commands.command(
        name="policy",
        help="Manage policy rules across namespaces and scopes.",
    )
    async def policy_cmd(ctx, action="", *args):
        action = action.lower().strip()
        if not has_manage_guild_permission(ctx):
            return await _ctx_reply(
                ctx, "You need `Manage Server` permission to use this command."
            )

        admin = get_or_create_policy_admin(sonata)
        usage = (
            "Usage:\n"
            "`$policy namespaces`\n"
            "`$policy show <namespace> <scope> <target>`\n"
            "`$policy set <namespace> <scope> <target> <action> <allow|deny>`\n"
            "`$policy remove <namespace> <scope> <target> <action>`\n"
            "`$policy clear <namespace> <scope> <target>`\n"
            "`$policy groups list <namespace>`\n"
            "`$policy groups show <namespace> <group>`\n"
            "`$policy groups upsert <namespace> <group> [members_csv|-] [roles_csv|-]`\n"
            "`$policy groups remove <namespace> <group>`\n"
            "`$policy groups member <add|remove> <namespace> <group> <user>`\n"
            "`$policy groups role <add|remove> <namespace> <group> <role>`"
        )

        if action in {"", "help"}:
            return await _ctx_reply(ctx, usage)

        try:
            result = await dispatch_policy_command(
                admin,
                action,
                args,
                usage,
                resolve_target=lambda scope, target: _resolve_and_validate_discord_target(
                    ctx, scope, target
                ),
                format_namespace=lambda n: f"`{n}`",
                resolve_user_id=_resolve_discord_user_id,
                resolve_role_id=_resolve_discord_role_id,
                resolve_members_csv=lambda raw: _resolve_discord_id_csv(
                    raw, _resolve_discord_user_id
                ),
                resolve_roles_csv=lambda raw: _resolve_discord_id_csv(
                    raw, _resolve_discord_role_id
                ),
                validate_user=lambda user_id: _validate_discord_target(
                    ctx, "user", user_id
                ),
                validate_role=lambda role_id: _validate_discord_target(
                    ctx, "group", role_id, role_check=True
                ),
            )
            if result is not None:
                return await _ctx_reply_chunks(ctx, result)
        except PolicyAdminError as e:
            return await _ctx_reply(ctx, str(e))

        await _ctx_reply(ctx, usage)

    bot.add_command(policy_cmd)
    bot._policy_prefix_registered = True


@MANAGER.with_context(manager=True, client=True)
def policy_register(context):
    """Register Discord ``$policy`` before the bot starts handling messages."""
    bot = context.client
    sonata = context.manager
    if bot is None or sonata is None:
        return
    _register_policy_command(bot, sonata)
