"""Hand-off buffer for AI-generated image bytes bound for Discord.

Image models run inside the synchronous ``chat.request`` call chain, which has
no access to the Discord client, while attachments can only be uploaded from
the async reply path. Generators stash their raw bytes here keyed by the
channel currently being served; the reply path drains the buffer and attaches
the images to the outgoing message so the image renders without depending on a
third-party host embedding correctly.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
import threading
from dataclasses import dataclass
from typing import Any, Iterable

# Discord accepts 10 attachments per message; a single turn should never come
# close, so a small cap keeps a runaway generator from pinning bytes in memory.
MAX_PENDING_PER_CHANNEL = 4

ATTACHED_NOTICE = "image generated and attached to this reply (no hosted link)"

_EXTENSION_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

_current_channel: contextvars.ContextVar = contextvars.ContextVar(
    "sonata_image_channel", default=None
)
_lock = threading.Lock()
_pending: dict[Any, list["GeneratedImage"]] = {}


@dataclass(frozen=True)
class GeneratedImage:
    """Raw bytes for one generated image plus its hosted-link fallback."""

    data: bytes
    filename: str
    url: str | None = None


def extension_for(mime_type: str | None) -> str:
    """Map a generator's reported MIME type to a file extension."""
    return _EXTENSION_BY_MIME.get((mime_type or "").strip().lower(), "png")


@contextlib.contextmanager
def current_channel(channel_id):
    """Bind images generated inside this block to ``channel_id``.

    Entering drops anything already queued for the channel so a turn that
    errored before its reply cannot leak stale images into the next one.
    """
    clear(channel_id)
    token = _current_channel.set(channel_id)
    try:
        yield
    finally:
        _current_channel.reset(token)


def stash(image_bytes: bytes, filename: str, url: str | None = None) -> bool:
    """Queue image bytes for the channel being served.

    Returns False when there is no bound channel (a non-Discord caller) or the
    channel's queue is full, which tells the caller its hosted link is still
    the only way the image can reach the user.
    """
    channel_id = _current_channel.get()
    if channel_id is None or not image_bytes:
        return False
    with _lock:
        queue = _pending.setdefault(channel_id, [])
        if len(queue) >= MAX_PENDING_PER_CHANNEL:
            return False
        queue.append(GeneratedImage(image_bytes, filename, url))
    return True


def take(channel_id) -> list[GeneratedImage]:
    """Remove and return every image queued for ``channel_id``."""
    with _lock:
        return _pending.pop(channel_id, [])


def clear(channel_id) -> None:
    """Discard anything queued for ``channel_id``."""
    with _lock:
        _pending.pop(channel_id, None)


def strip_urls(text: str, images: Iterable[GeneratedImage]) -> str:
    """Remove hosted links for images that are shipping as attachments.

    Only the exact URLs handed back by the generators are removed, so unrelated
    links the model included in its reply survive. A markdown link collapses to
    its title text to keep the surrounding sentence readable.
    """
    urls = [image.url for image in images if image.url]
    if not text or not urls:
        return text

    for url in urls:
        escaped = re.escape(url)
        text = re.sub(rf"\[([^\]]*)\]\(\s*<?{escaped}>?\s*\)", r"\1", text)
        text = re.sub(rf"<{escaped}>|{escaped}", "", text)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
