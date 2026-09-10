"""Voice edge for the same turn cycle (docs/turn-cycle.md).

Push-to-talk first: record → STT → conductor text → optional TTS of reply.
Full-duplex / VAD are out of v1.

STT: uses `whisper` CLI or Python `whisper` if installed; otherwise fails closed
with an install hint. TTS: `espeak-ng` (present on this Fedora host).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path


class VoiceError(Exception):
    pass


def speak(text: str, *, voice: str | None = None) -> None:
    """Speak text with espeak-ng. No-op on empty text."""
    text = (text or "").strip()
    if not text:
        return
    if os.environ.get("BOT_SPEAK", "1").lower() in {"0", "false", "no"}:
        return
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise VoiceError("espeak-ng not installed (dnf install espeak-ng)")
    voice = voice or os.environ.get("BOT_TTS_VOICE", "en")
    # Cap runaway replies
    spoken = text[:800]
    r = subprocess.run(
        [exe, "-v", voice, "--", spoken],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise VoiceError((r.stderr or r.stdout or f"espeak exit {r.returncode}").strip())


def record_wav(path: Path, *, seconds: float = 4.0, rate: int = 16000) -> Path:
    """Record mono WAV from the default mic via arecord."""
    if seconds <= 0:
        raise VoiceError("record seconds must be > 0")
    exe = shutil.which("arecord")
    if not exe:
        raise VoiceError("arecord not installed (alsa-utils)")
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # S16_LE mono — whisper-friendly
    cmd = [
        exe,
        "-f",
        "S16_LE",
        "-c",
        "1",
        "-r",
        str(rate),
        "-d",
        str(max(1, int(round(seconds)))),
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 10)
    if r.returncode != 0 or not path.exists() or path.stat().st_size < 44:
        raise VoiceError(
            (r.stderr or r.stdout or "arecord failed").strip()
            or f"no audio written to {path}"
        )
    return path


def _transcribe_whisper_cli(path: Path) -> str:
    exe = shutil.which("whisper")
    if not exe:
        raise VoiceError("missing")
    out_dir = path.parent
    r = subprocess.run(
        [
            exe,
            str(path),
            "--model",
            os.environ.get("BOT_WHISPER_MODEL", "base"),
            "--language",
            os.environ.get("BOT_STT_LANG", "en"),
            "--output_format",
            "txt",
            "--output_dir",
            str(out_dir),
            "--fp16",
            "False",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    txt = path.with_suffix(".txt")
    if r.returncode != 0 and not txt.exists():
        raise VoiceError((r.stderr or r.stdout or "whisper CLI failed").strip())
    return txt.read_text(encoding="utf-8", errors="replace").strip()


def _transcribe_whisper_py(path: Path) -> str:
    try:
        import whisper  # type: ignore
    except ImportError as e:
        raise VoiceError("missing") from e
    model_name = os.environ.get("BOT_WHISPER_MODEL", "base")
    model = whisper.load_model(model_name)
    result = model.transcribe(
        str(path),
        language=os.environ.get("BOT_STT_LANG") or None,
        fp16=False,
    )
    return str(result.get("text") or "").strip()


def transcribe(path: Path) -> str:
    """Speech-to-text a WAV/AIFF/MP3 path. Prefers whisper CLI, then Python package."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise VoiceError(f"audio file not found: {path}")
    errors: list[str] = []
    for fn in (_transcribe_whisper_cli, _transcribe_whisper_py):
        try:
            text = fn(path)
            if text:
                return text
            errors.append(f"{fn.__name__}: empty transcript")
        except VoiceError as e:
            if str(e) != "missing":
                errors.append(str(e))
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")
    raise VoiceError(
        "STT unavailable. Install openai-whisper (`pip install openai-whisper`) "
        "or the `whisper` CLI. Details: " + "; ".join(errors[:3])
    )


def listen(
    *,
    seconds: float = 4.0,
    wav_path: Path | None = None,
) -> tuple[str, Path]:
    """Record (or use wav_path) and return (transcript, wav_used)."""
    if wav_path is not None:
        path = wav_path.expanduser().resolve()
        return transcribe(path), path
    with tempfile.TemporaryDirectory(prefix="bot-voice-") as tmp:
        path = Path(tmp) / "utterance.wav"
        record_wav(path, seconds=seconds)
        # copy out before tmp cleanup
        fd, keep_name = tempfile.mkstemp(prefix="bot-utterance-", suffix=".wav")
        os.close(fd)
        keep = Path(keep_name)
        try:
            keep.write_bytes(path.read_bytes())
            text = transcribe(keep)
        except BaseException:
            keep.unlink(missing_ok=True)
            raise
        return text, keep


def wav_duration_s(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)
