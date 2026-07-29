"""Structured, correlated logging for wake-word activation paths."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import re
from typing import Callable, Iterator
from uuid import uuid4


TraceEmitter = Callable[[str], None]
CHAT_WAKE_NAMES = ("sonata", "sona", "ソナ", "ソナタ")


def chat_wake_word_pattern(bot_user_id: int) -> re.Pattern[str]:
    names = "|".join(rf"\b{re.escape(name)}\b" for name in CHAT_WAKE_NAMES)
    return re.compile(rf"<@{bot_user_id}>|{names}", re.IGNORECASE)


def find_chat_wake_word(message: str, bot_user_id: int) -> str | None:
    """Return the exact mention or bounded Sonata alias that activated chat."""

    match = chat_wake_word_pattern(bot_user_id).search(message)
    return match.group(0) if match else None


def _format_value(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 240 else text[:237] + "..."


@dataclass
class ActivationTrace:
    """Emit each activation stage and a final end-to-end path."""

    source: str
    emit: TraceEmitter = print
    trace_id: str = field(default_factory=lambda: uuid4().hex[:8])
    stages: list[str] = field(default_factory=list)
    closed: bool = False

    def stage(self, name: str, **details: object) -> None:
        if self.closed:
            return
        self.stages.append(name)
        suffix = " ".join(
            f"{key}={_format_value(value)}" for key, value in details.items()
        )
        message = (
            f"[activation:{self.trace_id}] {len(self.stages):02d} {name}"
            + (f" | {suffix}" if suffix else "")
        )
        self.emit(message)

    def finish(self, outcome: str, **details: object) -> None:
        if self.closed:
            return
        suffix = " ".join(
            f"{key}={_format_value(value)}" for key, value in details.items()
        )
        path = " -> ".join(self.stages) or "(no stages)"
        message = (
            f"[activation:{self.trace_id}] {outcome.upper()} | "
            f"source={self.source!r} path={path}"
            + (f" | {suffix}" if suffix else "")
        )
        self.emit(message)
        self.closed = True


_ACTIVE_TRACE: ContextVar[ActivationTrace | None] = ContextVar(
    "active_activation_trace", default=None
)


def get_active_activation_trace() -> ActivationTrace | None:
    return _ACTIVE_TRACE.get()


@contextmanager
def use_activation_trace(trace: ActivationTrace | None) -> Iterator[None]:
    """Make a trace available to synchronous downstream hooks."""

    if trace is None:
        yield
        return

    token = _ACTIVE_TRACE.set(trace)
    try:
        yield
    finally:
        _ACTIVE_TRACE.reset(token)
