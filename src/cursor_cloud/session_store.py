"""Owned session persistence protocols and in-memory implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from .errors import OwnershipError, ValidationError
from .models import (
    AgentSession,
    IdleDecision,
    ModelDecision,
    RunStatus,
    ScopeKey,
    utcnow,
)


class SessionStore(Protocol):
    async def get_active(self, scope: ScopeKey) -> AgentSession | None: ...

    async def list_sessions(self, scope: ScopeKey) -> list[AgentSession]: ...

    async def get_session(self, scope: ScopeKey, agent_id: str) -> AgentSession | None: ...

    async def upsert(self, session: AgentSession) -> AgentSession: ...

    async def set_active(self, scope: ScopeKey, agent_id: str) -> AgentSession: ...

    async def touch_activity(self, scope: ScopeKey, agent_id: str | None = None) -> None: ...

    async def save_idle_decision(self, decision: IdleDecision) -> IdleDecision: ...

    async def get_idle_decision(self, decision_id: str) -> IdleDecision | None: ...

    async def save_model_decision(self, decision: ModelDecision) -> ModelDecision: ...

    async def get_model_decision(self, decision_id: str) -> ModelDecision | None: ...

    async def all_sessions(self) -> list[AgentSession]: ...

    def lock_for(self, scope: ScopeKey) -> asyncio.Lock: ...


class MemorySessionStore:
    """In-memory store used by tests and as a base for Beacon adapters."""

    def __init__(self, *, max_recent: int = 20):
        self.max_recent = max_recent
        self._sessions: dict[str, dict[str, AgentSession]] = {}
        self._active: dict[str, str] = {}
        self._idle: dict[str, IdleDecision] = {}
        self._model: dict[str, ModelDecision] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def lock_for(self, scope: ScopeKey) -> asyncio.Lock:
        key = scope.as_str()
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _bucket(self, scope: ScopeKey) -> dict[str, AgentSession]:
        return self._sessions.setdefault(scope.as_str(), {})

    async def get_active(self, scope: ScopeKey) -> AgentSession | None:
        agent_id = self._active.get(scope.as_str())
        if not agent_id:
            return None
        session = self._bucket(scope).get(agent_id)
        if session is None:
            return None
        if session.owner_id != scope.user_id:
            return None
        return session

    async def list_sessions(self, scope: ScopeKey) -> list[AgentSession]:
        items = [
            s
            for s in self._bucket(scope).values()
            if s.owner_id == scope.user_id and s.scope.as_str() == scope.as_str()
        ]
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items[: self.max_recent]

    async def get_session(self, scope: ScopeKey, agent_id: str) -> AgentSession | None:
        session = self._bucket(scope).get(agent_id)
        if session is None:
            return None
        if session.owner_id != scope.user_id or session.scope.as_str() != scope.as_str():
            raise OwnershipError()
        return session

    async def upsert(self, session: AgentSession) -> AgentSession:
        session.updated_at = utcnow()
        bucket = self._bucket(session.scope)
        bucket[session.agent_id] = session
        # Bound history per scope.
        if len(bucket) > self.max_recent:
            ordered = sorted(bucket.values(), key=lambda s: s.updated_at, reverse=True)
            keep = {s.agent_id for s in ordered[: self.max_recent]}
            for agent_id in list(bucket):
                if agent_id not in keep:
                    del bucket[agent_id]
        if session.active:
            self._active[session.scope.as_str()] = session.agent_id
            for other in bucket.values():
                other.active = other.agent_id == session.agent_id
        return session

    async def set_active(self, scope: ScopeKey, agent_id: str) -> AgentSession:
        session = await self.get_session(scope, agent_id)
        if session is None:
            raise OwnershipError()
        for other in self._bucket(scope).values():
            other.active = other.agent_id == agent_id
        session.active = True
        session.updated_at = utcnow()
        self._active[scope.as_str()] = agent_id
        return session

    async def touch_activity(self, scope: ScopeKey, agent_id: str | None = None) -> None:
        target_id = agent_id or self._active.get(scope.as_str())
        if not target_id:
            return
        session = self._bucket(scope).get(target_id)
        if session is None:
            return
        session.last_meaningful_activity_at = utcnow()
        session.updated_at = utcnow()

    async def save_idle_decision(self, decision: IdleDecision) -> IdleDecision:
        self._idle[decision.decision_id] = decision
        return decision

    async def get_idle_decision(self, decision_id: str) -> IdleDecision | None:
        return self._idle.get(decision_id)

    async def save_model_decision(self, decision: ModelDecision) -> ModelDecision:
        self._model[decision.decision_id] = decision
        return decision

    async def get_model_decision(self, decision_id: str) -> ModelDecision | None:
        return self._model.get(decision_id)

    async def all_sessions(self) -> list[AgentSession]:
        out: list[AgentSession] = []
        for bucket in self._sessions.values():
            out.extend(bucket.values())
        return out

    def export_state(self) -> dict[str, Any]:
        return {
            "sessions": {
                scope: {aid: s.to_dict() for aid, s in bucket.items()}
                for scope, bucket in self._sessions.items()
            },
            "active": dict(self._active),
            "idle": {k: v.to_dict() for k, v in self._idle.items()},
            "model": {k: v.to_dict() for k, v in self._model.items()},
        }

    def import_state(self, data: dict[str, Any]) -> None:
        self._sessions.clear()
        self._active = {
            str(k): str(v) for k, v in (data.get("active") or {}).items()
        }
        for scope_key, bucket in (data.get("sessions") or {}).items():
            parsed: dict[str, AgentSession] = {}
            for agent_id, raw in (bucket or {}).items():
                session = AgentSession.from_dict(raw)
                parsed[str(agent_id)] = session
            self._sessions[str(scope_key)] = parsed
        self._idle = {
            k: IdleDecision.from_dict(v) for k, v in (data.get("idle") or {}).items()
        }
        self._model = {
            k: ModelDecision.from_dict(v) for k, v in (data.get("model") or {}).items()
        }


def session_is_idle(
    session: AgentSession,
    *,
    idle_minutes: int,
    now=None,
) -> bool:
    now = now or utcnow()
    last = session.last_meaningful_activity_at
    delta = (now - last).total_seconds()
    return delta >= idle_minutes * 60


def ensure_owned(session: AgentSession | None, scope: ScopeKey) -> AgentSession:
    if session is None:
        raise OwnershipError()
    if session.owner_id != scope.user_id or session.scope.as_str() != scope.as_str():
        raise OwnershipError()
    return session


def validate_agent_id(agent_id: str) -> str:
    text = str(agent_id or "").strip()
    if not text or len(text) > 128:
        raise ValidationError(
            "Invalid agent id",
            user_message="Provide a valid owned agent id.",
        )
    return text


MEANINGFUL_STREAM_EVENTS = frozenset(
    {"status", "assistant", "thinking", "tool_call", "result"}
)


def is_meaningful_stream_event(event_name: str) -> bool:
    return event_name in MEANINGFUL_STREAM_EVENTS


ACTIVE_RUN_STATUSES = frozenset(
    {RunStatus.QUEUED, RunStatus.CREATING, RunStatus.RUNNING}
)


def run_is_busy(status: RunStatus | str | None) -> bool:
    if status is None:
        return False
    if not isinstance(status, RunStatus):
        status = RunStatus.from_api(str(status))
    return bool(status.is_active)
