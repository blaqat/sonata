"""
Load Sonata runtime and plugin configuration from `sonata.config.json` (or `SONATA_CONFIG`).

Plugin defaults are discovered from the plugin modules, then project-level defaults are
layered on top so the config file only needs to override what you want to change.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from random import randint
from typing import Any

from modules.plugins import PLUGINS_DICT


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
class RuntimeConfig:
    random_config: bool = False
    prompt_reset: bool = False
    vc_recording: bool = False
    vc_speaking: bool = True


def _plugin_defaults_from_modules() -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for plugin_name, plugin in PLUGINS_DICT.items():
        context = getattr(plugin, "CONTEXT", None)
        defaults[plugin_name] = deepcopy(getattr(context, "plugin_config", {}) or {})
    return defaults


def _project_plugin_defaults() -> dict[str, Any]:
    return {
        "chat": {
            "summarize": True,
            "max_chats": 30,
            "view_replies": True,
            "auto": "c",
            "ignore": [],
            "response_map": {
                "subi": [
                    0.005,
                    "i dont know but can you play piano for me? <a:kittypleading:1213940324658057236>",
                ],
                "log": [0.005, "BWAAAAAAAA BWAAAAAA BWAAAAAAAAAAAAA"],
                "blaqat": [0.005, "yes master"],
                "ans": [0.01, "youre the robot why dont u tell me hmmm?"],
            },
            "bot_whitelist": [
                "BluBot",
                1311742291521835048,
                746799398994051162,
            ],
            "censor": False,
        },
        "self_commands": {
            "gif_search": "random",
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
    }


def _default_document() -> dict[str, Any]:
    return {
        "runtime": {
            "random_config": False,
            "prompt_reset": False,
            "vc_recording": False,
            "vc_speaking": True,
        },
        "plugins": deep_merge(_plugin_defaults_from_modules(), _project_plugin_defaults()),
    }


def _runtime_from_dict(data: dict[str, Any]) -> RuntimeConfig:
    return RuntimeConfig(
        random_config=bool(data.get("random_config", False)),
        prompt_reset=bool(data.get("prompt_reset", False)),
        vc_recording=bool(data.get("vc_recording", False)),
        vc_speaking=bool(data.get("vc_speaking", True)),
    )


def load_config(path: Path | None = None) -> tuple[RuntimeConfig, dict[str, Any]]:
    """Return runtime settings and merged plugin kwargs for `Sonata.extend`."""
    doc = _default_document()
    cfg_path = path or config_file_path()
    if cfg_path.is_file():
        with open(cfg_path, encoding="utf-8") as f:
            loaded = json.load(f)
        doc = deep_merge(doc, loaded)

    runtime = _runtime_from_dict(doc["runtime"])
    plugins = deepcopy(doc["plugins"])
    return runtime, plugins


def rand_runtime(runtime: RuntimeConfig, plugins: dict[str, Any]) -> None:
    """Randomize the same runtime and plugin toggles as the former `rand_config()`."""
    models = ["g", "o", "c", "a", "m", "x"]
    gif_searches = ["tenor", "giphy", "google", "random"]

    runtime.prompt_reset = bool(randint(0, 1))
    runtime.vc_recording = bool(randint(0, 1))
    runtime.vc_speaking = bool(randint(0, 1))

    plugins.setdefault("chat", {})["auto"] = models[randint(0, len(models) - 1)]
    plugins.setdefault("self_commands", {})["gif_search"] = gif_searches[
        randint(0, len(gif_searches) - 1)
    ]
    plugins["self_commands"]["agent"] = bool(randint(0, 1))
    plugins.setdefault("term_commands", {})["inject_emojis"] = bool(randint(0, 1))
