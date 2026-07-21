"""Thread chat-room status sink: one Activity message + frozen finals."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Protocol

from .models import RunSnapshot, RunStatus
from .thread_renderer import (
    format_thread_chat_info,
    render_thread_activity,
    render_thread_final,
    render_thread_summary,
)

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
        include_chat_info: bool = False,
        chat_info_model: str | None = None,
        chat_info_repository_url: str | None = None,
    ):
        self.channel = channel
        self.activity_message = activity_message
        self.edit_interval_ms = max(200, int(edit_interval_ms))
        self.allowed_mentions = allowed_mentions
        self.final_translator = final_translator
        self._include_chat_info = bool(include_chat_info)
        self._chat_info_model = chat_info_model
        self._chat_info_repository_url = chat_info_repository_url
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
        if terminal and snapshot.status.is_terminal:
            if self._last_terminal_run_id == snapshot.run_id:
                return
            self._last_terminal_run_id = snapshot.run_id
            await self._emit_terminal(
                snapshot,
                agent_name=agent_name,
                skipped_images=skipped_images,
            )
            return

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

    async def _emit_terminal(
        self,
        snapshot: RunSnapshot,
        *,
        agent_name: str | None,
        skipped_images: list[str] | None,
    ) -> None:
        first_finished = (
            self._include_chat_info and snapshot.status == RunStatus.FINISHED
        )
        summary = render_thread_summary(snapshot)

        if first_finished:
            branch = None
            for git in list(snapshot.git_branches or []):
                name = str(git.branch or "").strip()
                if name:
                    branch = name
                    break
            chat_info = format_thread_chat_info(
                agent_id=snapshot.agent_id,
                model=self._chat_info_model,
                branch=branch,
            )
            self._include_chat_info = False
            try:
                await self._edit_activity(chat_info, force=True)
            except Exception:
                self.degraded = True
            if summary:
                try:
                    await self._send(summary)
                except Exception:
                    self.degraded = True
        else:
            content = summary if summary else "\u200b"
            try:
                await self._edit_activity(content, force=True)
            except Exception:
                self.degraded = True

        # Translate the answer body only — Chat Info / summary stay outside Sona.
        final = render_thread_final(
            snapshot,
            agent_name=agent_name,
            skipped_images=skipped_images,
            chat_info=None,
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
        try:
            await self._send(final)
        except Exception:
            self.degraded = True

    async def _send(self, content: str) -> None:
        kwargs: dict[str, Any] = {}
        if self.allowed_mentions is not None:
            kwargs["allowed_mentions"] = self.allowed_mentions
        await self.channel.send(content[:2000], **kwargs)

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
