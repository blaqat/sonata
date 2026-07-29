"""Structured, correlated logging for wake-word activation paths."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Iterator
from uuid import uuid4


TraceEmitter = Callable[[str], None]


def matches_voice_wake_word(transcript: str, wake_word: str = "sonata") -> bool:
    """Mirror the voice listener's case-insensitive substring match."""

    return wake_word.casefold() in transcript.casefold()


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
