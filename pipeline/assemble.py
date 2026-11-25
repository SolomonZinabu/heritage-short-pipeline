"""Stage: assembly. Turns the generated assets into the film with FFmpeg.

Everything here is deterministic: the same storyboard, narration, pictures and
music always give the same film. That is why the edit is code.

The radio cut comes first on purpose. It is the narration over a placeholder
score on a black screen, made to test the story before any picture exists.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image

from . import cache, ffmpeg, media, subtitles, timeline
from .config import OUTPUTS
from .util import say, slugify

STAGE = "assembly"
# Raised whenever the edit itself changes, so that a film made by an older edit
# is never mistaken for a current one.
EDIT_VERSION = 2
AUDIO_RATE = 48000
# Each aspect ratio, and the storyboard setting that holds its size.
RATIOS = {"9x16": "vertical", "16x9": "horizontal"}
# How a still is moved when its shot has no video clip. They alternate, so that
# consecutive shots do not feel the same.
MOVES = ("zoom_in", "pan_right", "zoom_out", "pan_left")


def _even(value: float) -> int:
    return max(2, int(round(value)) // 2 * 2)


def sizes(settings: dict[str, Any], mock: bool) -> dict[str, tuple[int, int]]:
    """Width and height of each aspect ratio. A mock run makes a quarter-size film, to stay quick."""
    scale = 0.25 if mock else 1.0
    return {
        ratio: (_even(settings["assembly"][name][0] * scale), _even(settings["assembly"][name][1] * scale))
        for ratio, name in RATIOS.items()
    }


def end_card(storyboard: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    return storyboard.get("end_card") or {
        "lines": settings["assembly"]["end_card_lines"],
        "seconds": settings["assembly"]["end_card_seconds"],
    }


def _move(shot: dict[str, Any], index: int) -> str:
    chosen = shot.get("kenburns", "auto")
    return MOVES[index % len(MOVES)] if chosen == "auto" else chosen


def _cover(width: int, height: int) -> str:
    """Fill the frame and cut away what does not fit, keeping the middle."""
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"


def _fit_inside(source_width: int, source_height: int, width: int, height: int) -> tuple[int, int]:
    """The largest size with the source's shape that fits in the frame."""
    if source_width * height > width * source_height:
        return width, _even(source_height * width / source_width)
    return _even(source_width * height / source_height), height


def _pad_to(duration: float, fps: int) -> str:
    """Hold the last frame when a clip is shorter than its shot, then stop at the shot's length."""
    return f",fps={fps},tpad=stop_mode=clone:stop_duration={duration:.3f},trim=duration={duration:.3f},setpts=PTS-STARTPTS"


def _kenburns(move: str, frames: int) -> str:
    """A slow move that never stops, so that a still feels alive.

    ``on`` is the number of the frame being made, which starts at 0.
    """
    moment = "0" if frames < 2 else f"(on/{frames - 1})"
    centre_x, centre_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    edge_x, edge_y = "(iw-iw/zoom)", "(ih-ih/zoom)"
    zoom, pan_x, pan_y = {
        "zoom_in": (f"1+0.12*{moment}", centre_x, centre_y),
        "zoom_out": (f"1.12-0.12*{moment}", centre_x, centre_y),
        "pan_right": ("1.15", f"{edge_x}*{moment}", centre_y),
        "pan_left": ("1.15", f"{edge_x}*(1-{moment})", centre_y),
        "pan_down": ("1.15", centre_x, f"{edge_y}*{moment}"),
        "pan_up": ("1.15", centre_x, f"{edge_y}*(1-{moment})"),
        "none": ("1.0", centre_x, centre_y),
    }[move]
    return f"zoompan=z='{zoom}':x='{pan_x}':y='{pan_y}'"


