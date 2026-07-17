"""Typed models for Cursor Cloud Agents, sessions, access, and stream events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def dt_from_iso(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    CREATING = "CREATING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

    @classmethod
    def from_api(cls, value: str | None) -> "RunStatus":
        if not value:
            return cls.QUEUED
        normalized = str(value).upper()
        try:
            return cls(normalized)
        except ValueError:
            return cls.RUNNING if normalized not in {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"} else cls.ERROR

    @property
    def is_active(self) -> bool:
        return self in {RunStatus.QUEUED, RunStatus.CREATING, RunStatus.RUNNING}

    @property
    def is_terminal(self) -> bool:
        return self in {
            RunStatus.FINISHED,
            RunStatus.ERROR,
            RunStatus.CANCELLED,
            RunStatus.EXPIRED,
        }


class AccessTier(int, Enum):
    GOD = 0
    ADMIN = 1
    APPROVAL = 2
    DENIED = 3


class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED_ONCE = "approved_once"
    APPROVED_TIMED = "approved_timed"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    REVOKED = "revoked"


class IdleChoice(str, Enum):
    PENDING = "pending"
    CONTINUE = "continue"
    NEW = "new"
    CANCEL = "cancel"


class ModelChoice(str, Enum):
    PENDING = "pending"
    NEW_SESSION = "new_session"
    CONTINUE_ORIGINAL = "continue_original"
    CANCEL = "cancel"


SUPPORTED_IMAGE_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 15 * 1024 * 1024
DISCORD_MESSAGE_LIMIT = 2000


@dataclass
class ImageInput:
    """Image payload for Cursor API prompts."""

    mime_type: str
    url: str | None = None
    data_b64: str | None = None
    size_bytes: int | None = None
    source_message_id: str | None = None
    skipped_reason: str | None = None

    def to_api(self) -> dict[str, Any]:
        if self.data_b64:
            return {"data": self.data_b64, "mimeType": self.mime_type}
        if self.url:
            return {"url": self.url}
        raise ValueError("ImageInput requires url or data_b64")

    def metadata(self) -> dict[str, Any]:
        return {
            "mime_type": self.mime_type,
            "url": self.url,
            "size_bytes": self.size_bytes,
            "source_message_id": self.source_message_id,
            "has_data": bool(self.data_b64),
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class ImageRetention:
    """Process-local retained image bytes for pending approvals (not Beacon)."""

    request_id: str
    images: list[ImageInput]
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    total_bytes: int = 0


@dataclass
class PromptImageMeta:
    mime_type: str
    size_bytes: int | None = None
    source_message_id: str | None = None
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptImageMeta":
        return cls(
            mime_type=str(data.get("mime_type") or ""),
            size_bytes=data.get("size_bytes"),
            source_message_id=(
                str(data["source_message_id"])
                if data.get("source_message_id") is not None
                else None
            ),
            fingerprint=str(data.get("fingerprint") or ""),
        )


@dataclass
class ScopeKey:
    guild_id: str
    channel_id: str
    user_id: str

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.guild_id, self.channel_id, self.user_id)

    def as_str(self) -> str:
        return f"{self.guild_id}:{self.channel_id}:{self.user_id}"

    @classmethod
    def from_str(cls, value: str) -> "ScopeKey":
        parts = str(value).split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"Invalid scope key: {value}")
        return cls(guild_id=parts[0], channel_id=parts[1], user_id=parts[2])

    def to_dict(self) -> dict[str, str]:
        return {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScopeKey":
        return cls(
            guild_id=str(data["guild_id"]),
            channel_id=str(data["channel_id"]),
            user_id=str(data["user_id"]),
        )


@dataclass
class ToolActivity:
    call_id: str
    name: str
    status: str
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolActivity":
        return cls(
            call_id=str(data.get("call_id") or ""),
            name=str(data.get("name") or "tool"),
            status=str(data.get("status") or ""),
            summary=str(data.get("summary") or ""),
        )


@dataclass
class GitBranchInfo:
    repo_url: str = ""
    branch: str | None = None
    pr_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GitBranchInfo":
        return cls(
            repo_url=str(data.get("repo_url") or data.get("repoUrl") or ""),
            branch=data.get("branch"),
            pr_url=data.get("pr_url") or data.get("prUrl"),
        )


@dataclass
class StreamEvent:
    event: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass
class RunSnapshot:
    run_id: str
    agent_id: str
    status: RunStatus = RunStatus.QUEUED
    result_text: str = ""
    assistant_text: str = ""
    thinking_text: str = ""
    error_message: str = ""
    duration_ms: int | None = None
    tools: list[ToolActivity] = field(default_factory=list)
    git_branches: list[GitBranchInfo] = field(default_factory=list)
    truncated: bool = False
    degraded: bool = False
    last_event_id: str | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "result_text": self.result_text,
            "assistant_text": self.assistant_text,
            "thinking_text": self.thinking_text,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "tools": [t.to_dict() for t in self.tools],
            "git_branches": [g.to_dict() for g in self.git_branches],
            "truncated": self.truncated,
            "degraded": self.degraded,
            "last_event_id": self.last_event_id,
            "updated_at": dt_to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunSnapshot":
        return cls(
            run_id=str(data.get("run_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            status=RunStatus.from_api(data.get("status")),
            result_text=str(data.get("result_text") or ""),
            assistant_text=str(data.get("assistant_text") or ""),
            thinking_text=str(data.get("thinking_text") or ""),
            error_message=str(data.get("error_message") or ""),
            duration_ms=data.get("duration_ms"),
            tools=[ToolActivity.from_dict(t) for t in data.get("tools") or []],
            git_branches=[
                GitBranchInfo.from_dict(g) for g in data.get("git_branches") or []
            ],
            truncated=bool(data.get("truncated")),
            degraded=bool(data.get("degraded")),
            last_event_id=data.get("last_event_id"),
            updated_at=dt_from_iso(data.get("updated_at")) or utcnow(),
        )


@dataclass
class AgentSession:
    """Owned durable agent metadata persisted locally (no secrets / raw images)."""

    scope: ScopeKey
    agent_id: str
    owner_id: str
    name: str = ""
    model: str | None = None
    preferred_model: str | None = None
    repository_url: str | None = None
    starting_ref: str | None = None
    latest_run_id: str | None = None
    latest_run_status: RunStatus = RunStatus.QUEUED
    status_channel_id: str | None = None
    status_message_id: str | None = None
    summary: str = ""
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    last_meaningful_activity_at: datetime = field(default_factory=utcnow)
    active: bool = False
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.to_dict(),
            "agent_id": self.agent_id,
            "owner_id": self.owner_id,
            "name": self.name,
            "model": self.model,
            "preferred_model": self.preferred_model,
            "repository_url": self.repository_url,
            "starting_ref": self.starting_ref,
            "latest_run_id": self.latest_run_id,
            "latest_run_status": self.latest_run_status.value,
            "status_channel_id": self.status_channel_id,
            "status_message_id": self.status_message_id,
            "summary": self.summary,
            "created_at": dt_to_iso(self.created_at),
            "updated_at": dt_to_iso(self.updated_at),
            "last_meaningful_activity_at": dt_to_iso(self.last_meaningful_activity_at),
            "active": self.active,
            "degraded": self.degraded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSession":
        scope_data = data.get("scope") or {}
        return cls(
            scope=ScopeKey.from_dict(scope_data),
            agent_id=str(data.get("agent_id") or ""),
            owner_id=str(data.get("owner_id") or ""),
            name=str(data.get("name") or ""),
            model=data.get("model"),
            preferred_model=data.get("preferred_model"),
            repository_url=data.get("repository_url"),
            starting_ref=data.get("starting_ref"),
            latest_run_id=data.get("latest_run_id"),
            latest_run_status=RunStatus.from_api(data.get("latest_run_status")),
            status_channel_id=(
                str(data["status_channel_id"])
                if data.get("status_channel_id") is not None
                else None
            ),
            status_message_id=(
                str(data["status_message_id"])
                if data.get("status_message_id") is not None
                else None
            ),
            summary=str(data.get("summary") or "")[:500],
            created_at=dt_from_iso(data.get("created_at")) or utcnow(),
            updated_at=dt_from_iso(data.get("updated_at")) or utcnow(),
            last_meaningful_activity_at=dt_from_iso(
                data.get("last_meaningful_activity_at")
            )
            or utcnow(),
            active=bool(data.get("active")),
            degraded=bool(data.get("degraded")),
        )


@dataclass
class RunRequestEnvelope:
    """Exact request shape hashed for one-run approvals."""

    requester_id: str
    scope: ScopeKey
    prompt_text: str
    model: str | None
    repository_url: str | None
    starting_ref: str | None
    agent_id: str | None
    is_follow_up: bool
    image_metas: list[PromptImageMeta] = field(default_factory=list)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "requester_id": self.requester_id,
            "scope": self.scope.to_dict(),
            "prompt_text": self.prompt_text,
            "model": self.model,
            "repository_url": self.repository_url,
            "starting_ref": self.starting_ref,
            "agent_id": self.agent_id,
            "is_follow_up": self.is_follow_up,
            "image_metas": [m.to_dict() for m in self.image_metas],
        }


@dataclass
class ApprovalRequest:
    request_id: str
    envelope_hash: str
    envelope: RunRequestEnvelope
    decision: ApprovalDecision = ApprovalDecision.PENDING
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    approval_channel_id: str | None = None
    approval_message_id: str | None = None
    grant_id: str | None = None
    prompt_preview: str = ""
    grant_minutes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "envelope_hash": self.envelope_hash,
            "envelope": self.envelope.canonical_dict(),
            "decision": self.decision.value,
            "created_at": dt_to_iso(self.created_at),
            "expires_at": dt_to_iso(self.expires_at),
            "decided_at": dt_to_iso(self.decided_at),
            "decided_by": self.decided_by,
            "approval_channel_id": self.approval_channel_id,
            "approval_message_id": self.approval_message_id,
            "grant_id": self.grant_id,
            "prompt_preview": self.prompt_preview,
            "grant_minutes": self.grant_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        env = data.get("envelope") or {}
        return cls(
            request_id=str(data.get("request_id") or ""),
            envelope_hash=str(data.get("envelope_hash") or ""),
            envelope=RunRequestEnvelope(
                requester_id=str(env.get("requester_id") or ""),
                scope=ScopeKey.from_dict(env.get("scope") or {}),
                prompt_text=str(env.get("prompt_text") or ""),
                model=env.get("model"),
                repository_url=env.get("repository_url"),
                starting_ref=env.get("starting_ref"),
                agent_id=env.get("agent_id"),
                is_follow_up=bool(env.get("is_follow_up")),
                image_metas=[
                    PromptImageMeta.from_dict(m) for m in env.get("image_metas") or []
                ],
            ),
            decision=ApprovalDecision(str(data.get("decision") or "pending")),
            created_at=dt_from_iso(data.get("created_at")) or utcnow(),
            expires_at=dt_from_iso(data.get("expires_at")),
            decided_at=dt_from_iso(data.get("decided_at")),
            decided_by=data.get("decided_by"),
            approval_channel_id=(
                str(data["approval_channel_id"])
                if data.get("approval_channel_id") is not None
                else None
            ),
            approval_message_id=(
                str(data["approval_message_id"])
                if data.get("approval_message_id") is not None
                else None
            ),
            grant_id=data.get("grant_id"),
            prompt_preview=str(data.get("prompt_preview") or ""),
            grant_minutes=data.get("grant_minutes"),
        )


@dataclass
class RunGrant:
    grant_id: str
    scope: ScopeKey
    user_id: str
    kind: str  # once | timed
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    envelope_hash: str | None = None
    request_id: str | None = None
    consumed: bool = False
    revoked: bool = False
    created_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "scope": self.scope.to_dict(),
            "user_id": self.user_id,
            "kind": self.kind,
            "created_at": dt_to_iso(self.created_at),
            "expires_at": dt_to_iso(self.expires_at),
            "envelope_hash": self.envelope_hash,
            "request_id": self.request_id,
            "consumed": self.consumed,
            "revoked": self.revoked,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunGrant":
        return cls(
            grant_id=str(data.get("grant_id") or ""),
            scope=ScopeKey.from_dict(data.get("scope") or {}),
            user_id=str(data.get("user_id") or ""),
            kind=str(data.get("kind") or "once"),
            created_at=dt_from_iso(data.get("created_at")) or utcnow(),
            expires_at=dt_from_iso(data.get("expires_at")),
            envelope_hash=data.get("envelope_hash"),
            request_id=data.get("request_id"),
            consumed=bool(data.get("consumed")),
            revoked=bool(data.get("revoked")),
            created_by=data.get("created_by"),
        )


@dataclass
class AccessAuditEvent:
    event_id: str
    actor_id: str
    action: str
    timestamp: datetime = field(default_factory=utcnow)
    target_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "timestamp": dt_to_iso(self.timestamp),
            "target_id": self.target_id,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccessAuditEvent":
        return cls(
            event_id=str(data.get("event_id") or ""),
            actor_id=str(data.get("actor_id") or ""),
            action=str(data.get("action") or ""),
            timestamp=dt_from_iso(data.get("timestamp")) or utcnow(),
            target_id=data.get("target_id"),
            detail=dict(data.get("detail") or {}),
        )


@dataclass
class IdleDecision:
    decision_id: str
    scope: ScopeKey
    agent_id: str
    choice: IdleChoice = IdleChoice.PENDING
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    consumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "scope": self.scope.to_dict(),
            "agent_id": self.agent_id,
            "choice": self.choice.value,
            "created_at": dt_to_iso(self.created_at),
            "expires_at": dt_to_iso(self.expires_at),
            "consumed": self.consumed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdleDecision":
        return cls(
            decision_id=str(data.get("decision_id") or ""),
            scope=ScopeKey.from_dict(data.get("scope") or {}),
            agent_id=str(data.get("agent_id") or ""),
            choice=IdleChoice(str(data.get("choice") or "pending")),
            created_at=dt_from_iso(data.get("created_at")) or utcnow(),
            expires_at=dt_from_iso(data.get("expires_at")),
            consumed=bool(data.get("consumed")),
        )


@dataclass
class ModelDecision:
    decision_id: str
    scope: ScopeKey
    agent_id: str
    preferred_model: str
    agent_model: str | None
    choice: ModelChoice = ModelChoice.PENDING
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime | None = None
    consumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "scope": self.scope.to_dict(),
            "agent_id": self.agent_id,
            "preferred_model": self.preferred_model,
            "agent_model": self.agent_model,
            "choice": self.choice.value,
            "created_at": dt_to_iso(self.created_at),
            "expires_at": dt_to_iso(self.expires_at),
            "consumed": self.consumed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelDecision":
        return cls(
            decision_id=str(data.get("decision_id") or ""),
            scope=ScopeKey.from_dict(data.get("scope") or {}),
            agent_id=str(data.get("agent_id") or ""),
            preferred_model=str(data.get("preferred_model") or ""),
            agent_model=data.get("agent_model"),
            choice=ModelChoice(str(data.get("choice") or "pending")),
            created_at=dt_from_iso(data.get("created_at")) or utcnow(),
            expires_at=dt_from_iso(data.get("expires_at")),
            consumed=bool(data.get("consumed")),
        )


@dataclass
class AgentRecord:
    id: str
    name: str = ""
    status: str = ""
    url: str | None = None
    latest_run_id: str | None = None
    model: str | None = None
    repos: list[dict[str, Any]] = field(default_factory=list)
    auto_create_pr: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "AgentRecord":
        repos = list(data.get("repos") or [])
        model = None
        model_obj = data.get("model")
        if isinstance(model_obj, dict):
            model = model_obj.get("id")
        elif isinstance(model_obj, str):
            model = model_obj
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            status=str(data.get("status") or ""),
            url=data.get("url"),
            latest_run_id=data.get("latestRunId") or data.get("latest_run_id"),
            model=model,
            repos=repos,
            auto_create_pr=data.get("autoCreatePR"),
            raw=data,
        )


@dataclass
class RunRecord:
    id: str
    agent_id: str
    status: RunStatus = RunStatus.QUEUED
    result: str | None = None
    duration_ms: int | None = None
    git: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RunRecord":
        return cls(
            id=str(data.get("id") or ""),
            agent_id=str(data.get("agentId") or data.get("agent_id") or ""),
            status=RunStatus.from_api(data.get("status")),
            result=data.get("result"),
            duration_ms=data.get("durationMs") or data.get("duration_ms"),
            git=data.get("git"),
            created_at=data.get("createdAt") or data.get("created_at"),
            updated_at=data.get("updatedAt") or data.get("updated_at"),
            raw=data,
        )


@dataclass
class ModelInfo:
    id: str
    display_name: str = ""
    aliases: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ModelInfo":
        return cls(
            id=str(data.get("id") or ""),
            display_name=str(data.get("displayName") or data.get("display_name") or ""),
            aliases=[str(a) for a in data.get("aliases") or []],
            raw=data,
        )
