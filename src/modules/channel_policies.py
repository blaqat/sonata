"""
Per-guild / per-channel / per-user **chat** policy façade and evaluation.

Durable chat rules live in ``PolicyAPI`` namespace ``chat``, persisted under
``policy_namespaces.chat`` (same shape as other namespaces). ``ChannelPolicy``
is an in-memory projection for programmatic helpers and legacy migration.

**ChannelPolicy** fields (projection of PolicyAPI rules):

- **can_speak**: If false, the bot does not process the channel (commands get a short
  reply; normal chat is ignored).
- **respond_all**: If true, the bot may respond without an @mention, reply, or
  ``$command`` (subject to ``should_respond_to_message`` in callers).
- **protected**: If true (channel scope only), Beacon encrypts that channel's chat
  memory path (``chat.protected``; side effects in ``policy_effects``).
- **command_policy_mode**: ``denylist`` (default) or ``allowlist``.
- **commands**: Normalized command names (no leading ``$``).

In **denylist** mode, each name in ``commands`` is **blocked**; ``allow``/``deny``
mutate that list. In **allowlist** mode, only listed commands are permitted;
``blacklist_add`` applies a full mute-style policy (no speak, allowlist, empty list).

**ChannelPolicies** migrates legacy ``channels``/``guilds``/``users``/``groups``
config once into ``policy_namespaces.chat``, then treats PolicyAPI as source of
truth. Evaluation merges **user**, **group**, **channel**, and **guild** rules
(see ``policy_api.EVAL_PRECEDENCE``).

**Operator commands**: Discord ``$policy …`` (requires Manage Server), terminal
``policy …`` (shared dispatch in ``policy_cli``; mutations via ``policy_admin``).
Programmatic access: ``sonata.chat.policy_manager`` after the chat plugin loads.
"""

import re
from dataclasses import dataclass

from modules.policy_api import EFFECT_ALLOW, EFFECT_DENY, get_or_create_policy_api
from modules.policy_effects import (
    beacon_chat_history_action,
    clear_beacon_chat_history_rule,
    ensure_beacon_namespace,
    has_beacon,
    sync_chat_protected_effects,
)


# Hard-coded channel ids still treated as no-speak (see chat mem validate); prefer $policy / config for new blocks.
LEGACY_CHANNEL_BLACKLIST = {
    1175907292072398858,
    724158738138660894,
    725170957206945859,
}

ALLOWLIST = "allowlist"
DENYLIST = "denylist"
CHANNEL_REFERENCE_RE = re.compile(r"^(?:<#)?(\d+)>?$")


def normalize_command_name(command):
    if command is None:
        return ""
    command = str(command).strip().lower()
    if command.startswith("$"):
        command = command[1:]
    return command


def normalize_commands(commands):
    if commands is None:
        return []
    if not isinstance(commands, (list, tuple, set)):
        commands = [commands]

    normalized = []
    for command in commands:
        command_name = normalize_command_name(command)
        if command_name and command_name not in normalized:
            normalized.append(command_name)
    return normalized


def parse_channel_reference(raw_channel):
    match = CHANNEL_REFERENCE_RE.match(str(raw_channel).strip())
    if match is None:
        return None
    return int(match.group(1))


def has_manage_guild_permission(ctx):
    author = getattr(ctx, "author", None)
    permissions = getattr(author, "guild_permissions", None)
    return bool(permissions and getattr(permissions, "manage_guild", False))


def should_track_message(policy):
    return policy.can_speak


def should_respond_to_message(
    policy,
    is_command=False,
    is_reply_to_sonata=False,
    called_sonata=False,
):
    if not policy.can_speak:
        return False
    return policy.respond_all or is_command or is_reply_to_sonata or called_sonata


def _is_canonical_chat_action(action):
    # Specific chat.command.<name> allows may be preserved via extra_rules in
    # denylist mode; only the structural/wildcard actions are reserved here.
    return action in {
        "chat.can_speak",
        "chat.respond_all",
        "chat.protected",
        "chat.command.*",
    }


