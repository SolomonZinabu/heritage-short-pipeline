"""Stage: narration. One text-to-speech call per shot, one WAV file per shot.

A line is made on its own, so that changing one line costs one call and
nothing else. The length of each line is then what sets the pace of the edit.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import cache, ffmpeg, media, timeline
from .config import OUTPUTS, private
from .providers import gemini_tts
from .retry import TransientError, with_retries
from .runlog import logged_call
from .util import say, select_shots

STAGE = "narration"
# The wait between two spoken lines, in seconds.
PAUSE_SECONDS = 6


def inputs_for(
    shot: dict[str, Any], storyboard: dict[str, Any], settings: dict[str, Any], voice: str | None = None
) -> dict[str, Any]:
    """Everything that can change a line's audio. Change any of it and the line is made again.

    ``voice`` is a try-out of another narrator. The storyboard's own voice stays
    what the film uses until the storyboard says otherwise.

    A shot's ``speech`` is what the service is asked to read. It is the line
    itself, unless the shot gives a ``speech`` of its own: the same words with a
    performance mark in them, such as ``<shout>`` before words that are called
    out. The narration, the words, is then left as the film-maker wrote it.
    """
    chosen = storyboard.get("narration", {})
    return {
        "model": settings["narration"]["model"],
        "text": shot.get("speech") or shot["narration"],
        "voice": voice or chosen.get("voice") or settings["narration"]["voice"],
        "style": chosen.get("style", settings["narration"]["style"]),
    }


def generate(path: Path, target: str, inputs: dict[str, Any], attempts: int) -> Path:
    """Call the model until an attempt succeeds, logging every attempt."""
    api_key = private("GEMINI_API_KEY")

    def attempt(number: int) -> Path:
        with logged_call(
            stage=STAGE,
            target=target,
            model=inputs["model"],
            parameters={name: inputs[name] for name in ("voice", "style")},
            seed=None,
            attempt=number,
        ) as record:
            # The speech API takes no seed. The saved file is what makes a shot repeatable.
            record["seed_note"] = "not accepted by this API; the saved file is the record"
            audio = gemini_tts.synthesize(
                inputs["text"],
                voice=inputs["voice"],
                style=inputs["style"],
                model=inputs["model"],
                api_key=api_key,
            )
            media.write_bytes(path, media.as_wav(audio))
            seconds = media.wav_seconds(path)
            record.update(
                output=cache.relative(path),
                output_sha256=cache.file_hash(path),
                output_seconds=round(seconds, 3),
                list_price_usd=gemini_tts.list_price_usd(seconds),
            )
        return path

    return with_retries(attempt, attempts=attempts, notify=say, service="speech")


def report(storyboard: dict[str, Any], paths: dict[str, Path], settings: dict[str, Any]) -> None:
    """Show planned against spoken length. A shot that grew to fit its line stands out here."""
    speech = {shot_id: media.wav_seconds(path) for shot_id, path in paths.items()}
    cuts = timeline.build(storyboard["shots"], speech, settings)
    say("")
    say(f"{'shot':8}{'planned':>9}{'spoken':>9}{'on screen':>11}")
    for shot, cut in zip(storyboard["shots"], cuts):
        if shot["id"] in speech:
            say(f"{shot['id']:8}{shot['duration_seconds']:9.2f}{cut.speech_seconds:9.2f}{cut.duration:11.2f}")
        else:
            say(f"{shot['id']:8}{shot['duration_seconds']:9.2f}{'none':>9}{cut.duration:11.2f}")
    end_card = float(storyboard.get("end_card", {}).get("seconds", settings["assembly"]["end_card_seconds"]))
    say(f"The film will run {timeline.film_seconds(cuts, end_card):.2f}s including the end card.")


def paced(raw: Path, speed: float, directory: Path, shot_id: str) -> Path:
    """A spoken line brought slightly closer together in time, its pitch unchanged.

    The service's pace is its own. When the film would run past its length, the
    lines can be made a few per cent shorter without speaking them again. The
    original is kept, and the shortened copy is named after it and the speed.
    """
    key = cache.cache_key(STAGE, {"line": cache.file_hash(raw), "speed": speed})
    path = cache.output_path(directory, shot_id, key, ".wav")
    if path.exists():
        return path
    part = path.with_name(f"{path.stem}.part.wav")
    ffmpeg.run_ffmpeg(["-y", "-i", str(raw), "-af", f"atempo={speed}", "-c:a", "pcm_s16le", str(part)])
    part.replace(path)
    return path


def run(
    storyboard: dict[str, Any],
    settings: dict[str, Any],
    *,
    only: str | None = None,
    force: bool = False,
    mock: bool = False,
    voice: str | None = None,
    tolerate_missing: bool = False,
) -> dict[str, Path]:
    """Return the narration file of every selected shot, making the ones that are missing.

    With ``tolerate_missing``, a line the service refuses to make just now is
    left out, and the cut goes on without it. That is for a first listen only:
    a finished film refuses to be made without every line.
    """
    directory = OUTPUTS / "_mock" / STAGE if mock else OUTPUTS / STAGE
    speed = float(settings["narration"].get("speed", 1.0))
    manifest = None if mock else cache.Manifest()
    paths: dict[str, Path] = {}
    for shot in select_shots(storyboard["shots"], only):
        inputs = inputs_for(shot, storyboard, settings, voice)
        key = cache.cache_key(STAGE, inputs)
        path = cache.output_path(directory, shot["id"], key, ".wav")
        if path.exists() and not force:
            say(f"{shot['id']}  narration  reused     {path.name}")
        elif mock:
            media.mock_narration(path, media.estimated_seconds(shot["narration"]))
            say(f"{shot['id']}  narration  mock        {path.name}")
        else:
            try:
                generate(path, shot["id"], inputs, int(settings["retries"]["attempts"]))
            except TransientError as exc:
                if not tolerate_missing:
                    raise
                say(f"{shot['id']}  narration  MISSING     {path.name}")
                say(f"    {exc}")
                continue
            say(f"{shot['id']}  narration  generated   {path.name}  {media.wav_seconds(path):.2f}s")
            # Calls made one right after another were refused for a while on 25 Nov 2026.
            # A short pause between two lines keeps the day's few requests from
            # being spent on refusals.
            time.sleep(PAUSE_SECONDS)
        if speed != 1.0 and not mock:
            path = paced(path, speed, directory, shot["id"])
        paths[shot["id"]] = path
        if manifest is not None:
            manifest.record(STAGE, shot["id"], {"file": str(path), "key": key, "produced_by": inputs["model"], "inputs": inputs})
    if manifest is not None:
        manifest.save()
    report(storyboard, paths, settings)
    return paths
