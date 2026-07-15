import importlib.util
import json
import pathlib
import sys
import types
import unittest
from unittest import mock


def _load_utils_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    module_path = src_root / "modules" / "utils.py"
    spec = importlib.util.spec_from_file_location("sonata_utils_klipy", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load utils module spec")

    # Stub heavy optional imports used at module import time.
    stubs = {}
    for name, mod in [
        ("annotated_types", types.SimpleNamespace(IsInfinite=type("IsInfinite", (), {}))),
        ("discord.colour", types.SimpleNamespace(Color=type("Color", (), {}))),
        ("typing_extensions", types.ModuleType("typing_extensions")),
        ("dotenv", types.ModuleType("dotenv")),
        ("prompt_toolkit", types.ModuleType("prompt_toolkit")),
        ("prompt_toolkit.formatted_text", types.ModuleType("prompt_toolkit.formatted_text")),
        ("prompt_toolkit.patch_stdout", types.ModuleType("prompt_toolkit.patch_stdout")),
    ]:
        stubs[name] = sys.modules.get(name)
        if name == "typing_extensions":
            mod.cast = lambda _t, v: v
        if name == "dotenv":
            mod.load_dotenv = lambda *_, **__: None
        if name == "prompt_toolkit":
            mod.PromptSession = type("PromptSession", (), {})
        if name == "prompt_toolkit.formatted_text":
            mod.ANSI = type("ANSI", (), {})
        if name == "prompt_toolkit.patch_stdout":

            class _Ctx:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            mod.patch_stdout = lambda *_, **__: _Ctx()
        sys.modules[name] = mod

    discord_stub = types.ModuleType("discord")
    discord_stub.colour = sys.modules["discord.colour"]
    stubs["discord"] = sys.modules.get("discord")
    sys.modules["discord"] = discord_stub

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in stubs.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


def _load_gif_helpers():
    """Load get_n / gif_klipy_search without pulling the full plugin graph."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    module_path = src_root / "modules" / "plugins" / "self-commands.py"
    source = module_path.read_text(encoding="utf-8")

    # Extract the helper section between GIF_CACHE and gif_google_search.
    start = source.index("GIF_CACHE = {}")
    end = source.index("\ndef gif_google_search")
    snippet = source[start:end]

    module = types.ModuleType("gif_helpers_under_test")
    module.json = json
    module.random = __import__("random")
    module.requests = mock.Mock()
    module.settings = types.SimpleNamespace(KLIPY="test-klipy-key", TENOR_G="tenor-key")
    module.parse = __import__("urllib.parse")
    module.request = mock.Mock()
    module.cprint = lambda *_, **__: None
    exec(compile(snippet, str(module_path), "exec"), module.__dict__)
    return module


class KlipyGifProviderTests(unittest.TestCase):
    def setUp(self):
        self.utils = _load_utils_module()
        self.gif = _load_gif_helpers()
        self.gif.GIF_CACHE.clear()

    def test_gif_provider_get_dl_url_uses_klipy_host(self):
        payload = {
            "results": [
                {
                    "media_formats": {
                        "mediumgif": {"url": "https://static.klipy.com/x/medium.gif"},
                        "gif": {"url": "https://static.klipy.com/x/full.gif"},
                    }
                }
            ]
        }
        fake_response = mock.Mock(status_code=200)
        fake_response.json.return_value = payload

        with mock.patch.object(self.utils.requests, "get", return_value=fake_response) as get:
            url = self.utils.gif_provider_get_dl_url(
                "https://klipy.com/view/funny-cat-123456.webp",
                "test-key",
                size="tinywebppreview_transparent",
            )

        self.assertEqual(url, "https://static.klipy.com/x/medium.gif")
        called_url = get.call_args.args[0]
        self.assertIn("api.klipy.com/v2/posts", called_url)
        self.assertIn("ids=123456", called_url)
        self.assertIn("key=test-key", called_url)

    def test_tenor_alias_pins_tenor_host(self):
        payload = {
            "results": [
                {"media_formats": {"mediumgif": {"url": "https://media.tenor.com/x.gif"}}}
            ]
        }
        fake_response = mock.Mock(status_code=200)
        fake_response.json.return_value = payload

        with mock.patch.object(self.utils.requests, "get", return_value=fake_response) as get:
            url = self.utils.tenor_get_dl_url(
                "https://tenor.com/view/funny-cat-999.webp",
                "tenor-key",
            )

        self.assertEqual(url, "https://media.tenor.com/x.gif")
        self.assertIn("tenor.googleapis.com/v2/posts", get.call_args.args[0])

    def test_gif_klipy_search_encodes_query_via_params(self):
        payload = {
            "results": [
                {"media_formats": {"gif": {"url": "https://static.klipy.com/a.gif"}}},
                {"media_formats": {"gif": {"url": "https://static.klipy.com/b.gif"}}},
            ]
        }
        fake_response = mock.Mock()
        fake_response.text = json.dumps(payload)
        self.gif.requests.get.return_value = fake_response

        result = self.gif.gif_klipy_search("cats", "&", "dogs", limit=15)

        self.assertEqual(result["link"], "https://static.klipy.com/a.gif")
        self.gif.requests.get.assert_called_once_with(
            "https://api.klipy.com/v2/search",
            params={"q": "cats & dogs", "key": "test-klipy-key", "limit": 15},
        )

    def test_gif_klipy_search_empty_results(self):
        fake_response = mock.Mock()
        fake_response.text = json.dumps({"results": []})
        self.gif.requests.get.return_value = fake_response

        result = self.gif.gif_klipy_search("nope")

        self.assertEqual(result, "Gif not found.")

    def test_get_n_safe_for_single_and_empty(self):
        self.assertEqual(self.gif.get_n("alone", 1), 0)
        self.assertEqual(self.gif.get_n("alone", 1), 0)
        self.assertEqual(self.gif.get_n("empty", 0), 0)


if __name__ == "__main__":
    unittest.main()
