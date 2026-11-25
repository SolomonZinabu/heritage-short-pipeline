"""The English subtitles and the end card, drawn with Pillow.

Text is drawn into images and laid over the film by FFmpeg, rather than with
FFmpeg's own subtitle filter. The look then does not depend on how FFmpeg was
built or which fonts it can find. An SRT file is written as well, for a player
that can show subtitles separately.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from PIL import Image, ImageDraw, ImageFont

# The share of the frame's height taken by the subtitle type in each aspect ratio.
SUBTITLE_SCALE = {True: 0.030, False: 0.045}

# Fonts to try, in order, for each script. A storyboard can name its own instead.
LATIN_FONTS = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)
ETHIOPIC_FONTS = (
    "C:/Windows/Fonts/ebrima.ttf",
    "C:/Windows/Fonts/nyala.ttf",
    "/usr/share/fonts/truetype/abyssinica/AbyssinicaSIL-R.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansEthiopic-Regular.ttf",
)


def needs_ethiopic(text: str) -> bool:
    return any(0x1200 <= ord(char) <= 0x137F for char in text)


def find_font(text: str, override: str = "") -> Path:
    """A font that can draw this text, or a clear error saying where to point one."""
    script = "Ethiopic" if needs_ethiopic(text) else "Latin"
    candidates = (override,) if override else (ETHIOPIC_FONTS if script == "Ethiopic" else LATIN_FONTS)
    for candidate in candidates:
        if Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit(
        f"No {script} font found for {text!r}. Name a .ttf file in the storyboard's settings.assembly."
    )


def font(path: Path, size: tuple[int, int], *, vertical: bool) -> ImageFont.FreeTypeFont:
    """The subtitle type at the size that suits this frame."""
    return ImageFont.truetype(str(path), int(size[1] * SUBTITLE_SCALE[vertical]))


def wrap(text: str, text_font: ImageFont.FreeTypeFont, max_width: float, max_chars: int) -> list[str]:
    """Break a line of text into lines short enough to read at a glance."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and (len(candidate) > max_chars or text_font.getlength(candidate) > max_width):
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def cues(
    text: str,
    start: float,
    end: float,
    text_font: ImageFont.FreeTypeFont,
    width: int,
    *,
    max_chars: int = 40,
    max_lines: int = 2,
) -> Iterator[tuple[float, float, list[str]]]:
    """Split one subtitle into cues of at most two lines, and share the time out by length."""
    lines = wrap(text, text_font, width * 0.84, max_chars)
    groups = [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)]
    weights = [sum(len(line) for line in group) for group in groups]
    total = sum(weights) or 1
    moment = start
    for group, weight in zip(groups, weights):
        until = moment + (end - start) * weight / total
        yield round(moment, 3), round(until - 0.04, 3), group
        moment = until


def _save(image: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def subtitle_png(path: Path, lines: list[str], size: tuple[int, int], font_path: Path, *, vertical: bool) -> Path:
    """A transparent frame the size of the film, with the text inside the safe area.

    On a phone the bottom fifth of the frame is covered by the app's own
    buttons, so the vertical film keeps its text above that.
    """
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    text_font = font(font_path, size, vertical=vertical)
    stroke = max(2, round(height * 0.0025))
    boxes = [draw.textbbox((0, 0), line, font=text_font, stroke_width=stroke) for line in lines]
    widths = [box[2] - box[0] for box in boxes]
    line_height = int(height * SUBTITLE_SCALE[vertical] * 1.28)
    block_bottom = int(height * (0.76 if vertical else 0.92))
    top = block_bottom - line_height * (len(lines) - 1) - (boxes[-1][3] - boxes[-1][1])
    pad_x, pad_y = int(width * 0.035), int(height * 0.012)
    left = (width - max(widths)) // 2 - pad_x
    draw.rounded_rectangle(
        (left, top - pad_y, width - left, block_bottom + pad_y),
        radius=int(height * 0.012),
        fill=(0, 0, 0, 150),
    )
    for index, line in enumerate(lines):
        x = (width - widths[index]) // 2 - boxes[index][0]
        y = top + index * line_height - boxes[index][1]
        draw.text((x, y), line, font=text_font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 235))
    return _save(image, path)


def end_card_png(path: Path, lines: list[str], size: tuple[int, int], font_path: Path, *, vertical: bool) -> Path:
    """A dark frame. The first line is the statement that the film was made with AI."""
    width, height = size
    image = Image.new("RGB", size, (10, 10, 12))
    draw = ImageDraw.Draw(image)
    scale = 0.060 if vertical else 0.085
    sizes = [scale if index == 0 else scale * 0.45 for index in range(len(lines))]
    fonts = [ImageFont.truetype(str(font_path), int(height * share)) for share in sizes]
    heights = [int(height * share * 1.35) for share in sizes]
    top = (height - sum(heights)) // 2
    for line, text_font, line_height in zip(lines, fonts, heights):
        box = draw.textbbox((0, 0), line, font=text_font)
        draw.text(((width - (box[2] - box[0])) // 2 - box[0], top - box[1]), line, font=text_font, fill=(240, 238, 232))
        top += line_height
    return _save(image, path)


def timecode(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours:02d}:{minutes:02d}:{rest // 1000:02d},{rest % 1000:03d}"


def write_srt(path: Path, subtitle_cues: list[tuple[float, float, list[str]]]) -> Path:
    """The subtitles as a file of their own."""
    blocks = []
    for number, (start, end, lines) in enumerate(subtitle_cues, start=1):
        blocks.append(f"{number}\n{timecode(start)} --> {timecode(end)}\n" + "\n".join(lines))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return path
