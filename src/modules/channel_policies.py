import re
from dataclasses import dataclass

from modules.policy_api import EFFECT_ALLOW, EFFECT_DENY, get_or_create_policy_api


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


@dataclass
class ChannelPolicy:
    can_speak: bool = True
    respond_all: bool = False
    command_policy_mode: str = DENYLIST
    commands: list[str] | None = None

    def __post_init__(self):
        self.can_speak = bool(self.can_speak)
        self.respond_all = bool(self.respond_all)
        if self.command_policy_mode not in {ALLOWLIST, DENYLIST}:
            self.command_policy_mode = DENYLIST
        self.commands = normalize_commands(self.commands)

    @classmethod
    def default(cls):
        return cls(
            can_speak=True,
            respond_all=False,
            command_policy_mode=DENYLIST,
            commands=[],
        )

    @classmethod
    def blacklisted(cls):
        return cls(
            can_speak=False,
            respond_all=False,
            command_policy_mode=ALLOWLIST,
            commands=[],
        )

    @classmethod
    def normalize(cls, policy=None):
        if isinstance(policy, cls):
            return cls(
                can_speak=policy.can_speak,
                respond_all=policy.respond_all,
                command_policy_mode=policy.command_policy_mode,
                commands=policy.commands,
            )

        if not isinstance(policy, dict):
            return cls.default()

        return cls(
            can_speak=policy.get("can_speak", True),
            respond_all=policy.get("respond_all", False),
            command_policy_mode=policy.get("command_policy_mode", DENYLIST),
            commands=policy.get("commands", []),
        )

    def to_dict(self):
        return {
            "can_speak": self.can_speak,
            "respond_all": self.respond_all,
            "command_policy_mode": self.command_policy_mode,
            "commands": list(self.commands),
        }

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
            f"command_policy_mode={self.command_policy_mode}, "
            f"commands=[{commands}]"
        )


class ChannelPolicies:
    def __init__(self, sonata):
        self.sonata = sonata
        self.channels = {}
        self.loaded = False
        self.policy_api = get_or_create_policy_api(sonata)
        self._ensure_chat_namespace()

    def _ensure_chat_namespace(self):
        if self.policy_api.has_namespace("chat"):
            return
        self.policy_api.register_namespace(
            "chat",
            plugin=True,
            default_decisions={
                "chat.can_speak": True,
                "chat.respond_all": False,
                "chat.command.*": True,
            },
        )

    def _sync_channel_scope(self, channel_id, policy):
        key = str(channel_id)
        policy = ChannelPolicy.normalize(policy)
        self.policy_api.clear_scope("chat", "channel", key)

        if not policy.can_speak:
            self.policy_api.set_rule(
                "chat", "channel", key, "chat.can_speak", EFFECT_DENY
            )

        if policy.respond_all:
            self.policy_api.set_rule(
                "chat", "channel", key, "chat.respond_all", EFFECT_ALLOW
            )

        if policy.command_policy_mode == DENYLIST:
            for command in policy.commands:
                self.policy_api.set_rule(
                    "chat",
                    "channel",
                    key,
                    f"chat.command.{normalize_command_name(command)}",
                    EFFECT_DENY,
                )
        else:
            self.policy_api.set_rule(
                "chat", "channel", key, "chat.command.*", EFFECT_DENY
            )
            for command in policy.commands:
                self.policy_api.set_rule(
                    "chat",
                    "channel",
                    key,
                    f"chat.command.{normalize_command_name(command)}",
                    EFFECT_ALLOW,
                )

    def _sync_policy_api(self):
        for channel_id, policy in self.channels.items():
            self._sync_channel_scope(channel_id, policy)

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

    def _persist(self):
        serialized = self._serialize_channels()
        self.sonata.config.set(channels=serialized)
        if hasattr(self.sonata, "beacon"):
            self.sonata.beacon.branch("policies").illuminate("channels", serialized)

    def init(self):
        beacon_channels = {}
        if hasattr(self.sonata, "beacon"):
            beacon_channels = (
                self.sonata.beacon.branch("policies").discover("channels") or {}
            )
        configured_channels = self.sonata.config.get("channels", {})
        channels = {}
        channels.update(self._normalize_channels_map(beacon_channels))
        channels.update(self._normalize_channels_map(configured_channels))
        self.channels = channels
        self.loaded = True
        self._sync_policy_api()
        self._persist()
        return self.channels

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
        self._persist()
        return removed.clone() if removed is not None else None

    def set_channel_flag(self, channel_id, key, value):
        if key not in {"can_speak", "respond_all"}:
            raise ValueError("Channel flag must be can_speak or respond_all")
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

    def can_speak(self, guild_id, channel_id, user_id=None):
        return self.policy_api.evaluate(
            "chat",
            "chat.can_speak",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            default=True,
        )

    def should_respond_all(self, guild_id, channel_id, user_id=None):
        return self.policy_api.evaluate(
            "chat",
            "chat.respond_all",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            default=False,
        )

    def is_command_allowed(self, guild_id, channel_id, command, user_id=None):
        command_name = normalize_command_name(command)
        if not command_name:
            return True
        return self.policy_api.evaluate(
            "chat",
            f"chat.command.{command_name}",
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
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
