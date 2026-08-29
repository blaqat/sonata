"""
Load Sonata runtime and plugin configuration from `sonata.config.json` (or `SONATA_CONFIG`).

Plugin defaults are discovered from the plugin modules, then project-level defaults are
layered on top so the config file only needs to override what you want to change.
"""

from __future__ import annotations

import json
import os
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from random import randint
from typing import Any

from modules.plugins import PLUGINS_DICT

_DEFAULT_AI_MODELS: dict[str, str] = {
    "dall_e": "gpt-image-2",
    "assistant": "gpt-4o",
    "grok": "grok-4.6",
    "openai": "gpt-5.6-terra",
    "claude": "claude-sonnet-4-6",
    "perplexity": "sonar",
    "gemini": "gemini-3.6-flash",
    "imagen": "gemini-3.1-flash-image",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_file_path() -> Path:
    env = os.environ.get("SONATA_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return _project_root() / "sonata.config.json"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


@dataclass
class AIModels:
    """Per-provider model id overrides. Empty or missing uses the built-in default for that AI."""

    dall_e: str | None = None
    assistant: str | None = None
    grok: str | None = None
    openai: str | None = None
    claude: str | None = None
    perplexity: str | None = None
    gemini: str | None = None
    imagen: str | None = None


@dataclass
class RuntimeConfig:
    random_config: bool = False
    prompt_reset: bool = False
    vc_recording: bool = False
    vc_speaking: bool = True
    ai_models: AIModels = field(default_factory=AIModels)


def resolve_ai_model(runtime: RuntimeConfig, key: str, builtin_default: str) -> str:
    """Use runtime.ai_models.<key> when set, else builtin_default (the previous hardcoded value)."""
    if key not in {f.name for f in fields(AIModels)}:
        return builtin_default
    raw = getattr(runtime.ai_models, key, None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return builtin_default


def configured_ai_model(key: str, runtime: RuntimeConfig | None = None) -> str:
    """Resolve a provider model id from live runtime config, else the built-in default.

    Same source as Gemini/OpenAI registration in ``index.py``: the loaded
    ``RuntimeConfig.ai_models`` value, falling back to ``_DEFAULT_AI_MODELS``.
    Uses the hot-reloaded ``_RUNTIME_INSTANCE`` when no runtime is passed.
    """
    builtin = _DEFAULT_AI_MODELS[key]
    source = runtime if runtime is not None else _RUNTIME_INSTANCE
    if source is None:
        return builtin
    return resolve_ai_model(source, key, builtin)


def _ai_models_from_merged_runtime(data: dict[str, Any]) -> AIModels:
    merged = {**_DEFAULT_AI_MODELS, **(data.get("ai_models") or {})}
    kwargs = {f.name: merged.get(f.name) for f in fields(AIModels)}
    return AIModels(**kwargs)


def _plugin_defaults_from_modules() -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for plugin_name, plugin in PLUGINS_DICT.items():
        context = getattr(plugin, "CONTEXT", None)
        defaults[plugin_name] = deepcopy(getattr(context, "plugin_config", {}) or {})
    return defaults


def _project_plugin_defaults() -> dict[str, Any]:
    from cursor_cloud.config import DEFAULT_PLUGIN_CONFIG

    return {
        "chat": {
            "summarize": True,
            "max_chats": 30,
            "view_replies": True,
            "auto": "c",
            "ignore": [],
            "bot_whitelist": [
                "BluBot",
                1311742291521835048,
                746799398994051162,
                1527366826793894109,
            ],
            "censor": False,
        },
        "self_commands": {
            "gif_search": "klipy",
            "agent": False,
            "search": {
                "num_results": 2,
            },
            "video": {
                "limit": 1,
                "max_results": 5,
            },
            "music": {
                "num_links": 1,
                "max_tracks_to_check": 10,
            },
        },
        "term_commands": {
            "inject_emojis": False,
        },
        "cursor": deepcopy(DEFAULT_PLUGIN_CONFIG),
    }


def _default_document() -> dict[str, Any]:
    return {
        "runtime": {
            "random_config": False,
            "prompt_reset": False,
            "vc_recording": False,
            "vc_speaking": True,
            "ai_models": dict(_DEFAULT_AI_MODELS),
        },
        "plugins": deep_merge(_plugin_defaults_from_modules(), _project_plugin_defaults()),
    }


def _runtime_from_dict(data: dict[str, Any]) -> RuntimeConfig:
    return RuntimeConfig(
        random_config=bool(data.get("random_config", False)),
        prompt_reset=bool(data.get("prompt_reset", False)),
        vc_recording=bool(data.get("vc_recording", False)),
        vc_speaking=bool(data.get("vc_speaking", True)),
        ai_models=_ai_models_from_merged_runtime(data),
    )


def load_config(path: Path | None = None) -> tuple[RuntimeConfig, dict[str, Any]]:
    """Return runtime settings and merged plugin kwargs for `Sonata.extend`."""
    global _RUNTIME_INSTANCE, _FILE_DOC
    doc = _default_document()
    cfg_path = path or config_file_path()
    global _CONFIG_PATH
    _CONFIG_PATH = cfg_path
    if cfg_path.is_file():
        with open(cfg_path, encoding="utf-8") as f:
            loaded = json.load(f)
        doc = deep_merge(doc, loaded)

    runtime = _runtime_from_dict(doc["runtime"])
    plugins = deepcopy(doc["plugins"])

    # Track the live instances so the config updater can hot-apply changes.
    _RUNTIME_INSTANCE = runtime
    if path is None:
        _FILE_DOC = _read_file_doc()
    else:
        try:
            with open(cfg_path, encoding="utf-8") as f:
                _FILE_DOC = json.load(f)
            if not isinstance(_FILE_DOC, dict):
                _FILE_DOC = {}
        except Exception:
            _FILE_DOC = {}

    return runtime, plugins


def rand_runtime(runtime: RuntimeConfig, plugins: dict[str, Any]) -> None:
    """Randomize the same runtime and plugin toggles as the former `rand_config()`."""
    models = ["g", "o", "c", "a", "m", "x"]
    gif_searches = ["klipy", "giphy", "google", "random", "tenor"]

    runtime.prompt_reset = bool(randint(0, 1))
    runtime.vc_recording = bool(randint(0, 1))
    runtime.vc_speaking = bool(randint(0, 1))

    plugins.setdefault("chat", {})["auto"] = models[randint(0, len(models) - 1)]
    plugins.setdefault("self_commands", {})["gif_search"] = gif_searches[
        randint(0, len(gif_searches) - 1)
    ]
    plugins["self_commands"]["agent"] = bool(randint(0, 1))
    plugins.setdefault("term_commands", {})["inject_emojis"] = bool(randint(0, 1))


# -------------------------------------------------------------------
# Runtime config updater (web terminal admin surface -- see SONA-38)
# -------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigField:
    """One editable config key exposed through the web terminal."""

    path: str
    label: str
    type: str  # bool | int | str | select | list
    group: str
    hot_reloadable: bool
    options: tuple[str, ...] = ()
    description: str = ""


AI_MODEL_FIELDS = tuple(_DEFAULT_AI_MODELS.keys())

# Maps `runtime.ai_models.<key>` to the registered AI_Type name so model id
# changes can be swapped into live AI requests without a restart.
_AI_MODEL_TO_TYPE = {
    "dall_e": "DallE",
    "assistant": "Assistant",
    "grok": "Grok",
    "openai": "OpenAI",
    "claude": "Claude",
    "perplexity": "Perplexity",
    "gemini": "Gemini",
    "imagen": "NanoBanana",
}

EDITABLE_FIELDS: tuple[ConfigField, ...] = (
    ConfigField(
        "runtime.prompt_reset",
        "Prompt Reset",
        "bool",
        "Runtime",
        False,
        description="Reinstall default instructions on next startup.",
    ),
    ConfigField(
        "runtime.random_config",
        "Random Config",
        "bool",
        "Runtime",
        False,
        description="Randomize toggles on next startup.",
    ),
    ConfigField(
        "runtime.vc_recording",
        "VC Recording",
        "bool",
        "Runtime",
        True,
        description="Auto-record when Sonata joins voice chat.",
    ),
    ConfigField(
        "runtime.vc_speaking",
        "VC Speaking",
        "bool",
        "Runtime",
        True,
        description="Allow TTS replies in voice chat.",
    ),
    *(
        ConfigField(
            f"runtime.ai_models.{key}",
            f"Model: {key}",
            "str",
            "Runtime",
            True,
            description=f"Model id override for {key}. Empty uses the built-in default.",
        )
        for key in AI_MODEL_FIELDS
    ),
    ConfigField(
        "plugins.chat.auto",
        "Chat Auto Model",
        "select",
        "Chat",
        True,
        options=("g", "o", "c", "a", "m", "x"),
        description="Default AI shortcut used for chat replies.",
    ),
    ConfigField(
        "plugins.chat.summarize",
        "Summarize Chats",
        "bool",
        "Chat",
        True,
    ),
    ConfigField(
        "plugins.chat.max_chats",
        "Max Chats Kept",
        "int",
        "Chat",
        True,
    ),
    ConfigField(
        "plugins.chat.view_replies",
        "View Replies",
        "bool",
        "Chat",
        True,
        description="Include replied-to context in prompts.",
    ),
    ConfigField(
        "plugins.chat.censor",
        "Censor Messages",
        "bool",
        "Chat",
        True,
    ),
    ConfigField(
        "plugins.chat.bot_whitelist",
        "Bot Whitelist",
        "list",
        "Chat",
        True,
        description="Bots allowed to run commands. Usernames or Discord user IDs.",
    ),
    ConfigField(
        "plugins.self_commands.agent",
        "Agent Mode",
        "bool",
        "Self Commands",
        True,
    ),
    ConfigField(
        "plugins.self_commands.gif_search",
        "GIF Search Engine",
        "select",
        "Self Commands",
        True,
        options=("klipy", "giphy", "google", "random", "tenor"),
    ),
    ConfigField(
        "plugins.self_commands.search.num_results",
        "Search Results",
        "int",
        "Self Commands",
        True,
    ),
    ConfigField(
        "plugins.term_commands.inject_emojis",
        "Inject Emojis",
        "bool",
        "Term Commands",
        False,
        description="Loaded once when the terminal loop starts; needs a restart.",
    ),
)

_MUTATION_LOG: deque[dict[str, Any]] = deque(maxlen=50)
_RUNTIME_INSTANCE: RuntimeConfig | None = None
_FILE_DOC: dict[str, Any] | None = None
_CONFIG_PATH: Path | None = None


class ConfigUpdateError(ValueError):
    """Raised when a config update fails validation."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def _field_by_path(path: str) -> ConfigField | None:
    for field_def in EDITABLE_FIELDS:
        if field_def.path == path:
            return field_def
    return None


def _doc_get(doc: dict[str, Any], path: str) -> Any:
    node: Any = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _doc_set(doc: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = doc
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _effective_doc() -> dict[str, Any]:
    file_doc = _FILE_DOC if _FILE_DOC is not None else _read_file_doc()
    return deep_merge(_default_document(), file_doc)


def _read_file_doc() -> dict[str, Any]:
    cfg_path = config_file_path()
    if not cfg_path.is_file():
        return {}
    try:
        with open(cfg_path, encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def save_config() -> Path:
    """Atomically persist the tracked override document back to disk."""
    if _FILE_DOC is None:
        raise RuntimeError("No config document loaded; call load_config() first.")
    cfg_path = _CONFIG_PATH or config_file_path()
    tmp_path = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_FILE_DOC, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp_path.replace(cfg_path)
    return cfg_path


def get_runtime_config() -> dict[str, Any]:
    """Return the safe, editable config view for the web terminal.

    Only allowlisted fields are returned -- never raw secrets or env-backed keys.
    """
    effective = _effective_doc()
    values: dict[str, Any] = {}
    for field_def in EDITABLE_FIELDS:
        value = _doc_get(effective, field_def.path)
        values[field_def.path] = value if value is not None else (
            "" if field_def.type == "str" else [] if field_def.type == "list" else None
        )
    return {
        "fields": [asdict(field_def) for field_def in EDITABLE_FIELDS],
        "values": values,
        "recent_mutations": list(_MUTATION_LOG),
    }


def get_config_view() -> dict[str, Any]:
    """Compatibility name for callers that treat this as a UI view."""
    return get_runtime_config()


def _validate_value(field_def: ConfigField, value: Any) -> tuple[bool, str, Any]:
    """Return (ok, error_message, normalized_value)."""
    if field_def.type == "bool":
        if isinstance(value, bool):
            return True, "", value
        return False, "must be true or false", value

    if field_def.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return False, "must be an integer", value
        if field_def.path == "plugins.chat.max_chats" and value < 0:
            return False, "must be a non-negative integer", value
        return True, "", value

    if field_def.type == "str":
        if not isinstance(value, str):
            return False, "must be a string", value
        return True, "", value.strip()

    if field_def.type == "select":
        if isinstance(value, str) and value.strip() in field_def.options:
            return True, "", value.strip()
        allowed = ", ".join(field_def.options)
        return False, f"must be one of: {allowed}", value

    if field_def.type == "list":
        if not isinstance(value, list):
            return False, "must be a list", value
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                return False, "entries must be usernames or user IDs", value
            text = str(item).strip()
            if not text:
                continue
            # Discord IDs pasted as strings normalize to ints so chat.py's
            # `author.id not in whitelist` check matches.
            normalized.append(int(text) if text.isdigit() else text)
        return True, "", normalized

    return False, "unsupported field type", value


def _live_apply_runtime(field_def: ConfigField, value: Any) -> None:
    if field_def.path.startswith("runtime.ai_models."):
        key = field_def.path.rsplit(".", 1)[-1]
        if _RUNTIME_INSTANCE is not None and hasattr(_RUNTIME_INSTANCE.ai_models, key):
            setattr(_RUNTIME_INSTANCE.ai_models, key, value or _DEFAULT_AI_MODELS[key])
        return
    leaf = field_def.path.split(".")[-1]
    if _RUNTIME_INSTANCE is not None and hasattr(_RUNTIME_INSTANCE, leaf):
        setattr(_RUNTIME_INSTANCE, leaf, value)


def _live_apply_ai_model(key: str, value: str) -> None:
    """Swap the resolved model into the registered AI_Type without a restart."""
    try:
        from modules.AI_manager import AI_TYPES

        ai_type = AI_TYPES.get(_AI_MODEL_TO_TYPE.get(key, ""))
        if ai_type is None:
            return
        model = value.strip() or _DEFAULT_AI_MODELS.get(key)
        if isinstance(model, str) and model:
            ai_type.config["model"] = model
    except Exception:
        pass


def _live_apply_plugin(path: str, value: Any) -> None:
    """Push a plugin override into the flat live Sonata config memory."""
    try:
        from modules.AI_manager import AI_Manager

        manager = AI_Manager.M.MANAGER
        if manager is None:
            return
        parts = path.split(".")[1:]
        live_parts = parts[1:]
        if not live_parts:
            return
        key = live_parts[0]
        if len(live_parts) == 1:
            manager.config.set(**{key: deepcopy(value)})
            return

        current = manager.config.get(key, {})
        nested = deepcopy(current) if isinstance(current, dict) else {}
        _doc_set(nested, ".".join(live_parts[1:]), value)
        manager.config.set(**{key: nested})
    except Exception:
        pass


def _log_mutation(actor: str, applied: dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor,
        "changes": applied,
    }
    _MUTATION_LOG.appendleft(entry)


def update_runtime_config(updates: dict[str, Any], actor: str = "unknown") -> dict[str, Any]:
    """Validate, persist and live-apply partial updates keyed by dotted path.

    Raises ConfigUpdateError when any key fails validation; nothing is written.
    """
    if not isinstance(updates, dict) or not updates:
        raise ConfigUpdateError({"updates": "a non-empty object of changes is required"})

    unknown = sorted(set(updates) - {f.path for f in EDITABLE_FIELDS})
    if unknown:
        raise ConfigUpdateError({path: "unknown config key" for path in unknown})

    validated: dict[str, tuple[ConfigField, Any]] = {}
    errors: dict[str, str] = {}
    for path, value in updates.items():
        field_def = _field_by_path(path)
        assert field_def is not None
        ok, message, normalized = _validate_value(field_def, value)
        if ok:
            validated[path] = (field_def, normalized)
        else:
            errors[path] = message
    if errors:
        raise ConfigUpdateError(errors)

    global _FILE_DOC
    if _FILE_DOC is None:
        _FILE_DOC = _read_file_doc()

    applied_values: dict[str, Any] = {}
    restart_required: list[str] = []
    original_doc = deepcopy(_FILE_DOC)
    try:
        for path, (field_def, value) in validated.items():
            _doc_set(_FILE_DOC, path, value)
            applied_values[path] = value
            if not field_def.hot_reloadable:
                restart_required.append(path)

        save_config()
    except Exception:
        # Roll back so rejected values never leak into views or a later save.
        _FILE_DOC.clear()
        _FILE_DOC.update(original_doc)
        raise

    for path, (field_def, value) in validated.items():
        if path.startswith("runtime.ai_models."):
            _live_apply_ai_model(path.rsplit(".", 1)[-1], value)
            _live_apply_runtime(field_def, value)
        elif path.startswith("runtime."):
            _live_apply_runtime(field_def, value)
        else:
            _live_apply_plugin(path, value)

    _log_mutation(actor, applied_values)

    return {
        "ok": True,
        "applied": sorted(applied_values),
        "restart_required": restart_required,
        "values": {f.path: _doc_get(_effective_doc(), f.path) for f in EDITABLE_FIELDS},
    }
