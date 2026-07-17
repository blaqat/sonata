"""Cursor cleanup invoked from SonataClient.close (py-cord has no on_close)."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


async def close_with_cursor_cleanup(
    bot: Any,
    *,
    sonata: Any = None,
    log_error: Callable[[str], None] | None = None,
    super_close: Callable[[], Awaitable[None]],
) -> None:
    """Idempotent Cursor runtime cleanup then await ``super_close``.

    This is the production shutdown body used by ``SonataClient.close`` so tests
    can exercise it without importing the full bot module.
    """
    log = log_error or (lambda _msg: None)
    if not getattr(bot, "_sonata_cursor_cleanup_done", False):
        bot._sonata_cursor_cleanup_done = True
        cleanup = getattr(bot, "_cursor_cleanup", None)
        if not callable(cleanup) and sonata is not None:
            cursor = getattr(sonata, "cursor", None)
            cleanup = getattr(cursor, "cleanup", None) if cursor is not None else None
        if not callable(cleanup) and sonata is not None:
            getter = getattr(sonata, "get", None)
            if callable(getter):
                cleanup = getter("cursor", "cleanup")
        if callable(cleanup):
            try:
                result = cleanup()
                if asyncio.iscoroutine(result):
                    await result
            except TypeError:
                try:
                    result = cleanup(sonata)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    log(f"Cursor cleanup failed: {exc}")
            except Exception as exc:
                log(f"Cursor cleanup failed: {exc}")
    await super_close()
