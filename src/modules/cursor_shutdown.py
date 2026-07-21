"""Cursor cleanup invoked from SonataClient.close (py-cord has no on_close)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable


async def close_with_cursor_cleanup(
    bot: Any,
    *,
    sonata: Any = None,
    log_error: Callable[[str], None] | None = None,
    super_close: Callable[[], Awaitable[None]],
) -> None:
    """Idempotent Cursor runtime cleanup then await ``super_close``.

    Production shutdown discovers exactly one attribute: ``bot._cursor_runtime``.
    Idempotency lives on ``CursorRuntime.closed`` (via ``aclose``).
    """
    _ = sonata  # call-site compat; discovery is bot._cursor_runtime only (F2).
    log = log_error or (lambda _msg: None)
    runtime = getattr(bot, "_cursor_runtime", None)
    if runtime is not None:
        try:
            aclose = getattr(runtime, "aclose", None)
            if callable(aclose):
                result = aclose()
                if hasattr(result, "__await__"):
                    await result
        except Exception as exc:
            log(f"Cursor cleanup failed: {exc}")
    await super_close()
