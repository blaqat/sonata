"""Hand-off buffer for AI-generated image bytes bound for Discord.

Image models run inside the synchronous ``chat.request`` call chain, which has
no access to the Discord client, while attachments can only be uploaded from
the async reply path. A caller that is able to deliver attachments opens a
``delivery_turn`` around its request; generators stash their raw bytes into
that turn, and the caller drains it to attach them to the outgoing message so
the image renders without depending on a third-party host embedding correctly.

The turn is the unit of ownership, not the channel: two replies in the same
channel can be in flight at once, and each must attach only its own images.
Callers that cannot attach (terminal and voice replies) simply never open a
turn, which leaves generators on their hosted-link path untouched.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
import threading
from dataclasses import dataclass
from typing import Iterable

# Discord accepts 10 attachments per message; a single turn should never come
# close, so a small cap keeps a runaway generator from pinning bytes in memory.
MAX_IMAGES_PER_TURN = 4

ATTACHED_NOTICE = "image generated and attached to this reply (no hosted link)"

DELIVERY_FAILED_NOTICE = (
    "(couldn't deliver the generated image — both the attachment upload and "
    "the image host failed)"
)

_EXTENSION_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

# Characters a URL may legitimately butt up against in prose. Requiring one of
# these (or end of string) stops a generated URL from matching inside a longer,
# distinct URL that merely starts with it. '?' and '&' are deliberately absent:
# they open a query string, so a link ending there is a different URL.
_URL_BOUNDARY = r"(?=$|[\s<>()\[\],.!;:'\"])"

_current_turn: contextvars.ContextVar = contextvars.ContextVar(
    "sonata_image_turn", default=None
)


@dataclass(frozen=True)
class GeneratedImage:
    """Raw bytes for one generated image plus its hosted-link fallback."""

    data: bytes
    filename: str
    url: str | None = None


class DeliveryTurn:
    """Images generated during one reply, owned by the caller that will send it."""

    def __init__(self):
        self._images: list[GeneratedImage] = []
        self._lock = threading.Lock()

    def add(self, image: GeneratedImage) -> bool:
        with self._lock:
            if len(self._images) >= MAX_IMAGES_PER_TURN:
                return False
            self._images.append(image)
            return True

    def take(self) -> list[GeneratedImage]:
        """Remove and return the images generated so far in this turn."""
        with self._lock:
            images, self._images = self._images, []
            return images


def extension_for(mime_type: str | None) -> str:
    """Map a generator's reported MIME type to a file extension."""
    return _EXTENSION_BY_MIME.get((mime_type or "").strip().lower(), "png")


@contextlib.contextmanager
def delivery_turn():
    """Collect images generated inside this block for the caller to attach.

    Yields the :class:`DeliveryTurn` to drain with ``take()``. Anything left
    undrained on exit is dropped, so a turn that errored before replying cannot
    leak its images into a later one.
    """
    turn = DeliveryTurn()
    token = _current_turn.set(turn)
    try:
        yield turn
    finally:
        _current_turn.reset(token)
        turn.take()


def stash(image_bytes: bytes, filename: str, url: str | None = None) -> bool:
    """Queue image bytes with the turn being served.

    Returns False when no turn is open (a caller that cannot attach) or the
    turn is full, which tells the generator its hosted link is still the only
    way the image can reach the user.
    """
    turn = _current_turn.get()
    if turn is None or not image_bytes:
        return False
    return turn.add(GeneratedImage(image_bytes, filename, url))


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
        text = re.sub(rf"<{escaped}>|{escaped}{_URL_BOUNDARY}", "", text)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
