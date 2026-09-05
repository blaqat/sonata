import ast
import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_utils():
    """Extract the AI error classifier from ``utils.py`` without its imports."""
    source = (SRC_ROOT / "modules" / "utils.py").read_text()
    tree = ast.parse(source)
    body = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and any(
                getattr(target, "id", None) in ("AI_ERROR_MESSAGES", "TRANSIENT_AI_ERRORS")
                for target in node.targets
            )
        )
        or (
            isinstance(node, ast.FunctionDef)
            and node.name == "classify_ai_error"
        )
    ]
    namespace = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), "modules/utils.py", "exec"), namespace)

    class _Utils:
        pass

    _Utils.classify_ai_error = staticmethod(namespace["classify_ai_error"])
    _Utils.TRANSIENT_AI_ERRORS = namespace["TRANSIENT_AI_ERRORS"]
    return _Utils


def _load_chat_class():
    """Extract the nested ``Chat`` class from the chat plugin builder."""
    sleeps = []
    source = (SRC_ROOT / "modules" / "plugins" / "chat.py").read_text()
    tree = ast.parse(source)
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "chat"
    )
    chat_class = next(
        node
        for node in builder.body
        if isinstance(node, ast.ClassDef) and node.name == "Chat"
    )

    utils = _load_utils()
    namespace = {
        "_censor_for_provider": lambda message, _config=None: message,
        "sona": types.SimpleNamespace(
            config=types.SimpleNamespace(get=lambda *_args, **_kwargs: "Claude"),
            name="Sonata",
        ),
        "prompt_manager": types.SimpleNamespace(
            exists=lambda name: name == "History",
            get_instructions=lambda: None,
            prompts={
                "History": lambda history: f"H:{history}",
                "Message": lambda user_name, message, replying_to: f"M:{user_name}:{message}",
                "MessageAssistant": "assistant prompt",
            },
        ),
        "classify_ai_error": utils.classify_ai_error,
        "TRANSIENT_AI_ERRORS": set(utils.TRANSIENT_AI_ERRORS),
        "AI_REQUEST_RETRIES": 1,
        "AI_RETRY_BACKOFF": 0.5,
        "_NO_RESPONSE": object(),
        "time": types.SimpleNamespace(sleep=sleeps.append),
        "cprint": lambda *_args, **_kwargs: None,
        "get_trace": lambda: "TRACEBACK",
    }
    exec(
        compile(ast.Module(body=[chat_class], type_ignores=[]), "chat.py", "exec"),
        namespace,
    )
    return namespace["Chat"], namespace, sleeps


class _RateLimitError(Exception):
    pass


class _APITimeoutError(Exception):
    pass


