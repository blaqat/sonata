import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from modules.activation_trace import (  # noqa: E402
    ActivationTrace,
    find_chat_wake_word,
    get_active_activation_trace,
    use_activation_trace,
)


class ActivationTraceTests(unittest.TestCase):
    def test_chat_wake_word_matches_bounded_sonata_alias(self):
        self.assertEqual(
            find_chat_wake_word("hey Sonata, roll a die", 123),
            "Sonata",
        )

    def test_chat_wake_word_matches_discord_mention(self):
        self.assertEqual(find_chat_wake_word("hey <@123> roll", 123), "<@123>")

    def test_literal_sonat_does_not_match_chat_aliases(self):
        self.assertIsNone(find_chat_wake_word("hey sonat, roll a die", 123))

    def test_trace_logs_each_stage_and_complete_path(self):
        messages = []
        trace = ActivationTrace(
            source="guild_chat", emit=messages.append, trace_id="abc123"
        )

        trace.stage("chat.wake_word.matched", matched_text="sonata")
        trace.stage("discord.command.invoke.completed")
        trace.finish("completed")

        self.assertEqual(
            messages[0],
            "[activation:abc123] 01 chat.wake_word.matched | "
            "matched_text='sonata'",
        )
        self.assertEqual(
            messages[1],
            "[activation:abc123] 02 discord.command.invoke.completed",
        )
        self.assertIn(
            "path=chat.wake_word.matched -> discord.command.invoke.completed",
            messages[2],
        )

    def test_active_trace_is_available_only_inside_context(self):
        trace = ActivationTrace(source="guild_chat", emit=lambda _: None)

        self.assertIsNone(get_active_activation_trace())
        with use_activation_trace(trace):
            self.assertIs(get_active_activation_trace(), trace)
        self.assertIsNone(get_active_activation_trace())


if __name__ == "__main__":
    unittest.main()
