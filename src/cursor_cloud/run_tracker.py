"""Consume Cursor SSE events into a coalesced status sink."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .client import CursorCloudClient
from .errors import CursorCloudError, StreamExpiredError
from .models import (
    GitBranchInfo,
    RunRecord,
    RunSnapshot,
    RunStatus,
    ScopeKey,
    StreamEvent,
    ToolActivity,
    utcnow,
)
from .run_log import RunLogStore, sanitize_log_summary
from .session_store import is_meaningful_stream_event
from .status_renderer import render_status, safe_tool_summary


class StatusSink(Protocol):
    async def update(self, content: str, *, terminal: bool = False) -> None: ...


OnActivity = Callable[[str], Awaitable[None] | None]


def is_stream_unavailable_error(data: dict[str, Any] | None) -> bool:
    """True when an SSE error means the stream ended, not that the agent failed."""
    payload = data or {}
    code = str(payload.get("code") or "").lower()
    message = str(
        payload.get("message") or payload.get("error") or payload.get("text") or ""
    ).lower()
    if code in {"stream_expired", "stream_unavailable", "gone"}:
        return True
    needles = (
        "no longer available",
        "stream expired",
        "stream is no longer",
        "stream unavailable",
        "run stream is no longer",
    )
    return any(n in message for n in needles)


class RunTracker:
    def __init__(
        self,
        client: CursorCloudClient,
        sink: StatusSink,
        *,
        edit_interval_ms: int = 1200,
        agent_name: str | None = None,
        skipped_images: list[str] | None = None,
        on_meaningful_activity: OnActivity | None = None,
        run_log: RunLogStore | None = None,
        scope: ScopeKey | None = None,
    ):
        self.client = client
        self.sink = sink
        self.edit_interval_ms = edit_interval_ms
        self.agent_name = agent_name
        self.skipped_images = skipped_images or []
        self.on_meaningful_activity = on_meaningful_activity
        self.run_log = run_log
        self.scope = scope
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._pending_render = False
        self._last_edit = 0.0
        self.snapshot: RunSnapshot | None = None
        self._pending_log_kinds: set[str] = set()

    def apply_event(self, snapshot: RunSnapshot, event: StreamEvent) -> RunSnapshot:
        if event.id:
            snapshot.last_event_id = event.id
        name = event.event
        data = event.data or {}

        if name == "status":
            snapshot.status = RunStatus.from_api(data.get("status"))
            if data.get("runId"):
                snapshot.run_id = str(data["runId"])
        elif name == "assistant":
            snapshot.assistant_text += str(data.get("text") or "")
            if snapshot.status.is_active:
                snapshot.status = RunStatus.RUNNING
        elif name == "thinking":
            snapshot.thinking_text += str(data.get("text") or "")
        elif name == "tool_call":
            call_id = str(data.get("callId") or data.get("call_id") or "")
            tool_name = str(data.get("name") or "tool")
            status = str(data.get("status") or "")
            summary = safe_tool_summary(
                tool_name,
                data.get("args"),
                data.get("result"),
                truncated=data.get("truncated") if isinstance(data.get("truncated"), dict) else None,
            )
            existing = next((t for t in snapshot.tools if t.call_id == call_id), None)
            if existing:
                existing.status = status
                existing.summary = summary
                existing.name = tool_name
            else:
                snapshot.tools.append(
                    ToolActivity(
                        call_id=call_id or f"anon-{len(snapshot.tools)}",
                        name=tool_name,
                        status=status,
                        summary=summary,
                    )
                )
            # Bound tool history
            if len(snapshot.tools) > 12:
                snapshot.tools = snapshot.tools[-12:]
        elif name == "interaction_update":
            # Prefer simplified events; ignore rich duplicates.
            pass
        elif name == "heartbeat":
            pass
        elif name == "result":
            snapshot.status = RunStatus.from_api(data.get("status") or "FINISHED")
            if data.get("text"):
                snapshot.result_text = str(data.get("text") or "")
            if data.get("durationMs") is not None:
                snapshot.duration_ms = int(data["durationMs"])
            git = data.get("git") or {}
            branches = []
            for item in git.get("branches") or []:
                branches.append(
                    GitBranchInfo(
                        repo_url=str(item.get("repoUrl") or ""),
                        branch=item.get("branch"),
                        pr_url=item.get("prUrl"),
                    )
                )
            if branches:
                snapshot.git_branches = branches
            # Successful result clears a prior non-fatal stream glitch message.
            if snapshot.status == RunStatus.FINISHED:
                snapshot.error_message = ""
        elif name == "error":
            if is_stream_unavailable_error(data):
                # Stream ended; caller reconciles via GET run — do not mark ERROR.
                pass
            else:
                snapshot.status = RunStatus.ERROR
                snapshot.error_message = str(
                    data.get("message") or data.get("code") or "Agent error"
                )
        elif name == "done":
            if not snapshot.status.is_terminal:
                # done without result — leave status as-is but mark finished if running
                if snapshot.status.is_active and not snapshot.error_message:
                    snapshot.status = RunStatus.FINISHED
        snapshot.updated_at = utcnow()
        return snapshot

    def apply_run_record(self, snapshot: RunSnapshot, run: RunRecord) -> RunSnapshot:
        """Reconcile snapshot fields from a GET /runs response."""
        snapshot.status = run.status
        if run.result:
            snapshot.result_text = run.result
        if run.duration_ms is not None:
            snapshot.duration_ms = run.duration_ms
        if run.id:
            snapshot.run_id = run.id
        git = run.git or {}
        branches = []
        for item in git.get("branches") or []:
            if not isinstance(item, dict):
                continue
            branches.append(
                GitBranchInfo(
                    repo_url=str(item.get("repoUrl") or item.get("repo_url") or ""),
                    branch=item.get("branch"),
                    pr_url=item.get("prUrl") or item.get("pr_url"),
                )
            )
        if branches:
            snapshot.git_branches = branches
        if snapshot.status == RunStatus.FINISHED:
            snapshot.error_message = ""
        elif snapshot.status == RunStatus.ERROR and not snapshot.error_message:
            snapshot.error_message = "Agent error"
        elif snapshot.status in {RunStatus.CANCELLED, RunStatus.EXPIRED}:
            snapshot.error_message = ""
        snapshot.updated_at = utcnow()
        return snapshot

    async def _reconcile_from_api(self, agent_id: str, run_id: str) -> None:
        if self.snapshot is None:
            return
        run = await self.client.get_run(agent_id, run_id)
        self.apply_run_record(self.snapshot, run)
        await self._log(
            "system",
            f"Reconciled from API: {run.status.value}",
            detail={"status": run.status.value},
        )
        if run.result:
            await self._log("result", sanitize_log_summary(run.result))

    async def _log(
        self,
        kind: str,
        summary: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if self.run_log is None or self.scope is None or self.snapshot is None:
            return
        try:
            await self.run_log.append(
                self.scope,
                agent_id=self.snapshot.agent_id,
                run_id=self.snapshot.run_id,
                kind=kind,
                summary=summary,
                detail=detail,
            )
        except Exception:
            # Logging must never break tracking.
            pass

    async def _flush_pending_text_logs(self) -> None:
        if self.snapshot is None or not self._pending_log_kinds:
            return
        pending = set(self._pending_log_kinds)
        self._pending_log_kinds.clear()
        if "thinking" in pending and self.snapshot.thinking_text:
            await self._log(
                "thinking",
                sanitize_log_summary(self.snapshot.thinking_text[-220:]),
            )
        if "assistant" in pending and self.snapshot.assistant_text:
            await self._log(
                "assistant",
                sanitize_log_summary(self.snapshot.assistant_text[-220:]),
            )

    async def _log_event(self, event: StreamEvent) -> None:
        name = event.event
        data = event.data or {}
        if name in {"thinking", "assistant"}:
            self._pending_log_kinds.add(name)
            return
        await self._flush_pending_text_logs()
        if name == "status":
            status = str(data.get("status") or "")
            await self._log("status", status or "status update")
        elif name == "tool_call":
            tool_name = str(data.get("name") or "tool")
            status = str(data.get("status") or "")
            summary = safe_tool_summary(
                tool_name,
                data.get("args"),
                data.get("result"),
                truncated=data.get("truncated")
                if isinstance(data.get("truncated"), dict)
                else None,
            )
            await self._log("tool_call", f"{status} {summary}".strip())
        elif name == "result":
            text = str(data.get("text") or data.get("status") or "result")
            await self._log("result", sanitize_log_summary(text))
        elif name == "error":
            if is_stream_unavailable_error(data):
                await self._log(
                    "system",
                    "Stream unavailable; reconciling",
                    detail={"code": str(data.get("code") or "")},
                )
            else:
                await self._log(
                    "error",
                    sanitize_log_summary(
                        str(data.get("message") or data.get("code") or "error")
                    ),
                )
        elif name == "done":
            await self._log("done", "done")
        elif name == "heartbeat":
            pass
        else:
            await self._log("system", sanitize_log_summary(name))

    async def _emit(self, *, terminal: bool = False) -> None:
        if self.snapshot is None:
            return
        if terminal or self._pending_log_kinds:
            await self._flush_pending_text_logs()
        content = render_status(
            self.snapshot,
            agent_name=self.agent_name,
            skipped_images=self.skipped_images,
        )
        try:
            await self.sink.update(content, terminal=terminal)
        except Exception:
            self.snapshot.degraded = True

    async def _coalesce_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self.edit_interval_ms / 1000.0)
            if self._pending_render and self.snapshot and not self.snapshot.status.is_terminal:
                self._pending_render = False
                await self._emit(terminal=False)

    async def _notify_activity(self, event_name: str) -> None:
        if not self.on_meaningful_activity:
            return
        if not is_meaningful_stream_event(event_name):
            return
        result = self.on_meaningful_activity(event_name)
        if asyncio.iscoroutine(result):
            await result

    async def track(
        self,
        agent_id: str,
        run_id: str,
        *,
        last_event_id: str | None = None,
        initial_status: RunStatus = RunStatus.QUEUED,
    ) -> RunSnapshot:
        self.snapshot = RunSnapshot(
            run_id=run_id,
            agent_id=agent_id,
            status=initial_status,
            last_event_id=last_event_id,
        )
        await self._emit(terminal=False)
        coalesce_task = asyncio.create_task(self._coalesce_loop())
        try:
            async for event in self.client.stream_run_with_fallback(
                agent_id, run_id, last_event_id=last_event_id
            ):
                if self._stop.is_set():
                    break

                stream_gone = event.event == "error" and is_stream_unavailable_error(
                    event.data
                )
                self.apply_event(self.snapshot, event)
                await self._log_event(event)
                await self._notify_activity(event.event)

                if stream_gone:
                    try:
                        await self._reconcile_from_api(agent_id, run_id)
                    except CursorCloudError as exc:
                        self.snapshot.status = RunStatus.ERROR
                        self.snapshot.error_message = exc.user_message
                    self._pending_render = False
                    await self._emit(terminal=True)
                    break

                if self.snapshot.status.is_terminal or event.event in {
                    "result",
                    "error",
                    "done",
                }:
                    self._pending_render = False
                    await self._emit(terminal=True)
                    if event.event in {"result", "error", "done"} or self.snapshot.status.is_terminal:
                        if event.event == "done" or self.snapshot.status.is_terminal:
                            break
                else:
                    self._pending_render = True

            # Stream ended without a terminal snapshot — poll once.
            if (
                self.snapshot
                and not self.snapshot.status.is_terminal
                and not self._stop.is_set()
            ):
                try:
                    await self._reconcile_from_api(agent_id, run_id)
                except CursorCloudError as exc:
                    self.snapshot.status = RunStatus.ERROR
                    self.snapshot.error_message = exc.user_message
                await self._emit(terminal=True)
        except StreamExpiredError:
            # Fallback should have handled; if not, poll once.
            try:
                await self._reconcile_from_api(agent_id, run_id)
                await self._emit(terminal=True)
            except CursorCloudError as exc:
                self.snapshot.status = RunStatus.ERROR
                self.snapshot.error_message = exc.user_message
                await self._emit(terminal=True)
        except CursorCloudError as exc:
            self.snapshot.status = RunStatus.ERROR
            self.snapshot.error_message = exc.user_message
            await self._emit(terminal=True)
        except Exception as exc:
            self.snapshot.status = RunStatus.ERROR
            self.snapshot.error_message = f"Tracker failed: {exc}"
            await self._emit(terminal=True)
        finally:
            self._stop.set()
            coalesce_task.cancel()
            try:
                await coalesce_task
            except asyncio.CancelledError:
                pass
            if self.snapshot and self.snapshot.status.is_terminal:
                await self._emit(terminal=True)
        return self.snapshot

    def start_background(self, agent_id: str, run_id: str, **kwargs) -> asyncio.Task:
        self._task = asyncio.create_task(self.track(agent_id, run_id, **kwargs))
        return self._task

    async def cancel_tracking(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class MemoryStatusSink:
    """Test sink that records edits."""

    def __init__(self):
        self.updates: list[tuple[str, bool]] = []

    async def update(self, content: str, *, terminal: bool = False) -> None:
        self.updates.append((content, terminal))
