"""Prompt and image context builders (Discord-agnostic helpers)."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from .errors import ValidationError
from .models import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    SUPPORTED_IMAGE_MIMES,
    ImageInput,
    PromptImageMeta,
)


MESSAGE_URL_RE = re.compile(
    r"(?:https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/)?"
    r"(?:@me|\d+)/(\d+)/(\d+)"
)
MESSAGE_ID_RE = re.compile(r"^\d{5,30}$")


class AttachmentLike(Protocol):
    url: str
    content_type: str | None
    size: int | None
    filename: str | None


class MessageLike(Protocol):
    id: Any
    content: str
    author: Any
    attachments: list[Any]
    reference: Any


@dataclass
class ChainMessage:
    message_id: str
    author: str
    content: str
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BuiltPrompt:
    text: str
    images: list[ImageInput]
    skipped_images: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def image_metas(self) -> list[PromptImageMeta]:
        return metas_from_images(self.images)

    def api_images(self) -> list[dict[str, Any]]:
        return [img.to_api() for img in self.images]


def image_fingerprint(img: ImageInput) -> str:
    """Stable fingerprint preferring retained bytes over CDN URL."""
    material = img.data_b64 or img.url or ""
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def metas_from_images(images: list[ImageInput]) -> list[PromptImageMeta]:
    metas: list[PromptImageMeta] = []
    for img in images:
        metas.append(
            PromptImageMeta(
                mime_type=img.mime_type,
                size_bytes=img.size_bytes,
                source_message_id=img.source_message_id,
                fingerprint=image_fingerprint(img),
            )
        )
    return metas


def metas_match(
    left: list[PromptImageMeta], right: list[PromptImageMeta]
) -> bool:
    """Exact ordered match of mime/size/source/fingerprint."""
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if (
            a.mime_type != b.mime_type
            or a.size_bytes != b.size_bytes
            or a.source_message_id != b.source_message_id
            or a.fingerprint != b.fingerprint
        ):
            return False
    return True


def guess_mime(content_type: str | None, filename: str | None, url: str | None) -> str | None:
    if content_type:
        mime = content_type.split(";")[0].strip().lower()
        if mime in SUPPORTED_IMAGE_MIMES:
            return mime
        if mime == "image/jpg":
            return "image/jpeg"
    name = (filename or "") + " " + (url or "")
    lower = name.lower()
    if lower.endswith(".png") or ".png?" in lower:
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg") or ".jpg?" in lower or ".jpeg?" in lower:
        return "image/jpeg"
    if lower.endswith(".gif") or ".gif?" in lower:
        return "image/gif"
    if lower.endswith(".webp") or ".webp?" in lower:
        return "image/webp"
    return None


def parse_message_reference(
    raw: str | None,
    *,
    current_guild_id: str | int | None = None,
    current_channel_id: str | int | None = None,
) -> tuple[str | None, str | None]:
    """Return (channel_id, message_id) or raise ValidationError."""
    if raw is None or not str(raw).strip():
        return None, None
    text = str(raw).strip()
    match = MESSAGE_URL_RE.search(text)
    if match:
        channel_id, message_id = match.group(1), match.group(2)
        # Full URL may include guild; reject cross-guild when parseable.
        full = re.search(
            r"discord(?:app)?\.com/channels/(@me|\d+)/(\d+)/(\d+)", text
        )
        if full:
            guild_part = full.group(1)
            if (
                guild_part != "@me"
                and current_guild_id is not None
                and str(guild_part) != str(current_guild_id)
            ):
                raise ValidationError(
                    "Message reference is in another guild.",
                    user_message="That message is not in this server.",
                )
            if (
                current_channel_id is not None
                and str(full.group(2)) != str(current_channel_id)
                and False
            ):
                # Cross-channel within guild is allowed if bot can fetch it.
                pass
        return channel_id, message_id
    if MESSAGE_ID_RE.match(text):
        if current_channel_id is None:
            raise ValidationError(
                "Message ID requires a channel context.",
                user_message="Could not resolve that message ID in this channel.",
            )
        return str(current_channel_id), text
    raise ValidationError(
        "Malformed message reference.",
        user_message="Provide a Discord message URL or numeric message ID.",
    )


def author_name(author: Any) -> str:
    if author is None:
        return "unknown"
    return (
        getattr(author, "display_name", None)
        or getattr(author, "name", None)
        or str(author)
    )


def attachment_dict(att: Any) -> dict[str, Any] | None:
    url = getattr(att, "url", None) or getattr(att, "proxy_url", None)
    if not url:
        return None
    content_type = getattr(att, "content_type", None)
    filename = getattr(att, "filename", None)
    size = getattr(att, "size", None)
    mime = guess_mime(content_type, filename, url)
    if mime is None:
        return None
    return {
        "url": str(url),
        "mime_type": mime,
        "size": int(size) if size is not None else None,
        "filename": filename,
    }


def collect_chain_attachments(
    messages: list[Any],
    *,
    max_depth: int = 20,
) -> list[ChainMessage]:
    """Build chronological ChainMessage list from already-fetched message objects."""
    seen_ids: set[str] = set()
    chain: list[ChainMessage] = []
    for msg in messages[: max(0, max_depth)]:
        mid = str(getattr(msg, "id", "") or "")
        if not mid or mid in seen_ids:
            continue
        seen_ids.add(mid)
        attachments = []
        for att in getattr(msg, "attachments", None) or []:
            parsed = attachment_dict(att)
            if parsed:
                attachments.append(parsed)
        chain.append(
            ChainMessage(
                message_id=mid,
                author=author_name(getattr(msg, "author", None)),
                content=str(getattr(msg, "content", "") or ""),
                attachments=attachments,
            )
        )
    return chain


def compose_prompt_text(
    instruction: str,
    chain: list[ChainMessage] | list[tuple[str, str]] | None,
    *,
    missing_refs: list[str] | None = None,
) -> str:
    parts = [instruction.strip()]
    if chain:
        parts.append("\n--- Reply chain (oldest → newest) ---")
        for item in chain:
            if isinstance(item, ChainMessage):
                author, content = item.author, item.content
                extra = ""
                if not content.strip() and item.attachments:
                    extra = " [image attachment]"
                parts.append(f"{author}: {content}{extra}".rstrip())
            else:
                author, content = item[0], item[1]
                parts.append(f"{author}: {content}")
    if missing_refs:
        parts.append("\n--- Context notes ---")
        for note in missing_refs:
            parts.append(f"- {note}")
    return "\n".join(parts).strip()


def select_images(
    *,
    direct: list[ImageInput],
    chain_attachments: list[tuple[str, dict[str, Any]]],
    max_images: int = MAX_IMAGES,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> tuple[list[ImageInput], list[str]]:
    """Select up to max_images preferring direct attachments, then chronological chain."""
    selected: list[ImageInput] = []
    skipped: list[str] = []
    seen_urls: set[str] = set()

    def try_add(img: ImageInput) -> None:
        nonlocal selected
        if len(selected) >= max_images:
            skipped.append(f"skipped (5-image cap): {img.url or img.source_message_id}")
            return
        if img.mime_type not in SUPPORTED_IMAGE_MIMES:
            skipped.append(f"unsupported type: {img.mime_type}")
            return
        if img.size_bytes is not None and img.size_bytes > max_bytes:
            skipped.append(
                f"oversized ({img.size_bytes} > {max_bytes}): {img.url or 'image'}"
            )
            return
        key = img.url or (img.data_b64[:32] if img.data_b64 else None)
        if key and key in seen_urls:
            skipped.append(f"duplicate: {img.url or 'image'}")
            return
        if key:
            seen_urls.add(key)
        selected.append(img)

    for img in direct:
        try_add(img)

    for message_id, att in chain_attachments:
        if len(selected) >= max_images:
            break
        try_add(
            ImageInput(
                mime_type=att["mime_type"],
                url=att.get("url"),
                size_bytes=att.get("size"),
                source_message_id=message_id,
            )
        )

    return selected, skipped


def images_from_discord_attachments(
    attachments: list[Any],
    *,
    source_message_id: str | None = None,
) -> list[ImageInput]:
    out: list[ImageInput] = []
    for att in attachments:
        parsed = attachment_dict(att)
        if not parsed:
            continue
        out.append(
            ImageInput(
                mime_type=parsed["mime_type"],
                url=parsed["url"],
                size_bytes=parsed.get("size"),
                source_message_id=source_message_id,
            )
        )
    return out


def chain_attachment_pairs(
    chain: list[ChainMessage],
) -> list[tuple[str, dict[str, Any]]]:
    pairs: list[tuple[str, dict[str, Any]]] = []
    for msg in chain:
        for att in msg.attachments:
            pairs.append((msg.message_id, att))
    return pairs


def build_run_prompt(
    instruction: str,
    *,
    reference_chain: list[tuple[str, str]] | None = None,
    chain_messages: list[ChainMessage] | None = None,
    direct_images: list[ImageInput] | None = None,
    missing_refs: list[str] | None = None,
    max_images: int = MAX_IMAGES,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> BuiltPrompt:
    chain_for_text: list[Any] | None = chain_messages or reference_chain
    text = compose_prompt_text(instruction, chain_for_text, missing_refs=missing_refs)
    pairs = chain_attachment_pairs(chain_messages or [])
    images, skipped = select_images(
        direct=direct_images or [],
        chain_attachments=pairs,
        max_images=max_images,
        max_bytes=max_bytes,
    )
    return BuiltPrompt(text=text, images=images, skipped_images=skipped)


def encode_image_bytes(data: bytes, mime_type: str) -> ImageInput:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValidationError(
            f"Image exceeds {MAX_IMAGE_BYTES} bytes",
            user_message="An image exceeds the 15MB Cursor limit.",
        )
    if mime_type not in SUPPORTED_IMAGE_MIMES:
        raise ValidationError(
            f"Unsupported mime {mime_type}",
            user_message="Only PNG, JPEG, GIF, and WebP images are supported.",
        )
    return ImageInput(
        mime_type=mime_type,
        data_b64=base64.b64encode(data).decode("ascii"),
        size_bytes=len(data),
    )


def is_http_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
