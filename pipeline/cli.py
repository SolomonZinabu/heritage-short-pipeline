"""The command line: ``python -m pipeline <command>``.

``film`` is the one command. It runs every stage, reuses what is already made,
and writes the film in both aspect ratios.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Callable

from . import assemble, config, ffmpeg, keyframes, narration, smoke
from .providers import ProviderError
from .util import say
from .validate_storyboard import SCHEMA, STORYBOARD, check_storyboard, load_storyboard


def _stage_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--only", help="work on these shots only, for example shot_03,shot_07")
    parser.add_argument("--force", action="store_true", help="make everything again, even what is already made")
    parser.add_argument("--mock", action="store_true", help="dry run: stand-ins instead of models, no calls, nothing logged")


def _load(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    """Every command starts the same way: the storyboard is checked, then its settings are filled in."""
    storyboard = load_storyboard(allow_draft=args.mock)
    settings = config.merge_settings(storyboard.get("settings"))
    if args.mock:
        say("MOCK RUN: stand-ins instead of models. Nothing is logged to runs.jsonl.")
    return storyboard, settings


def cmd_validate(args: argparse.Namespace) -> int:
    import json

    storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    errors, todos, total = check_storyboard(storyboard, json.loads(SCHEMA.read_text(encoding="utf-8")), allow_draft=args.allow_draft)
    for error in errors:
        say(f"Error: {error}")
    if errors:
        return 1
    say(f"{'Draft structure valid' if todos else 'Storyboard valid'}; {len(storyboard['shots'])} shots; {total:g}s including the end card.")
    return 0


def cmd_narration(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    narration.run(storyboard, settings, only=args.only, force=args.force, mock=args.mock)
    return 0


def cmd_keyframes(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    keyframes.run(storyboard, settings, only=args.only, force=args.force, mock=args.mock)
    return 0


def cmd_radio(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    voices = narration.run(storyboard, settings, force=args.force, mock=args.mock)
    say("")
    out = assemble.radio_cut(storyboard, settings, narration=voices, force=args.force, mock=args.mock)
    say(f"Radio cut: {cache_relative(out)}  {ffmpeg.duration_seconds(out):.2f}s")
    return 0


def cmd_film(args: argparse.Namespace) -> int:
    storyboard, settings = _load(args)
    voices = narration.run(storyboard, settings, force=args.force, mock=args.mock)
    say("")
    stills = keyframes.run(storyboard, settings, force=args.force, mock=args.mock)
    say("")
    made = assemble.film(storyboard, settings, narration=voices, keyframes=stills, force=args.force, mock=args.mock)
    return 0


def cache_relative(path) -> str:
    from . import cache

    return cache.relative(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pipeline", description="Turn storyboard.json into a short film.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    check = commands.add_parser("validate", help="check the storyboard")
    check.add_argument("--allow-draft", action="store_true", help="allow TODO placeholders")
    check.set_defaults(handler=cmd_validate)

    commands.add_parser("doctor", help="check tools, keys (names only) and the storyboard").set_defaults(handler=None)
    commands.add_parser("smoke", help="call each hosted model once and log it").set_defaults(handler=None)

    for name, help_text, handler in (
        ("narration", "speak the line of every shot", cmd_narration),
        ("keyframes", "make the reference sheet and the still of every shot", cmd_keyframes),
        ("radio", "narration over a placeholder score, on a black screen", cmd_radio),
    ):
        stage = commands.add_parser(name, help=help_text)
        _stage_options(stage)
        stage.set_defaults(handler=handler)

    film = commands.add_parser("film", help="everything: narration, keyframes and the edit, in both aspect ratios")
    film.add_argument("--force", action="store_true", help="make everything again, even what is already made")
    film.add_argument("--mock", action="store_true", help="dry run: stand-ins instead of models, no calls, nothing logged")
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
    except (config.MissingSetting, ffmpeg.FFmpegError, ProviderError) as exc:
        say(f"Stopped: {exc}")
        return 2
    except KeyboardInterrupt:
        say("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
