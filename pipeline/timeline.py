"""The timing of the edit: when each shot starts and how long it stays on screen.

Pure arithmetic, no FFmpeg, so both the narration report and the assembly
agree on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Cut:
    """One shot's place on the timeline."""

    shot_id: str
    index: int
    start: float
    duration: float
    speech_start: float
    speech_seconds: float

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 3)


def build(shots: list[dict[str, Any]], speech: dict[str, float], settings: dict[str, Any]) -> list[Cut]:
    """Let the narration set the pace.

    A shot lasts its planned time, or longer when its line needs it, so a line
    is never cut off. The planner's ``duration_seconds`` is therefore a floor.
    """
    lead_in = float(settings["assembly"]["lead_in_seconds"])
    tail = float(settings["assembly"]["tail_seconds"])
    cuts: list[Cut] = []
    start = 0.0
    for index, shot in enumerate(shots):
        spoken = float(speech.get(shot["id"], 0.0))
        duration = max(float(shot["duration_seconds"]), lead_in + spoken + tail)
        cuts.append(Cut(shot["id"], index, round(start, 3), round(duration, 3), round(start + lead_in, 3), spoken))
        start += duration
    return cuts


def shots_seconds(cuts: list[Cut]) -> float:
    return round(sum(cut.duration for cut in cuts), 3)


def film_seconds(cuts: list[Cut], end_card_seconds: float) -> float:
    return round(shots_seconds(cuts) + end_card_seconds, 3)
