"""Thread chat-room status sink: one Activity message + frozen finals."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Protocol

from .models import RunSnapshot, RunStatus
from .thread_renderer import render_thread_activity, render_thread_final

FinalTranslator = Callable[[str], Awaitable[str]]


class MessageLike(Protocol):
    id: int

    async def edit(self, content: str, **kwargs: Any) -> Any: ...


class ChannelLike(Protocol):
    async def send(self, content: str, **kwargs: Any) -> MessageLike: ...


class ThreadActivitySink:
    """Snapshot-aware sink for bound Cursor threads."""

    def __init__(
        self,
        channel: ChannelLike,
        activity_message: MessageLike,
        *,
        edit_interval_ms: int = 1200,
        allowed_mentions: Any = None,
        final_translator: FinalTranslator | None = None,
    ):
        self.channel = channel
        self.activity_message = activity_message
        self.edit_interval_ms = max(200, int(edit_interval_ms))
        self.allowed_mentions = allowed_mentions
        self.final_translator = final_translator
        self._last_edit = 0.0
        self._last_terminal_run_id: str | None = None
        self.degraded = False

    async def update(self, content: str, *, terminal: bool = False) -> None:
        # Classic render fallback (tests / recovery).
        await self._edit_activity(content, force=terminal)

    async def update_from_snapshot(
        self,
        snapshot: RunSnapshot,
        *,
        terminal: bool = False,
        agent_name: str | None = None,
        skipped_images: list[str] | None = None,
    ) -> None:
        activity = render_thread_activity(
            snapshot,
            agent_name=agent_name,
            skipped_images=skipped_images,
        )
        try:
            await self._edit_activity(
                activity, force=terminal or snapshot.status.is_terminal
            )
        except Exception:
            # Activity edit failures must not suppress the frozen final response.
            self.degraded = True

        if terminal and snapshot.status.is_terminal:
            if self._last_terminal_run_id == snapshot.run_id:
                return
            self._last_terminal_run_id = snapshot.run_id
            final = render_thread_final(
                snapshot,
                agent_name=agent_name,
                skipped_images=skipped_images,
            )
            if (
                self.final_translator is not None
                and snapshot.status == RunStatus.FINISHED
            ):
                try:
                    final = await self.final_translator(final)
                except Exception:
                    # Translator must fail open; keep original final text.
                    pass
            kwargs: dict[str, Any] = {}
            if self.allowed_mentions is not None:
                kwargs["allowed_mentions"] = self.allowed_mentions
            try:
                await self.channel.send(final[:2000], **kwargs)
            except Exception:
                self.degraded = True

    async def _edit_activity(self, content: str, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_edit) * 1000.0 < self.edit_interval_ms:
            return
        kwargs: dict[str, Any] = {}
        if self.allowed_mentions is not None:
            kwargs["allowed_mentions"] = self.allowed_mentions
        try:
            await self.activity_message.edit(content[:2000], **kwargs)
            self._last_edit = now
        except Exception:
            self.degraded = True
            raise
