"""Bounded Beacon/memory run activity log (local; Cursor v1 has no conversation API)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import ScopeKey, dt_from_iso, dt_to_iso, utcnow
from .status_renderer import redact_untrusted


LOG_KINDS = frozenset(
    {
        "prompt",
        "status",
        "assistant",
        "thinking",
        "tool_call",
        "result",
        "error",
        "done",
        "system",
    }
)

# Default /cursor history view: skip status/system/done noise.
HISTORY_FOCUS_KINDS = frozenset(
    {
        "prompt",
        "thinking",
        "tool_call",
        "assistant",
        "result",
        "error",
    }
)

DEFAULT_MAX_RUNS_PER_SCOPE = 10
DEFAULT_MAX_ENTRIES_PER_RUN = 200
SUMMARY_LIMIT = 240


@dataclass
class RunLogEntry:
    kind: str
    summary: str
    at: str = field(default_factory=lambda: dt_to_iso(utcnow()) or "")
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "at": self.at,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunLogEntry":
        return cls(
            kind=str(data.get("kind") or "system"),
            summary=str(data.get("summary") or ""),
            at=str(data.get("at") or dt_to_iso(utcnow()) or ""),
            detail=dict(data.get("detail") or {}),
        )


def sanitize_log_summary(text: str, *, limit: int = SUMMARY_LIMIT) -> str:
    return redact_untrusted(text or "")[:limit]


class RunLogStore(Protocol):
    async def append(
        self,
        scope: ScopeKey,
        *,
        agent_id: str,
        run_id: str,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None: ...

    async def get_entries(
        self,
        scope: ScopeKey,
        run_id: str,
        *,
        offset: int = 0,
        limit: int = 40,
        kinds: frozenset[str] | set[str] | None = None,
    ) -> list[RunLogEntry]: ...

    async def list_run_ids(self, scope: ScopeKey) -> list[str]: ...

    async def entry_count(
        self,
        scope: ScopeKey,
        run_id: str,
        *,
        kinds: frozenset[str] | set[str] | None = None,
    ) -> int: ...


class MemoryRunLogStore:
    """In-memory run log used by tests and as Beacon adapter base."""

    def __init__(
        self,
        *,
        max_runs_per_scope: int = DEFAULT_MAX_RUNS_PER_SCOPE,
        max_entries_per_run: int = DEFAULT_MAX_ENTRIES_PER_RUN,
    ):
        self.max_runs_per_scope = max_runs_per_scope
        self.max_entries_per_run = max_entries_per_run
        # scope_str -> ordered run ids (oldest first)
        self._order: dict[str, list[str]] = {}
        # scope_str -> run_id -> {agent_id, entries}
        self._runs: dict[str, dict[str, dict[str, Any]]] = {}

    def export_state(self) -> dict[str, Any]:
        return {
            "order": {k: list(v) for k, v in self._order.items()},
            "runs": {
                sk: {
                    rid: {
                        "agent_id": meta.get("agent_id"),
                        "entries": [e.to_dict() for e in meta.get("entries") or []],
                        "updated_at": meta.get("updated_at"),
                    }
                    for rid, meta in runs.items()
                }
                for sk, runs in self._runs.items()
            },
        }

    def import_state(self, data: dict[str, Any]) -> None:
        self._order = {
            str(k): [str(r) for r in (v or [])]
            for k, v in (data.get("order") or {}).items()
        }
        self._runs = {}
        for sk, runs in (data.get("runs") or {}).items():
            bucket: dict[str, dict[str, Any]] = {}
            for rid, meta in (runs or {}).items():
                entries = [
                    RunLogEntry.from_dict(e) for e in (meta or {}).get("entries") or []
                ]
                bucket[str(rid)] = {
                    "agent_id": str((meta or {}).get("agent_id") or ""),
                    "entries": entries,
                    "updated_at": (meta or {}).get("updated_at"),
                }
            self._runs[str(sk)] = bucket

    def _ensure_run(self, scope: ScopeKey, *, agent_id: str, run_id: str) -> dict[str, Any]:
        sk = scope.as_str()
        order = self._order.setdefault(sk, [])
        runs = self._runs.setdefault(sk, {})
        if run_id not in runs:
            runs[run_id] = {
                "agent_id": agent_id,
                "entries": [],
                "updated_at": dt_to_iso(utcnow()),
            }
            order.append(run_id)
        else:
            runs[run_id]["agent_id"] = agent_id or runs[run_id].get("agent_id") or ""
            if run_id in order:
                order.remove(run_id)
            order.append(run_id)
        while len(order) > self.max_runs_per_scope:
            old = order.pop(0)
            runs.pop(old, None)
        return runs[run_id]

    async def append(
        self,
        scope: ScopeKey,
        *,
        agent_id: str,
        run_id: str,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not run_id:
            return
        kind_norm = str(kind or "system")
        if kind_norm not in LOG_KINDS:
            kind_norm = "system"
        meta = self._ensure_run(scope, agent_id=agent_id, run_id=run_id)
        entries: list[RunLogEntry] = meta["entries"]
        entries.append(
            RunLogEntry(
                kind=kind_norm,
                summary=sanitize_log_summary(summary),
                detail=dict(detail or {}),
            )
        )
        if len(entries) > self.max_entries_per_run:
            del entries[: len(entries) - self.max_entries_per_run]
        meta["updated_at"] = dt_to_iso(utcnow())

    async def get_entries(
        self,
        scope: ScopeKey,
        run_id: str,
        *,
        offset: int = 0,
        limit: int = 40,
        kinds: frozenset[str] | set[str] | None = None,
    ) -> list[RunLogEntry]:
        meta = (self._runs.get(scope.as_str()) or {}).get(run_id)
        if not meta:
            return []
        entries: list[RunLogEntry] = list(meta.get("entries") or [])
        if kinds is not None:
            entries = [e for e in entries if e.kind in kinds]
        start = max(0, int(offset))
        end = start + max(1, min(int(limit), 80))
        return list(entries[start:end])

    async def list_run_ids(self, scope: ScopeKey) -> list[str]:
        # Newest first for UX.
        order = list(self._order.get(scope.as_str()) or [])
        return list(reversed(order))

    async def entry_count(
        self,
        scope: ScopeKey,
        run_id: str,
        *,
        kinds: frozenset[str] | set[str] | None = None,
    ) -> int:
        meta = (self._runs.get(scope.as_str()) or {}).get(run_id)
        if not meta:
            return 0
        entries: list[RunLogEntry] = meta.get("entries") or []
        if kinds is not None:
            return sum(1 for e in entries if e.kind in kinds)
        return len(entries)


def format_history_message(
    entries: list[RunLogEntry],
    *,
    run_id: str,
    page: int,
    total_entries: int,
    page_size: int,
    agent_id: str | None = None,
    limit: int = 2000,
) -> str:
    """Discord H3 history page (<= limit)."""
    total_pages = max(1, (total_entries + page_size - 1) // page_size) if total_entries else 1
    page = max(1, min(page, total_pages))
    lines = [
        "### History",
        f"Run: `{run_id}`",
        f"Page: {page}/{total_pages} ({total_entries} entries)",
    ]
    if agent_id:
        lines.append(f"Agent: `{redact_untrusted(agent_id)[:80]}`")
    lines.append("")
    if not entries:
        lines.append("_No log entries for this run._")
    else:
        for entry in entries:
            stamp = ""
            parsed = dt_from_iso(entry.at)
            if parsed is not None:
                stamp = parsed.strftime("%H:%M:%S")
            prefix = f"`{stamp}` " if stamp else ""
            summary = redact_untrusted(entry.summary)[:180]
            lines.append(f"- {prefix}**{entry.kind}** {summary}".rstrip())

    text = "\n".join(lines).strip()
    if len(text) > limit:
        marker = "\n…(truncated)"
        text = text[: max(0, limit - len(marker))] + marker
    return text[:limit]
