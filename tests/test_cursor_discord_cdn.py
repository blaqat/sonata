import pathlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.discord_cdn import DiscordCDNDownloader, is_allowed_discord_cdn_url
from cursor_cloud.errors import ValidationError


class TestDiscordCDNAllowlist(unittest.TestCase):
    def test_hosts(self):
        self.assertTrue(is_allowed_discord_cdn_url("https://cdn.discordapp.com/attachments/1/a.png"))
        self.assertTrue(is_allowed_discord_cdn_url("https://media.discordapp.net/attachments/1/a.png"))
        self.assertFalse(is_allowed_discord_cdn_url("https://evil.example/a.png"))
        self.assertFalse(is_allowed_discord_cdn_url("https://discord.com/attachments/1/a.png"))

    def test_https_only_rejects_http_allowlisted_host(self):
        self.assertFalse(
            is_allowed_discord_cdn_url("http://cdn.discordapp.com/attachments/1/a.png")
        )
        self.assertFalse(
            is_allowed_discord_cdn_url("http://media.discordapp.net/attachments/1/a.png")
        )


class TestDiscordCDNDownloader(unittest.IsolatedAsyncioTestCase):
    async def test_no_authorization_header_sent(self):
        seen = {}

        class FakeResponse:
            status_code = 200
            headers = {"Content-Type": "image/png"}
            content = b"\x89PNG\r\n\x1a\n" + b"x" * 16

            async def aclose(self):
                return None

            def raise_for_status(self):
                return None

        client = MagicMock()
        request = MagicMock()
        request.headers = {"Accept": "image/*,*/*", "Authorization": "Basic leaked"}
        client.build_request.return_value = request

        async def send(req, follow_redirects=False):
            seen["headers"] = dict(req.headers)
            seen["follow"] = follow_redirects
            return FakeResponse()

        client.send = AsyncMock(side_effect=send)
        downloader = DiscordCDNDownloader(client=client, max_bytes=1024)
        data, mime = await downloader.download(
            "https://cdn.discordapp.com/attachments/1/a.png"
        )
        self.assertEqual(mime, "image/png")
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertNotIn("Authorization", seen["headers"])
        self.assertFalse(seen["follow"])

    async def test_rejects_unapproved_host(self):
        downloader = DiscordCDNDownloader(client=MagicMock())
        with self.assertRaises(ValidationError):
            await downloader.download("https://evil.example/a.png")

    async def test_rejects_redirect_off_allowlist(self):
        class Redirect:
            status_code = 302
            headers = {"Location": "https://evil.example/leak.png"}

            async def aclose(self):
                return None

        client = MagicMock()
        req = MagicMock()
        req.headers = {}
        client.build_request.return_value = req
        client.send = AsyncMock(return_value=Redirect())
        downloader = DiscordCDNDownloader(client=client)
        with self.assertRaises(ValidationError):
            await downloader.download("https://cdn.discordapp.com/attachments/1/a.png")


if __name__ == "__main__":
    unittest.main()
