"""Stage: narration. One text-to-speech call per shot, one WAV file per shot.

A line is made on its own, so that changing one line costs one call and
nothing else. The length of each line is then what sets the pace of the edit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import cache, media, timeline
from .config import OUTPUTS, private
from .providers import gemini_tts
from .retry import TransientError, with_retries
from .runlog import logged_call
from .util import say, select_shots

STAGE = "narration"


def inputs_for(
    shot: dict[str, Any], storyboard: dict[str, Any], settings: dict[str, Any], voice: str | None = None
) -> dict[str, Any]:
    """Everything that can change a line's audio. Change any of it and the line is made again.

    ``voice`` is a try-out of another narrator. The storyboard's own voice stays
    what the film uses until the storyboard says otherwise.
    """
    chosen = storyboard.get("narration", {})
    return {
        "model": settings["narration"]["model"],
        "text": shot["narration"],
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
        paths[shot["id"]] = path
        if manifest is not None:
            manifest.record(STAGE, shot["id"], {"file": str(path), "key": key, "produced_by": inputs["model"], "inputs": inputs})
    if manifest is not None:
        manifest.save()
    report(storyboard, paths, settings)
    return paths
