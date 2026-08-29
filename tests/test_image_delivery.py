import pathlib
import sys
import threading
import types
import unittest
from unittest import mock


def _src_root():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    return src_root


def _load_deliver_image(image_delivery):
    """Load _deliver_image without pulling index.py's full import graph."""
    module_path = _src_root() / "index.py"
    source = module_path.read_text(encoding="utf-8")

    start = source.index("def _deliver_image")
    end = source.index("\n\nnest_asyncio.apply()")

    class CatboxUploadError(Exception):
        pass

    module = types.ModuleType("deliver_image_under_test")
    module.image_delivery = image_delivery
    module.CatboxUploadError = CatboxUploadError
    module.upload_to_catbox = mock.Mock(return_value="https://files.catbox.moe/a.png")
    exec(compile(source[start:end], str(module_path), "exec"), module.__dict__)  # noqa: S102
    return module


class DeliveryTurnTests(unittest.TestCase):
    def setUp(self):
        _src_root()
        from modules import image_delivery

        self.delivery = image_delivery

    def test_stash_without_an_open_turn_is_rejected(self):
        self.assertFalse(self.delivery.stash(b"bytes", "a.png"))

    def test_open_turn_receives_stashed_image(self):
        with self.delivery.delivery_turn() as turn:
            self.assertTrue(self.delivery.stash(b"bytes", "a.png", url="https://x/a"))
            images = turn.take()

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, b"bytes")
        self.assertEqual(images[0].filename, "a.png")
        self.assertEqual(images[0].url, "https://x/a")

    def test_take_drains_the_turn(self):
        with self.delivery.delivery_turn() as turn:
            self.delivery.stash(b"bytes", "a.png")
            self.assertEqual(len(turn.take()), 1)
            self.assertEqual(turn.take(), [])

    def test_empty_bytes_are_not_queued(self):
        with self.delivery.delivery_turn() as turn:
            self.assertFalse(self.delivery.stash(b"", "a.png"))
            self.assertEqual(turn.take(), [])

    def test_undrained_images_do_not_survive_the_turn(self):
        with self.delivery.delivery_turn() as turn:
            self.delivery.stash(b"orphan", "a.png")

        self.assertEqual(turn.take(), [])

    def test_turn_is_capped(self):
        cap = self.delivery.MAX_IMAGES_PER_TURN
        with self.delivery.delivery_turn() as turn:
            accepted = [
                self.delivery.stash(b"bytes", f"{i}.png") for i in range(cap + 2)
            ]
            self.assertEqual(len(turn.take()), cap)

        self.assertEqual(accepted, [True] * cap + [False, False])

    def test_concurrent_turns_do_not_share_images(self):
        """Two replies in one channel must each attach only their own image."""
        started = threading.Barrier(2)
        results = {}

        def run(name, payload):
            with self.delivery.delivery_turn() as turn:
                self.delivery.stash(payload, "a.png")
                started.wait(timeout=5)
                results[name] = [image.data for image in turn.take()]

        threads = [
            threading.Thread(target=run, args=("first", b"one")),
            threading.Thread(target=run, args=("second", b"two")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(results, {"first": [b"one"], "second": [b"two"]})

    def test_nested_turn_restores_the_outer_one(self):
        with self.delivery.delivery_turn() as outer:
            with self.delivery.delivery_turn() as inner:
                self.delivery.stash(b"inner", "a.png")
                inner_images = inner.take()
            self.delivery.stash(b"outer", "b.png")
            outer_images = outer.take()

        self.assertEqual([i.data for i in inner_images], [b"inner"])
        self.assertEqual([i.data for i in outer_images], [b"outer"])


class ExtensionForTests(unittest.TestCase):
    def setUp(self):
        _src_root()
        from modules import image_delivery

        self.delivery = image_delivery

    def test_known_mime_types_map_to_extensions(self):
        self.assertEqual(self.delivery.extension_for("image/png"), "png")
        self.assertEqual(self.delivery.extension_for("image/jpeg"), "jpg")
        self.assertEqual(self.delivery.extension_for("IMAGE/WEBP"), "webp")

    def test_unknown_and_missing_mime_types_default_to_png(self):
        self.assertEqual(self.delivery.extension_for(None), "png")
        self.assertEqual(self.delivery.extension_for("application/octet-stream"), "png")


class StripUrlsTests(unittest.TestCase):
    def setUp(self):
        _src_root()
        from modules import image_delivery

        self.delivery = image_delivery

    def _image(self, url):
        return self.delivery.GeneratedImage(b"bytes", "a.png", url)

    def test_markdown_link_collapses_to_its_title(self):
        text = "here you go [a cat](https://files.catbox.moe/a.png) enjoy"
        result = self.delivery.strip_urls(
            text, [self._image("https://files.catbox.moe/a.png")]
        )
        self.assertEqual(result, "here you go a cat enjoy")

    def test_bare_url_is_removed(self):
        text = "done https://files.catbox.moe/a.png"
        result = self.delivery.strip_urls(
            text, [self._image("https://files.catbox.moe/a.png")]
        )
        self.assertEqual(result, "done")

    def test_trailing_sentence_punctuation_is_kept(self):
        text = "done https://files.catbox.moe/a.png. next"
        result = self.delivery.strip_urls(
            text, [self._image("https://files.catbox.moe/a.png")]
        )
        self.assertEqual(result, "done . next")

    def test_unrelated_links_survive(self):
        text = "see [docs](https://example.com/a.png) and https://files.catbox.moe/a.png"
        result = self.delivery.strip_urls(
            text, [self._image("https://files.catbox.moe/a.png")]
        )
        self.assertEqual(result, "see [docs](https://example.com/a.png) and")

    def test_longer_url_sharing_a_prefix_is_left_intact(self):
        generated = "https://files.catbox.moe/a.png"
        other = "https://files.catbox.moe/a.png?download=1"
        result = self.delivery.strip_urls(f"mirror {other}", [self._image(generated)])
        self.assertEqual(result, f"mirror {other}")

    def test_prefix_match_inside_a_markdown_link_is_left_intact(self):
        generated = "https://files.catbox.moe/a.png"
        other = "https://files.catbox.moe/a.png?download=1"
        text = f"mirror [dl]({other})"
        self.assertEqual(self.delivery.strip_urls(text, [self._image(generated)]), text)

    def test_regex_metacharacters_in_url_are_literal(self):
        url = "https://files.catbox.moe/a+b(1).png?x=1"
        result = self.delivery.strip_urls(f"pic {url} done", [self._image(url)])
        self.assertEqual(result, "pic done")

    def test_images_without_urls_leave_text_untouched(self):
        text = "no link here"
        self.assertEqual(
            self.delivery.strip_urls(text, [self._image(None)]),
            text,
        )

    def test_empty_text_is_passed_through(self):
        self.assertEqual(self.delivery.strip_urls("", [self._image("https://x/a")]), "")


class DeliverImageTests(unittest.TestCase):
    def setUp(self):
        _src_root()
        from modules import image_delivery

        self.delivery = image_delivery
        self.mod = _load_deliver_image(image_delivery)

    def test_returns_hosted_url_and_queues_bytes_for_attachment(self):
        with self.delivery.delivery_turn() as turn:
            result = self.mod._deliver_image(b"raw", "image/jpeg")
            images = turn.take()

        self.assertEqual(result, "https://files.catbox.moe/a.png")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, b"raw")
        self.assertEqual(images[0].filename, "generated.jpg")
        self.assertEqual(images[0].url, "https://files.catbox.moe/a.png")

    def test_upload_failure_still_attaches_inside_a_turn(self):
        self.mod.upload_to_catbox.side_effect = self.mod.CatboxUploadError("nope")

        with self.delivery.delivery_turn() as turn:
            result = self.mod._deliver_image(b"raw", "image/png")
            images = turn.take()

        self.assertEqual(result, self.delivery.ATTACHED_NOTICE)
        self.assertEqual([image.data for image in images], [b"raw"])
        self.assertIsNone(images[0].url)

    def test_upload_failure_outside_a_turn_still_raises(self):
        """Terminal and voice replies cannot attach, so they keep the old error."""
        self.mod.upload_to_catbox.side_effect = self.mod.CatboxUploadError("nope")

        with self.assertRaises(self.mod.CatboxUploadError):
            self.mod._deliver_image(b"raw", "image/png")

    def test_unknown_mime_type_falls_back_to_png_filename(self):
        with self.delivery.delivery_turn() as turn:
            self.mod._deliver_image(b"raw", None)
            images = turn.take()

        self.assertEqual(images[0].filename, "generated.png")


if __name__ == "__main__":
    unittest.main()
