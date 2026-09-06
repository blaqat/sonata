import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _load_emoji_utils():
    module_path = SRC_ROOT / "modules" / "emoji_utils.py"
    spec = importlib.util.spec_from_file_location("emoji_utils_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


emoji_utils = _load_emoji_utils()


class EmojiUtilsTests(unittest.TestCase):
    def test_get_emoji_id_static(self):
        emoji_id, animated, name = emoji_utils.get_emoji_id(":smile:123456>")
        self.assertEqual(emoji_id, "123456")
        self.assertFalse(animated)
        self.assertEqual(name, "smile")

    def test_get_emoji_id_animated(self):
        emoji_id, animated, name = emoji_utils.get_emoji_id("a:wave:999>")
        self.assertEqual(emoji_id, "999")
        self.assertTrue(animated)
        self.assertEqual(name, "wave")

    def test_get_emoji_id_missing(self):
        self.assertEqual(emoji_utils.get_emoji_id("not-an-emoji"), (None, False, None))

    def test_trans_emo_static(self):
        link, name, ext = emoji_utils.trans_emo(":cat:42>")
        self.assertEqual(link, "https://cdn.discordapp.com/emojis/42.png")
        self.assertEqual(name, "cat")
        self.assertEqual(ext, ".png")

    def test_trans_emo_animated(self):
        link, name, ext = emoji_utils.trans_emo("a:dance:7>")
        self.assertEqual(link, "https://cdn.discordapp.com/emojis/7.gif")
        self.assertEqual(name, "dance")
        self.assertEqual(ext, ".gif")

    def test_trans_emo_invalid_returns_none(self):
        self.assertIsNone(emoji_utils.trans_emo("nope"))

    def test_chunk_list(self):
        self.assertEqual(list(emoji_utils.chunk_list([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])

    def test_read_images_formats_sorted_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = tmp if tmp.endswith("/") else tmp + "/"
            pathlib.Path(directory, "zeta.png").write_bytes(b"z")
            pathlib.Path(directory, "alpha.gif").write_bytes(b"a")
            text = emoji_utils.read_images(directory)
            self.assertEqual(text, ":alpha: :zeta:\n")

    def test_download_emoji_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = tmp if tmp.endswith("/") else tmp + "/"
            fake_response = mock.Mock()
            fake_response.content = b"emoji-bytes"
            with mock.patch.object(emoji_utils.requests, "get", return_value=fake_response) as get:
                emoji_utils.download_emoji(
                    "https://cdn.discordapp.com/emojis/1.png",
                    "smile",
                    ".png",
                    directory=directory,
                )
            get.assert_called_once_with("https://cdn.discordapp.com/emojis/1.png")
            self.assertEqual(pathlib.Path(directory, "smile.png").read_bytes(), b"emoji-bytes")


if __name__ == "__main__":
    unittest.main()
