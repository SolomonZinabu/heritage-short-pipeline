"""Keyframes with FLUX on Cloudflare Workers AI, over its REST API.

The image comes back as base64 inside JSON. Its published prices are here too,
so every call can record what it would have cost at list price.
"""
from __future__ import annotations

import base64
import math
from pathlib import Path

from ..providers import ProviderError, post

ACCOUNT_URL = "https://api.cloudflare.com/client/v4/accounts"

KLEIN_4B = "@cf/black-forest-labs/flux-2-klein-4b"
KLEIN_9B = "@cf/black-forest-labs/flux-2-klein-9b"

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


def _tiles(pixels: int) -> int:
    return max(1, math.ceil(pixels / (512 * 512)))


def list_price_usd(
    model: str, width: int, height: int, reference_pixels: int = 0
) -> float | None:
    """What one call would cost at list price, or None when the price is not known here.

    Free allowance is not taken into account. The prices are the ones
    Cloudflare publishes per 512 by 512 tile.
    """
    if model == KLEIN_4B:
        output = _tiles(width * height) * 0.000287
        # Reference images are input tiles. With none, there is nothing to count.
        reference = math.ceil(reference_pixels / (512 * 512)) * 0.000059
        return round(output + reference, 6)
    if model == KLEIN_9B:
        megapixels = width * height / 1_048_576
        output = 0.015 + max(0.0, megapixels - 1) * 0.002
        return round(output + reference_pixels / 1_048_576 * 0.002, 6)
    return None


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
