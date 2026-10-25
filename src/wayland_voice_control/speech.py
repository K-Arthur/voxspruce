"""Shared, bounded Vosk streaming decoding; drafts never become final text."""

import json


class DecoderError(RuntimeError):
    """Fixed application-authored recognition error, without dependency content."""


class StreamingDecoder:
    def __init__(self, recognizer):
        self.recognizer = recognizer
        self._finalized = ""
        self.draft = ""

    @staticmethod
    def _text(raw, key):
        # Bound dependency payload parsing as well as the resulting transcript.
        if not isinstance(raw, str) or len(raw) > 65536:
            raise DecoderError("The recognizer returned an invalid payload.")
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            raise DecoderError("The recognizer returned an invalid payload.") from None
        if not isinstance(value, dict) or not isinstance(value.get(key, ""), str):
            raise DecoderError("The recognizer returned invalid text.")
        return value.get(key, "").strip()

    @staticmethod
    def _join(first, second):
        value = " ".join(part for part in (first, second) if part)
        if len(value) > 4000:
            raise DecoderError("Recognized text exceeded the 4000 character limit.")
        return value

    def accept(self, chunk):
        if not isinstance(chunk, bytes) or not 0 < len(chunk) <= 4096:
            raise DecoderError("The microphone returned an invalid audio block.")
        if self.recognizer.AcceptWaveform(chunk):
            self._finalized = self._join(
                self._finalized, self._text(self.recognizer.Result(), "text")
            )
            self.draft = self._finalized
        else:
            self.draft = self._join(
                self._finalized, self._text(self.recognizer.PartialResult(), "partial")
            )
        return self.draft

    def finish(self):
        try:
            return self._join(
                self._finalized, self._text(self.recognizer.FinalResult(), "text")
            )
        finally:
            self.clear()

    def clear(self):
        self._finalized = self.draft = ""
