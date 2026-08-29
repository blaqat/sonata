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


class ImageDeliveryBufferTests(unittest.TestCase):
    def setUp(self):
        _src_root()
        from modules import image_delivery

        self.delivery = image_delivery
        self.addCleanup(self.delivery.clear, "chan")
        self.addCleanup(self.delivery.clear, "other")

    def test_stash_without_bound_channel_is_rejected(self):
        self.assertFalse(self.delivery.stash(b"bytes", "a.png"))

    def test_bound_channel_receives_stashed_image(self):
        with self.delivery.current_channel("chan"):
            self.assertTrue(self.delivery.stash(b"bytes", "a.png", url="https://x/a"))

        images = self.delivery.take("chan")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, b"bytes")
        self.assertEqual(images[0].filename, "a.png")
        self.assertEqual(images[0].url, "https://x/a")

    def test_take_drains_the_queue(self):
        with self.delivery.current_channel("chan"):
            self.delivery.stash(b"bytes", "a.png")

        self.assertEqual(len(self.delivery.take("chan")), 1)
        self.assertEqual(self.delivery.take("chan"), [])

    def test_empty_bytes_are_not_queued(self):
        with self.delivery.current_channel("chan"):
            self.assertFalse(self.delivery.stash(b"", "a.png"))
        self.assertEqual(self.delivery.take("chan"), [])

    def test_entering_a_turn_drops_images_left_by_a_failed_turn(self):
        with self.delivery.current_channel("chan"):
            self.delivery.stash(b"stale", "stale.png")

        with self.delivery.current_channel("chan"):
            self.delivery.stash(b"fresh", "fresh.png")

        images = self.delivery.take("chan")
        self.assertEqual([image.data for image in images], [b"fresh"])

    def test_queue_is_capped_per_channel(self):
        cap = self.delivery.MAX_PENDING_PER_CHANNEL
        with self.delivery.current_channel("chan"):
            accepted = [
                self.delivery.stash(b"bytes", f"{i}.png") for i in range(cap + 2)
            ]

        self.assertEqual(accepted, [True] * cap + [False, False])
        self.assertEqual(len(self.delivery.take("chan")), cap)

    def test_channels_stay_isolated_across_threads(self):
        def run(channel_id, payload):
            with self.delivery.current_channel(channel_id):
                self.delivery.stash(payload, "a.png")

        threads = [
            threading.Thread(target=run, args=("chan", b"one")),
            threading.Thread(target=run, args=("other", b"two")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual([i.data for i in self.delivery.take("chan")], [b"one"])
        self.assertEqual([i.data for i in self.delivery.take("other")], [b"two"])

    def test_nested_binding_restores_the_outer_channel(self):
        with self.delivery.current_channel("chan"):
            with self.delivery.current_channel("other"):
                self.delivery.stash(b"inner", "a.png")
            self.delivery.stash(b"outer", "b.png")

        self.assertEqual([i.data for i in self.delivery.take("chan")], [b"outer"])
        self.assertEqual([i.data for i in self.delivery.take("other")], [b"inner"])


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

    def test_unrelated_links_survive(self):
        text = "see [docs](https://example.com/a.png) and https://files.catbox.moe/a.png"
        result = self.delivery.strip_urls(
            text, [self._image("https://files.catbox.moe/a.png")]
        )
        self.assertEqual(result, "see [docs](https://example.com/a.png) and")

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
        self.addCleanup(self.delivery.clear, "chan")

    def test_returns_hosted_url_and_queues_bytes_for_attachment(self):
        with self.delivery.current_channel("chan"):
            result = self.mod._deliver_image(b"raw", "image/jpeg")

        self.assertEqual(result, "https://files.catbox.moe/a.png")
        images = self.delivery.take("chan")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, b"raw")
        self.assertEqual(images[0].filename, "generated.jpg")
        self.assertEqual(images[0].url, "https://files.catbox.moe/a.png")

    def test_upload_failure_still_attaches_when_a_channel_is_bound(self):
        self.mod.upload_to_catbox.side_effect = self.mod.CatboxUploadError("nope")

        with self.delivery.current_channel("chan"):
            result = self.mod._deliver_image(b"raw", "image/png")

        self.assertEqual(result, self.delivery.ATTACHED_NOTICE)
        images = self.delivery.take("chan")
        self.assertEqual([image.data for image in images], [b"raw"])
        self.assertIsNone(images[0].url)

    def test_upload_failure_without_a_channel_still_raises(self):
        self.mod.upload_to_catbox.side_effect = self.mod.CatboxUploadError("nope")

        with self.assertRaises(self.mod.CatboxUploadError):
            self.mod._deliver_image(b"raw", "image/png")

    def test_unknown_mime_type_falls_back_to_png_filename(self):
        with self.delivery.current_channel("chan"):
            self.mod._deliver_image(b"raw", None)

        self.assertEqual(self.delivery.take("chan")[0].filename, "generated.png")


if __name__ == "__main__":
    unittest.main()