def _normalize_extra_rules(extra_rules):
    if not extra_rules:
        return []
    normalized = []
    seen = set()
    for rule in extra_rules:
        if not isinstance(rule, dict):
            continue
        action = str(rule.get("action") or "").strip().lower()
        effect = str(rule.get("effect") or "").strip().lower()
        if not action or effect not in {EFFECT_ALLOW, EFFECT_DENY}:
            continue
        if _is_canonical_chat_action(action):
            continue
        key = (action, effect)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"action": action, "effect": effect})
    return normalized


@dataclass
class ChannelPolicy:
    # Stored shape for one guild/channel/user policy row (mirrored into PolicyAPI "chat" rules).
    can_speak: bool = True
    respond_all: bool = False
    protected: bool = False
    command_policy_mode: str = DENYLIST
    commands: list[str] | None = None
    # Non-standard chat.* actions preserved across PolicyAPI ↔ ChannelPolicies round-trips.
    extra_rules: list[dict] | None = None

    def __post_init__(self):
        self.can_speak = bool(self.can_speak)
        self.respond_all = bool(self.respond_all)
        self.protected = bool(self.protected)
        if self.command_policy_mode not in {ALLOWLIST, DENYLIST}:
            self.command_policy_mode = DENYLIST
        self.commands = normalize_commands(self.commands)
        self.extra_rules = _normalize_extra_rules(self.extra_rules)

    @classmethod
    def default(cls):
        return cls(
            can_speak=True,
            respond_all=False,
            protected=False,
            command_policy_mode=DENYLIST,
            commands=[],
            extra_rules=[],
        )

    @classmethod
    def blacklisted(cls):
        # allowlist + empty list => no commands; can_speak off stops chat entirely
        return cls(
            can_speak=False,
            respond_all=False,
            protected=False,
            command_policy_mode=ALLOWLIST,
            commands=[],
            extra_rules=[],
        )

    @classmethod
    def normalize(cls, policy=None):
        if isinstance(policy, cls):
            return cls(
                can_speak=policy.can_speak,
                respond_all=policy.respond_all,
                protected=policy.protected,
                command_policy_mode=policy.command_policy_mode,
                commands=policy.commands,
                extra_rules=policy.extra_rules,
            )

        if not isinstance(policy, dict):
            return cls.default()

        return cls(
            can_speak=policy.get("can_speak", True),
            respond_all=policy.get("respond_all", False),
            protected=policy.get("protected", False),
            command_policy_mode=policy.get("command_policy_mode", DENYLIST),
            commands=policy.get("commands", []),
            extra_rules=policy.get("extra_rules", []),
        )

    def to_dict(self):
        data = {
            "can_speak": self.can_speak,
            "respond_all": self.respond_all,
            "protected": self.protected,
            "command_policy_mode": self.command_policy_mode,
            "commands": list(self.commands),
        }
        if self.extra_rules:
            data["extra_rules"] = [dict(rule) for rule in self.extra_rules]
        return data

    def clone(self):
        return type(self).normalize(self)

    def with_updates(self, **updates):
        data = self.to_dict()
        data.update(updates)
        return type(self).normalize(data)

    def allows_command(self, command):
        command_name = normalize_command_name(command)
        if not command_name:
            return True
        # Denylist: block listed; allowlist: only listed pass
        if self.command_policy_mode == DENYLIST:
            return command_name not in self.commands
        return command_name in self.commands

    def allow_command(self, command):
        command_name = normalize_command_name(command)
        if not command_name:
            return self.clone()

        commands = list(self.commands)
        if self.command_policy_mode == DENYLIST:
            commands = [name for name in commands if name != command_name]
        elif command_name not in commands:
            commands.append(command_name)
        return self.with_updates(commands=commands)

    def deny_command(self, command):
        command_name = normalize_command_name(command)
        if not command_name:
            return self.clone()

        commands = list(self.commands)
        if self.command_policy_mode == DENYLIST:
            if command_name not in commands:
                commands.append(command_name)
        else:
            commands = [name for name in commands if name != command_name]
        return self.with_updates(commands=commands)

    def __str__(self):
        commands = ", ".join(self.commands) if self.commands else "(none)"
        return (
            f"can_speak={self.can_speak}, "
            f"respond_all={self.respond_all}, "
            f"protected={self.protected}, "
            f"command_policy_mode={self.command_policy_mode}, "
            f"commands=[{commands}]"
        )