def _blurred_backdrop(width: int, height: int) -> str:
    """A small, blurred, darkened copy of the picture, to stand behind it.

    The copy is made one eighth the size and then enlarged, which makes the
    blur both strong and cheap. A radius of 4 is the most the colour detail of
    the small copy allows.
    """
    small = _cover(max(2, width // 8), max(2, height // 8))
    blur = "boxblur=luma_radius=4:luma_power=2:chroma_radius=4:chroma_power=2"
    return f"{small},{blur},eq=brightness=-0.12,scale={width}:{height},setsar=1"


def _render(path: Path, args: list[str], *, quiet: bool = True) -> str:
    """Run FFmpeg into a temporary file, and move it into place only when it succeeded.

    A failed run then leaves nothing behind. A file with the final name is
    always a complete one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.stem}.part{path.suffix}")
    try:
        shown = ffmpeg.run_ffmpeg([*args, str(part)], quiet=quiet)
    except ffmpeg.FFmpegError:
        part.unlink(missing_ok=True)
        raise
    part.replace(path)
    return shown


def _frame_count(path: Path) -> int:
    """How many frames a film has, found by decoding it."""
    shown = ffmpeg.run_ffmpeg(["-i", str(path), "-map", "0:v", "-c", "copy", "-f", "null", "-"], quiet=False)
    counts = [int(value) for value in re.findall(r"frame=\s*(\d+)", shown)]
    return counts[-1] if counts else 0


def _encode(*, crf: int, preset: str, fps: int, total: float) -> list[str]:
    """Settings shared by every film: H.264 picture, AAC sound, in a form phones and browsers play."""
    return [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}",
    ]


def segment(
    out: Path,
    *,
    source: Path | None,
    kind: str,
    duration: float,
    width: int,
    height: int,
    fit: str,
    fps: int,
    move: str = "none",
) -> Path:
    """One shot at one aspect ratio: a clip of exactly ``duration`` seconds, without sound.

    ``kind`` is "clip" for a generated video, "still" for a keyframe, or "black".
    With ``fit`` "cover" the picture fills the frame. With "blur" the whole
    picture is kept, over a blurred copy of itself.
    """
    frames = max(1, round(duration * fps))
    encode = ["-t", f"{duration + 0.05:.3f}", "-r", str(fps), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16"]

    if kind == "black":
        _render(out, ["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={duration:.3f}", "-pix_fmt", "yuv420p", *encode])
        return out

    pad = _pad_to(duration, fps)
    inputs = ["-i", str(source)]
    if kind == "clip":
        if fit == "cover":
            graph = f"[0:v]{_cover(width, height)},setsar=1{pad},format=yuv420p[vout]"
        else:
            whole = f"scale={width}:{height}:force_original_aspect_ratio=decrease,setsar=1"
            graph = (
                f"[0:v]split=2[bg][fg];[bg]{_blurred_backdrop(width, height)}{pad}[b];[fg]{whole}{pad}[f];"
                f"[b][f]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[vout]"
            )
    elif fit == "cover":
        # The picture is enlarged first. The move is then made in steps far
        # smaller than a pixel, which keeps it smooth.
        travel = f"{_cover(2 * width, 2 * height)},{_kenburns(move, frames)}:d={frames}:s={width}x{height}:fps={fps}"
        graph = f"[0:v]{travel},trim=duration={duration:.3f},setpts=PTS-STARTPTS,format=yuv420p[vout]"
    else:
        with Image.open(source) as image:
            source_width, source_height = image.size
        fitted = _fit_inside(source_width, source_height, width, height)
        travel = (
            f"{_cover(2 * fitted[0], 2 * fitted[1])},{_kenburns(move, frames)}:d={frames}:s={fitted[0]}x{fitted[1]}:fps={fps},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS"
        )
        backdrop = f"{_blurred_backdrop(width, height)},loop=loop=-1:size=1:start=0,fps={fps},trim=duration={duration:.3f},setpts=PTS-STARTPTS"
        graph = f"[0:v]split=2[bg][fg];[bg]{backdrop}[b];[fg]{travel}[f];[b][f]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[vout]"

    _render(out, [*inputs, "-filter_complex", graph, "-map", "[vout]", *encode])
    return out


def _concat(parts: list[Path], out: Path, *, expected_frames: int) -> Path:
    """Join shots that were encoded the same way, without encoding them again.

    FFmpeg can stop at a damaged shot and still report success, so the joined
    picture is counted before it is trusted.
    """
    listing = out.with_suffix(".txt")
    # Full paths with forward slashes, so the list does not depend on the folder FFmpeg is started in.
    listing.write_text("".join(f"file '{part.resolve().as_posix()}'\n" for part in parts), encoding="utf-8")
    try:
        _render(out, ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy"])
    finally:
        listing.unlink(missing_ok=True)
    frames = _frame_count(out)
    if frames != expected_frames:
        raise ffmpeg.FFmpegError(f"the joined picture has {frames} frames but should have {expected_frames}")
    return out


def _stereo() -> str:
    return f"aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:channel_layouts=stereo"


def mix_audio(
    out_wav: Path,
    *,
    cuts: list[timeline.Cut],
    narration: dict[str, Path],
    music: Path | None,
    total: float,
    settings: dict[str, Any],
) -> Path:
    """Lay each narration line at its place on the timeline, put the score under it, and duck the score while the narrator speaks."""
    inputs: list[str] = []
    graph: list[str] = []
    lines: list[str] = []
    for cut in cuts:
        wav = narration.get(cut.shot_id)
        if wav is None:
            continue
        index = len(lines) + (1 if music is not None else 0)
        inputs += ["-i", str(wav)]
        label = f"line{len(lines)}"
        graph.append(f"[{index}:a]{_stereo()},adelay={int(round(cut.speech_start * 1000))}:all=1[{label}]")
        lines.append(f"[{label}]")
    if not lines:
        raise SystemExit("There is no narration to mix.")
    joined = "".join(lines) + (f"amix=inputs={len(lines)}:normalize=0," if len(lines) > 1 else "")
    graph.append(f"{joined}apad=whole_dur={total:.3f},atrim=duration={total:.3f}[voice]")

    if music is None:
        graph.append("[voice]anull[mix]")
    else:
        duck = settings["assembly"]["duck"]
        fade_out = min(3.0, total / 2)
        # The score is repeated only as often as the film needs it. A stream
        # that never ends would keep the ducking filter waiting for ever.
        length = ffmpeg.duration_seconds(music)
        repeats = max(0, math.ceil(total / length) - 1)
        inputs = ["-stream_loop", str(repeats), "-i", str(music), *inputs]
        graph.append(
            f"[0:a]{_stereo()},atrim=duration={total:.3f},asetpts=PTS-STARTPTS,volume={settings['assembly']['music_gain']},"
            f"afade=t=in:st=0:d=1.5,afade=t=out:st={total - fade_out:.3f}:d={fade_out}[score]"
        )
        graph.append(
            f"[score][voice]sidechaincompress=threshold={duck['threshold']}:ratio={duck['ratio']}:"
            f"attack={duck['attack']}:release={duck['release']}[ducked]"
        )
        graph.append("[ducked][voice]amix=inputs=2:normalize=0[mix]")

    # The stop time is a guard: whatever happens in the graph, the file ends with the film.
    _render(
        out_wav,
        [*inputs, "-filter_complex", ";".join(graph), "-map", "[mix]", "-t", f"{total:.3f}", "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE)],
    )
    return out_wav


def _loudness_filter(settings: dict[str, Any], measured: dict[str, float] | None = None) -> str:
    """Loudness in two passes: the first only measures, the second applies the measurement."""
    target = settings["assembly"]["loudness"]
    chain = f"loudnorm=I={target['i']}:TP={target['tp']}:LRA={target['lra']}"
    if measured is None:
        return chain + ":print_format=json"
    return (
        chain
        + f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}"
        + f":measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true:print_format=summary"
        + f",aresample={AUDIO_RATE}"
    )


def measure_loudness(wav: Path, settings: dict[str, Any]) -> dict[str, float]:
    shown = ffmpeg.run_ffmpeg(["-i", str(wav), "-af", _loudness_filter(settings), "-f", "null", "-"], quiet=False)
    start, end = shown.rfind("{"), shown.rfind("}")
    values = json.loads(shown[start:end + 1])
    return {name: float(values[name]) for name in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}


def _report_loudness(shown: str) -> None:
    """Show what the last pass measured, as evidence for the edit's loudness."""
    for line in shown.splitlines():
        if "Input Integrated:" in line or "Output Integrated:" in line or "Output True Peak:" in line:
            say("  loudness:" + line.split("]", 1)[-1].strip())


def _prepare(
    storyboard: dict[str, Any],
    settings: dict[str, Any],
    narration: dict[str, Path],
    mock: bool,
) -> tuple[list[timeline.Cut], dict[str, Any], float, Path, Path, str]:
    """What every cut has in common: the timing, the folders, the title's file-name form."""
    speech = {shot_id: media.wav_seconds(path) for shot_id, path in narration.items()}
    cuts = timeline.build(storyboard["shots"], speech, settings)
    card = end_card(storyboard, settings)
    total = timeline.film_seconds(cuts, float(card["seconds"]))
    base = OUTPUTS / "_mock" if mock else OUTPUTS
    return cuts, card, total, base / "_build", base, slugify(storyboard["project_title"])


def _subtitle_until(cut: timeline.Cut) -> float:
    """When a shot's subtitle leaves the screen: a moment after its line ends."""
    return min(cut.end, cut.speech_start + max(cut.speech_seconds, 1.2) + 0.25)


def radio_cut(
    storyboard: dict[str, Any],
    settings: dict[str, Any],
    *,
    narration: dict[str, Path],
    force: bool = False,
    mock: bool = False,
) -> Path:
    """The first cut: the narration over a placeholder score on a black screen."""
    cuts, _, total, build, base, title = _prepare(storyboard, settings, narration, mock)
    fps = int(settings["assembly"]["fps"])
    width, height = sizes(settings, mock)["16x9"]
    key = cache.cache_key(
        "radio",
        {
            "cuts": [(cut.shot_id, cut.start, cut.duration) for cut in cuts],
            "narration": {shot_id: cache.file_hash(path) for shot_id, path in narration.items()},
            "total": total,
            "size": [width, height],
            "fps": fps,
            "music_gain": settings["assembly"]["music_gain"],
            "duck": settings["assembly"]["duck"],
            "loudness": settings["assembly"]["loudness"],
            "edit": EDIT_VERSION,
        },
    )
    out = base / "radio" / f"{title}-radio-{key[:10]}.mp4"
    if out.exists() and not force:
        say(f"Radio cut reused: {cache.relative(out)}")
        return out

    placeholder = build / f"placeholder-{int(total)}s.wav"
    if not placeholder.exists():
        media.placeholder_music(placeholder, total)
    mix = build / f"radio-{key[:16]}-mix.wav"
    if not mix.exists() or force:
        mix_audio(mix, cuts=cuts, narration=narration, music=placeholder, total=total, settings=settings)
    measured = measure_loudness(mix, settings)
    shown = _render(
        out,
        [
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={total:.3f}",
            "-i", str(mix), "-map", "0:v", "-map", "1:a", "-af", _loudness_filter(settings, measured),
            *_encode(crf=28, preset="veryfast", fps=fps, total=total),
        ],
        quiet=False,
    )
    _report_loudness(shown)
    return out


def film(
    storyboard: dict[str, Any],
    settings: dict[str, Any],
    *,
    narration: dict[str, Path],
    keyframes: dict[str, Path] | None = None,
    clips: dict[str, Path] | None = None,
    music: Path | None = None,
    force: bool = False,
    mock: bool = False,
) -> dict[str, Path]:
    """Cut the shots together, add subtitles, the end card and the sound, in both aspect ratios.

    ``clips`` holds a video for a shot that has one. A shot without one is shown
    as its keyframe, moved slowly. A shot without a keyframe is black.
    """
    clips, keyframes = clips or {}, keyframes or {}
    shots = storyboard["shots"]
    cuts, card, total, build, base, title = _prepare(storyboard, settings, narration, mock)
    assembly = settings["assembly"]
    fps, fit = int(assembly["fps"]), assembly["fit"]
    frame_sizes = sizes(settings, mock)
    tool = ffmpeg.ffmpeg_version()

    pictures: dict[str, list[Any]] = {}
    for index, shot in enumerate(shots):
        if shot["id"] in clips:
            source, kind = clips[shot["id"]], "clip"
        elif shot["id"] in keyframes:
            source, kind = keyframes[shot["id"]], "still"
        else:
            source, kind = None, "black"
        pictures[shot["id"]] = [kind, cache.file_hash(source) if source else None, _move(shot, index)]

    subtitle_font_path = subtitles.find_font(" ".join(shot["subtitle_en"] for shot in shots), assembly["subtitle_font"])
    card_font_path = subtitles.find_font(" ".join(card["lines"]), assembly["end_card_font"])

    key = cache.cache_key(
        STAGE,
        {
            "cuts": [(cut.shot_id, cut.start, cut.duration) for cut in cuts],
            "narration": {shot_id: cache.file_hash(path) for shot_id, path in narration.items()},
            "pictures": pictures,
            "music": cache.file_hash(music) if music else "placeholder",
            "total": total,
            "sizes": {ratio: list(size) for ratio, size in frame_sizes.items()},
            "fps": fps,
            "fit": fit,
            "duck": assembly["duck"],
            "loudness": assembly["loudness"],
            "music_gain": assembly["music_gain"],
            "crf": assembly["crf"],
            "subtitles": [shot["subtitle_en"] for shot in shots],
            "end_card": card,
            "fonts": [subtitle_font_path.name, card_font_path.name],
            "ffmpeg": tool,
            "edit": EDIT_VERSION,
        },
    )
    work = build / f"film-{key[:16]}"
    stem = f"{title}-{key[:10]}"

    # The sound is the same in both aspect ratios, so it is mixed once.
    mix = build / f"{work.name}-mix.wav"
    if not mix.exists() or force:
        if music is None:
            say("No score has been chosen yet, so the placeholder score is used.")
            music = build / f"placeholder-{int(total)}s.wav"
            if not music.exists():
                media.placeholder_music(music, total)
        mix_audio(mix, cuts=cuts, narration=narration, music=music, total=total, settings=settings)
    measured = measure_loudness(mix, settings)

    # A subtitle file of its own, for a player that can show subtitles separately.
    plain = subtitles.font(subtitle_font_path, frame_sizes["16x9"], vertical=False)
    srt_cues: list[tuple[float, float, list[str]]] = []
    for shot, cut in zip(shots, cuts):
        srt_cues.extend(subtitles.cues(shot["subtitle_en"], cut.speech_start, _subtitle_until(cut), plain, 10**9))
    srt = base / "film" / f"{stem}.srt"
    subtitles.write_srt(srt, srt_cues)
    made: dict[str, Path] = {"srt": srt}

    for ratio, (width, height) in frame_sizes.items():
        out = base / "film" / f"{stem}-{ratio}.mp4"
        if out.exists() and not force:
            say(f"{ratio} film reused: {cache.relative(out)}")
            made[ratio] = out
            continue

        # Each shot is brought to this frame and length once, and kept.
        parts: list[Path] = []
        for cut in cuts:
            kind, source_hash, move = pictures[cut.shot_id]
            segment_key = cache.cache_key(
                "segment",
                {
                    "kind": kind,
                    "source": source_hash,
                    "duration": cut.duration,
                    "size": [width, height],
                    "fit": fit,
                    "fps": fps,
                    "move": move if kind == "still" else None,
                    "ffmpeg": tool,
                    "edit": EDIT_VERSION,
                },
            )
            part = build / "segments" / f"{segment_key[:20]}.mp4"
            if not part.exists():
                segment(
                    part,
                    source=clips.get(cut.shot_id) or keyframes.get(cut.shot_id),
                    kind=kind,
                    duration=cut.duration,
                    width=width,
                    height=height,
                    fit=fit,
                    fps=fps,
                    move=move,
                )
            parts.append(part)
        picture = _concat(parts, build / f"{work.name}-{ratio}-picture.mp4", expected_frames=round(timeline.shots_seconds(cuts) * fps))

        # Subtitles and the end card are images laid over the picture, each
        # only while its moment lasts. The picture is first held to the end of
        # the film, because an overlay cannot outlast what it is laid on.
        vertical = ratio == "9x16"
        font = subtitles.font(subtitle_font_path, (width, height), vertical=vertical)
        overlays = build / f"{work.name}-{ratio}-overlays"
        inputs = ["-i", str(picture)]
        graph: list[str] = [f"[0:v]tpad=stop_mode=clone:stop_duration={float(card['seconds']):.3f},setsar=1[base]"]
        last = "base"
        number = 0
        for shot, cut in zip(shots, cuts):
            for start, end, lines in subtitles.cues(shot["subtitle_en"], cut.speech_start, _subtitle_until(cut), font, width):
                png = subtitles.subtitle_png(overlays / f"sub-{number:03d}.png", lines, (width, height), subtitle_font_path, vertical=vertical)
                inputs += ["-i", str(png)]
                graph.append(f"[{last}][{number + 1}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[v{number}]")
                last = f"v{number}"
                number += 1
        card_png = subtitles.end_card_png(overlays / "end.png", card["lines"], (width, height), card_font_path, vertical=vertical)
        inputs += ["-i", str(card_png), "-i", str(mix)]
        card_input, audio_input = number + 1, number + 2
        card_start = total - float(card["seconds"])
        graph.append(f"[{last}][{card_input}]overlay=0:0:enable='gte(t,{card_start:.3f})'[vout]")

        shown = _render(
            out,
            [
                *inputs,
                "-filter_complex", ";".join(graph),
                "-map", "[vout]", "-map", f"{audio_input}:a",
                "-af", _loudness_filter(settings, measured),
                *_encode(crf=int(assembly["crf"]), preset="medium", fps=fps, total=total),
            ],
            quiet=False,
        )
        _report_loudness(shown)
        # A film whose picture is shorter than its sound looks finished but is not, so it is counted.
        frames = _frame_count(out)
        if frames != round(total * fps):
            raise ffmpeg.FFmpegError(f"the {ratio} film has {frames} frames but should have {round(total * fps)}")
        say(f"{ratio} film written: {cache.relative(out)}  {width}x{height}  {frames} frames  {ffmpeg.duration_seconds(out):.2f}s")
        made[ratio] = out
    return made
