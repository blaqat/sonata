import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from modules.activation_trace import (  # noqa: E402
    ActivationTrace,
    get_active_activation_trace,
    matches_voice_wake_word,
    use_activation_trace,
)


class ActivationTraceTests(unittest.TestCase):
    def test_voice_wake_word_matches_transcribed_sonata(self):
        self.assertTrue(matches_voice_wake_word("hey Sonata, roll a die"))

    def test_literal_sonat_does_not_match_without_whisper_normalizing_it(self):
        self.assertFalse(matches_voice_wake_word("hey sonat, roll a die"))

    def test_trace_logs_each_stage_and_complete_path(self):
        messages = []
        trace = ActivationTrace(source="voice", emit=messages.append, trace_id="abc123")

        trace.stage("whisper.transcript.received", transcript="sonata roll")
        trace.stage("wake_word.matched", wake_word="sonata")
        trace.finish("completed")

        self.assertEqual(
            messages[0],
            "[activation:abc123] 01 whisper.transcript.received | "
            "transcript='sonata roll'",
        )
        self.assertEqual(
            messages[1],
            "[activation:abc123] 02 wake_word.matched | wake_word='sonata'",
        )
        self.assertIn(
            "path=whisper.transcript.received -> wake_word.matched",
            messages[2],
        )

    def test_active_trace_is_available_only_inside_context(self):
        trace = ActivationTrace(source="voice", emit=lambda _: None)

        self.assertIsNone(get_active_activation_trace())
        with use_activation_trace(trace):
            self.assertIs(get_active_activation_trace(), trace)
        self.assertIsNone(get_active_activation_trace())


if __name__ == "__main__":
    unittest.main()
