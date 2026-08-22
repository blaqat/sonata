import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock


def load_self_commands_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "src" / "modules" / "plugins" / "self-commands.py"

    class DummyPromptStore:
        def set_instructions(self, *_, **__):
            return None

    class DummyPromptManager:
        def __init__(self):
            self.sent = []

        def send(self, *args, **kwargs):
            self.sent.append((args, kwargs))
            return ""

    class DummyManager:
        def __init__(self):
            self.MANAGER = types.SimpleNamespace(
                config={"read": {"max_chars": 80, "timeout": 5, "goto_timeout_ms": 1234}}
            )
            self.commands = {}
            self.memory = {}
            self.PROMPTS = DummyPromptStore()

        def set(self, key, name, func, usage=None, desc=None, inst=None):
            if key == "command":
                self.commands[name] = {
                    "func": func,
                    "usage": usage,
                    "desc": desc,
                    "instructions": inst,
                }
            else:
                self.memory.setdefault(key, {})[name] = func

        def get(self, key, inner=None):
            if key == "command":
                return self.commands
            if key == "state":
                return self.memory.get("state", {})
            return self.memory.get(key, {})

        def do(self, key, action, *args):
            if key == "command" and action == "validate":
                return args[0] in self.commands
            if key == "command" and action == "list":
                return "; ".join(
                    f"{name} - {meta['usage']} - {meta['desc']}"
                    for name, meta in self.commands.items()
                )
            if key == "command" and action == "str":
                name = args[0]
                meta = self.commands[name]
                return f"{name} - {meta['usage']} - {meta['desc']}"
            if key == "command" and action == "use":
                name = args[0]
                return self.commands[name]["func"](*args[1:])
            if key == "state" and action == "clear":
                self.memory["state"] = {}
                return None
            raise AssertionError(f"Unsupported do() call: {(key, action, args)}")

        def mem(self, *_, **__):
            def decorator(func):
                return func

            return decorator

        def new_helper(self, *_args, **_kwargs):
            def decorator(func):
                return func

            return decorator

        def command(self, name, usage, desc=None, inst=None):
            def decorator(func):
                self.commands[name] = {
                    "func": func,
                    "usage": usage,
                    "desc": desc,
                    "instructions": inst,
                }
                return func

            return decorator

        def prompt(self, func):
            return func

        def effect_post(self, func):
            return func

    dummy_manager = DummyManager()
    dummy_prompt_manager = DummyPromptManager()
    ai_manager_stub = types.ModuleType("modules.AI_manager")

    class AIManagerStub:
        @staticmethod
        def init(*_, **__):
            context = types.SimpleNamespace(prompt_manager=dummy_prompt_manager)
            return context, dummy_manager, dummy_prompt_manager

    ai_manager_stub.AI_Manager = AIManagerStub

    utils_stub = types.ModuleType("modules.utils")
    utils_stub.async_cprint = lambda *_, **__: None
    utils_stub.async_print = lambda *_, **__: None
    utils_stub.setter = lambda value, *_args, **_kwargs: value
    utils_stub.settings = types.SimpleNamespace(
        WEATHER="weather-key",
        SEARCH_KEY="search-key",
        SEARCH_ID="search-id",
        TENOR_G="tenor-key",
        GIPHY="giphy-key",
        CLOUDFLARE_ACCOUNT_ID=None,
        CLOUDFLARE_API_TOKEN=None,
    )

    google_images_stub = types.ModuleType("google_images_search")
    google_images_stub.GoogleImagesSearch = type("GoogleImagesSearch", (), {})

    googleapiclient_stub = types.ModuleType("googleapiclient")
    googleapiclient_discovery_stub = types.ModuleType("googleapiclient.discovery")
    googleapiclient_discovery_stub.build = lambda *_, **__: None

    nuvem_stub = types.ModuleType("nuvem_de_som")
    nuvem_stub.SoundCloud = type("SoundCloud", (), {})

    youtube_stub = types.ModuleType("youtubesearchpython")
    youtube_stub.VideosSearch = type("VideosSearch", (), {})

    original_modules = {
        "modules.AI_manager": sys.modules.get("modules.AI_manager"),
        "modules.utils": sys.modules.get("modules.utils"),
        "google_images_search": sys.modules.get("google_images_search"),
        "googleapiclient": sys.modules.get("googleapiclient"),
        "googleapiclient.discovery": sys.modules.get("googleapiclient.discovery"),
        "nuvem_de_som": sys.modules.get("nuvem_de_som"),
        "youtubesearchpython": sys.modules.get("youtubesearchpython"),
    }

    sys.modules["modules.AI_manager"] = ai_manager_stub
    sys.modules["modules.utils"] = utils_stub
    sys.modules["google_images_search"] = google_images_stub
    sys.modules["googleapiclient"] = googleapiclient_stub
    sys.modules["googleapiclient.discovery"] = googleapiclient_discovery_stub
    sys.modules["nuvem_de_som"] = nuvem_stub
    sys.modules["youtubesearchpython"] = youtube_stub

    try:
        spec = importlib.util.spec_from_file_location("self_commands", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load self-commands module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


self_commands = load_self_commands_module()


class SelfCommandHelpersTests(unittest.TestCase):
    def setUp(self):
        # Tests mutate the shared module-level settings stub; restore per test.
        for attr in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
            original = getattr(self_commands.settings, attr)
            self.addCleanup(setattr, self_commands.settings, attr, original)

    def test_normalize_url_adds_https(self):
        self.assertEqual(
            self_commands.normalize_url("example.com/docs"),
            "https://example.com/docs",
        )

    def test_normalize_url_preserves_protocol_relative(self):
        self.assertEqual(
            self_commands.normalize_url("//cdn.example.com/image"),
            "https://cdn.example.com/image",
        )

    def test_normalize_url_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            self_commands.normalize_url("ftp://example.com/file")

    def test_truncate_markdown_rejects_negative_limit(self):
        content, truncated = self_commands._truncate_markdown("hello world", -3)
        self.assertTrue(truncated)
        self.assertIn("...[truncated]", content)
        self.assertNotIn("hello world", content)

    def test_read_command_description_mentions_posted_links(self):
        command = self_commands.MANAGER.get("command")["read"]
        self.assertIn("links users post", command["desc"])

    def test_cloudflare_read_requires_configuration(self):
        result = self_commands.cloudflare_markdown_read("https://example.com")
        self.assertEqual(result["status"], "error")
        self.assertIn("not configured", result["message"])

    def test_cloudflare_read_returns_compact_markdown_payload(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"
        fake_response = mock.Mock()
        fake_response.ok = True
        fake_response.json.return_value = {
            "success": True,
            "result": "# Example Title\n\n" + ("body " * 40),
        }

        with mock.patch.object(self_commands.requests, "post", return_value=fake_response) as post:
            result = self_commands.cloudflare_markdown_read("example.com")

        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["params"], {"browser": "kitesurf"})
        self.assertEqual(result["status"], "found")
        payload = result["result"][0]
        self.assertEqual(payload["backend"], "browser_run")
        self.assertEqual(payload["engine"], "kitesurf")
        self.assertEqual(payload["url"], "https://example.com")
        self.assertEqual(payload["title"], "Example Title")
        self.assertTrue(payload["truncated"])
        self.assertIn("...[truncated]", payload["content"])

    def test_cloudflare_read_falls_back_to_chromium_after_empty_extract(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"
        empty_response = mock.Mock()
        empty_response.ok = True
        empty_response.json.return_value = {"success": True, "result": ""}
        good_response = mock.Mock()
        good_response.ok = True
        good_response.json.return_value = {
            "success": True,
            "result": "# Fallback Title\n\nbody",
        }

        with mock.patch.object(
            self_commands.requests, "post", side_effect=[empty_response, good_response]
        ) as post:
            result = self_commands.cloudflare_markdown_read("https://example.com")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["params"], {"browser": "kitesurf"})
        self.assertIsNone(post.call_args_list[1].kwargs["params"])
        self.assertEqual(result["status"], "found")
        payload = result["result"][0]
        self.assertEqual(payload["engine"], "chromium")
        self.assertEqual(payload["title"], "Fallback Title")
        self.assertIn("chromium", result["message"])

    def test_cloudflare_read_hard_page_hosts_skip_kitesurf(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"
        config = self_commands.MANAGER.MANAGER.config.setdefault("read", {})
        original_hosts = config.get("hard_page_hosts")
        config["hard_page_hosts"] = ["example.com"]
        good_response = mock.Mock()
        good_response.ok = True
        good_response.json.return_value = {"success": True, "result": "# Hard\n\nbody"}
        try:
            with mock.patch.object(
                self_commands.requests, "post", return_value=good_response
            ) as post:
                result = self_commands.cloudflare_markdown_read("https://www.example.com/login")
        finally:
            if original_hosts is None:
                config.pop("hard_page_hosts", None)
            else:
                config["hard_page_hosts"] = original_hosts

        post.assert_called_once()
        self.assertIsNone(post.call_args.kwargs["params"])
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["result"][0]["engine"], "chromium")

    def test_cloudflare_read_hard_page_hosts_ignore_port(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"
        config = self_commands.MANAGER.MANAGER.config.setdefault("read", {})
        original_hosts = config.get("hard_page_hosts")
        config["hard_page_hosts"] = ["example.com"]
        good_response = mock.Mock()
        good_response.ok = True
        good_response.json.return_value = {"success": True, "result": "# Hard\n\nbody"}
        try:
            with mock.patch.object(
                self_commands.requests, "post", return_value=good_response
            ) as post:
                result = self_commands.cloudflare_markdown_read(
                    "https://www.example.com:443/login"
                )
        finally:
            if original_hosts is None:
                config.pop("hard_page_hosts", None)
            else:
                config["hard_page_hosts"] = original_hosts

        post.assert_called_once()
        self.assertIsNone(post.call_args.kwargs["params"])
        self.assertEqual(result["result"][0]["engine"], "chromium")

    def test_cloudflare_read_falls_back_after_challenge_extract(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"
        challenge_response = mock.Mock()
        challenge_response.ok = True
        challenge_response.json.return_value = {
            "success": True,
            "result": '---\ntitle: "Just a moment..."\n---',
        }
        good_response = mock.Mock()
        good_response.ok = True
        good_response.json.return_value = {
            "success": True,
            "result": "# Real Title\n\narticle body",
        }

        with mock.patch.object(
            self_commands.requests,
            "post",
            side_effect=[challenge_response, good_response],
        ) as post:
            result = self_commands.cloudflare_markdown_read(
                "https://gizmodo.com/some-article"
            )

        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].kwargs["params"], {"browser": "kitesurf"})
        self.assertIsNone(post.call_args_list[1].kwargs["params"])
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["result"][0]["engine"], "chromium")
        self.assertEqual(result["result"][0]["title"], "Real Title")

    def test_cloudflare_read_reports_all_engine_failures(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"

        def failing_post(*_args, **_kwargs):
            response = mock.Mock()
            response.ok = False
            response.status_code = 401
            response.text = "unauthorized"
            response.json.return_value = {
                "success": False,
                "errors": [{"message": "Authentication error"}],
            }
            return response

        with mock.patch.object(self_commands.requests, "post", side_effect=failing_post) as post:
            result = self_commands.cloudflare_markdown_read("https://example.com")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(result["status"], "error")
        self.assertIn("kitesurf: Authentication error", result["message"])
        self.assertIn("chromium: Authentication error", result["message"])

    def test_cloudflare_read_surfaces_api_errors(self):
        self_commands.settings.CLOUDFLARE_ACCOUNT_ID = "acct"
        self_commands.settings.CLOUDFLARE_API_TOKEN = "token"
        fake_response = mock.Mock()
        fake_response.ok = False
        fake_response.status_code = 403
        fake_response.text = "forbidden"
        fake_response.json.return_value = {
            "success": False,
            "errors": [{"message": "Authentication error"}],
        }

        with mock.patch.object(self_commands.requests, "post", return_value=fake_response):
            result = self_commands.cloudflare_markdown_read("https://example.com")

        self.assertEqual(result["status"], "error")
        self.assertIn("Authentication error", result["message"])


if __name__ == "__main__":
    unittest.main()
