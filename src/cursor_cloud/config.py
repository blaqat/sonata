"""Cursor Cloud configuration (file defaults + env secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .errors import ConfigurationError


DEFAULT_API_BASE = "https://api.cursor.com"
DEFAULT_PLUGIN_CONFIG: dict[str, Any] = {
    "enabled": False,
    "api_base_url": DEFAULT_API_BASE,
    "default_repository_url": "",
    "default_ref": "main",
    "default_model": "",
    "auto_create_pr": False,
    "chain_depth": 20,
    "max_images": 5,
    "max_image_bytes": 15 * 1024 * 1024,
    "status_edit_interval_ms": 1200,
    "connect_timeout_seconds": 10.0,
    "read_timeout_seconds": 60.0,
    "stream_timeout_seconds": 900.0,
    "max_recent_sessions": 20,
    "session_idle_prompt_minutes": 10,
    "max_retained_image_bytes": 40 * 1024 * 1024,
    "access": {
        "tier1_user_ids": [],
        "tier2_user_ids": [],
        "default_grant_minutes": 10,
        "approval_timeout_hours": 12,
        "min_grant_minutes": 1,
        "max_grant_minutes": 180,
        "audit_history_limit": 200,
    },
}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _parse_discord_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or not text.isdigit() or len(text) < 5:
        return None
    return text


@dataclass
class AccessConfig:
    tier1_user_ids: list[str] = field(default_factory=list)
    tier2_user_ids: list[str] = field(default_factory=list)
    default_grant_minutes: int = 10
    approval_timeout_hours: int = 12
    min_grant_minutes: int = 1
    max_grant_minutes: int = 180
    audit_history_limit: int = 200

    def clamp_grant_minutes(self, minutes: int | None) -> int:
        value = self.default_grant_minutes if minutes is None else int(minutes)
        return max(self.min_grant_minutes, min(self.max_grant_minutes, value))


@dataclass
class CursorCloudConfig:
    enabled: bool = False
    api_key: str = ""
    api_base_url: str = DEFAULT_API_BASE
    default_repository_url: str = ""
    default_ref: str = "main"
    default_model: str = ""
    auto_create_pr: bool = False
    chain_depth: int = 20
    max_images: int = 5
    max_image_bytes: int = 15 * 1024 * 1024
    status_edit_interval_ms: int = 1200
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    stream_timeout_seconds: float = 900.0
    max_recent_sessions: int = 20
    session_idle_prompt_minutes: int = 10
    max_retained_image_bytes: int = 40 * 1024 * 1024
    god_user_id: str | None = None
    access: AccessConfig = field(default_factory=AccessConfig)

    @property
    def is_ready(self) -> bool:
        return bool(
            self.enabled
            and self.api_key
            and self.god_user_id
            and self.default_repository_url
        )

    def readiness_error(self) -> str | None:
        if not self.enabled:
            return "Cursor plugin is disabled."
        if not self.api_key:
            return "CURSOR_API_KEY is not configured."
        if not self.god_user_id:
            return "GOD is missing or invalid; Cursor commands are fail-closed."
        if not self.default_repository_url:
            return "plugins.cursor.default_repository_url is required."
        return None

    def require_ready(self) -> None:
        err = self.readiness_error()
        if err:
            raise ConfigurationError(err)


def load_cursor_config(
    plugin_config: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> CursorCloudConfig:
    """Build config from plugin kwargs + environment (secrets never from JSON)."""
    env_map = env if env is not None else os.environ
    raw = {**DEFAULT_PLUGIN_CONFIG, **(plugin_config or {})}
    access_raw = {
        **DEFAULT_PLUGIN_CONFIG["access"],
        **(raw.get("access") or {}),
    }

    api_key = str(env_map.get("CURSOR_API_KEY") or "").strip()
    god_user_id = _parse_discord_id(env_map.get("GOD"))

    access = AccessConfig(
        tier1_user_ids=_as_str_list(access_raw.get("tier1_user_ids")),
        tier2_user_ids=_as_str_list(access_raw.get("tier2_user_ids")),
        default_grant_minutes=_as_int(access_raw.get("default_grant_minutes"), 10),
        approval_timeout_hours=_as_int(access_raw.get("approval_timeout_hours"), 12),
        min_grant_minutes=_as_int(access_raw.get("min_grant_minutes"), 1),
        max_grant_minutes=_as_int(access_raw.get("max_grant_minutes"), 180),
        audit_history_limit=_as_int(access_raw.get("audit_history_limit"), 200),
    )

    # Remove GOD from tier lists if mistakenly configured in JSON.
    if god_user_id:
        access.tier1_user_ids = [u for u in access.tier1_user_ids if u != god_user_id]
        access.tier2_user_ids = [u for u in access.tier2_user_ids if u != god_user_id]

    # Ambiguous membership: if listed in both, keep higher tier (Tier1).
    both = set(access.tier1_user_ids) & set(access.tier2_user_ids)
    if both:
        access.tier2_user_ids = [u for u in access.tier2_user_ids if u not in both]

    idle_minutes = _as_int(raw.get("session_idle_prompt_minutes"), 10)
    idle_minutes = max(1, min(240, idle_minutes))

    return CursorCloudConfig(
        enabled=bool(raw.get("enabled", False)),
        api_key=api_key,
        api_base_url=str(raw.get("api_base_url") or DEFAULT_API_BASE).rstrip("/"),
        default_repository_url=str(raw.get("default_repository_url") or "").strip(),
        default_ref=str(raw.get("default_ref") or "main").strip() or "main",
        default_model=str(raw.get("default_model") or "").strip(),
        auto_create_pr=bool(raw.get("auto_create_pr", False)),
        chain_depth=max(1, _as_int(raw.get("chain_depth"), 20)),
        max_images=max(1, min(5, _as_int(raw.get("max_images"), 5))),
        max_image_bytes=_as_int(raw.get("max_image_bytes"), 15 * 1024 * 1024),
        status_edit_interval_ms=max(
            250, _as_int(raw.get("status_edit_interval_ms"), 1200)
        ),
        connect_timeout_seconds=_as_float(raw.get("connect_timeout_seconds"), 10.0),
        read_timeout_seconds=_as_float(raw.get("read_timeout_seconds"), 60.0),
        stream_timeout_seconds=_as_float(raw.get("stream_timeout_seconds"), 900.0),
        max_recent_sessions=max(1, _as_int(raw.get("max_recent_sessions"), 20)),
        session_idle_prompt_minutes=idle_minutes,
        max_retained_image_bytes=_as_int(
            raw.get("max_retained_image_bytes"), 40 * 1024 * 1024
        ),
        god_user_id=god_user_id,
        access=access,
    )
