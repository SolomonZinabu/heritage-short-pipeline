"""Stage: keyframes. The reference sheet first, then one still image per shot.

Every prompt carries the same style block and character description, and the
reference images travel with it. That is what keeps the look and the person the
same from shot to shot, because an image model has no memory of the last one.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import cache, media
from .config import OUTPUTS, private
from .providers import cloudflare_flux
from .retry import with_retries
from .runlog import logged_call
from .util import say, select_shots

STAGE = "keyframes"
REFERENCE_STAGE = "references"


def compose_prompt(*parts: str) -> str:
    """Join prompt parts into one prompt, leaving out the empty ones."""
    return ". ".join(part.strip().rstrip(".") for part in parts if part and part.strip())


def shot_prompt(storyboard: dict[str, Any], shot: dict[str, Any]) -> str:
    return compose_prompt(shot["image_prompt"], storyboard["visual_style"], storyboard["character_reference_prompt"])


def _image_size(path: Path) -> list[int]:
    from PIL import Image

    with Image.open(path) as image:
        return [image.width, image.height]


def generate(
    directory: Path,
    label: str,
    key: str,
    stage: str,
    inputs: dict[str, Any],
    references: list[Path],
    attempts: int,
) -> Path:
    """Call the model until an attempt succeeds, then keep the image under its cache key."""
    account_id = private("CLOUDFLARE_ACCOUNT_ID")
    api_token = private("CLOUDFLARE_API_TOKEN")
    reference_pixels = sum(_image_size(path)[0] * _image_size(path)[1] for path in references)

    def attempt(number: int) -> Path:
        with logged_call(
            stage=stage,
            target=label,
            model=inputs["model"],
            parameters={name: inputs[name] for name in ("width", "height", "steps")},
            seed=inputs["seed"],
            attempt=number,
        ) as record:
            image, suffix = cloudflare_flux.generate_image(
                inputs["prompt"],
                model=inputs["model"],
                width=inputs["width"],
                height=inputs["height"],
                steps=inputs["steps"],
                seed=inputs["seed"],
                reference_images=references,
                account_id=account_id,
                api_token=api_token,
            )
            path = media.write_bytes(cache.output_path(directory, label, key, suffix), image)
            record.update(
                output=cache.relative(path),
                output_sha256=cache.file_hash(path),
                output_size=_image_size(path),
                list_price_usd=cloudflare_flux.list_price_usd(
                    inputs["model"], inputs["width"], inputs["height"], reference_pixels
                ),
            )
        return path

    return with_retries(attempt, attempts=attempts, notify=say)


def run(
    storyboard: dict[str, Any],
    settings: dict[str, Any],
    *,
    only: str | None = None,
    force: bool = False,
    mock: bool = False,
) -> dict[str, Path]:
    """Return the keyframe of every selected shot, making the reference sheet and the images that are missing."""
    base = OUTPUTS / "_mock" if mock else OUTPUTS
    stage_settings = settings["keyframes"]
    width, height = (512, 512) if mock else (int(stage_settings["width"]), int(stage_settings["height"]))
    steps = int(stage_settings["steps"])
    attempts = int(settings["retries"]["attempts"])

    references: list[Path] = []
    for index, reference in enumerate(storyboard.get("references", [])):
        inputs = {
            "model": stage_settings["model"],
            "prompt": compose_prompt(reference["prompt"], storyboard["visual_style"]),
            "width": width,
            "height": height,
            "steps": steps,
            "seed": reference["seed"],
        }
        key = cache.cache_key(REFERENCE_STAGE, inputs)
        path = cache.find_output(base / REFERENCE_STAGE, reference["id"], key, cache.IMAGE_SUFFIXES)
        if path:
            if not force:
                say(f"{reference['id']:<10} reference  reused     {path.name}")
            else:
                path = None
        if path is None:
            if mock:
                path = media.mock_image(
                    cache.output_path(base / REFERENCE_STAGE, reference["id"], key, ".png"),
                    reference["id"], width, height, 40 + 30 * index,
                )
                say(f"{reference['id']:<10} reference  mock        {path.name}")
            else:
                path = generate(base / REFERENCE_STAGE, reference["id"], key, REFERENCE_STAGE, inputs, [], attempts)
                say(f"{reference['id']:<10} reference  generated   {path.name}")
        references.append(path)

    if not stage_settings["use_references"]:
        references = []
    used = {path.stem.split("-")[0]: path for path in references}

    keyframes: dict[str, Path] = {}
    manifest = None if mock else cache.Manifest()
    for index, shot in enumerate(select_shots(storyboard["shots"], only)):
        inputs = {
            "model": stage_settings["model"],
            "prompt": shot_prompt(storyboard, shot),
            "width": width,
            "height": height,
            "steps": steps,
            "seed": shot["seed"] if stage_settings["send_seed"] else None,
            # A new reference image means every keyframe built on it is out of date.
            "references": {name: cache.file_hash(path) for name, path in used.items()},
        }
        key = cache.cache_key(STAGE, inputs)
        path = None if force else cache.find_output(base / STAGE, shot["id"], key, cache.IMAGE_SUFFIXES)
        if path:
            say(f"{shot['id']:<10} keyframe   reused     {path.name}")
        elif mock:
            path = media.mock_image(
                cache.output_path(base / STAGE, shot["id"], key, ".png"),
                shot["id"], width, height, 60 + 22 * index,
            )
            say(f"{shot['id']:<10} keyframe   mock        {path.name}")
        else:
            path = generate(base / STAGE, shot["id"], key, STAGE, inputs, list(used.values()), attempts)
            say(f"{shot['id']:<10} keyframe   generated   {path.name}")
        keyframes[shot["id"]] = path
        if manifest is not None:
            manifest.record(STAGE, shot["id"], {"file": str(path), "key": key, "produced_by": inputs["model"], "inputs": inputs})
    if manifest is not None:
        manifest.save()
    return keyframes
