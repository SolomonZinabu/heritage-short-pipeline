"""Audio and image helpers that need no model.

Reading a WAV's length, the placeholder score for the radio cut, and the mock
assets a dry run uses in place of generated ones.
"""
from __future__ import annotations

import io
import math
import wave
from pathlib import Path

TTS_SAMPLE_RATE = 24000  # Gemini TTS returns 24 kHz, mono, 16-bit


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def as_wav(audio: bytes) -> bytes:
    """A complete WAV file. Audio that arrives as bare PCM is given a header."""
    if audio[:4] == b"RIFF":
        return audio
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(TTS_SAMPLE_RATE)
        out.writeframes(audio)
    return buffer.getvalue()


def write_bytes(path: Path, data: bytes) -> Path:
    """Write a file whole. A half-written output can never be mistaken for a finished one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    part.replace(path)
    return path


def _write_mono_wav(path: Path, sample_rate: int, samples) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for value in samples:
        frames += int(max(-1.0, min(1.0, value)) * 32767).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(bytes(frames))
    return path


def placeholder_music(path: Path, seconds: float, sample_rate: int = 24000) -> Path:
    """A soft pad that swells and settles: the temp track for the radio cut.

    It costs nothing to make and is not the film's score.
    """
    chord = (146.83, 220.0, 293.66, 369.99)  # D, A, D, F sharp: an open, warm sonority

    def samples():
        for n in range(int(seconds * sample_rate)):
            t = n / sample_rate
            swell = 0.5 - 0.5 * math.cos(2 * math.pi * t / 13.0)
            breath = 0.5 + 0.5 * math.sin(2 * math.pi * 0.7 * t + math.sin(t))
            tone = sum(math.sin(2 * math.pi * frequency * t) for frequency in chord) / len(chord)
            yield 0.2 * (0.3 + 0.7 * swell) * (0.7 + 0.3 * breath) * tone

    return _write_mono_wav(path, sample_rate, samples())


def estimated_seconds(text: str) -> float:
    """A rough guess at speaking time, used by mock runs and the timing table."""
    return 0.6 + 0.38 * len(text.split())


def mock_narration(path: Path, seconds: float) -> Path:
    """A quiet, speech-like tone of the right length, for a dry run."""
    sample_rate = TTS_SAMPLE_RATE

    def samples():
        for n in range(int(seconds * sample_rate)):
            t = n / sample_rate
            fade = max(0.0, min(1.0, t / 0.05, (seconds - t) / 0.2))
            syllables = 0.5 + 0.5 * math.sin(2 * math.pi * 3.2 * t)
            yield 0.4 * fade * syllables * math.sin(2 * math.pi * 196 * t)

    return _write_mono_wav(path, sample_rate, samples())


def mock_image(path: Path, label: str, width: int, height: int, shade: int) -> Path:
    """A plain coloured frame with a centred disc, so a dry run can show cropping and movement."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), (shade, 60, 140 - shade // 3))
    draw = ImageDraw.Draw(image)
    radius = min(width, height) // 4
    centre = (width // 2, height // 2)
    draw.ellipse(
        (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius),
        outline=(255, 255, 255),
        width=max(2, width // 128),
    )
    draw.text((width // 16, height // 16), label, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
