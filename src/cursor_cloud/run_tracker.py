"""Consume Cursor SSE events into a coalesced status sink."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .client import CursorCloudClient
from .errors import CursorCloudError, StreamExpiredError, TransportError
from .models import (
    GitBranchInfo,
    RunSnapshot,
    RunStatus,
    StreamEvent,
    ToolActivity,
    utcnow,
)
from .session_store import is_meaningful_stream_event
from .status_renderer import render_status, safe_tool_summary


class StatusSink(Protocol):
    async def update(self, content: str, *, terminal: bool = False) -> None: ...


OnActivity = Callable[[str], Awaitable[None] | None]


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
    ):
        self.client = client
        self.sink = sink
        self.edit_interval_ms = edit_interval_ms
        self.agent_name = agent_name
        self.skipped_images = skipped_images or []
        self.on_meaningful_activity = on_meaningful_activity
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._pending_render = False
        self._last_edit = 0.0
        self.snapshot: RunSnapshot | None = None

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
        elif name == "error":
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

    async def _emit(self, *, terminal: bool = False) -> None:
        if self.snapshot is None:
            return
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
                self.apply_event(self.snapshot, event)
                await self._notify_activity(event.event)
                if self.snapshot.status.is_terminal or event.event in {"result", "error", "done"}:
                    self._pending_render = False
                    await self._emit(terminal=True)
                    if event.event in {"result", "error", "done"} or self.snapshot.status.is_terminal:
                        if event.event == "done" or self.snapshot.status.is_terminal:
                            break
                else:
                    self._pending_render = True
        except StreamExpiredError:
            # Fallback should have handled; if not, poll once.
            try:
                run = await self.client.get_run(agent_id, run_id)
                self.snapshot.status = run.status
                self.snapshot.result_text = run.result or self.snapshot.result_text
                self.snapshot.duration_ms = run.duration_ms
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
