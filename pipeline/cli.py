"""The command line: ``python -m pipeline <command>``.

``film`` is the one command. It runs every stage, reuses what is already made,
and writes the film in both aspect ratios.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import assemble, audio_check, cache, config, costs, ffmpeg, keyframes, music, narration, smoke
from .providers import ProviderError
from .retry import TransientError
from .runlog import redact
from .util import say
from .validate_storyboard import SCHEMA, STORYBOARD, check_storyboard, load_storyboard


def _mock_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mock", action="store_true", help="dry run: stand-ins instead of models, no calls, nothing logged")


def _voice_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--voice", help="try another narrator for this run, for example --voice Algieba")


def _load(args: argparse.Namespace, *, allow_draft: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Every command starts the same way: the storyboard is checked, then its settings are filled in."""
    storyboard = load_storyboard(allow_draft=args.mock or allow_draft)
    settings = config.merge_settings(storyboard.get("settings"))
    if args.mock:
        say("MOCK RUN: stand-ins instead of models. Nothing is logged to runs.jsonl.")
    return storyboard, settings


def cmd_validate(args: argparse.Namespace) -> int:
    storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    errors, todos, total = check_storyboard(storyboard, json.loads(SCHEMA.read_text(encoding="utf-8")), allow_draft=args.allow_draft)
    for error in errors:
        say(f"Error: {error}")
    if todos and not args.allow_draft:
        say(f"{len(todos)} fields still to fill:")
        for path in todos:
            say(f"  {path}")
    if errors:
        return 1
    say(f"{'Draft structure valid' if todos else 'Storyboard valid'}; {len(storyboard['shots'])} shots; {total:g}s including the end card.")
    return 0


def _voice(args: argparse.Namespace) -> str | None:
    """Another narrator for this run only. It reaches the log, and nothing else is changed."""
    return getattr(args, "voice", None)


def cmd_narration(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    narration.run(storyboard, settings, only=args.only, force=args.force, mock=args.mock, voice=_voice(args))
    return 0


def cmd_keyframes(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    keyframes.run(storyboard, settings, only=args.only, force=args.force, mock=args.mock)
    return 0


def cmd_music(args: argparse.Namespace) -> int:
    if args.action == "import":
        if not args.source:
            raise SystemExit("Name the file to import. For example: python -m pipeline music import score.zip")
        music.import_results(Path(args.source))
        return 0
    # The short test does not use the storyboard, so it can be written while the storyboard is still a draft.
    storyboard, settings = _load(args, allow_draft=args.smoke)
    if args.action == "export":
        say(f"The job for Kaggle is written: {cache.relative(music.export(storyboard, settings, smoke=args.smoke))}")
        return 0
    return 0 if music.run(storyboard, settings, mock=args.mock) else 1


def cmd_radio(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    # A first listen is worth making even when the speech service refuses a line
    # for now. The cut then says so, instead of failing to exist.
    voices = narration.run(
        storyboard, settings, force=args.force, mock=args.mock, voice=_voice(args), tolerate_missing=True
    )
    missing = [shot["id"] for shot in storyboard["shots"] if shot["id"] not in voices]
    if missing:
        say("")
        say(f"No line for {', '.join(missing)} yet: that shot is silent in this cut.")
    say("")
    out = assemble.radio_cut(storyboard, settings, narration=voices, force=args.force, mock=args.mock)
    say(f"Radio cut: {cache.relative(out)}  {ffmpeg.duration_seconds(out):.2f}s")
    return 0


def cmd_film(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    voices = narration.run(storyboard, settings, force=args.force, mock=args.mock, voice=_voice(args))
    say("")
    stills = keyframes.run(storyboard, settings, force=args.force, mock=args.mock)
    say("")
    score = music.run(storyboard, settings, mock=args.mock)
    say("")
    assemble.film(storyboard, settings, narration=voices, keyframes=stills, music=score, force=args.force, mock=args.mock)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipeline", description="Turn storyboard.json into a short film.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    check = commands.add_parser("validate", help="check the storyboard")
    check.add_argument("--allow-draft", action="store_true", help="allow TODO placeholders")
    check.set_defaults(handler=cmd_validate)

    sound = commands.add_parser("check", help="measure generated sound: level, silence at each end, how high or low the voice is")
    sound.add_argument("paths", nargs="*", help="sound files or folders; by default the narration and the music")
    sound.set_defaults(handler=lambda args: audio_check.main(args.paths))

    commands.add_parser("doctor", help="check tools, keys (names only) and the storyboard").set_defaults(handler=None)
    commands.add_parser("smoke", help="call each hosted model once and log it").set_defaults(handler=None)
    commands.add_parser("costs", help="summarise runs.jsonl for COSTS.md").set_defaults(handler=lambda args: costs.main())

    for name, help_text, handler in (
        ("narration", "speak the line of every shot", cmd_narration),
        ("keyframes", "make the reference sheet and the still of every shot", cmd_keyframes),
    ):
        stage = commands.add_parser(name, help=help_text)
        stage.add_argument("--only", help="work on these shots only, for example shot_03,shot_07")
        stage.add_argument("--force", action="store_true", help="make everything again, even what is already made")
        if name == "narration":
            _voice_option(stage)
        _mock_option(stage)
        stage.set_defaults(handler=handler)

    score = commands.add_parser("music", help="the score: reuse it, or write the job that makes it on Kaggle")
    score.add_argument("action", nargs="?", default="make", choices=["make", "export", "import"])
    score.add_argument("source", nargs="?", help="for import: the score.zip downloaded from Kaggle")
    score.add_argument("--smoke", action="store_true", help="with export: a 15-second test instead of the real score")
    _mock_option(score)
    score.set_defaults(handler=cmd_music)

    radio = commands.add_parser("radio", help="narration over a placeholder score, on a black screen")
    radio.add_argument("--force", action="store_true", help="make everything again, even what is already made")
    _voice_option(radio)
    _mock_option(radio)
    radio.set_defaults(handler=cmd_radio)

    film = commands.add_parser("film", help="everything: narration, keyframes, the score and the edit, in both aspect ratios")
    film.add_argument("--force", action="store_true", help="make everything again, even what is already made")
    _voice_option(film)
    _mock_option(film)
    film.set_defaults(handler=cmd_film)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # A console that cannot show a script must not crash the run over it.
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return smoke.doctor()
    if args.command == "smoke":
        return smoke.smoke()
    try:
        return args.handler(args)
    except (config.MissingSetting, ffmpeg.FFmpegError, ProviderError, TransientError) as exc:
        say(f"Stopped: {redact(str(exc))}")
        return 2
    except KeyboardInterrupt:
        say("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
