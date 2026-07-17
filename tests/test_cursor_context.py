import pathlib
import sys
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.context import (
    build_run_prompt,
    collect_chain_attachments,
    compose_prompt_text,
    parse_message_reference,
    select_images,
)
from cursor_cloud.errors import ValidationError
from cursor_cloud.models import ImageInput, MAX_IMAGE_BYTES


class FakeAtt:
    def __init__(self, url, content_type="image/png", size=100, filename="a.png"):
        self.url = url
        self.content_type = content_type
        self.size = size
        self.filename = filename


class FakeMsg:
    def __init__(self, mid, author, content, attachments=None, reference=None):
        self.id = mid
        self.author = SimpleNamespace(name=author, display_name=author)
        self.content = content
        self.attachments = attachments or []
        self.reference = reference


class TestContext(unittest.TestCase):
    def test_parse_message_url_and_id(self):
        ch, mid = parse_message_reference(
            "https://discord.com/channels/1/2/3",
            current_guild_id=1,
            current_channel_id=2,
        )
        self.assertEqual((ch, mid), ("2", "3"))
        ch, mid = parse_message_reference(
            "99999", current_guild_id=1, current_channel_id=42
        )
        self.assertEqual((ch, mid), ("42", "99999"))

    def test_cross_guild_rejected(self):
        with self.assertRaises(ValidationError):
            parse_message_reference(
                "https://discord.com/channels/9/2/3",
                current_guild_id=1,
                current_channel_id=2,
            )

    def test_malformed_rejected(self):
        with self.assertRaises(ValidationError):
            parse_message_reference("not-a-ref", current_channel_id=1)

    def test_chronological_prompt_and_images(self):
        m1 = FakeMsg(1, "a", "first", [FakeAtt("https://cdn/a.png")])
        m2 = FakeMsg(2, "b", "", [FakeAtt("https://cdn/b.jpeg", "image/jpeg")])
        chain = collect_chain_attachments([m1, m2])
        built = build_run_prompt(
            "fix this",
            chain_messages=chain,
            direct_images=[
                ImageInput(mime_type="image/png", url="https://cdn/direct.png", size_bytes=10)
            ],
        )
        self.assertIn("fix this", built.text)
        self.assertIn("a: first", built.text)
        self.assertIn("[image attachment]", built.text)
        self.assertEqual(built.images[0].url, "https://cdn/direct.png")
        self.assertTrue(any(i.url == "https://cdn/b.jpeg" for i in built.images))

    def test_dedupe_and_cap(self):
        imgs = [
            ImageInput(mime_type="image/png", url=f"https://cdn/{i}.png", size_bytes=1)
            for i in range(6)
        ]
        # duplicate url
        imgs.append(ImageInput(mime_type="image/png", url="https://cdn/0.png", size_bytes=1))
        selected, skipped = select_images(direct=imgs, chain_attachments=[])
        self.assertEqual(len(selected), 5)
        self.assertTrue(any("cap" in s or "duplicate" in s for s in skipped))

    def test_mime_and_size(self):
        selected, skipped = select_images(
            direct=[
                ImageInput(mime_type="image/tiff", url="https://cdn/x.tiff"),
                ImageInput(
                    mime_type="image/png",
                    url="https://cdn/big.png",
                    size_bytes=MAX_IMAGE_BYTES + 1,
                ),
            ],
            chain_attachments=[],
        )
        self.assertEqual(selected, [])
        self.assertEqual(len(skipped), 2)

    def test_compose_missing_refs(self):
        text = compose_prompt_text(
            "go",
            [("u", "hi")],
            missing_refs=["Message 1 missing"],
        )
        self.assertIn("Message 1 missing", text)


if __name__ == "__main__":
    unittest.main()
