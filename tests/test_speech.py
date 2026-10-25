import unittest
from unittest.mock import Mock


class StreamingDecoderTests(unittest.TestCase):
    def decoder(self):
        from wayland_voice_control import speech
        self.assertTrue(hasattr(speech, "StreamingDecoder"))
        recognizer = Mock()
        return speech.StreamingDecoder(recognizer), recognizer

    def test_partial_replaces_previous_partial_and_final_segments_are_not_duplicated(self):
        decoder, recognizer = self.decoder()
        recognizer.AcceptWaveform.side_effect = [False, False, True, False]
        recognizer.PartialResult.side_effect = [
            '{"partial":"hel"}', '{"partial":"hello"}', '{"partial":"wor"}'
        ]
        recognizer.Result.return_value = '{"text":"hello"}'
        recognizer.FinalResult.return_value = '{"text":"world"}'
        self.assertEqual([decoder.accept(b"\0\0") for _ in range(4)],
                         ["hel", "hello", "hello", "hello wor"])
        self.assertEqual(decoder.finish(), "hello world")
        self.assertEqual(decoder.draft, "")

    def test_malformed_and_oversize_payloads_have_fixed_private_errors(self):
        from wayland_voice_control import speech
        self.assertTrue(hasattr(speech, "StreamingDecoder"))
        for payload in ('secret', '[]', '{"partial":22}', '{"partial":"' + 'x'*4001 + '"}'):
            with self.subTest(payload=payload[:20]):
                decoder, recognizer = self.decoder()
                recognizer.AcceptWaveform.return_value = False
                recognizer.PartialResult.return_value = payload
                with self.assertRaises(speech.DecoderError) as caught:
                    decoder.accept(b"\0\0")
                self.assertNotIn("secret", str(caught.exception))
                self.assertNotIn("xxxx", str(caught.exception))

    def test_accumulated_segments_and_partial_share_4000_character_bound(self):
        from wayland_voice_control import speech
        self.assertTrue(hasattr(speech, "StreamingDecoder"))
        decoder, recognizer = self.decoder()
        recognizer.AcceptWaveform.side_effect = [True, False]
        recognizer.Result.return_value = '{"text":"' + 'a'*3998 + '"}'
        recognizer.PartialResult.return_value = '{"partial":"bb"}'
        decoder.accept(b"\0\0")
        with self.assertRaises(speech.DecoderError):
            decoder.accept(b"\0\0")