class ChannelPolicies:
    """Chat policy façade: PolicyAPI is durable truth; maps are a projection."""

    def __init__(self, sonata):
        self.sonata = sonata
        self.guilds = {}
        self.users = {}
        self.channels = {}
        self.groups = {}
        self.loaded = False
        self.policy_api = get_or_create_policy_api(sonata)
        self._ensure_chat_namespace()
        ensure_beacon_namespace(sonata, self.policy_api)
        self.init()

    def _ensure_chat_namespace(self):
        if self.policy_api.has_namespace("chat"):
            self.policy_api.activate_namespace("chat")
            return
        # Defaults: speak and all commands allowed unless a scope adds a deny
        self.policy_api.register_namespace(
            "chat",
            plugin=True,
            default_decisions={
                "chat.can_speak": True,
                "chat.respond_all": False,
                "chat.protected": False,
                "chat.command.*": True,
            },
        )

    def _has_beacon(self):
        return has_beacon(self.sonata)

    def _beacon_chat_history_action(self, channel_id):
        return beacon_chat_history_action(self.sonata, channel_id)

    def _clear_beacon_chat_history_rule(self, channel_id):
        clear_beacon_chat_history_rule(self.sonata, channel_id, self.policy_api)

    def _policy_from_scope_rules(self, scope, scope_id):
        rules = self.policy_api.get_scope_rules("chat", scope, scope_id)
        if not rules:
            return None

        policy = ChannelPolicy.default()
        allowed_commands = []
        denied_commands = []
        allowlist_mode = False
        extra_rules = []

        for rule in rules:
            if rule.action == "chat.can_speak":
                policy.can_speak = rule.effect != EFFECT_DENY
            elif rule.action == "chat.respond_all":
                policy.respond_all = rule.effect == EFFECT_ALLOW
            elif rule.action == "chat.protected":
                if scope == "channel":
                    policy.protected = rule.effect == EFFECT_ALLOW
            elif rule.action == "chat.command.*":
                allowlist_mode = rule.effect == EFFECT_DENY
            elif rule.action.startswith("chat.command."):
                command = normalize_command_name(
                    rule.action.removeprefix("chat.command.")
                )
                if not command:
                    continue
                if rule.effect == EFFECT_ALLOW:
                    allowed_commands.append(command)
                else:
                    denied_commands.append(command)
            else:
                extra_rules.append({"action": rule.action, "effect": rule.effect})

        if allowlist_mode:
            policy.command_policy_mode = ALLOWLIST
            policy.commands = normalize_commands(allowed_commands)
        else:
            policy.command_policy_mode = DENYLIST
            policy.commands = normalize_commands(denied_commands)
            # Keep explicit allows that aren't represented by denylist commands.
            for command in normalize_commands(allowed_commands):
                extra_rules.append(
                    {"action": f"chat.command.{command}", "effect": EFFECT_ALLOW}
                )

        return policy.with_updates(extra_rules=extra_rules)

    def refresh_from_policy_api(self):
        """Rebuild in-memory ChannelPolicy maps from PolicyAPI (projection only)."""
        guilds = {}
        for scope_id in self.policy_api.list_scope_ids("chat", "guild"):
            policy = self._policy_from_scope_rules("guild", scope_id)
            if policy is not None:
                guilds[str(scope_id)] = policy

        users = {}
        for scope_id in self.policy_api.list_scope_ids("chat", "user"):
            policy = self._policy_from_scope_rules("user", scope_id)
            if policy is not None:
                users[str(scope_id)] = policy

        channels = {}
        for scope_id in self.policy_api.list_scope_ids("chat", "channel"):
            policy = self._policy_from_scope_rules("channel", scope_id)
            if policy is not None:
                channels[str(scope_id)] = policy

        self.guilds = guilds
        self.users = users
        self.channels = channels
        self.loaded = True
        sync_chat_protected_effects(self.sonata, self.policy_api)

    def _sync_channel_scope(self, channel_id, policy):
        key = str(channel_id)
        self._sync_scope("channel", key, policy)

    def _sync_guild_scope(self, guild_id, policy):
        key = str(guild_id)
        self._sync_scope("guild", key, policy)

    def _sync_user_scope(self, user_id, policy):
        key = str(user_id)
        self._sync_scope("user", key, policy)

    def _sync_scope(self, scope, scope_id, policy):
        policy = ChannelPolicy.normalize(policy)
        # Full replace for this scope id so removed commands disappear from PolicyAPI
        self.policy_api.clear_scope("chat", scope, scope_id)

        if not policy.can_speak:
            self.policy_api.set_rule(
                "chat", scope, scope_id, "chat.can_speak", EFFECT_DENY
            )

        # Default in namespace is respond_all False; only set rule when opting in
        if policy.respond_all:
            self.policy_api.set_rule(
                "chat", scope, scope_id, "chat.respond_all", EFFECT_ALLOW
            )

        # Protection is channel-scoped only (Beacon encrypt paths are per channel).
        if policy.protected and scope == "channel":
            self.policy_api.set_rule(
                "chat", scope, scope_id, "chat.protected", EFFECT_ALLOW
            )

        if policy.command_policy_mode == DENYLIST:
            for command in policy.commands:
                self.policy_api.set_rule(
                    "chat",
                    scope,
                    scope_id,
                    f"chat.command.{normalize_command_name(command)}",
                    EFFECT_DENY,
                )
        else:
            # Allowlist: deny everything, then allow named commands back
            self.policy_api.set_rule(
                "chat", scope, scope_id, "chat.command.*", EFFECT_DENY
            )
            for command in policy.commands:
                self.policy_api.set_rule(
                    "chat",
                    scope,
                    scope_id,
                    f"chat.command.{normalize_command_name(command)}",
                    EFFECT_ALLOW,
                )

        for rule in policy.extra_rules:
            self.policy_api.set_rule(
                "chat",
                scope,
                scope_id,
                rule["action"],
                rule["effect"],
            )

    def _sync_policy_api(self):
        # Order does not affect evaluate(); each scope id is independent
        for guild_id, policy in self.guilds.items():
            self._sync_guild_scope(guild_id, policy)
        for user_id, policy in self.users.items():
            self._sync_user_scope(user_id, policy)
        for channel_id, policy in self.channels.items():
            self._sync_channel_scope(channel_id, policy)
        for group_id, data in self.groups.items():
            self._sync_group(group_id, data)

    def _normalize_users_map(self, users):
        if not isinstance(users, dict):
            return {}
        normalized = {}
        for user_id, policy in users.items():
            policy = ChannelPolicy.normalize(policy)
            if policy.protected:
                policy = policy.with_updates(protected=False)
            normalized[str(user_id)] = policy
        return normalized

    def _normalize_guilds_map(self, guilds):
        if not isinstance(guilds, dict):
            return {}
        normalized = {}
        for guild_id, policy in guilds.items():
            policy = ChannelPolicy.normalize(policy)
            if policy.protected:
                policy = policy.with_updates(protected=False)
            normalized[str(guild_id)] = policy
        return normalized

    def _normalize_channels_map(self, channels):
        if not isinstance(channels, dict):
            return {}
        return {
            str(channel_id): ChannelPolicy.normalize(policy)
            for channel_id, policy in channels.items()
        }

    def _serialize_channels(self):
        return {
            channel_id: policy.to_dict() for channel_id, policy in self.channels.items()
        }

    def _serialize_guilds(self):
        return {guild_id: policy.to_dict() for guild_id, policy in self.guilds.items()}

    def _serialize_users(self):
        return {user_id: policy.to_dict() for user_id, policy in self.users.items()}

    def _normalize_groups_map(self, groups):
        if not isinstance(groups, dict):
            return {}

        normalized = {}
        for group_id, data in groups.items():
            group_key = str(group_id or "").strip().lower()
            if not group_key:
                continue
            if not isinstance(data, dict):
                data = {}
            rules = []
            for rule in data.get("rules", []):
                if not isinstance(rule, dict):
                    continue
                action = str(rule.get("action") or "").strip().lower()
                effect = str(rule.get("effect") or "").strip().lower()
                if not action or effect not in {EFFECT_ALLOW, EFFECT_DENY}:
                    continue
                rules.append({"action": action, "effect": effect})
            normalized[group_key] = {
                "members": sorted(
                    {str(member).strip() for member in data.get("members", []) if str(member).strip()}
                ),
                "roles": sorted(
                    {str(role_id).strip() for role_id in data.get("roles", []) if str(role_id).strip()}
                ),
                "rules": rules,
            }
        return normalized

    def _serialize_groups(self):
        serialized = {}
        for group_id in self.policy_api.list_groups("chat"):
            group_name = self._group_name_from_id(group_id)
            group_data = self.policy_api.get_group("chat", group_name) or {}
            group_rules = self.policy_api.get_scope_rules("chat", "group", group_id)
            serialized[group_id] = {
                "members": group_data.get("members", []),
                "roles": group_data.get("roles", []),
                "rules": [
                    {"action": rule.action, "effect": rule.effect}
                    for rule in group_rules
                ],
            }
        return serialized

    def _group_name_from_id(self, group_id):
        group_key = str(group_id or "").strip().lower()
        if ":" in group_key:
            return group_key.split(":", 1)[1]
        return group_key

    def _sync_group(self, group_id, data):
        group_name = self._group_name_from_id(group_id)
        self.policy_api.upsert_group(
            "chat",
            group_name,
            members=data.get("members", []),
            role_ids=data.get("roles", []),
        )
        self.policy_api.clear_scope("chat", "group", group_id)
        for rule in data.get("rules", []):
            self.policy_api.set_group_rule(
                "chat",
                group_name,
                rule["action"],
                rule["effect"],
            )

    def _persist(self):
        """Persist chat namespace in PolicyAPI-native ``policy_namespaces`` shape."""
        from modules.policy_admin import get_or_create_policy_admin

        admin = get_or_create_policy_admin(self.sonata)
        admin._persist_namespace("chat")
        sync_chat_protected_effects(self.sonata, self.policy_api)

    def _has_native_chat(self):
        config_ns = self.sonata.config.get("policy_namespaces", {}) or {}
        if config_ns.get("chat"):
            return True
        if self._has_beacon():
            try:
                data = (
                    self.sonata.beacon.branch("policies")
                    .branch("namespaces")
                    .discover("chat")
                )
            except Exception:
                data = None
            if data:
                return True
        return False

    def _load_legacy_maps(self):
        beacon_channels = {}
        beacon_guilds = {}
        beacon_users = {}
        beacon_groups = {}
        if self._has_beacon():
            policies_branch = self.sonata.beacon.branch("policies")
            beacon_channels = policies_branch.discover("channels") or {}
            beacon_guilds = policies_branch.discover("guilds") or {}
            beacon_users = policies_branch.discover("users") or {}
            beacon_groups = policies_branch.discover("groups") or {}

        configured_channels = self.sonata.config.get("channels", {}) or {}
        configured_guilds = self.sonata.config.get("guilds", {}) or {}
        configured_users = self.sonata.config.get("users", {}) or {}
        configured_groups = self.sonata.config.get("groups", {}) or {}

        guilds = {}
        guilds.update(self._normalize_guilds_map(beacon_guilds))
        guilds.update(self._normalize_guilds_map(configured_guilds))

        users = {}
        users.update(self._normalize_users_map(beacon_users))
        users.update(self._normalize_users_map(configured_users))

        channels = {}
        channels.update(self._normalize_channels_map(beacon_channels))
        channels.update(self._normalize_channels_map(configured_channels))

        groups = {}
        groups.update(self._normalize_groups_map(beacon_groups))
        groups.update(self._normalize_groups_map(configured_groups))
        return guilds, users, channels, groups

    def _clear_legacy_chat_stores(self):
        """Stop dual-write: clear legacy ChannelPolicy blob keys after migration."""
        self.sonata.config.set(channels={}, guilds={}, users={}, groups={})
        if self._has_beacon():
            policies_branch = self.sonata.beacon.branch("policies")
            policies_branch.illuminate("channels", {})
            policies_branch.illuminate("guilds", {})
            policies_branch.illuminate("users", {})
            policies_branch.illuminate("groups", {})

    def _migrate_legacy_to_native(self, admin):
        guilds, users, channels, groups = self._load_legacy_maps()
        if not (guilds or users or channels or groups):
            return False
        self.guilds = guilds
        self.users = users
        self.channels = channels
        self.groups = groups
        self._sync_policy_api()
        admin._persist_namespace("chat")
        self._clear_legacy_chat_stores()
        return True

    def init(self):
        if self.loaded:
            return self.channels

        from modules.policy_admin import get_or_create_policy_admin

        admin = get_or_create_policy_admin(self.sonata)
        if self._has_native_chat():
            admin.load_namespace("chat")
        else:
            self._migrate_legacy_to_native(admin)

        self.refresh_from_policy_api()
        self.loaded = True
        return self.channels

    def get_guilds(self):
        if not self.loaded:
            self.init()
        return {guild_id: policy.clone() for guild_id, policy in self.guilds.items()}

    def get_guild_policy(self, guild_id):
        if not self.loaded:
            self.init()
        policy = self.guilds.get(str(guild_id))
        if policy is None:
            return ChannelPolicy.default()
        return policy.clone()

    def get_users(self):
        if not self.loaded:
            self.init()
        return {user_id: policy.clone() for user_id, policy in self.users.items()}

    def get_user_policy(self, user_id):
        if not self.loaded:
            self.init()
        policy = self.users.get(str(user_id))
        if policy is None:
            return ChannelPolicy.default()
        return policy.clone()

    def set_guild_policy(self, guild_id, **updates):
        key = str(guild_id)
        current = self.get_guild_policy(key)
        policy = current.with_updates(**updates)
        self.guilds[key] = policy
        self._sync_guild_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def set_user_policy(self, user_id, **updates):
        key = str(user_id)
        current = self.get_user_policy(key)
        policy = current.with_updates(**updates)
        self.users[key] = policy
        self._sync_user_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def remove_guild_policy(self, guild_id):
        if not self.loaded:
            self.init()
        key = str(guild_id)
        removed = self.guilds.pop(key, None)
        self.policy_api.clear_scope("chat", "guild", key)
        self._persist()
        return removed.clone() if removed is not None else None

    def set_guild_flag(self, guild_id, key, value):
        if key not in {"can_speak", "respond_all"}:
            raise ValueError("Guild flag must be can_speak or respond_all")
        return self.set_guild_policy(guild_id, **{key: bool(value)})

    def remove_user_policy(self, user_id):
        if not self.loaded:
            self.init()
        key = str(user_id)
        removed = self.users.pop(key, None)
        self.policy_api.clear_scope("chat", "user", key)
        self._persist()
        return removed.clone() if removed is not None else None

    def set_user_flag(self, user_id, key, value):
        if key not in {"can_speak", "respond_all"}:
            raise ValueError("User flag must be can_speak or respond_all")
        return self.set_user_policy(user_id, **{key: bool(value)})

    def allow_user_command(self, user_id, command):
        key = str(user_id)
        policy = self.get_user_policy(key).allow_command(command)
        self.users[key] = policy
        self._sync_user_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def deny_user_command(self, user_id, command):
        key = str(user_id)
        policy = self.get_user_policy(key).deny_command(command)
        self.users[key] = policy
        self._sync_user_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def allow_guild_command(self, guild_id, command):
        key = str(guild_id)
        policy = self.get_guild_policy(key).allow_command(command)
        self.guilds[key] = policy
        self._sync_guild_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def deny_guild_command(self, guild_id, command):
        key = str(guild_id)
        policy = self.get_guild_policy(key).deny_command(command)
        self.guilds[key] = policy
        self._sync_guild_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def upsert_user_group(self, name, *, members=None, role_ids=None):
        group_id = self.policy_api.upsert_group(
            "chat",
            name,
            members=members,
            role_ids=role_ids,
        )
        self.loaded = True
        self._persist()
        return group_id

    def remove_user_group(self, name):
        removed = self.policy_api.remove_group("chat", name)
        self.loaded = True
        self._persist()
        return removed

    def allow_group_command(self, group_name, command):
        command_name = normalize_command_name(command)
        if not command_name:
            return None
        rule = self.policy_api.set_group_rule(
            "chat", group_name, f"chat.command.{command_name}", EFFECT_ALLOW
        )
        self.loaded = True
        self._persist()
        return rule

    def deny_group_command(self, group_name, command):
        command_name = normalize_command_name(command)
        if not command_name:
            return None
        rule = self.policy_api.set_group_rule(
            "chat", group_name, f"chat.command.{command_name}", EFFECT_DENY
        )
        self.loaded = True
        self._persist()
        return rule

    def allow_group_feature(self, group_name, action):
        action_name = str(action or "").strip().lower()
        if not action_name:
            return None
        rule = self.policy_api.set_group_rule(
            "chat", group_name, action_name, EFFECT_ALLOW
        )
        self.loaded = True
        self._persist()
        return rule

    def deny_group_feature(self, group_name, action):
        action_name = str(action or "").strip().lower()
        if not action_name:
            return None
        rule = self.policy_api.set_group_rule(
            "chat", group_name, action_name, EFFECT_DENY
        )
        self.loaded = True
        self._persist()
        return rule

    def get_channels(self):
        if not self.loaded:
            self.init()
        return {
            channel_id: policy.clone() for channel_id, policy in self.channels.items()
        }

    def get_channel_policy(self, channel_id):
        if not self.loaded:
            self.init()
        policy = self.channels.get(str(channel_id))
        if policy is None:
            return ChannelPolicy.default()
        return policy.clone()

    def set_channel_policy(self, channel_id, **updates):
        key = str(channel_id)
        current = self.get_channel_policy(key)
        policy = current.with_updates(**updates)
        self.channels[key] = policy
        self._sync_channel_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def remove_channel_policy(self, channel_id):
        if not self.loaded:
            self.init()
        key = str(channel_id)
        removed = self.channels.pop(key, None)
        self.policy_api.clear_scope("chat", "channel", key)
        self._clear_beacon_chat_history_rule(key)
        self._persist()
        return removed.clone() if removed is not None else None

    def set_channel_flag(self, channel_id, key, value):
        if key not in {"can_speak", "respond_all", "protected"}:
            raise ValueError("Channel flag must be can_speak, respond_all or protected")
        return self.set_channel_policy(channel_id, **{key: bool(value)})

    def allow_command(self, channel_id, command):
        key = str(channel_id)
        policy = self.get_channel_policy(key).allow_command(command)
        self.channels[key] = policy
        self._sync_channel_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def deny_command(self, channel_id, command):
        key = str(channel_id)
        policy = self.get_channel_policy(key).deny_command(command)
        self.channels[key] = policy
        self._sync_channel_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def blacklist_add(self, channel_id):
        key = str(channel_id)
        policy = ChannelPolicy.blacklisted()
        self.channels[key] = policy
        self._sync_channel_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    def blacklist_remove(self, channel_id):
        key = str(channel_id)
        policy = ChannelPolicy.default()
        self.channels[key] = policy
        self._sync_channel_scope(key, policy)
        self.loaded = True
        self._persist()
        return policy.clone()

    # --- Evaluation helpers (merge guild/channel/user/group via policy_api.EVAL_PRECEDENCE) ---

    def can_speak(
        self, guild_id, channel_id, user_id=None, role_ids=None, group_ids=None
    ):
        return self.policy_api.evaluate(
            "chat",
            "chat.can_speak",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            role_ids=role_ids,
            group_ids=group_ids,
            default=True,
        )

    def should_respond_all(
        self,
        guild_id,
        channel_id,
        user_id=None,
        role_ids=None,
        group_ids=None,
    ):
        return self.policy_api.evaluate(
            "chat",
            "chat.respond_all",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            role_ids=role_ids,
            group_ids=group_ids,
            default=False,
        )

    def is_protected(
        self,
        guild_id,
        channel_id,
        user_id=None,
        role_ids=None,
        group_ids=None,
    ):
        # Channel-only: privacy/logging must not be overridden by user/group rules,
        # and Beacon encryption is keyed per channel path.
        return self.policy_api.evaluate(
            "chat",
            "chat.protected",
            channel_id=channel_id,
            default=False,
        )

    def is_command_allowed(
        self,
        guild_id,
        channel_id,
        command,
        user_id=None,
        role_ids=None,
        group_ids=None,
    ):
        command_name = normalize_command_name(command)
        if not command_name:
            return True  # Non-$ messages are not gated by command rules
        return self.policy_api.evaluate(
            "chat",
            f"chat.command.{command_name}",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            role_ids=role_ids,
            group_ids=group_ids,
            default=True,
        )


