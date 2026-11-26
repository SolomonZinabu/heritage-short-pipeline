"""Look at generated sound before anyone listens to it.

A narration line can come back silent, clipped, or in a voice that is not what
was asked for. These measurements cannot judge acting. They answer the plain
questions: is there sound, at what level, how much silence at each end, and is
the voice high or low. They are found with plain arithmetic, so the check needs
nothing installed beyond FFmpeg.
"""
from __future__ import annotations

import array
import math
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import ffmpeg
from .config import OUTPUTS
from .util import say

RATE = 8000  # enough for a voice: 60 to 400 Hz
FRAME = 320  # 40 ms, long enough to hold three periods of a low voice
HOP = 80  # 10 ms
LOW_HZ, HIGH_HZ = 60, 400
# A frame quieter than this, compared with the loudest one, is taken as silence.
QUIET = 0.05
FLOOR = 0.003  # -50 dBFS


def samples(path: Path) -> list[float]:
    """The sound as one channel of numbers between -1 and 1, brought to RATE."""
    done = subprocess.run(
        [ffmpeg.ffmpeg_path(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        capture_output=True,
        check=True,
    )
    raw = array.array("h")
    raw.frombytes(done.stdout)
    if sys.byteorder != "little":
        raw.byteswap()
    return [value / 32768 for value in raw]


def _db(value: float) -> str:
    return "-inf" if value <= 0 else f"{20 * math.log10(value):.1f}"


def _pitch(frame: list[float]) -> float | None:
    """The fundamental frequency of one frame, in Hz, or None when it holds no clear tone.

    The frame is compared with a shifted copy of itself. The shift that fits
    best is one period, or a multiple of it. The shortest shift that fits nearly
    as well is taken, because it is the period itself.
    """
    mean = sum(frame) / len(frame)
    centred = [value - mean for value in frame]
    if sum(value * value for value in centred) <= 0:
        return None
    running = [0.0]
    for value in centred:
        running.append(running[-1] + value * value)
    total = len(centred)
    scores: list[tuple[int, float]] = []
    for lag in range(RATE // HIGH_HZ, RATE // LOW_HZ + 1):
        overlap = sum(centred[i] * centred[i + lag] for i in range(total - lag))
        first, second = running[total - lag], running[total] - running[lag]
        scores.append((lag, overlap / math.sqrt(first * second) if first and second else 0.0))
    best = max(score for _, score in scores)
    if best < 0.6:
        return None
    # The shortest shift is taken only when it fits almost as well as the best
    # one. With a looser rule, a bright vowel is often read an octave too high.
    for index, (lag, score) in enumerate(scores):
        before = scores[index - 1][1] if index else -1.0
        after = scores[index + 1][1] if index + 1 < len(scores) else -1.0
        if score >= 0.92 * best and score >= before and score >= after:
            return RATE / lag
    return None


def measure(path: Path) -> dict[str, Any]:
    """Measure one sound file."""
    sound = samples(path)
    frames = [sound[start:start + FRAME] for start in range(0, len(sound) - FRAME + 1, HOP)]
    levels = [math.sqrt(sum(value * value for value in frame) / FRAME) for frame in frames]
    loudest = max(levels, default=0.0)
    audible = [index for index, level in enumerate(levels) if level > max(FLOOR, QUIET * loudest)]
    peak = max((abs(value) for value in sound), default=0.0)

    pitches: list[float] = []
    if audible:
        # Every second audible frame is enough: the voice does not jump about faster than that.
        for index in audible[::2]:
            found = _pitch(frames[index])
            if found is not None:
                pitches.append(found)
    first = audible[0] * HOP / RATE if audible else len(sound) / RATE
    last = (audible[-1] * HOP + FRAME) / RATE if audible else 0.0
    return {
        "seconds": len(sound) / RATE,
        "quiet_start": first,
        "quiet_end": max(0.0, len(sound) / RATE - last),
        "sound": max(0.0, last - first),
        "peak_db": _db(peak),
        "clipped": sum(1 for value in sound if abs(value) >= 0.999),
        "pitch_hz": statistics.median(pitches) if pitches else None,
        "low_hz": statistics.quantiles(pitches, n=4)[0] if len(pitches) >= 4 else None,
        "high_hz": statistics.quantiles(pitches, n=4)[2] if len(pitches) >= 4 else None,
        "voiced": len(pitches) / max(1, len(audible[::2])),
    }


def collect(paths: list[str]) -> list[Path]:
    """The sound files named, or those inside the folders named. By default, narration and music."""
    given = [Path(name) for name in paths] if paths else [OUTPUTS / "narration", OUTPUTS / "music"]
    found: list[Path] = []
    for item in given:
        if item.is_dir():
            found.extend(sorted(path for path in item.iterdir() if path.suffix.lower() in (".wav", ".mp3", ".flac")))
        elif item.is_file():
            found.append(item)
    return found


def report(paths: list[Path]) -> None:
    """Show one line per file."""
    say(f"{'file':42}{'seconds':>9}{'quiet in':>10}{'quiet out':>11}{'peak dB':>9}{'clipped':>9}{'voice Hz':>10}{'middle half':>13}")
    for path in paths:
        found = measure(path)
        voice = "-" if found["pitch_hz"] is None else f"{found['pitch_hz']:.0f}"
        middle = "-" if found["low_hz"] is None else f"{found['low_hz']:.0f}-{found['high_hz']:.0f}"
        say(
            f"{path.name[:40]:42}{found['seconds']:9.2f}{found['quiet_start']:10.2f}{found['quiet_end']:11.2f}"
            f"{found['peak_db']:>9}{found['clipped']:9}{voice:>10}{middle:>13}"
        )


def main(argv: list[str] | None = None) -> int:
    paths = collect(list(argv or []))
    if not paths:
        say("No sound files found.")
        return 1
    report(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
