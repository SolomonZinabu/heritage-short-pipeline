"""Stage: keyframes. The reference sheet first, then one still image per shot.

Every prompt carries the same style block and character description, and the
reference images travel with it. That is what keeps the look and the person the
same from shot to shot, because an image model has no memory of the last one.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import cache, media
from .config import OUTPUTS, ROOT, private
from .providers import cloudflare_flux
from .retry import with_retries
from .runlog import logged_call
from .util import say, select_shots

STAGE = "keyframes"
REFERENCE_STAGE = "references"


def compose_prompt(*parts: str) -> str:
    """Join prompt parts into one prompt, leaving out the empty ones."""
    return ". ".join(part.strip().rstrip(".") for part in parts if part and part.strip())


def cast_of(storyboard: dict[str, Any], shot: dict[str, Any]) -> list[dict[str, Any]]:
    """The references a shot is built on: the ones it names, or all of them when it names none.

    A shot of milk spilling on the ground shows no one, and a shot of the boy
    running shows no one but him. Sending the mother as well would only blur
    both.
    """
    references = {reference["id"]: reference for reference in storyboard.get("references", [])}
    if "cast" not in shot:
        return list(references.values())
    return [references[name] for name in shot["cast"]]


def shot_prompt(storyboard: dict[str, Any], shot: dict[str, Any]) -> str:
    """The shot's own prompt, the style block, and a description of each reference in the shot."""
    parts = [shot["image_prompt"], storyboard["visual_style"]]
    cast = cast_of(storyboard, shot)
    if cast or "cast" in shot:
        parts += [member["prompt"] for member in cast]
    else:
        parts.append(storyboard["character_reference_prompt"])
    return compose_prompt(*parts)


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
    reference_sizes = [_image_size(path) for path in references]

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
                neurons=cloudflare_flux.neurons(inputs["model"], inputs["width"], inputs["height"], reference_sizes),
                list_price_usd=cloudflare_flux.list_price_usd(
                    inputs["model"], inputs["width"], inputs["height"], reference_sizes
                ),
            )
        return path

    return with_retries(attempt, attempts=attempts, notify=say, service="images")


def from_photo(reference: dict[str, Any], width: int, height: int, base: Path) -> Path:
    """A photo given in the storyboard, kept as a reference for a real person.

    Nothing is generated. The photo is only brought down to the size of the
    generated references. The copy is named after the photo's fingerprint, so
    it is found again even where the photo itself is not: the photographs of
    real people stay out of the public repository, and a clean clone that holds
    the copy still runs.
    """
    from PIL import Image, ImageOps

    source = ROOT / reference["file"]
    fingerprint = reference.get("sha256")
    if source.is_file():
        found = cache.file_hash(source)
        if fingerprint and fingerprint != found:
            raise SystemExit(f"{reference['id']}: the photo {reference['file']} has changed. Its sha256 in the storyboard must become {found}.")
        fingerprint = found
    if not fingerprint:
        raise SystemExit(f"{reference['id']}: there is no photo at {reference['file']}, and no sha256 to find its copy by.")
    key = cache.cache_key(REFERENCE_STAGE, {"source": fingerprint, "size": [width, height]})
    # A copy of a photograph is not a stand-in, so a dry run may use the real
    # one. That is what lets a clean clone, which has the copies and not the
    # photographs, run without calling anything.
    for folder in (base / REFERENCE_STAGE, OUTPUTS / REFERENCE_STAGE):
        path = cache.find_output(folder, reference["id"], key, (".jpg",))
        if path is not None:
            return path
    if not source.is_file():
        raise SystemExit(
            f"{reference['id']}: there is no photo at {reference['file']}, and no copy of it in outputs/references. "
            "The film-maker keeps the photographs. Ask him for them, or put the copy back."
        )
    path = cache.output_path(base / REFERENCE_STAGE, reference["id"], key, ".jpg")
    with Image.open(source) as picture:
        picture = ImageOps.exif_transpose(picture).convert("RGB")
        picture.thumbnail((width, height))  # shrunk to fit, never enlarged
        path.parent.mkdir(parents=True, exist_ok=True)
        picture.save(path, "JPEG", quality=94)
    return path


