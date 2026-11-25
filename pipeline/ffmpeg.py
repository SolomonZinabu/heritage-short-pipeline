"""Where FFmpeg comes from, and small helpers for running it.

The pipeline prefers the FFmpeg inside the ``imageio-ffmpeg`` package, because
it is the same build on every machine. FFmpeg is deterministic, so the same
inputs then give the same film. Set ``FFMPEG_BIN`` to use another copy.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .config import load_env

_DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")

# The filters the edit relies on. A stripped-down FFmpeg build may lack some.
NEEDED_FILTERS = (
    "overlay", "concat", "zoompan", "sidechaincompress", "loudnorm",
    "amix", "adelay", "atrim", "afade", "tpad", "scale", "crop",
)


class FFmpegError(RuntimeError):
    """FFmpeg refused a request or failed."""


def ffmpeg_path() -> str:
    load_env()
    override = os.environ.get("FFMPEG_BIN")
    if override:
        return override
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-nostdin", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ffmpeg_version() -> str:
    result = _run(["-version"])
    return result.stdout.splitlines()[0] if result.stdout else result.stderr.strip()


def missing_filters() -> list[str]:
    """The filters from NEEDED_FILTERS that this FFmpeg does not have."""
    names = set()
    for line in _run(["-filters"]).stdout.splitlines():
        # A filter's line names its type, such as "V->V" for picture in and out.
        if "->" in line:
            names.add(line.split()[1])
    return [name for name in NEEDED_FILTERS if name not in names]


def run_ffmpeg(args: list[str], *, cwd: Path | None = None, quiet: bool = True) -> str:
    """Run FFmpeg once and return what it printed.

    On failure the error carries the end of FFmpeg's output, which is where the
    reason is.
    """
    command = ["-y"]
    if quiet:
        command += ["-loglevel", "error"]
    result = _run([*command, *args], cwd=cwd)
    if result.returncode != 0:
        shown = " ".join(str(arg) for arg in args[:4])
        raise FFmpegError(f"ffmpeg {shown} ... exited with {result.returncode}:\n{result.stderr.strip()[-2500:]}")
    return result.stderr


def duration_seconds(path: Path) -> float:
    """The length of an audio or video file, read from FFmpeg's own description of it."""
    result = _run(["-i", str(path)])
    match = _DURATION.search(result.stderr)
    if not match:
        raise FFmpegError(f"could not read the duration of {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
