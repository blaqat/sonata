"""Unauthenticated Discord CDN image downloads (never reuse Cursor API auth)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .errors import ValidationError
from .models import SUPPORTED_IMAGE_MIMES, MAX_IMAGE_BYTES


ALLOWED_DISCORD_CDN_HOSTS = frozenset(
    {
        "cdn.discordapp.com",
        "media.discordapp.net",
    }
)


def is_allowed_discord_cdn_url(url: str) -> bool:
    """Allow only HTTPS Discord CDN hosts (reject HTTP even on allowlisted hosts)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host in ALLOWED_DISCORD_CDN_HOSTS


class DiscordCDNDownloader:
    """Separate httpx client with no Authorization / Basic auth headers."""

    def __init__(
        self,
        *,
        max_bytes: int = MAX_IMAGE_BYTES,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.max_bytes = max_bytes
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._client = client
        self._owns_client = client is None

    async def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout,
                write=self._connect_timeout,
                pool=self._connect_timeout,
            )
            # follow_redirects=False so we can validate each hop's host.
            self._client = httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                headers={"Accept": "image/*,*/*"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def download(
        self,
        url: str,
        *,
        expected_mime: str | None = None,
        max_redirects: int = 3,
    ) -> tuple[bytes, str]:
        if not is_allowed_discord_cdn_url(url):
            raise ValidationError(
                f"URL host not allowlisted: {url}",
                user_message="Image URL is not an allowed Discord CDN host.",
            )
        client = await self._ensure()
        current = url
        for _ in range(max_redirects + 1):
            # Explicitly ensure no auth leaks even if a caller swapped the client.
            request = client.build_request("GET", current)
            if "Authorization" in request.headers:
                del request.headers["Authorization"]
            response = await client.send(request, follow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                await response.aclose()
                if not location:
                    raise ValidationError(
                        "Redirect without Location",
                        user_message="Image download redirect was invalid.",
                    )
                # Resolve relative redirects against current URL.
                next_url = str(httpx.URL(current).join(location))
                if not is_allowed_discord_cdn_url(next_url):
                    raise ValidationError(
                        f"Redirect host not allowlisted: {next_url}",
                        user_message="Image redirect left the Discord CDN allowlist.",
                    )
                current = next_url
                continue
            try:
                response.raise_for_status()
                data = response.content
            finally:
                await response.aclose()

            if len(data) > self.max_bytes:
                raise ValidationError(
                    f"Image exceeds {self.max_bytes} bytes",
                    user_message="An image exceeds the configured size limit.",
                )
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            mime = content_type or (expected_mime or "")
            if mime == "image/jpg":
                mime = "image/jpeg"
            if mime and mime not in SUPPORTED_IMAGE_MIMES:
                if expected_mime and expected_mime in SUPPORTED_IMAGE_MIMES:
                    mime = expected_mime
                else:
                    raise ValidationError(
                        f"Unsupported mime {mime}",
                        user_message="Downloaded image type is not supported.",
                    )
            if not mime:
                mime = expected_mime or "image/png"
            return data, mime

        raise ValidationError(
            "Too many redirects",
            user_message="Image download exceeded redirect limit.",
        )
