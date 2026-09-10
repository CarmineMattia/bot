from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from spike import voice


def _write_silent_wav(path: Path, *, seconds: float = 0.2, rate: int = 16000) -> None:
    nframes = int(rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * nframes)


class VoiceSpeakTests(unittest.TestCase):
    def test_speak_invokes_espeak(self) -> None:
        with patch("spike.voice.shutil.which", return_value="/usr/bin/espeak-ng"), patch(
            "spike.voice.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            voice.speak("hello bot")
        run.assert_called_once()
        args = run.call_args[0][0]
        self.assertEqual(args[0], "/usr/bin/espeak-ng")
        self.assertIn("hello bot", args)

    def test_speak_disabled_by_env(self) -> None:
        with patch.dict("os.environ", {"BOT_SPEAK": "0"}), patch(
            "spike.voice.subprocess.run"
        ) as run:
            voice.speak("should not speak")
        run.assert_not_called()

    def test_speak_missing_espeak(self) -> None:
        with patch("spike.voice.shutil.which", return_value=None):
            with self.assertRaises(voice.VoiceError):
                voice.speak("x")


class VoiceSttTests(unittest.TestCase):
    def test_transcribe_fails_closed_without_whisper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.wav"
            _write_silent_wav(path)
            with patch("spike.voice.shutil.which", return_value=None), patch.dict(
                "sys.modules", {"whisper": None}
            ):
                # force import failure path
                with patch(
                    "spike.voice._transcribe_whisper_cli",
                    side_effect=voice.VoiceError("missing"),
                ), patch(
                    "spike.voice._transcribe_whisper_py",
                    side_effect=voice.VoiceError("missing"),
                ):
                    with self.assertRaises(voice.VoiceError) as ctx:
                        voice.transcribe(path)
        self.assertIn("STT unavailable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
