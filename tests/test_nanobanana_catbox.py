import pathlib
import sys
import types
import unittest
from unittest import mock

import requests


def _load_catbox_helper():
    """Load upload_to_catbox without pulling the full utils import graph."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    module_path = src_root / "modules" / "utils.py"
    source = module_path.read_text(encoding="utf-8")

    start = source.index("_catbox_logger = logging.getLogger")
    end = source.index("\n\nclass Map:")

    snippet = source[start:end]

    module = types.ModuleType("catbox_helper_under_test")
    module.logging = __import__("logging")
    module.requests = requests
    module.time = types.SimpleNamespace(sleep=mock.Mock())
    exec(compile(snippet, str(module_path), "exec"), module.__dict__)  # noqa: S102
    return module


class NanoBananaCatboxUploadTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_catbox_helper()

    def _response(self, status_code=200, text=""):
        response = mock.Mock(spec=requests.Response)
        response.status_code = status_code
        response.text = text
        return response

    def test_success_returns_stripped_url_with_bounded_request(self):
        with mock.patch.object(
            self.mod.requests,
            "post",
            return_value=self._response(text="https://files.catbox.moe/abc.jpg\n"),
        ) as post:
            url = self.mod.upload_to_catbox(b"image-bytes")

        self.assertEqual(url, "https://files.catbox.moe/abc.jpg")
        post.assert_called_once()
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["timeout"], (10, 30))
        self.assertEqual(kwargs["headers"]["User-Agent"], self.mod._CATBOX_UA)
        self.assertEqual(kwargs["files"]["reqtype"], (None, "fileupload"))
        name, payload = kwargs["files"]["fileToUpload"]
        self.assertEqual(name, "image.jpg")
        self.assertEqual(payload, b"image-bytes")
        self.mod.time.sleep.assert_not_called()

    def test_retries_transient_failures_before_succeeding(self):
        responses = [
            self._response(status_code=502, text="<html>bad gateway</html>"),
            self._response(text="not a url"),
            self._response(text="https://files.catbox.moe/fixed.jpg"),
        ]
        with mock.patch.object(self.mod.requests, "post", side_effect=responses) as post:
            url = self.mod.upload_to_catbox(b"image-bytes")

        self.assertEqual(url, "https://files.catbox.moe/fixed.jpg")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in self.mod.time.sleep.call_args_list], [1, 2]
        )

    def test_exhausted_retries_raise_concise_error_and_log_detail(self):
        long_body = "<html>" + "x" * 5000 + "</html>"
        with (
            mock.patch.object(
                self.mod.requests,
                "post",
                return_value=self._response(status_code=403, text=long_body),
            ) as post,
            mock.patch.object(self.mod._catbox_logger, "warning") as warning,
            self.assertRaises(self.mod.CatboxUploadError) as ctx,
        ):
            self.mod.upload_to_catbox(b"image-bytes")

        self.assertEqual(post.call_count, 3)
        message = str(ctx.exception)
        self.assertIn("HTTP 403", message)
        self.assertIn("Failed to upload image to catbox", message)
        self.assertLess(len(message), 300)
        self.assertIn(long_body[:200], warning.call_args.args[-1])

    def test_network_errors_are_retried(self):
        with mock.patch.object(
            self.mod.requests,
            "post",
            side_effect=[
                requests.ConnectionError("reset by peer"),
                self._response(text="https://files.catbox.moe/back.jpg"),
            ],
        ) as post:
            url = self.mod.upload_to_catbox(b"image-bytes")

        self.assertEqual(url, "https://files.catbox.moe/back.jpg")
        self.assertEqual(post.call_count, 2)
        self.mod.time.sleep.assert_called_once_with(1)

    def test_all_network_errors_raise(self):
        with mock.patch.object(
            self.mod.requests,
            "post",
            side_effect=requests.Timeout("timed out"),
        ), self.assertRaises(self.mod.CatboxUploadError) as ctx:
            self.mod.upload_to_catbox(b"image-bytes", attempts=3)

        self.assertIn("request error", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