class ClassifyAIErrorTests(unittest.TestCase):
    def setUp(self):
        self.classify = _load_utils().classify_ai_error

    def test_rate_limit_by_status_code_and_quota(self):
        self.assertEqual(self.classify(ValueError("429 Too Many Requests"))[0], "rate_limit")
        self.assertEqual(
            self.classify(ValueError("429 Resource has been exhausted (e.g. check quota)."))[0],
            "rate_limit",
        )

    def test_sdk_exception_names_are_matched(self):
        self.assertEqual(self.classify(_RateLimitError("slow down"))[0], "rate_limit")
        self.assertEqual(self.classify(_APITimeoutError("request timed out"))[0], "timeout")

    def test_auth_failures(self):
        category, message = self.classify(ValueError("400 API key not valid."))
        self.assertEqual(category, "auth")
        self.assertNotIn("API key not valid", message)

    def test_safety_blocks(self):
        category, message = self.classify(
            ValueError("The Candidate is blocked: finish_reason SAFETY")
        )
        self.assertEqual(category, "blocked")
        self.assertNotIn("SAFETY", message)

    def test_server_errors(self):
        self.assertEqual(self.classify(RuntimeError("500 Internal Server Error"))[0], "server_error")

    def test_connection_error_with_http_5xx_is_server_error(self):
        self.assertEqual(
            self.classify(ConnectionError("503 Service Unavailable"))[0],
            "server_error",
        )

    def test_connection_error_without_http_status_is_timeout(self):
        self.assertEqual(
            self.classify(ConnectionError("[Errno 54] Connection reset by peer"))[0],
            "timeout",
        )

    def test_gemini_404_model_not_found(self):
        category, message = self.classify(
            ValueError(
                "404 models/definitely-not-a-real-model is not found for API "
                "version v1beta, or is not supported for generateContent."
            )
        )
        self.assertEqual(category, "not_found")
        self.assertNotIn("definitely-not-a-real-model", message)

    def test_openai_model_does_not_exist(self):
        self.assertEqual(
            self.classify(
                ValueError(
                    "The model `gpt-who-knows` does not exist or you do not have access to it."
                )
            )[0],
            "not_found",
        )

    def test_anthropic_not_found_error_type(self):
        self.assertEqual(
            self.classify(ValueError("not_found_error: model not found"))[0], "not_found"
        )

    def test_bad_request_invalid_parameter(self):
        self.assertEqual(
            self.classify(
                ValueError(
                    "Error code: 400 - {'error': {'message': \"Invalid parameter: "
                    "'model'\", 'type': 'invalid_request_error'}}"
                )
            )[0],
            "bad_request",
        )
        self.assertEqual(
            self.classify(ValueError("400 Bad Request"))[0], "bad_request"
        )

    def test_unknown_errors_fall_back_to_internal(self):
        self.assertEqual(self.classify(ValueError("boom"))[0], "internal")


class ChatRequestErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.Chat, self.namespace, self.sleeps = _load_chat_class()
        self.chat = self.Chat()
        self.saved = []
        self.chat.get_history = lambda *_args, **_kwargs: []
        self.chat.send = lambda *args: self.saved.append(args)

    def _run_request(self, do_results, **kwargs):
        calls = []

        def do(*args, **_kwargs):
            calls.append(1)
            result = do_results[min(len(calls), len(do_results)) - 1]
            if isinstance(result, Exception):
                raise result
            return result

        sona = types.SimpleNamespace(do=do)
        self.namespace["sona"] = types.SimpleNamespace(
            do=do,
            get=lambda key, *args, **kwargs: {"config": {}}[key],
            config=types.SimpleNamespace(get=lambda *_args, **_kwargs: {}),
            name="Sonata",
        )
        # Rebind closure defaults against the fresh stub (default args are
        # evaluated at class creation, so only bodies need it here).
        request = self.Chat.request.__get__(self.chat)
        result = request("chn", "hi", "alice", save=True, AI="Claude", **kwargs)
        return result, calls

    def test_provider_error_returns_safe_message_without_saving(self):
        result, calls = self._run_request([ValueError("400 API key not valid.")])
        self.assertEqual(result, "My AI credentials were rejected — the API keys need checking.")
        self.assertEqual(calls, [1])
        self.assertEqual(self.saved, [])

    def test_transient_failure_is_retried_once_then_succeeds(self):
        result, calls = self._run_request(
            [_RateLimitError("429 slow down"), "ok"]
        )
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.sleeps, [0.5])
        self.assertEqual(len(self.saved), 1)

    def test_persistent_transient_failure_returns_safe_message_after_retry(self):
        result, calls = self._run_request(
            [_RateLimitError("429"), _RateLimitError("429")]
        )
        self.assertEqual(result, "I'm rate limited right now — give me a minute and ask again.")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.sleeps), 1)
        self.assertEqual(self.saved, [])

    def test_non_transient_failure_does_not_retry(self):
        result, calls = self._run_request([ValueError("boom")])
        self.assertEqual(result, "Something went wrong while I was thinking about that.")
        self.assertEqual(calls, [1])
        self.assertEqual(self.sleeps, [])

    def test_raise_on_error_opt_out_rethrows(self):
        with self.assertRaises(ValueError):
            self._run_request([ValueError("400 API key not valid.")], raise_on_error=True)


