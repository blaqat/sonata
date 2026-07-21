"""Consume Cursor SSE events into a coalesced status sink."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from .client import CursorCloudClient
from .errors import CursorCloudError, StreamExpiredError, ValidationError
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
from .status_renderer import redact_untrusted, render_status, safe_tool_summary, tool_family
from .stream_gone import is_stream_unavailable_error, is_stream_unavailable_exc

logger = logging.getLogger("sonata.cursor.tracker")

# When SSE dies while the run is still active, poll GET run until terminal.
DEFAULT_POLL_INTERVAL_S = 2.0
DEFAULT_POLL_MAX_S = 900.0
# Transient GET failures after stream drop (create/stream race on follow-ups).
MAX_POLL_RECONCILE_FAILURES = 20
# Best-effort SSE catch-up after GET already reports terminal — must not delay
# the Discord answer for the full stream read timeout (often many minutes).
CATCHUP_RESUME_TIMEOUT_S = 12.0
MAX_SUBAGENTS = 10
MAX_TASK_LABEL_CHARS = 80
_TASK_LABEL_KEYS = ("description", "name", "title", "task")


class StatusSink(Protocol):
    async def update(self, content: str, *, terminal: bool = False) -> None: ...


@runtime_checkable
class SnapshotSink(Protocol):
    async def update_from_snapshot(
        self,
        snapshot: RunSnapshot,
        *,
        terminal: bool = False,
        agent_name: str | None = None,
        skipped_images: list[str] | None = None,
    ) -> None: ...


OnActivity = Callable[[str], Awaitable[None] | None]


class RunTracker:
    def __init__(
        self,
        client: CursorCloudClient,
        sink: StatusSink | SnapshotSink,
        *,
        edit_interval_ms: int = 1200,
        agent_name: str | None = None,
        skipped_images: list[str] | None = None,
        on_meaningful_activity: OnActivity | None = None,
        run_log: RunLogStore | None = None,
        scope: ScopeKey | None = None,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        poll_max_s: float = DEFAULT_POLL_MAX_S,
    ):
        self.client = client
        self.sink = sink
        self.edit_interval_ms = edit_interval_ms
        self.agent_name = agent_name
        self.skipped_images = skipped_images or []
        self.on_meaningful_activity = on_meaningful_activity
        self.run_log = run_log
        self.scope = scope
        self.poll_interval_s = max(0.05, float(poll_interval_s))
        self.poll_max_s = max(self.poll_interval_s, float(poll_max_s))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._pending_render = False
        self._last_edit = 0.0
        self.snapshot: RunSnapshot | None = None
        self._pending_log_kinds: set[str] = set()
        self._logged_result_text: str | None = None
        self._seen_tool_call_ids: set[str] = set()
        # Transient monotonic thinking timer (not serialized).
        self._thinking_started_at: float | None = None

    def _close_thinking(self, snapshot: RunSnapshot) -> None:
        if self._thinking_started_at is None:
            return
        elapsed = max(0.0, time.monotonic() - self._thinking_started_at)
        self._thinking_started_at = None
        # Event bursts can fit inside one monotonic tick; keep a visible floor so
        # follow-up summaries still show Thought when thinking events arrived.
        if elapsed < 0.001:
            elapsed = 0.001
        prior = float(snapshot.thinking_seconds or 0.0)
        snapshot.thinking_seconds = prior + elapsed

    def _task_label_from_args(self, args: Any, *, fallback_index: int) -> str:
        if isinstance(args, dict):
            for key in _TASK_LABEL_KEYS:
                if key not in args:
                    continue
                raw = args.get(key)
                if raw is None:
                    continue
                text = redact_untrusted(str(raw)).strip()
                if text:
                    return text[:MAX_TASK_LABEL_CHARS]
        return f"Subagent {fallback_index}"

    def apply_event(self, snapshot: RunSnapshot, event: StreamEvent) -> RunSnapshot:
        if event.id:
            snapshot.last_event_id = event.id
        name = event.event
        data = event.data or {}

        if name == "status":
            self._close_thinking(snapshot)
            snapshot.status = RunStatus.from_api(data.get("status"))
            if data.get("runId"):
                snapshot.run_id = str(data["runId"])
        elif name == "assistant":
            self._close_thinking(snapshot)
            snapshot.assistant_text += str(data.get("text") or "")
            if snapshot.status.is_active:
                snapshot.status = RunStatus.RUNNING
        elif name == "thinking":
            if self._thinking_started_at is None:
                self._thinking_started_at = time.monotonic()
            snapshot.thinking_text += str(data.get("text") or "")
        elif name == "tool_call":
            self._close_thinking(snapshot)
            call_id = str(data.get("callId") or data.get("call_id") or "")
            tool_name = str(data.get("name") or "tool")
            status = str(data.get("status") or "")
            tool_args = data.get("args")
            family = tool_family(tool_name, tool_args)
            summary = safe_tool_summary(
                tool_name,
                tool_args,
                data.get("result"),
                truncated=data.get("truncated") if isinstance(data.get("truncated"), dict) else None,
            )
            resolved_id = call_id or f"anon-{len(snapshot.tools)}"
            if resolved_id not in self._seen_tool_call_ids:
                self._seen_tool_call_ids.add(resolved_id)
                snapshot.tool_family_counts[family] = (
                    int(snapshot.tool_family_counts.get(family, 0)) + 1
                )
            existing = next((t for t in snapshot.tools if t.call_id == resolved_id), None)
            if existing:
                existing.status = status
                existing.summary = summary
                existing.name = tool_name
            else:
                snapshot.tools.append(
                    ToolActivity(
                        call_id=resolved_id,
                        name=tool_name,
                        status=status,
                        summary=summary,
                    )
                )
            # Bound tool history (family counts / subagents are independent).
            if len(snapshot.tools) > 12:
                snapshot.tools = snapshot.tools[-12:]

            if family == "subagent":
                existing_sa = next(
                    (t for t in snapshot.subagents if t.call_id == resolved_id),
                    None,
                )
                if existing_sa:
                    existing_sa.status = status
                    existing_sa.summary = summary
                    existing_sa.name = tool_name
                    if not existing_sa.label or existing_sa.label.lower().startswith(
                        "subagent "
                    ):
                        existing_sa.label = self._task_label_from_args(
                            data.get("args"),
                            fallback_index=snapshot.subagents.index(existing_sa) + 1,
                        )
                elif len(snapshot.subagents) < MAX_SUBAGENTS:
                    label = self._task_label_from_args(
                        data.get("args"),
                        fallback_index=len(snapshot.subagents) + 1,
                    )
                    snapshot.subagents.append(
                        ToolActivity(
                            call_id=resolved_id,
                            name=tool_name,
                            status=status,
                            summary=summary,
                            label=label,
                        )
                    )
        elif name == "interaction_update":
            # Prefer simplified events; ignore rich duplicates.
            pass
        elif name == "heartbeat":
            pass
        elif name == "result":
            self._close_thinking(snapshot)
            snapshot.status = RunStatus.from_api(data.get("status") or "FINISHED")
            if data.get("text"):
                snapshot.result_text = str(data.get("text") or "")
            if data.get("durationMs") is not None:
                snapshot.duration_ms = int(data["durationMs"])
            git = data.get("git") or {}
            branches = GitBranchInfo.from_api_list(
                git.get("branches") if isinstance(git, dict) else git
            )
            if branches:
                snapshot.git_branches = branches
            # Successful result clears a prior non-fatal stream glitch message.
            if snapshot.status == RunStatus.FINISHED:
                snapshot.error_message = ""
        elif name == "error":
            self._close_thinking(snapshot)
            if is_stream_unavailable_error(data):
                # Stream ended; caller reconciles via GET run — do not mark ERROR.
                pass
            else:
                snapshot.status = RunStatus.ERROR
                snapshot.error_message = str(
                    data.get("message") or data.get("code") or "Agent error"
                )
        elif name == "done":
            self._close_thinking(snapshot)
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
        branches = GitBranchInfo.from_api_list(
            git.get("branches") if isinstance(git, dict) else git
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
        prev = self.snapshot.status
        self.apply_run_record(self.snapshot, run)
        if prev != self.snapshot.status or run.result:
            api_err = ""
            if isinstance(run.raw, dict):
                api_err = str(
                    run.raw.get("error") or run.raw.get("message") or ""
                )[:200]
            logger.info(
                "cursor.reconcile agent=%s run=%s api_status=%s snap=%s→%s "
                "has_result=%s err=%r",
                agent_id,
                run_id,
                getattr(run.status, "value", run.status),
                prev.value,
                self.snapshot.status.value,
                bool(run.result),
                api_err,
            )
        # Only persist the final answer once — skip RUNNING reconcile spam.
        if run.result and run.result != self._logged_result_text:
            self._logged_result_text = run.result
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
            # Skip CREATING/RUNNING noise; terminal status is covered by result/error.
            return
        if name == "tool_call":
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
            if text != self._logged_result_text:
                self._logged_result_text = text
                await self._log("result", sanitize_log_summary(text))
        elif name == "error":
            if is_stream_unavailable_error(data):
                # Stream drop is operational; follow via GET run — don't clutter history.
                return
            await self._log(
                "error",
                sanitize_log_summary(
                    str(data.get("message") or data.get("code") or "error")
                ),
            )
        elif name in {"done", "heartbeat"}:
            return
        # Ignore unknown event kinds in history (keeps focus on tools/thinking/result).

    def _snapshot_has_traceability(self) -> bool:
        """True when the snapshot can render a non-empty thread summary."""
        if self.snapshot is None:
            return False
        if float(self.snapshot.thinking_seconds or 0.0) > 0:
            return True
        if self.snapshot.subagents:
            return True
        counts = self.snapshot.tool_family_counts or {}
        return any(
            family != "subagent" and int(count) > 0
            for family, count in counts.items()
        )

    async def _apply_stream_event(self, event: StreamEvent) -> bool:
        """Apply one SSE event. Returns True when the caller should stop the stream."""
        if self.snapshot is None:
            return True
        stream_gone = event.event == "error" and is_stream_unavailable_error(
            event.data
        )
        if event.event == "error":
            logger.warning(
                "cursor.sse_error agent=%s run=%s stream_gone=%s data=%r",
                self.snapshot.agent_id,
                self.snapshot.run_id,
                stream_gone,
                event.data,
            )
        self.apply_event(self.snapshot, event)
        await self._log_event(event)
        await self._notify_activity(event.event)
        if stream_gone:
            return True
        # Stop on stream end / terminal payload events only. Do NOT stop merely
        # because GET already marked the snapshot terminal — catch-up after poll
        # must still read thinking/tool_call events that enrich the summary.
        if event.event == "done":
            self._pending_render = False
            return True
        if event.event in {"result", "error"}:
            self._pending_render = False
            return bool(self.snapshot.status.is_terminal)
        self._pending_render = True
        return False

    def _invalid_last_event_id_error(self, exc: BaseException) -> bool:
        message = " ".join(
            str(part)
            for part in (exc, getattr(exc, "user_message", ""), getattr(exc, "code", ""))
            if part
        ).lower()
        code = str(getattr(exc, "code", "") or "").lower()
        return "last_event" in message or "invalid_last_event" in code

    async def _iter_resume_events(
        self,
        stream_run: Callable[..., AsyncIterator[StreamEvent]],
        agent_id: str,
        run_id: str,
        last_event_id: str | None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield resume SSE events; retry once without Last-Event-ID if rejected."""
        try:
            async for event in stream_run(
                agent_id, run_id, last_event_id=last_event_id
            ):
                yield event
            return
        except ValidationError as exc:
            if not (last_event_id and self._invalid_last_event_id_error(exc)):
                raise
            logger.warning(
                "cursor.stream_resume_retry_without_last_event agent=%s run=%s",
                agent_id,
                run_id,
            )
        async for event in stream_run(agent_id, run_id, last_event_id=None):
            yield event

    async def _try_resume_stream(self, agent_id: str, run_id: str) -> bool:
        """Reconnect to SSE to recover thinking/tool events after stream-gone.

        Follow-up runs often open the stream before it is ready. Polling GET can
        observe FINISHED without ever receiving tool_call/thinking events. While
        the retention window is open, retrying ``stream_run`` recovers them.

        Returns True when the snapshot is terminal after this attempt.
        """
        if self.snapshot is None or self._stop.is_set():
            return bool(self.snapshot and self.snapshot.status.is_terminal)
        stream_run = getattr(self.client, "stream_run", None)
        if stream_run is None:
            # Test fakes may only implement stream_run_with_fallback.
            return bool(self.snapshot.status.is_terminal)
        last_event_id = self.snapshot.last_event_id
        logger.info(
            "cursor.stream_resume_try agent=%s run=%s last_event_id=%s "
            "has_trace=%s status=%s",
            agent_id,
            run_id,
            last_event_id,
            self._snapshot_has_traceability(),
            self.snapshot.status.value,
        )
        try:
            async for event in self._iter_resume_events(
                stream_run, agent_id, run_id, last_event_id
            ):
                if self._stop.is_set():
                    break
                stop = await self._apply_stream_event(event)
                if self._pending_render and self.snapshot and not self.snapshot.status.is_terminal:
                    self._pending_render = False
                    await self._emit(terminal=False)
                if stop:
                    break
        except StreamExpiredError as exc:
            logger.warning(
                "cursor.stream_resume_expired agent=%s run=%s msg=%r",
                agent_id,
                run_id,
                (exc.user_message or str(exc))[:300],
            )
            return bool(self.snapshot and self.snapshot.status.is_terminal)
        except CursorCloudError as exc:
            if is_stream_unavailable_exc(exc):
                logger.warning(
                    "cursor.stream_resume_unavailable agent=%s run=%s "
                    "http=%s code=%s msg=%r",
                    agent_id,
                    run_id,
                    getattr(exc, "status", None),
                    getattr(exc, "code", None),
                    (exc.user_message or str(exc))[:300],
                )
                return bool(self.snapshot and self.snapshot.status.is_terminal)
            raise
        except Exception:
            logger.exception(
                "cursor.stream_resume_failed agent=%s run=%s", agent_id, run_id
            )
            return bool(self.snapshot and self.snapshot.status.is_terminal)

        logger.info(
            "cursor.stream_resume_end agent=%s run=%s status=%s has_trace=%s",
            agent_id,
            run_id,
            self.snapshot.status.value if self.snapshot else None,
            self._snapshot_has_traceability(),
        )
        return bool(self.snapshot and self.snapshot.status.is_terminal)

    async def _emit_terminal_with_catchup(self, agent_id: str, run_id: str) -> None:
        """Emit terminal status, with a bounded SSE catch-up when summary is empty.

        Catch-up is best-effort. GET may already have the final answer; never let
        a hung resume suppress or indefinitely delay that terminal publish.
        """
        if self.snapshot is None:
            return
        if not self._snapshot_has_traceability():
            try:
                await asyncio.wait_for(
                    self._try_resume_stream(agent_id, run_id),
                    timeout=CATCHUP_RESUME_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "cursor.stream_catchup_timeout agent=%s run=%s timeout_s=%s",
                    agent_id,
                    run_id,
                    CATCHUP_RESUME_TIMEOUT_S,
                )
            except CursorCloudError:
                # Catchup is best-effort; still publish the final answer.
                pass
        self._pending_render = False
        await self._emit(terminal=True)

    async def _follow_until_terminal(self, agent_id: str, run_id: str) -> None:
        """Poll GET run until the agent finishes after the SSE stream drops.

        Interleaves SSE resume attempts so follow-up tool/thinking events are not
        lost when the first stream open races create_run.
        """
        if self.snapshot is None:
            return
        deadline = time.monotonic() + self.poll_max_s
        consecutive_failures = 0
        logger.info(
            "cursor.poll_start agent=%s run=%s status=%s poll_max_s=%s",
            agent_id,
            run_id,
            self.snapshot.status.value,
            self.poll_max_s,
        )
        while not self._stop.is_set() and time.monotonic() < deadline:
            # Prefer SSE resume: GET alone never carries tool/thinking payloads.
            try:
                if await self._try_resume_stream(agent_id, run_id):
                    # Resume already consumed available SSE; do not open a second
                    # unbounded stream before publishing the terminal answer.
                    self._pending_render = False
                    await self._emit(terminal=True)
                    return
            except CursorCloudError as exc:
                consecutive_failures += 1
                logger.warning(
                    "cursor.poll_stream_resume_failed agent=%s run=%s failures=%s "
                    "http=%s code=%s msg=%r",
                    agent_id,
                    run_id,
                    consecutive_failures,
                    getattr(exc, "status", None),
                    getattr(exc, "code", None),
                    (exc.user_message or str(exc))[:300],
                )
                hard = getattr(exc, "status", None) in {401, 403}
                if hard:
                    self.snapshot.status = RunStatus.ERROR
                    self.snapshot.error_message = exc.user_message
                    self._pending_render = False
                    await self._emit(terminal=True)
                    return

            try:
                await self._reconcile_from_api(agent_id, run_id)
                consecutive_failures = 0
            except CursorCloudError as exc:
                consecutive_failures += 1
                logger.warning(
                    "cursor.poll_reconcile_failed agent=%s run=%s failures=%s "
                    "http=%s code=%s msg=%r",
                    agent_id,
                    run_id,
                    consecutive_failures,
                    getattr(exc, "status", None),
                    getattr(exc, "code", None),
                    (exc.user_message or str(exc))[:300],
                )
                hard = getattr(exc, "status", None) in {401, 403}
                if hard or consecutive_failures >= MAX_POLL_RECONCILE_FAILURES:
                    self.snapshot.status = RunStatus.ERROR
                    self.snapshot.error_message = exc.user_message
                    self._pending_render = False
                    await self._emit(terminal=True)
                    return
            if self.snapshot.status.is_terminal:
                logger.warning(
                    "cursor.poll_terminal agent=%s run=%s status=%s has_trace=%s",
                    agent_id,
                    run_id,
                    self.snapshot.status.value,
                    self._snapshot_has_traceability(),
                )
                await self._emit_terminal_with_catchup(agent_id, run_id)
                return
            self._pending_render = False
            await self._emit(terminal=False)
            await asyncio.sleep(self.poll_interval_s)

        if self.snapshot and not self.snapshot.status.is_terminal and not self._stop.is_set():
            logger.warning(
                "cursor.poll_timeout agent=%s run=%s last_status=%s failures=%s",
                agent_id,
                run_id,
                self.snapshot.status.value,
                consecutive_failures,
            )
            try:
                await self._reconcile_from_api(agent_id, run_id)
            except CursorCloudError as exc:
                logger.warning(
                    "cursor.poll_timeout_reconcile_failed agent=%s run=%s msg=%r",
                    agent_id,
                    run_id,
                    (exc.user_message or str(exc))[:300],
                )
                self.snapshot.status = RunStatus.ERROR
                self.snapshot.error_message = exc.user_message
            if not self.snapshot.status.is_terminal:
                self.snapshot.status = RunStatus.ERROR
                self.snapshot.error_message = (
                    self.snapshot.error_message
                    or "Timed out waiting for run to finish after stream ended."
                )
            await self._emit_terminal_with_catchup(agent_id, run_id)

    async def _emit(self, *, terminal: bool = False) -> None:
        if self.snapshot is None:
            return
        if terminal:
            self._close_thinking(self.snapshot)
        if terminal or self._pending_log_kinds:
            await self._flush_pending_text_logs()
        # Snapshot-aware sinks (thread chat-room UX) bypass classic single-message render.
        try:
            if isinstance(self.sink, SnapshotSink):
                await self.sink.update_from_snapshot(
                    self.snapshot,
                    terminal=terminal,
                    agent_name=self.agent_name,
                    skipped_images=self.skipped_images,
                )
            else:
                content = render_status(
                    self.snapshot,
                    agent_name=self.agent_name,
                    skipped_images=self.skipped_images,
                )
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
        self._seen_tool_call_ids.clear()
        self._thinking_started_at = None
        logger.info(
            "cursor.track_start agent=%s run=%s initial=%s last_event_id=%s",
            agent_id,
            run_id,
            initial_status.value if hasattr(initial_status, "value") else initial_status,
            last_event_id,
        )
        await self._emit(terminal=False)
        coalesce_task = asyncio.create_task(self._coalesce_loop())
        terminal_emitted = False
        try:
            async for event in self.client.stream_run_with_fallback(
                agent_id, run_id, last_event_id=last_event_id
            ):
                if self._stop.is_set():
                    logger.warning(
                        "cursor.track_stop_set agent=%s run=%s", agent_id, run_id
                    )
                    break

                stream_gone = event.event == "error" and is_stream_unavailable_error(
                    event.data
                )
                stop = await self._apply_stream_event(event)

                if stream_gone:
                    # Stream ended; GET run may still be RUNNING — keep following.
                    # Do not ERROR on the first reconcile miss (follow-up create/stream race).
                    try:
                        await self._reconcile_from_api(agent_id, run_id)
                    except CursorCloudError as exc:
                        logger.warning(
                            "cursor.stream_unavailable_reconcile_failed "
                            "agent=%s run=%s http=%s code=%s msg=%r — will poll",
                            agent_id,
                            run_id,
                            getattr(exc, "status", None),
                            getattr(exc, "code", None),
                            (exc.user_message or str(exc))[:300],
                        )
                    if self.snapshot.status.is_terminal:
                        await self._emit_terminal_with_catchup(agent_id, run_id)
                        terminal_emitted = True
                    else:
                        self._pending_render = False
                        await self._emit(terminal=False)
                        await self._follow_until_terminal(agent_id, run_id)
                        terminal_emitted = True
                    break

                if stop:
                    logger.warning(
                        "cursor.track_sse_terminal agent=%s run=%s event=%s status=%s",
                        agent_id,
                        run_id,
                        event.event,
                        self.snapshot.status.value,
                    )
                    # Healthy SSE path already has events; no catchup needed.
                    self._pending_render = False
                    await self._emit(terminal=True)
                    terminal_emitted = True
                    break

            # Stream ended without a terminal snapshot — poll until finished.
            if (
                self.snapshot
                and not self.snapshot.status.is_terminal
                and not self._stop.is_set()
            ):
                logger.warning(
                    "cursor.stream_ended_non_terminal agent=%s run=%s status=%s",
                    agent_id,
                    run_id,
                    self.snapshot.status.value,
                )
                await self._follow_until_terminal(agent_id, run_id)
                terminal_emitted = True
        except StreamExpiredError as exc:
            logger.warning(
                "cursor.track_stream_expired agent=%s run=%s msg=%r — will poll",
                agent_id,
                run_id,
                (exc.user_message or str(exc))[:300],
            )
            # Fallback should have handled; if not, follow via GET run.
            if self.snapshot and not self.snapshot.status.is_terminal:
                await self._follow_until_terminal(agent_id, run_id)
                terminal_emitted = True
        except CursorCloudError as exc:
            logger.warning(
                "cursor.track_cloud_error agent=%s run=%s http=%s code=%s msg=%r",
                agent_id,
                run_id,
                getattr(exc, "status", None),
                getattr(exc, "code", None),
                (exc.user_message or str(exc))[:300],
            )
            # Follow-up stream open often fails with "stream no longer available"
            # while the run is still active — poll GET instead of freezing as Error.
            if is_stream_unavailable_exc(exc) and self.snapshot:
                if not self.snapshot.status.is_terminal:
                    await self._follow_until_terminal(agent_id, run_id)
                    terminal_emitted = True
                else:
                    await self._emit_terminal_with_catchup(agent_id, run_id)
                    terminal_emitted = True
            else:
                self.snapshot.status = RunStatus.ERROR
                self.snapshot.error_message = exc.user_message
                await self._emit(terminal=True)
                terminal_emitted = True
        except Exception as exc:
            logger.exception("cursor.track_failed agent=%s run=%s", agent_id, run_id)
            self.snapshot.status = RunStatus.ERROR
            self.snapshot.error_message = f"Tracker failed: {exc}"
            await self._emit(terminal=True)
            terminal_emitted = True
        finally:
            self._stop.set()
            coalesce_task.cancel()
            try:
                await coalesce_task
            except asyncio.CancelledError:
                pass
            logger.info(
                "cursor.track_end agent=%s run=%s status=%s degraded=%s err=%r",
                agent_id,
                run_id,
                self.snapshot.status.value if self.snapshot else None,
                getattr(self.snapshot, "degraded", None),
                (getattr(self.snapshot, "error_message", None) or "")[:200],
            )
            if (
                not terminal_emitted
                and self.snapshot
                and self.snapshot.status.is_terminal
            ):
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
