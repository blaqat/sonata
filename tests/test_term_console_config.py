import json
import pathlib
import sys
import unittest
from unittest import mock

repo_root = pathlib.Path(__file__).resolve().parents[1]
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))

from modules.term_console import TerminalConsole, TermConsoleServer
from sonata_config import ConfigUpdateError


class ConfigRouteTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = TermConsoleServer(
            TerminalConsole(),
            command_handler=None,
            secret="sekrit",
        )
        self.token = "test-token"
        self.server.tokens[self.token] = 0.0

    def _request(self, method: str, body: bytes = b"", authenticated=True) -> dict:
        headers = {}
        if authenticated:
            headers["cookie"] = f"{self.server.cookie_name}={self.token}"
        return {
            "method": method,
            "path": "/api/config",
            "query": {},
            "headers": headers,
            "body": body,
        }

    async def test_config_get_requires_authentication(self):
        status, _headers, body = await self.server._dispatch(
            self._request("GET", authenticated=False), writer=None
        )
        self.assertEqual(status, 401)
        payload = json.loads(body)
        self.assertFalse(payload["ok"])

    async def test_config_get_returns_view(self):
        view = {
            "fields": [{"path": "runtime.vc_speaking", "type": "bool"}],
            "values": {"runtime.vc_speaking": True},
            "recent_mutations": [],
        }
        with mock.patch("sonata_config.get_runtime_config", return_value=view):
            status, headers, body = await self.server._dispatch(
                self._request("GET"), writer=None
            )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), view)
        self.assertIn("application/json", headers["Content-Type"])

    async def test_config_patch_applies_updates(self):
        result = {
            "ok": True,
            "applied": ["plugins.chat.censor"],
            "restart_required": [],
            "values": {"plugins.chat.censor": True},
        }
        with mock.patch(
            "sonata_config.update_runtime_config", return_value=result
        ) as updater:
            status, _headers, body = await self.server._dispatch(
                self._request(
                    "PATCH",
                    json.dumps({"updates": {"plugins.chat.censor": True}}).encode(),
                ),
                writer=None,
            )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["values"], result["values"])
        self.assertIn("web:", updater.call_args.kwargs["actor"])

    async def test_config_patch_rejects_invalid_updates(self):
        error = ConfigUpdateError(
            {"plugins.chat.auto": "must be one of: g, o, c, a, m, x"}
        )
        with mock.patch(
            "sonata_config.update_runtime_config", side_effect=error
        ):
            status, _headers, body = await self.server._dispatch(
                self._request(
                    "PATCH",
                    json.dumps({"updates": {"plugins.chat.auto": "zzz"}}).encode(),
                ),
                writer=None,
            )
        self.assertEqual(status, 400)
        payload = json.loads(body)
        self.assertFalse(payload["ok"])
        self.assertIn("plugins.chat.auto", payload["errors"])

    async def test_config_patch_requires_authentication(self):
        status, _headers, _body = await self.server._dispatch(
            self._request("PATCH", b'{"updates": {}}', authenticated=False),
            writer=None,
        )
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