def from_still(still: dict[str, Any], label: str) -> Path:
    """A picture made elsewhere and given in the storyboard, for a whole shot or for part of one.

    Nothing is generated. The picture is copied, and cut to its ``crop`` when it
    has one, so that what the film shows is on record with everything else. A
    crop is given as left, top, right and bottom, each from 0 to 1 of the way
    across or down the picture.
    """
    from PIL import Image, ImageOps

    source = ROOT / still["file"]
    if not source.is_file():
        raise SystemExit(f"{label}: there is no picture at {still['file']}.")
    crop = still.get("crop")
    key = cache.cache_key("still", {"source": cache.file_hash(source), "crop": crop})
    path = cache.output_path(OUTPUTS / STAGE, label, key, ".jpg")
    if path.exists():
        return path
    with Image.open(source) as picture:
        picture = ImageOps.exif_transpose(picture).convert("RGB")
        if crop:
            left, top, right, bottom = (float(value) for value in crop)
            picture = picture.crop(
                (round(left * picture.width), round(top * picture.height), round(right * picture.width), round(bottom * picture.height))
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        picture.save(path, "JPEG", quality=95)
    return path


def _reference_sheet(
    storyboard: dict[str, Any], settings: dict[str, Any], *, base: Path, size: tuple[int, int], full: tuple[int, int], mock: bool, force: bool
) -> list[Path]:
    """The references of the storyboard: a photograph is copied, a brief is generated."""
    stage_settings = settings["keyframes"]
    width, height = size
    steps = int(stage_settings["steps"])
    attempts = int(settings["retries"]["attempts"])
    references: list[Path] = []
    for index, reference in enumerate(storyboard.get("references", [])):
        if reference.get("file"):
            # A photograph is copied once, at full size, whether this is a dry run or not.
            path = from_photo(reference, *full, base)
            say(f"{reference['id']:<10} reference  photo       {path.name}")
            references.append(path)
            continue
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
    return references


def run(
    storyboard: dict[str, Any],
    settings: dict[str, Any],
    *,
    only: str | None = None,
    force: bool = False,
    mock: bool = False,
) -> dict[str, list[Path]]:
    """Return the pictures of every selected shot, in order: the ones given in the storyboard, or made here."""
    base = OUTPUTS / "_mock" if mock else OUTPUTS
    stage_settings = settings["keyframes"]
    full = (int(stage_settings["width"]), int(stage_settings["height"]))
    width, height = (512, 512) if mock else full
    steps = int(stage_settings["steps"])
    attempts = int(settings["retries"]["attempts"])
    selected = select_shots(storyboard["shots"], only)
    # The reference sheet is only for pictures made here.
    if any(not shot.get("stills") for shot in selected):
        references = _reference_sheet(storyboard, settings, base=base, size=(width, height), full=full, mock=mock, force=force)
    else:
        references = []

    if not stage_settings["use_references"]:
        references = []
    used = {path.stem.split("-")[0]: path for path in references}

    keyframes: dict[str, list[Path]] = {}
    manifest = None if mock else cache.Manifest()
    for index, shot in enumerate(selected):
        if shot.get("stills"):
            # A picture given by the film-maker is used as it is, dry run or not.
            paths = []
            for number, still in enumerate(shot["stills"], start=1):
                label = shot["id"] if len(shot["stills"]) == 1 else f"{shot['id']}-{number}"
                path = from_still(still, label)
                say(f"{label:<12}still       given       {path.name}")
                paths.append(path)
                if manifest is not None:
                    manifest.record(STAGE, label, {"file": str(path), "produced_by": "given by the film-maker", "inputs": still})
            keyframes[shot["id"]] = paths
            continue
        cast = cast_of(storyboard, shot)
        inputs = {
            "model": stage_settings["model"],
            "prompt": shot_prompt(storyboard, shot),
            "width": width,
            "height": height,
            "steps": steps,
            "seed": shot["seed"] if stage_settings["send_seed"] else None,
            # A new reference image means every keyframe built on it is out of date.
            "references": {member["id"]: cache.file_hash(used[member["id"]]) for member in cast if member["id"] in used},
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
            shown = [used[member["id"]] for member in cast if member["id"] in used]
            path = generate(base / STAGE, shot["id"], key, STAGE, inputs, shown, attempts)
            say(f"{shot['id']:<10} keyframe   generated   {path.name}")
        keyframes[shot["id"]] = [path]
        if manifest is not None:
            manifest.record(STAGE, shot["id"], {"file": str(path), "key": key, "produced_by": inputs["model"], "inputs": inputs})
    if manifest is not None:
        manifest.save()
    return keyframes
