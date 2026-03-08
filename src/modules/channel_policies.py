import re


LEGACY_CHANNEL_BLACKLIST = {
    1175907292072398858,
    724158738138660894,
    725170957206945859,
}


def default_channel_policy(can_speak=True):
    return {
        "can_speak": can_speak,
        "respond_all": False,
        "allowed_commands": ["*"] if can_speak else [],
    }


def normalize_allowed_commands(commands):
    if commands is None:
        return ["*"]
    if not isinstance(commands, (list, tuple, set)):
        commands = [commands]

    normalized = []
    for command in commands:
        if command is None:
            continue
        command = str(command).strip().lower()
        if command.startswith("$"):
            command = command[1:]
        if command and command not in normalized:
            normalized.append(command)

    return normalized or ["*"]


def normalize_channel_policy(policy):
    base = default_channel_policy()
    if isinstance(policy, dict):
        base["can_speak"] = bool(policy.get("can_speak", base["can_speak"]))
        base["respond_all"] = bool(policy.get("respond_all", base["respond_all"]))
        base["allowed_commands"] = normalize_allowed_commands(
            policy.get("allowed_commands", base["allowed_commands"])
        )
    return base


def normalize_channels_map(channels):
    if not isinstance(channels, dict):
        return {}
    return {
        str(channel_id): normalize_channel_policy(policy)
        for channel_id, policy in channels.items()
    }


def merge_channels(*channels_maps):
    merged = {}
    for channels in channels_maps:
        merged.update(normalize_channels_map(channels))
    return merged


def ensure_channels_config(config):
    channels = normalize_channels_map(config.get("channels", {}))
    if not channels:
        channels = {
            str(channel_id): default_channel_policy(can_speak=False)
            for channel_id in LEGACY_CHANNEL_BLACKLIST
        }
        config.set(channels=channels)
    return channels


def persist_channels(sonata, channels):
    if not hasattr(sonata, "beacon"):
        return
    sonata.beacon.branch("chat").guide("channels", channels)


def init_channels(sonata):
    default_channels = {
        str(channel_id): default_channel_policy(can_speak=False)
        for channel_id in LEGACY_CHANNEL_BLACKLIST
    }
    beacon_channels = {}
    if hasattr(sonata, "beacon"):
        beacon_channels = sonata.beacon.branch("chat").locate("channels") or {}
    configured_channels = sonata.config.get("channels", {})

    channels = merge_channels(default_channels, beacon_channels, configured_channels)
    sonata.config.set(channels=channels)
    persist_channels(sonata, channels)
    return channels


def get_channel_policy(config, channel_id):
    channels = ensure_channels_config(config)
    return normalize_channel_policy(channels.get(str(channel_id), default_channel_policy()))


def is_command_allowed(channel_policy, command):
    if not command:
        return True
    allowed_commands = channel_policy.get("allowed_commands", ["*"])
    return "*" in allowed_commands or command.lower() in allowed_commands


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
    allowed = policy.get("allowed_commands", [])
    allowed_str = ", ".join(allowed) if allowed else "(none)"
    return (
        f"`{channel_id}` -> "
        f"can_speak={policy.get('can_speak', True)}, "
        f"respond_all={policy.get('respond_all', False)}, "
        f"allowed_commands=[{allowed_str}]"
    )


def resolve_channel_in_guild(guild, raw_channel, current_channel=None):
    if guild is None:
        return None, "This command only works in a server."

    raw = str(raw_channel).strip()
    if raw.lower() in {"here", "current", "this"} and current_channel is not None:
        return current_channel, None

    mention_match = re.search(r"\d+", raw)
    if mention_match:
        channel = guild.get_channel(int(mention_match.group(0)))
        if channel is not None:
            return channel, None
        return None, f"Channel id `{raw_channel}` was not found."

    target_name = raw.lstrip("#").lower()
    for channel in guild.text_channels:
        if channel.name.lower() == target_name:
            return channel, None

    return None, f"Channel `{raw_channel}` was not found."
