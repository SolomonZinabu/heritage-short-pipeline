"""Keyframes with FLUX on Cloudflare Workers AI, over its REST API.

The image comes back as base64 inside JSON. Cloudflare's published prices are
here too, so every call can record what it used and what it would have cost on
the paid plan.
"""
from __future__ import annotations

import base64
import math
from pathlib import Path

from ..providers import ProviderError, post

ACCOUNT_URL = "https://api.cloudflare.com/client/v4/accounts"

KLEIN_4B = "@cf/black-forest-labs/flux-2-klein-4b"
KLEIN_9B = "@cf/black-forest-labs/flux-2-klein-9b"

# Cloudflare measures use in Neurons. A picture counts as a grid of tiles.
TILE = 512
FREE_NEURONS_PER_DAY = 10_000
OUTPUT_TILE_NEURONS = {KLEIN_4B: 26.05}
INPUT_TILE_NEURONS = {KLEIN_4B: 5.37}
NEURON_USD = 0.011 / 1000  # the price of one Neuron on the paid plan

# How each model's bytes reveal their format.
_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG", ".png"),
)


def image_suffix(image: bytes) -> str:
    for signature, suffix in _SIGNATURES:
        if image.startswith(signature):
            return suffix
    return ".webp" if image[8:12] == b"WEBP" else ".jpg"


def _tiles(width: int, height: int) -> int:
    return max(1, math.ceil(width / TILE)) * max(1, math.ceil(height / TILE))


def neurons(
    model: str, width: int, height: int, reference_sizes: list[tuple[int, int]] | None = None
) -> float | None:
    """How much of the day's free allowance one call uses, or None when that is not known here."""
    if model == KLEIN_4B:
        used = _tiles(width, height) * OUTPUT_TILE_NEURONS[model]
        used += sum(_tiles(w, h) * INPUT_TILE_NEURONS[model] for w, h in reference_sizes or [])
        return round(used, 2)
    if model == KLEIN_9B:
        megapixels = width * height / 1_048_576
        used = 1363.64 + max(0.0, megapixels - 1) * 181.82
        used += sum(w * h / 1_048_576 * 181.82 for w, h in reference_sizes or [])
        return round(used, 2)
    return None


def list_price_usd(
    model: str, width: int, height: int, reference_sizes: list[tuple[int, int]] | None = None
) -> float | None:
    """What one call would cost on the paid plan, or None when the price is not known here.

    The free allowance is not taken into account.
    """
    used = neurons(model, width, height, reference_sizes)
    return None if used is None else round(used * NEURON_USD, 6)


def generate_image(
    prompt: str,
    *,
    model: str,
    width: int,
    height: int,
    steps: int,
    account_id: str,
    api_token: str,
    seed: int | None = None,
    reference_images: list[Path] | None = None,
    timeout: float = 240.0,
) -> tuple[bytes, str]:
    """Make one image and return its bytes and their file suffix.

    ``seed`` and ``reference_images`` are sent only when given, because they
    are optional inputs.
    """
    fields = [("prompt", (None, prompt)), ("width", (None, str(width))), ("height", (None, str(height))), ("steps", (None, str(steps)))]
    if seed is not None:
        fields.append(("seed", (None, str(seed))))
    for path in reference_images or []:
        fields.append(("image", (path.name, path.read_bytes(), "image/png")))

    response = post(
        f"{ACCOUNT_URL}/{account_id}/ai/run/{model}",
        timeout=timeout,
        headers={"Authorization": f"Bearer {api_token}"},
        files=fields,
    )
    if response.status_code != 200:
        raise ProviderError(f"{model} answered HTTP {response.status_code}: {response.text[:300]}")
    body = response.json()
    if not body.get("success") or "image" not in body.get("result", {}):
        raise ProviderError(f"{model} returned no image: {str(body.get('errors'))[:300]}")
    image = base64.b64decode(body["result"]["image"])
    return image, image_suffix(image)
