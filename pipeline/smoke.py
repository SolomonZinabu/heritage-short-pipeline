"""Two checks that cost almost nothing: is everything in place, and does each service answer?

``doctor`` looks at the machine and never calls a model. ``smoke`` makes the
smallest useful request to each hosted service, and logs it like any other call.
"""
from __future__ import annotations

import importlib
import json
import platform
import time
from pathlib import Path

from . import cache, config, ffmpeg, media
from .providers import cloudflare_flux, gemini_tts
from .runlog import logged_call, redact
from .util import say
from .validate_storyboard import check_storyboard

# "Hello! This is a first test." in Amharic, the language of the narration.
TTS_SAMPLE = "ሰላም! ይህ የመጀመሪያ ሙከራ ነው።"
IMAGE_SAMPLE = "a warm hand-painted illustration of a highland market at sunrise"
PACKAGES = (("jsonschema", "jsonschema"), ("requests", "requests"), ("PIL", "Pillow"), ("imageio_ffmpeg", "imageio-ffmpeg"))


def doctor() -> int:
    """Report what is ready. Private values are only ever reported as set or not set."""
    ready = True
    say(f"Python {platform.python_version()} on {platform.system()}")
    for name, label in PACKAGES:
        try:
            importlib.import_module(name)
            say(f"  {label:16} installed")
        except ImportError:
            ready = False
            say(f"  {label:16} MISSING. Run: python -m pip install -r requirements.txt")

    say(f"  {'FFmpeg':21} {ffmpeg.ffmpeg_path()}")
    say(f"  {'':21} {ffmpeg.ffmpeg_version()}")
    missing = ffmpeg.missing_filters()
    if missing:
        ready = False
        say(f"  {'':21} missing filters: {', '.join(missing)}. Install a full FFmpeg build, or set FFMPEG_BIN.")

    for name, present in config.private_status().items():
        if not present:
            ready = False
        say(f"  {name:21} {'set' if present else 'not set'}")

    try:
        storyboard = json.loads(config.STORYBOARD.read_text(encoding="utf-8"))
        schema = json.loads(config.SCHEMA.read_text(encoding="utf-8"))
        errors, todos, total = check_storyboard(storyboard, schema, allow_draft=True)
        if errors:
            ready = False
            for error in errors:
                say(f"  storyboard        {error}")
        else:
            state = "ready" if not todos else f"a draft with {len(todos)} TODO fields"
            say(f"  {'storyboard':21} {state}; {total:g}s including the end card")
    except (OSError, ValueError) as exc:
        ready = False
        say(f"  storyboard             could not be read: {exc}")

    say("Kaggle is not checked from here. It is checked the first time a job runs there.")
    say("Ready." if ready else "Not ready yet: see the lines above.")
    return 0 if ready else 1


def _try_tts(folder: Path, settings: dict) -> tuple[str, dict | None]:
    model, voice = settings["narration"]["model"], settings["narration"]["voice"]
    with logged_call(
        stage="smoke", target="tts", model=model, parameters={"voice": voice, "style": "", "text": TTS_SAMPLE}, seed=None
    ) as record:
        audio = media.as_wav(gemini_tts.synthesize(TTS_SAMPLE, voice=voice, style="", model=model, api_key=config.private("GEMINI_API_KEY")))
        path = media.write_bytes(folder / f"tts-{time.strftime('%Y%m%d-%H%M%S')}.wav", audio)
        seconds = media.wav_seconds(path)
        record.update(
            output=cache.relative(path), output_sha256=cache.file_hash(path), output_seconds=round(seconds, 3),
            list_price_usd=gemini_tts.list_price_usd(seconds),
        )
    return f"ok, {seconds:.2f}s of speech in {folder.name}/{path.name}", record


def _try_image(folder: Path, settings: dict) -> tuple[str, dict | None]:
    model = settings["keyframes"]["model"]
    with logged_call(
        stage="smoke", target="image", model=model, parameters={"width": 512, "height": 512, "steps": 4}, seed=1
    ) as record:
        image, suffix = cloudflare_flux.generate_image(
            IMAGE_SAMPLE,
            model=model,
            width=512,
            height=512,
            steps=4,
            seed=1,
            account_id=config.private("CLOUDFLARE_ACCOUNT_ID"),
            api_token=config.private("CLOUDFLARE_API_TOKEN"),
        )
        path = media.write_bytes(folder / f"image-{time.strftime('%Y%m%d-%H%M%S')}{suffix}", image)
        record.update(
            output=cache.relative(path),
            output_sha256=cache.file_hash(path),
            list_price_usd=cloudflare_flux.list_price_usd(model, 512, 512),
        )
    return f"ok, {folder.name}/{path.name}", record


def smoke() -> int:
    """Call each hosted service once and log it: the cheapest way to learn what works today."""
    folder = config.OUTPUTS / "smoke"
    folder.mkdir(parents=True, exist_ok=True)
    settings = config.merge_settings(json.loads(config.STORYBOARD.read_text(encoding="utf-8")).get("settings"))
    present = config.private_status()
    failed = False

    say("Gemini TTS")
    if present["GEMINI_API_KEY"]:
        failed |= _report(_try_tts, folder, settings)
    else:
        say("  skipped: GEMINI_API_KEY is not set")

    say("Cloudflare FLUX")
    if present["CLOUDFLARE_API_TOKEN"] and present["CLOUDFLARE_ACCOUNT_ID"]:
        failed |= _report(_try_image, folder, settings)
    else:
        say("  skipped: CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID is not set")

    say("Every call, including a failed one, is a line in runs.jsonl.")
    return 1 if failed else 0


def _report(attempt, folder: Path, settings: dict) -> bool:
    """Run one attempt and say how it went. Returns True when it failed."""
    try:
        message, record = attempt(folder, settings)
    except Exception as exc:  # The failure is already logged; show it without a traceback, and without any private value.
        say(f"  FAILED: {redact(f'{type(exc).__name__}: {exc}')}")
        return True
    say(f"  {message}  in {record['latency_seconds']:.1f}s")
    return False