def default_channel_policy(can_speak=True):
    if can_speak:
        return ChannelPolicy.default().to_dict()
    return ChannelPolicy.blacklisted().to_dict()


def normalize_allowed_commands(commands, fallback_to_wildcard=False):
    return normalize_commands(commands)


def normalize_channel_policy(policy):
    return ChannelPolicy.normalize(policy).to_dict()


def get_channel_policy(config, channel_id):
    channels = config.get("channels", {})
    return ChannelPolicy.normalize(channels.get(str(channel_id))).to_dict()


def is_command_allowed(channel_policy, command):
    return ChannelPolicy.normalize(channel_policy).allows_command(command)


def get_command_name(message):
    if not message or not message.startswith("$"):
        return ""
    split = message[1:].strip().split(" ", 1)
    return split[0].lower() if split else ""


def parse_bool(value):
    value = str(value).strip().lower()
    if value in {"1", "true", "t", "yes", "y", "on", "enable", "enabled"}:
        return True
    if value in {"0", "false", "f", "no", "n", "off", "disable", "disabled"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def format_channel_policy(channel_id, policy):
    return f"`{channel_id}` -> {ChannelPolicy.normalize(policy)}"


def resolve_channel_in_guild(
    guild, raw_channel, current_channel=None, allow_current=False
):
    if guild is None:
        return None, "This command only works in a server."

    raw = str(raw_channel).strip()
    if allow_current and raw.lower() in {"here", "current", "this"}:
        if current_channel is not None:
            return current_channel, None
        return None, "No current channel is set."

    channel_id = parse_channel_reference(raw)
    if channel_id is None:
        return None, "Channel must be a channel id or Discord channel mention."

    channel = guild.get_channel(channel_id)
    if channel is not None:
        return channel, None
    return None, f"Channel id `{raw_channel}` was not found."