class AIQuestionConciseErrorTests(unittest.IsolatedAsyncioTestCase):
    def _load_ai_question(self):
        from modules import image_delivery

        source = (SRC_ROOT / "index.py").read_text()
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "ai_question"
        )
        namespace = {
            "RESPONSE_FAILURES": {},
            "MAX_FAILURES": 3,
            "image_delivery": image_delivery,
        }
        exec(
            compile(ast.Module(body=[function], type_ignores=[]), "src/index.py", "exec"),
            namespace,
        )
        return namespace

    async def test_failure_replies_concise_message_without_traceback(self):
        namespace = self._load_ai_question()
        replies = []
        channel = types.SimpleNamespace(id=7)

        class _RuntimeConfig:
            def set(self, **_kwargs):
                pass

            def get(self, _key, default=None):
                return default

        class _RuntimeChat:
            def request(self, *_args, **_kwargs):
                raise ValueError("400 API key not valid.")

            def send(self, *_args):
                pass

        sonata = types.SimpleNamespace(
            config=_RuntimeConfig(),
            chat=_RuntimeChat(),
            name="Sonata",
            get=lambda *_args, **_kwargs: None,
        )
        ctx = types.SimpleNamespace(typing=lambda: _Typing(), message=object())

        namespace.update(
            {
                "Sonata": sonata,
                "asyncio": __import__("asyncio"),
                "get_channel": lambda _ctx: _async(channel),
                "get_full_name": lambda _ctx: "alice",
                "get_chain": lambda _message: None,
                "ctx_reply": lambda _ctx, text: _async(replies.append(text)),
                "classify_ai_error": _load_utils().classify_ai_error,
                "cprint": lambda *_args, **_kwargs: None,
                "print": lambda *_args, **_kwargs: None,
                "get_trace": lambda: "FULL TRACEBACK",
                "ordinal": lambda value: f"{value}th",
                "settings": types.SimpleNamespace(GOD=1),
                "restart": lambda: None,
            }
        )
        ai_question = namespace["ai_question"]

        await ai_question(ctx, "hello", ai="Claude", short="c")

        self.assertEqual(len(replies), 1)
        reply = replies[0]
        self.assertIn("messed up (1th time)", reply)
        self.assertIn("API keys need checking", reply)
        self.assertNotIn("```py", reply)
        self.assertNotIn("FULL TRACEBACK", reply)
        self.assertEqual(namespace["RESPONSE_FAILURES"][7], 1)

    async def test_max_failures_triggers_restart(self):
        namespace = self._load_ai_question()
        replies = []
        restarted = []
        channel = types.SimpleNamespace(id=9)

        class _RuntimeConfig:
            def set(self, **_kwargs):
                pass

            def get(self, _key, default=None):
                return default

        class _RuntimeChat:
            def request(self, *_args, **_kwargs):
                raise ValueError("boom")

            def send(self, *_args):
                pass

        sonata = types.SimpleNamespace(
            config=_RuntimeConfig(),
            chat=_RuntimeChat(),
            name="Sonata",
            get=lambda *_args, **_kwargs: None,
        )
        ctx = types.SimpleNamespace(typing=lambda: _Typing(), message=object())

        namespace.update(
            {
                "Sonata": sonata,
                "asyncio": __import__("asyncio"),
                "get_channel": lambda _ctx: _async(channel),
                "get_full_name": lambda _ctx: "alice",
                "get_chain": lambda _message: None,
                "ctx_reply": lambda _ctx, text: _async(replies.append(text)),
                "classify_ai_error": _load_utils().classify_ai_error,
                "cprint": lambda *_args, **_kwargs: None,
                "print": lambda *_args, **_kwargs: None,
                "get_trace": lambda: "FULL TRACEBACK",
                "ordinal": lambda value: f"{value}th",
                "settings": types.SimpleNamespace(GOD=1),
                "restart": lambda: restarted.append(True),
            }
        )
        ai_question = namespace["ai_question"]

        for _ in range(3):
            await ai_question(ctx, "hello", ai="Claude", short="c")

        self.assertEqual(namespace["RESPONSE_FAILURES"][9], 3)
        self.assertEqual(restarted, [True])


class _Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def _async(value):
    async def _inner():
        return value

    return _inner()


if __name__ == "__main__":
    unittest.main()
